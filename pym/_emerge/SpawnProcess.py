# Copyright 2008-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
	import fcntl
except ImportError:
	# http://bugs.jython.org/issue1074
	fcntl = None

from _emerge.SubProcess import SubProcess
import sys
import portage
from portage import os
from portage.const import BASH_BINARY
from portage.util._async.PipeLogger import PipeLogger

# https://bugs.gentoo.org/show_bug.cgi?id=456296
import platform
if platform.system() in ("Darwin",):
    # disable FD_CLOEXEC on stdout, breaks horribly
    fcntl = None

class SpawnProcess(SubProcess):

	"""
	Constructor keyword args are passed into portage.process.spawn().
	The required "args" keyword argument will be passed as the first
	spawn() argument.
	"""

	_spawn_kwarg_names = ("env", "opt_name", "fd_pipes",
		"uid", "gid", "groups", "umask", "logfile",
		"path_lookup", "pre_exec", "close_fds")

	__slots__ = ("args",) + \
		_spawn_kwarg_names + ("_pipe_logger", "_selinux_type",)

	def _start(self):

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes

		master_fd, slave_fd = self._pipe(fd_pipes)

		can_log = self._can_log(slave_fd)
		if can_log:
			log_file_path = self.logfile
		else:
			log_file_path = None

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
			null_input = os.open('/dev/null', os.O_RDWR)
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

		if log_file_path is not None or self.background:
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

		kwargs = {}
		for k in self._spawn_kwarg_names:
			v = getattr(self, k)
			if v is not None:
				kwargs[k] = v

		kwargs["fd_pipes"] = fd_pipes
		kwargs["returnpid"] = True
		kwargs.pop("logfile", None)

		retval = self._spawn(self.args, **kwargs)

		os.close(slave_fd)
		if null_input is not None:
			os.close(null_input)

		if isinstance(retval, int):
			# spawn failed
			self._unregister()
			self._set_returncode((self.pid, retval))
			self._async_wait()
			return

		self.pid = retval[0]
		portage.process.spawned_pids.remove(self.pid)

		stdout_fd = None
		if can_log and not self.background:
			stdout_fd = os.dup(fd_pipes_orig[1])
			if fcntl is not None:
				try:
					fcntl.FD_CLOEXEC
				except AttributeError:
					pass
				else:
					try:
						fcntl.fcntl(stdout_fd, fcntl.F_SETFL,
							fcntl.fcntl(stdout_fd,
							fcntl.F_GETFL) | fcntl.FD_CLOEXEC)
					except IOError:
						# FreeBSD may return "Inappropriate ioctl for device"
						# error here (ENOTTY).
						pass

		self._pipe_logger = PipeLogger(background=self.background,
			scheduler=self.scheduler, input_fd=master_fd,
			log_file_path=log_file_path,
			stdout_fd=stdout_fd)
		self._pipe_logger.addExitListener(self._pipe_logger_exit)
		self._pipe_logger.start()
		self._registered = True

	def _can_log(self, slave_fd):
		return True

	def _pipe(self, fd_pipes):
		"""
		@type fd_pipes: dict
		@param fd_pipes: pipes from which to copy terminal size if desired.
		"""
		return os.pipe()

	def _spawn(self, args, **kwargs):
		spawn_func = portage.process.spawn

		if self._selinux_type is not None:
			spawn_func = portage.selinux.spawn_wrapper(spawn_func,
				self._selinux_type)
			# bash is an allowed entrypoint, while most binaries are not
			if args[0] != BASH_BINARY:
				args = [BASH_BINARY, "-c", "exec \"$@\"", args[0]] + args

		return spawn_func(args, **kwargs)

	def _pipe_logger_exit(self, pipe_logger):
		self._pipe_logger = None
		self._unregister()
		self.wait()

	def _waitpid_loop(self):
		SubProcess._waitpid_loop(self)

		pipe_logger = self._pipe_logger
		if pipe_logger is not None:
			self._pipe_logger = None
			pipe_logger.removeExitListener(self._pipe_logger_exit)
			pipe_logger.cancel()
			pipe_logger.wait()
