#!/usr/bin/env python
# Copyright 2010-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# This is a helper which ebuild processes can use
# to communicate with portage's main python process.
#
# It runs for every has_version and best_version call, so it uses the
# standard library only: importing portage would take most of the time
# of a run.

import locale
import os
import sys

if (
    sys.getfilesystemencoding().lower() != "utf-8"
    or locale.getpreferredencoding(False).lower() != "utf-8"
):
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


import signal


# Inherit from KeyboardInterrupt to avoid a traceback from asyncio.
class SignalInterrupt(KeyboardInterrupt):
    def __init__(self, signum):
        self.signum = signum


try:

    def signal_interrupt(signum, _frame):
        raise SignalInterrupt(signum)

    def debug_signal(_signum, _frame):
        import pdb

        pdb.set_trace()

    # Prevent "[Errno 32] Broken pipe" exceptions when writing to a pipe.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal_interrupt)
    signal.signal(signal.SIGUSR1, debug_signal)

    import errno
    import fcntl
    import io
    import pickle
    import select
    import time

    # Timeout for each individual communication attempt (we retry
    # as long as the daemon process appears to be alive).
    _COMMUNICATE_RETRY_TIMEOUT = 15  # seconds

    RETURNCODE_FAILURE = 2

    class _NoGlobalsUnpickler(pickle.Unpickler):
        """
        Like portage.util.pickle.NoGlobalsUnpickler, reject pickle global
        references.
        """

        def find_class(self, module, name):
            raise pickle.UnpicklingError(
                f"pickle global reference '{module}.{name}' is forbidden"
            )

    def _writemsg(msg):
        sys.stderr.write(msg)
        sys.stderr.flush()

    def _poll(fd, eventmask, timeout):
        # POLLHUP, POLLERR and POLLNVAL are reported whatever eventmask
        # asks for, so an eventmask of 0 waits for the fd to go away.
        poller = select.poll()
        poller.register(fd, eventmask)
        return poller.poll(timeout * 1000)

    class EbuildIpc:
        def __init__(self):
            self.fifo_dir = os.environ["PORTAGE_BUILDDIR"]
            self.ipc_in_fifo = os.path.join(self.fifo_dir, ".ipc", "in")
            self.ipc_out_fifo = os.path.join(self.fifo_dir, ".ipc", "out")
            self.ipc_lock_file = os.path.join(self.fifo_dir, ".ipc", "lock")
            alive_fd = os.environ.get("PORTAGE_IPC_ALIVE_FD")
            self._alive_fd = None if alive_fd is None else int(alive_fd)
            # Only a portage that predates PORTAGE_IPC_ALIVE_FD runs us
            # without it: one that was already running when a newer
            # portage was installed, whose phases then run these files.
            # Its daemon and build directory are locked by portage.locks,
            # which uses lockf() wherever lockf() works.
            self._legacy = self._alive_fd is None
            head, tail = os.path.split(self.fifo_dir.rstrip(os.sep))
            self.builddir_lock_file = os.path.join(
                head, "." + tail + ".portage_lockfile"
            )

        def _daemon_is_alive(self):
            if self._legacy:
                return self._builddir_is_locked()
            # Portage holds the write end of this pipe for as long as the
            # daemon can answer, and gave us the read end, so a hangup
            # means that the daemon is gone. Nothing is ever written to
            # it, so this neither blocks nor consumes anything.
            events = _poll(self._alive_fd, 0, 0)
            return not events

        def _builddir_is_locked(self):
            # An older portage holds the build directory lock for as long
            # as the daemon runs. Do not create the lock file: if it does
            # not exist, nobody holds it.
            try:
                fd = os.open(self.builddir_lock_file, os.O_RDWR)
            except FileNotFoundError:
                return False
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                if e.errno in (errno.EACCES, errno.EAGAIN, errno.ENOLCK):
                    return True
                raise
            finally:
                # Closing the fd releases the lock if we took it.
                os.close(fd)
            return False

        def _open_ipc_lock_file(self):
            old_mask = os.umask(0o000)
            try:
                return os.open(self.ipc_lock_file, os.O_CREAT | os.O_RDWR, 0o660)
            finally:
                os.umask(old_mask)

        def _lock_ipc_legacy(self):
            # An older daemon and its clients unlink this file whenever
            # they release it, so a lock may land on a file that is no
            # longer there. Retry until the lock is on the current one.
            while True:
                lock_fd = self._open_ipc_lock_file()
                try:
                    fcntl.lockf(lock_fd, fcntl.LOCK_EX)
                    st = os.stat(self.ipc_lock_file)
                except FileNotFoundError:
                    os.close(lock_fd)
                    continue
                except BaseException:
                    os.close(lock_fd)
                    raise
                fst = os.fstat(lock_fd)
                if (st.st_dev, st.st_ino) == (fst.st_dev, fst.st_ino):
                    return lock_fd
                os.close(lock_fd)

        def communicate(self, args):
            if self._legacy:
                lock_fd = self._lock_ipc_legacy()
            else:
                # This file is only ever locked by the daemon and its
                # clients, which lets both sides use flock() directly
                # instead of agreeing on what portage.locks would have
                # picked.
                lock_fd = self._open_ipc_lock_file()
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                except BaseException:
                    os.close(lock_fd)
                    raise
            try:
                return self._communicate(args)
            finally:
                os.close(lock_fd)

        def _timeout_retry_msg(self, start_time, when):
            time_elapsed = time.time() - start_time
            _writemsg(
                f"ebuild-ipc timed out {when} after {time_elapsed} seconds, retrying...\n"
            )

        def _no_daemon_msg(self):
            _writemsg("ebuild-ipc: daemon process not detected\n")

        def _write_request(self, buf):
            start_time = time.time()
            try:
                fd = os.open(self.ipc_in_fifo, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as e:
                if e.errno == errno.ENXIO:
                    # This happens if the daemon has been killed.
                    return RETURNCODE_FAILURE
                raise

            try:
                while not _poll(fd, select.POLLOUT, _COMMUNICATE_RETRY_TIMEOUT):
                    if self._daemon_is_alive():
                        self._timeout_retry_msg(start_time, "during write")
                    else:
                        self._no_daemon_msg()
                        return RETURNCODE_FAILURE

                # The whole buf should be able to fit in the fifo with
                # a single write call, so there's no valid reason for
                # os.write to raise EAGAIN here.
                while buf:
                    try:
                        buf = buf[os.write(fd, buf) :]
                    except OSError:
                        return RETURNCODE_FAILURE
                return os.EX_OK
            finally:
                os.close(fd)

        def _receive_reply(self, input_fd):
            start_time = time.time()
            read_data = []
            eof = False
            while not eof:
                if not _poll(
                    input_fd, select.POLLIN | select.POLLPRI, _COMMUNICATE_RETRY_TIMEOUT
                ):
                    if self._daemon_is_alive():
                        self._timeout_retry_msg(start_time, "during read")
                        continue
                    self._no_daemon_msg()
                    return RETURNCODE_FAILURE

                while True:
                    try:
                        data = os.read(input_fd, 4096)
                    except OSError as e:
                        if e.errno == errno.EAGAIN:
                            break
                        if e.errno != errno.EIO:
                            raise
                        data = b""
                    if not data:
                        eof = True
                        break
                    read_data.append(data)

            buf = b"".join(read_data)

            retval = RETURNCODE_FAILURE

            if not buf:
                _writemsg("ebuild-ipc: read failed\n")

            else:
                try:
                    reply = _NoGlobalsUnpickler(io.BytesIO(buf)).load()
                except SystemExit:
                    raise
                except Exception as e:
                    # The pickle module can raise practically
                    # any exception when given corrupt data.
                    _writemsg(f"ebuild-ipc: {e}\n")

                else:
                    out, err, retval = reply

                    if out:
                        sys.stdout.write(out)
                        sys.stdout.flush()

                    if err:
                        sys.stderr.write(err)
                        sys.stderr.flush()

            return retval

        def _communicate(self, args):
            if not self._daemon_is_alive():
                self._no_daemon_msg()
                return RETURNCODE_FAILURE

            # Open the input fifo before the output fifo, in order to make it
            # possible for the daemon to send a reply without blocking. This
            # improves performance, and also makes it possible for the daemon
            # to do a non-blocking write without a race condition.
            input_fd = os.open(self.ipc_out_fifo, os.O_RDONLY | os.O_NONBLOCK)
            try:
                retval = self._write_request(pickle.dumps(args))
                if retval != os.EX_OK:
                    _writemsg(f"ebuild-ipc: write failed: {retval}\n")
                    return retval

                if not self._daemon_is_alive():
                    self._no_daemon_msg()
                    return RETURNCODE_FAILURE

                return self._receive_reply(input_fd)
            finally:
                os.close(input_fd)

    def ebuild_ipc_main(args):
        return EbuildIpc().communicate(args)

    if __name__ == "__main__":
        sys.exit(ebuild_ipc_main(sys.argv[1:]))

except KeyboardInterrupt as e:
    # Prevent traceback on ^C
    signum = getattr(e, "signum", signal.SIGINT)
    signal.signal(signum, signal.SIG_DFL)
    signal.raise_signal(signum)
