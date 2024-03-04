# Copyright 2008-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import sys

from _emerge.SubProcess import SubProcess
import portage
from portage import os
from portage.const import BASH_BINARY
from portage.output import EOutput
from portage.util._async.BuildLogger import BuildLogger
from portage.util._async.PipeLogger import PipeLogger
from portage.util._pty import _create_pty_or_pipe
from portage.util.futures import asyncio


class SpawnProcess(SubProcess):
    """
    Constructor keyword args are passed into portage.process.spawn().
    The required "args" keyword argument will be passed as the first
    spawn() argument.
    """

    _spawn_kwarg_names = (
        "env",
        "opt_name",
        "fd_pipes",
        "uid",
        "gid",
        "groups",
        "umask",
        "logfile",
        "path_lookup",
        "pre_exec",
        "close_fds",
        "unshare_ipc",
        "unshare_mount",
        "unshare_pid",
        "unshare_net",
    )

    __slots__ = (
        ("args", "create_pipe", "log_filter_file")
        + _spawn_kwarg_names
        + (
            "_main_task",
            "_main_task_cancel",
            "_pty_ready",
            "_selinux_type",
        )
    )

    # Max number of attempts to kill the processes listed in cgroup.procs,
    # given that processes may fork before they can be killed.
    _CGROUP_CLEANUP_RETRY_MAX = 8

    def _start(self):
        if self.fd_pipes is None:
            self.fd_pipes = {}
        else:
            self.fd_pipes = self.fd_pipes.copy()
        fd_pipes = self.fd_pipes
        log_file_path = None

        if fd_pipes or self.logfile or not self.background:
            if self.create_pipe is not False:
                master_fd, slave_fd = self._pipe(fd_pipes)

                can_log = self._can_log(slave_fd)
                if can_log:
                    log_file_path = self.logfile
            else:
                if self.logfile:
                    raise NotImplementedError(
                        "logfile conflicts with create_pipe=False"
                    )
                # When called via process.spawn and ForkProcess._start,
                # SpawnProcess will have created a pipe earlier, so it
                # would be redundant to do it here (it could also trigger
                # spawn recursion via set_term_size as in bug 923750).
                master_fd = None
                slave_fd = None
                can_log = False

            null_input = None
            if not self.background or 0 in fd_pipes:
                # Subclasses such as AbstractEbuildProcess may have already passed
                # in a null file descriptor in fd_pipes, so use that when given.
                pass
            else:
                # TODO: Use job control functions like tcsetpgrp() to control
                # access to stdin. Until then, use /dev/null so that any
                # attempts to read from stdin will immediately return EOF
                # instead of blocking indefinitely.
                null_input = os.open("/dev/null", os.O_RDWR)
                fd_pipes[0] = null_input

            fd_pipes.setdefault(0, portage._get_stdin().fileno())
            fd_pipes.setdefault(1, sys.__stdout__.fileno())
            fd_pipes.setdefault(2, sys.__stderr__.fileno())

            # flush any pending output
            stdout_filenos = (sys.__stdout__.fileno(), sys.__stderr__.fileno())
            for fd in fd_pipes.values():
                if fd in stdout_filenos:
                    sys.__stdout__.flush()
                    sys.__stderr__.flush()
                    break

            fd_pipes_orig = fd_pipes.copy()

            if slave_fd is None:
                pass
            elif log_file_path is not None or self.background:
                fd_pipes[1] = slave_fd
                fd_pipes[2] = slave_fd

            else:
                # Create a dummy pipe that PipeLogger uses to efficiently
                # monitor for process exit by listening for the EOF event.
                # Re-use of the allocated fd number for the key in fd_pipes
                # guarantees that the keys will not collide for similarly
                # allocated pipes which are used by callers such as
                # FileDigester and MergeProcess. See the _setup_pipes
                # docstring for more benefits of this allocation approach.
                self._dummy_pipe_fd = slave_fd
                fd_pipes[slave_fd] = slave_fd
        else:
            can_log = False
            slave_fd = None
            null_input = None

        kwargs = {}
        for k in self._spawn_kwarg_names:
            v = getattr(self, k)
            if v is not None:
                kwargs[k] = v

        kwargs["fd_pipes"] = fd_pipes
        kwargs["returnproc"] = True
        kwargs.pop("logfile", None)

        self._proc = self._spawn(self.args, **kwargs)

        if slave_fd is not None:
            os.close(slave_fd)
        if null_input is not None:
            os.close(null_input)

        if not fd_pipes:
            self._registered = True
            self._async_waitpid()
            return

        stdout_fd = None
        if can_log and not self.background:
            stdout_fd = os.dup(fd_pipes_orig[1])

        self._start_main_task(
            master_fd, log_file_path=log_file_path, stdout_fd=stdout_fd
        )
        self._registered = True

    def _start_main_task(self, pr, log_file_path=None, stdout_fd=None):
        if pr is None:
            build_logger = None
            pipe_logger = None
        else:
            build_logger = BuildLogger(
                env=self.env,
                log_path=log_file_path,
                log_filter_file=self.log_filter_file,
                scheduler=self.scheduler,
            )
            build_logger.start()

            pipe_logger = PipeLogger(
                background=self.background,
                scheduler=self.scheduler,
                input_fd=pr,
                log_file_path=build_logger.stdin,
                stdout_fd=stdout_fd,
            )

            pipe_logger.start()

        self._main_task_cancel = functools.partial(
            self._main_cancel, build_logger, pipe_logger
        )
        self._main_task = asyncio.ensure_future(
            self._main(build_logger, pipe_logger, loop=self.scheduler),
            loop=self.scheduler,
        )
        self._main_task.add_done_callback(self._main_exit)

    async def _main(self, build_logger, pipe_logger, loop=None):
        if isinstance(self._pty_ready, asyncio.Future):
            await self._pty_ready
            self._pty_ready = None
        try:
            if pipe_logger is not None and pipe_logger.poll() is None:
                await pipe_logger.async_wait()
            if build_logger is not None and build_logger.poll() is None:
                await build_logger.async_wait()
        except asyncio.CancelledError:
            self._main_cancel(build_logger, pipe_logger)
            raise

    def _main_cancel(self, build_logger, pipe_logger):
        if pipe_logger is not None and pipe_logger.poll() is None:
            pipe_logger.cancel()
        if build_logger is not None and build_logger.poll() is None:
            build_logger.cancel()

    def _main_exit(self, main_task):
        self._main_task = None
        self._main_task_cancel = None
        try:
            main_task.result()
        except asyncio.CancelledError:
            self.cancel()
        self._async_waitpid()

    def _async_wait(self):
        # Allow _main_task to exit normally rather than via cancellation.
        if self._main_task is None:
            super()._async_wait()

    def _async_waitpid(self):
        # Allow _main_task to exit normally rather than via cancellation.
        if self._main_task is None:
            super()._async_waitpid()

    def _can_log(self, slave_fd):
        return True

    def _pipe(self, fd_pipes):
        """
        @type fd_pipes: dict
        @param fd_pipes: pipes from which to copy terminal size if desired.
        """
        stdout_pipe = None
        if not self.background:
            stdout_pipe = fd_pipes.get(1)
        self._pty_ready, master_fd, slave_fd = _create_pty_or_pipe(
            copy_term_size=stdout_pipe
        )
        return (master_fd, slave_fd)

    def _spawn(
        self, args: list[str], **kwargs
    ) -> portage.process.MultiprocessingProcess:
        spawn_func = portage.process.spawn

        if self._selinux_type is not None:
            spawn_func = portage.selinux.spawn_wrapper(spawn_func, self._selinux_type)
            # bash is an allowed entrypoint, while most binaries are not
            if args[0] != BASH_BINARY:
                args = [BASH_BINARY, "-c", 'exec "$@"', args[0]] + args

        return spawn_func(args, **kwargs)

    def _unregister(self):
        SubProcess._unregister(self)
        if self._main_task is not None:
            self._main_task.done() or self._main_task.cancel()
        if isinstance(self._pty_ready, asyncio.Future):
            (
                self._pty_ready.done()
                and (self._pty_ready.cancelled() or self._pty_ready.result() or True)
            ) or self._pty_ready.cancel()
            self._pty_ready = None

    def _cancel(self):
        if self._main_task is not None:
            if not self._main_task.done():
                if self._main_task_cancel is not None:
                    self._main_task_cancel()
                    self._main_task_cancel = None
                self._main_task.cancel()
        SubProcess._cancel(self)

    def _elog(self, elog_funcname, lines):
        elog_func = getattr(EOutput(), elog_funcname)
        for line in lines:
            elog_func(line)
