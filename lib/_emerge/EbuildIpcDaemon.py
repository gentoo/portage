# Copyright 2010-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import fcntl
import io
import logging
import os
import pickle

from portage.localization import _
from portage.util import writemsg_level
from portage.util.pickle import NoGlobalsUnpickler

from _emerge.FifoIpcDaemon import FifoIpcDaemon


class EbuildIpcDaemon(FifoIpcDaemon):
    """
    This class serves as an IPC daemon, which ebuild processes can use
    to communicate with portage's main python process.

    Here are a few possible uses:

    1) Robust subshell/subprocess die support. This allows the ebuild
       environment to reliably die without having to rely on signal IPC.

    2) Delegation of portageq calls to the main python process, eliminating
       performance and userpriv permission issues.

    3) Reliable ebuild termination in cases when the ebuild has accidentally
       left orphan processes running in the background (as in bug #278895).

    4) Detect cases in which bash has exited unexpectedly (as in bug #190128).
    """

    __slots__ = (
        "commands",
        "_reply_buf",
        "_reply_fd",
        "_reply_hook",
        "_reply_timeout_id",
    )

    # The client keeps reading as long as the daemon is alive, so this
    # only bounds how long a reply to a client that stops reading waits
    # before its reply hook runs anyway.
    _SEND_REPLY_TIMEOUT = 15  # seconds

    def _input_handler(self):
        # Read the whole pickle in a single atomic read() call.
        data = self._read_buf(self._files.pipe_in)
        if data is None:
            pass  # EAGAIN
        elif data:
            try:
                obj = NoGlobalsUnpickler(io.BytesIO(data)).load()
            except SystemExit:
                raise
            except Exception:
                # The pickle module can raise practically
                # any exception when given corrupt data.
                pass
            else:
                self._reopen_input()

                cmd_key = obj[0]
                cmd_handler = self.commands[cmd_key]
                reply = cmd_handler(obj)
                # The command may have a hook to run once its reply has
                # been sent. The 'exit' command, which the helpers of a
                # portage without PORTAGE_EBUILD_EXIT_FD still send, uses
                # it to start the timer that kills a phase which does not
                # exit by itself. Starting that timer only now keeps the
                # phase from being killed while ebuild-ipc still waits
                # for the reply.
                self._send_reply(reply, getattr(cmd_handler, "reply_hook", None))

        else:  # EIO/POLLHUP
            # This can be triggered due to a race condition which happens when
            # the previous _reopen_input() call occurs before the writer has
            # closed the pipe (see bug #401919). It's not safe to re-open
            # without a lock here, since it's possible that another writer will
            # write something to the pipe just before we close it, and in that
            # case the write will be lost. Therefore, try for a non-blocking
            # lock, and only re-open the pipe if the lock is acquired.
            #
            # Only the daemon and its clients lock this file, so both
            # sides use flock() directly rather than portage.locks.
            lock_filename = os.path.join(os.path.dirname(self.input_fifo), "lock")
            old_mask = os.umask(0o000)
            try:
                lock_fd = os.open(lock_filename, os.O_CREAT | os.O_RDWR, 0o660)
            finally:
                os.umask(old_mask)
            try:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as e:
                    if e.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    # We'll try again when another IO_HUP event arrives.
                else:
                    self._reopen_input()
            finally:
                os.close(lock_fd)

    def _send_reply(self, reply, reply_hook):
        """
        Send the reply to the client, and call reply_hook once it has
        been sent, or once it is clear that it cannot be.
        """
        # File streams are in unbuffered mode since we do atomic
        # read and write of whole pickles. Use non-blocking mode so
        # we don't hang if the client is killed before we can send
        # the reply. We rely on the client opening the other side
        # of this fifo before it sends its request, since otherwise
        # we'd have a race condition with this open call raising
        # ENXIO if the client hasn't opened the fifo yet.
        self._reply_hook = reply_hook
        try:
            self._reply_fd = os.open(self.output_fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            # This probably means that the client has been killed,
            # which causes open to fail with ENXIO.
            self._reply_done(e)
            return

        self._reply_buf = pickle.dumps(reply)
        self._reply_handler()

    def _reply_handler(self):
        while self._reply_buf:
            try:
                self._reply_buf = self._reply_buf[
                    os.write(self._reply_fd, self._reply_buf) :
                ]
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    self._reply_done(e)
                    return
                # A reply that does not fit in the pipe buffer takes
                # more than one write, so let the event loop send the
                # rest as the client reads.
                if self._reply_timeout_id is None:
                    self.scheduler.add_writer(self._reply_fd, self._reply_handler)
                    self._reply_timeout_id = self.scheduler.call_later(
                        self._SEND_REPLY_TIMEOUT,
                        self._reply_done,
                        TimeoutError(errno.ETIMEDOUT, "client did not read the reply"),
                    )
                return

        self._reply_done()

    def _reply_done(self, error=None):
        self._close_reply()

        if error is not None:
            writemsg_level(
                f"!!! EbuildIpcDaemon {_('failed to send reply')}: {error}\n",
                level=logging.ERROR,
                noiselevel=-1,
            )

        reply_hook, self._reply_hook = self._reply_hook, None
        if reply_hook is not None:
            reply_hook()

    def _close_reply(self):
        if self._reply_timeout_id is not None:
            self._reply_timeout_id.cancel()
            self._reply_timeout_id = None
            self.scheduler.remove_writer(self._reply_fd)

        if self._reply_fd is not None:
            os.close(self._reply_fd)
            self._reply_fd = None

        self._reply_buf = None

    def _unregister(self):
        self._reply_hook = None
        self._close_reply()
        FifoIpcDaemon._unregister(self)
