# Copyright 2012-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import functools
import multiprocessing
import warnings
import signal
import sys

import portage
from portage import os
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
        "_proc",
        "_proc_join_task",
    )

    _file_names = ("connection", "slave_fd")
    _files_dict = slot_dict_class(_file_names, prefix="")

    # Number of seconds between poll attempts for process exit status
    # (after the sentinel has become ready).
    _proc_join_interval = 0.1

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

        retval = self._spawn(self.args, fd_pipes=self.fd_pipes)

        self.pid = retval[0]
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
                stdout_fd = os.dup(self.fd_pipes[1])

            if self._HAVE_SEND_HANDLE:
                master_fd, slave_fd = self._pipe(self.fd_pipes)
                self.fd_pipes[1] = slave_fd
                self.fd_pipes[2] = slave_fd
                self._files = self._files_dict(connection=connection, slave_fd=slave_fd)
            else:
                master_fd = connection

            self._start_main_task(
                master_fd, log_file_path=self.logfile, stdout_fd=stdout_fd
            )

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
        fd_list = list(set(self.fd_pipes.values()))
        self._files.connection.send(
            (self.fd_pipes, fd_list),
        )
        for fd in fd_list:
            multiprocessing.reduction.send_handle(
                self._files.connection,
                fd,
                self.pid,
            )

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
                    os.close(self._files.slave_fd)
                    del self._files.slave_fd

        await super()._main(build_logger, pipe_logger, loop=loop)

    def _spawn(self, args, fd_pipes=None, **kwargs):
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

            if self._fd_pipes_send_handle:
                # Handle fd_pipes in _main instead.
                fd_pipes = None

            self._proc = multiprocessing.Process(
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
            self._proc.start()
        finally:
            if stdin_dup is not None:
                os.close(stdin_dup)

        self._proc_join_task = asyncio.ensure_future(
            self._proc_join(self._proc, loop=self.scheduler), loop=self.scheduler
        )
        self._proc_join_task.add_done_callback(
            functools.partial(self._proc_join_done, self._proc)
        )

        return [self._proc.pid]

    def _cancel(self):
        if self._proc is None:
            super()._cancel()
        else:
            self._proc.terminate()

    def _async_wait(self):
        if self._proc_join_task is None:
            super()._async_wait()

    def _async_waitpid(self):
        if self._proc_join_task is None:
            super()._async_waitpid()

    async def _proc_join(self, proc, loop=None):
        sentinel_reader = self.scheduler.create_future()
        self.scheduler.add_reader(
            proc.sentinel,
            lambda: sentinel_reader.done() or sentinel_reader.set_result(None),
        )
        try:
            await sentinel_reader
        finally:
            # If multiprocessing.Process supports the close method, then
            # access to proc.sentinel will raise ValueError if the
            # sentinel has been closed. In this case it's not safe to call
            # remove_reader, since the file descriptor may have been closed
            # and then reallocated to a concurrent coroutine. When the
            # close method is not supported, proc.sentinel remains open
            # until proc's finalizer is called.
            try:
                self.scheduler.remove_reader(proc.sentinel)
            except ValueError:
                pass

        # Now that proc.sentinel is ready, poll until process exit
        # status has become available.
        while True:
            proc.join(0)
            if proc.exitcode is not None:
                break
            await asyncio.sleep(self._proc_join_interval, loop=loop)

    def _proc_join_done(self, proc, future):
        future.cancelled() or future.result()
        self._was_cancelled()
        if self.returncode is None:
            self.returncode = proc.exitcode

        self._proc = None
        if hasattr(proc, "close"):
            proc.close()
        self._proc_join_task = None
        self._async_wait()

    def _unregister(self):
        super()._unregister()
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.terminate()
            self._proc = None
        if self._proc_join_task is not None:
            self._proc_join_task.cancel()
            self._proc_join_task = None

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
