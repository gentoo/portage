# Copyright 2012-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import warnings
import signal
import sys

from typing import Optional

import portage
from portage import multiprocessing, os
from portage.cache.mappings import slot_dict_class
from portage.util.futures import asyncio
from _emerge.SpawnProcess import SpawnProcess


class ForkProcess(SpawnProcess):
    # NOTE: This class overrides the meaning of the SpawnProcess 'args'
    # attribute, and uses it to hold the positional arguments for the
    # 'target' function.
    __slots__ = (
        "kwargs",
        "target",
        "_child_connection",
        # Duplicate file descriptors for use by _send_fd_pipes background thread.
        "_fd_pipes",
    )

    _file_names = ("connection", "slave_fd")
    _files_dict = slot_dict_class(_file_names, prefix="")

    _HAVE_SEND_HANDLE = getattr(multiprocessing.reduction, "HAVE_SEND_HANDLE", False)

    def _start(self):
        if multiprocessing.get_start_method() == "fork":
            # Backward compatibility mode.
            super()._start()
            return

        # This mode supports multiprocessing start methods
        # other than fork. Note that the fd_pipes implementation
        # uses a thread via run_in_executor, and threads are not
        # recommended for mixing with the fork start method due
        # to cpython issue 84559.
        if self.fd_pipes and not self._HAVE_SEND_HANDLE:
            raise NotImplementedError(
                'fd_pipes only supported with HAVE_SEND_HANDLE or multiprocessing start method "fork"'
            )

        if self.fd_pipes or self.logfile or not self.background:
            # Log via multiprocessing.Pipe if necessary.
            connection, self._child_connection = multiprocessing.Pipe(
                duplex=self._HAVE_SEND_HANDLE
            )

        # Handle fd_pipes in _main instead, since file descriptors are
        # not inherited with the multiprocessing "spawn" start method.
        # Pass fd_pipes=None to spawn here so that it doesn't leave
        # a closed stdin duplicate in fd_pipes (that would trigger
        # "Bad file descriptor" error if we tried to send it via
        # send_handle).
        self._proc = self._spawn(self.args, fd_pipes=None)

        self._registered = True

        if self._child_connection is None:
            self._async_waitpid()
        else:
            self._child_connection.close()
            self.fd_pipes = self.fd_pipes or {}
            stdout_fd = None
            if not self.background:
                self.fd_pipes.setdefault(0, portage._get_stdin().fileno())
                self.fd_pipes.setdefault(1, sys.__stdout__.fileno())
                self.fd_pipes.setdefault(2, sys.__stderr__.fileno())
                if self.create_pipe is not False:
                    stdout_fd = os.dup(self.fd_pipes[1])

            if self._HAVE_SEND_HANDLE:
                if self.create_pipe is not False:
                    master_fd, slave_fd = self._pipe(self.fd_pipes)
                    self.fd_pipes[1] = slave_fd
                    self.fd_pipes[2] = slave_fd
                else:
                    if self.logfile:
                        raise NotImplementedError(
                            "logfile conflicts with create_pipe=False"
                        )
                    # When called via process.spawn, SpawnProcess
                    # will have created a pipe earlier, so it would be
                    # redundant to do it here (it could also trigger spawn
                    # recursion via set_term_size as in bug 923750). Use
                    # /dev/null for master_fd, triggering early return
                    # of _main, followed by _async_waitpid.
                    # TODO: Optimize away the need for master_fd here.
                    master_fd = os.open(os.devnull, os.O_RDONLY)
                    slave_fd = None

                self._files = self._files_dict(connection=connection, slave_fd=slave_fd)

                # Create duplicate file descriptors in self._fd_pipes
                # so that the caller is free to manage the lifecycle
                # of the original fd_pipes.
                self._fd_pipes = {}
                fd_map = {}
                for dest, src in list(self.fd_pipes.items()):
                    if src not in fd_map:
                        src_new = fd_map[src] = os.dup(src)
                        old_fdflags = fcntl.fcntl(src, fcntl.F_GETFD)
                        fcntl.fcntl(src_new, fcntl.F_SETFD, old_fdflags)
                        os.set_inheritable(
                            src_new, not bool(old_fdflags & fcntl.FD_CLOEXEC)
                        )
                    self._fd_pipes[dest] = fd_map[src]

                asyncio.ensure_future(
                    self._proc.wait(), self.scheduler
                ).add_done_callback(self._close_fd_pipes)
            else:
                master_fd = connection

            self._start_main_task(
                master_fd, log_file_path=self.logfile, stdout_fd=stdout_fd
            )

    def _close_fd_pipes(self, future):
        """
        Cleanup self._fd_pipes if needed, since _send_fd_pipes could
        have been cancelled.
        """
        # future.result() raises asyncio.CancelledError if
        # future.cancelled(), but that should not happen.
        future.result()
        if self._fd_pipes is not None:
            for fd in set(self._fd_pipes.values()):
                os.close(fd)
            self._fd_pipes = None

    @property
    def _fd_pipes_send_handle(self):
        """Returns True if we have a connection to implement fd_pipes via send_handle."""
        return bool(
            self._HAVE_SEND_HANDLE
            and self._files
            and getattr(self._files, "connection", False)
        )

    def _send_fd_pipes(self):
        """
        Communicate with _bootstrap to send fd_pipes via send_handle.
        This performs blocking IO, intended for invocation via run_in_executor.
        """
        fd_list = list(set(self._fd_pipes.values()))
        try:
            self._files.connection.send(
                (self._fd_pipes, fd_list),
            )
            for fd in fd_list:
                multiprocessing.reduction.send_handle(
                    self._files.connection,
                    fd,
                    self.pid,
                )
        except BrokenPipeError as e:
            # This case is triggered by testAsynchronousLockWaitCancel
            # when the test case terminates the child process while
            # this thread is still sending the fd_pipes (bug 923852).
            # Even if the child terminated abnormally, then there is
            # no harm in suppressing the exception here, since the
            # child error should have gone to stderr.
            raise asyncio.CancelledError from e

        # self._fd_pipes contains duplicates that must be closed.
        for fd in fd_list:
            os.close(fd)
        self._fd_pipes = None

    async def _main(self, build_logger, pipe_logger, loop=None):
        try:
            if self._fd_pipes_send_handle:
                await self.scheduler.run_in_executor(
                    None,
                    self._send_fd_pipes,
                )
        except asyncio.CancelledError:
            self._main_cancel(build_logger, pipe_logger)
            raise
        finally:
            if self._files:
                if hasattr(self._files, "connection"):
                    self._files.connection.close()
                    del self._files.connection
                if hasattr(self._files, "slave_fd"):
                    if self._files.slave_fd is not None:
                        os.close(self._files.slave_fd)
                    del self._files.slave_fd

        await super()._main(build_logger, pipe_logger, loop=loop)

    def _spawn(
        self, args: list[str], fd_pipes: Optional[dict[int, int]] = None, **kwargs
    ) -> portage.process.MultiprocessingProcess:
        """
        Override SpawnProcess._spawn to fork a subprocess that calls
        self._run(). This uses multiprocessing.Process in order to leverage
        any pre-fork and post-fork interpreter housekeeping that it provides,
        promoting a healthy state for the forked interpreter.
        """

        if self.__class__._run is ForkProcess._run:
            # target replaces the deprecated self._run method
            target = self.target
            args = self.args
            kwargs = self.kwargs
        else:
            # _run implementation triggers backward-compatibility mode
            target = self._run
            args = None
            kwargs = None
            warnings.warn(
                'portage.util._async.ForkProcess.ForkProcess._run is deprecated in favor of the "target" parameter',
                UserWarning,
                stacklevel=2,
            )

        # Since multiprocessing.Process closes sys.__stdin__, create a
        # temporary duplicate of fd_pipes[0] so that sys.__stdin__ can
        # be restored in the subprocess, in case this is needed for
        # things like PROPERTIES=interactive support.
        stdin_dup = None
        try:
            stdin_fd = fd_pipes.get(0) if fd_pipes else None
            if stdin_fd is not None and stdin_fd == portage._get_stdin().fileno():
                stdin_dup = os.dup(stdin_fd)
                fcntl.fcntl(
                    stdin_dup, fcntl.F_SETFD, fcntl.fcntl(stdin_fd, fcntl.F_GETFD)
                )
                fd_pipes[0] = stdin_dup

            proc = multiprocessing.Process(
                target=self._bootstrap,
                args=(
                    self._child_connection,
                    self._HAVE_SEND_HANDLE,
                    fd_pipes,
                    target,
                    args,
                    kwargs,
                ),
            )
            proc.start()
        finally:
            if stdin_dup is not None:
                os.close(stdin_dup)

        return portage.process.MultiprocessingProcess(proc)

    def _cancel(self):
        if self._proc is None:
            super()._cancel()
        else:
            self._proc.terminate()

    def _unregister(self):
        super()._unregister()
        if self._proc is not None:
            self._proc.terminate()

    @staticmethod
    def _bootstrap(child_connection, have_send_handle, fd_pipes, target, args, kwargs):
        # Use default signal handlers in order to avoid problems
        # killing subprocesses as reported in bug #353239.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        # Unregister SIGCHLD handler and wakeup_fd for the parent
        # process's event loop (bug 655656).
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        try:
            wakeup_fd = signal.set_wakeup_fd(-1)
            if wakeup_fd > 0:
                os.close(wakeup_fd)
        except (ValueError, OSError):
            pass

        portage.locks._close_fds()

        if child_connection is not None:
            if have_send_handle:
                fd_pipes, fd_list = child_connection.recv()
                fd_pipes_map = {}
                for fd in fd_list:
                    fd_pipes_map[fd] = multiprocessing.reduction.recv_handle(
                        child_connection
                    )
                child_connection.close()
                for k, v in list(fd_pipes.items()):
                    fd_pipes[k] = fd_pipes_map[v]

            else:
                fd_pipes = fd_pipes or {}
                fd_pipes[sys.stdout.fileno()] = child_connection.fileno()
                fd_pipes[sys.stderr.fileno()] = child_connection.fileno()
                fd_pipes[child_connection.fileno()] = child_connection.fileno()

        if fd_pipes:
            # We don't exec, so use close_fds=False
            # (see _setup_pipes docstring).
            portage.process._setup_pipes(fd_pipes, close_fds=False)

        # Since multiprocessing.Process closes sys.__stdin__ and
        # makes sys.stdin refer to os.devnull, restore it when
        # appropriate.
        if fd_pipes and 0 in fd_pipes:
            # It's possible that sys.stdin.fileno() is already 0,
            # and in that case the above _setup_pipes call will
            # have already updated its identity via dup2. Otherwise,
            # perform the dup2 call now, and also copy the file
            # descriptor flags.
            if sys.stdin.fileno() != 0:
                os.dup2(0, sys.stdin.fileno())
                fcntl.fcntl(
                    sys.stdin.fileno(), fcntl.F_SETFD, fcntl.fcntl(0, fcntl.F_GETFD)
                )
            sys.__stdin__ = sys.stdin

        sys.exit(target(*(args or []), **(kwargs or {})))

    def _run(self):
        """
        Deprecated and replaced with the "target" constructor parameter.
        """
        raise NotImplementedError(self)
