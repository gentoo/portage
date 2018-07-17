# Copyright 2008-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
	import fcntl
except ImportError:
	# http://bugs.jython.org/issue1074
	fcntl = None

import errno
import logging
import signal
import sys

from _emerge.SubProcess import SubProcess
import portage
from portage import os
from portage.const import BASH_BINARY
from portage.localization import _
from portage.output import EOutput
from portage.util import writemsg_level
from portage.util._async.PipeLogger import PipeLogger

class SpawnProcess(SubProcess):

	"""
	Constructor keyword args are passed into portage.process.spawn().
	The required "args" keyword argument will be passed as the first
	spawn() argument.
	"""

	_spawn_kwarg_names = ("env", "opt_name", "fd_pipes",
		"uid", "gid", "groups", "umask", "logfile",
		"path_lookup", "pre_exec", "close_fds", "cgroup",
		"unshare_ipc", "unshare_net")

	__slots__ = ("args",) + \
		_spawn_kwarg_names + ("_pipe_logger", "_selinux_type",)

	# Max number of attempts to kill the processes listed in cgroup.procs,
	# given that processes may fork before they can be killed.
	_CGROUP_CLEANUP_RETRY_MAX = 8

	def _start(self):

		if self.fd_pipes is None:
			self.fd_pipes = {}
		else:
			self.fd_pipes = self.fd_pipes.copy()
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
			self.returncode = retval
			self._async_wait()
			return

		self.pid = retval[0]

		stdout_fd = None
		if can_log and not self.background:
			stdout_fd = os.dup(fd_pipes_orig[1])
			# FD_CLOEXEC is enabled by default in Python >=3.4.
			if sys.hexversion < 0x3040000 and fcntl is not None:
				try:
					fcntl.FD_CLOEXEC
				except AttributeError:
					pass
				else:
					fcntl.fcntl(stdout_fd, fcntl.F_SETFD,
						fcntl.fcntl(stdout_fd,
						fcntl.F_GETFD) | fcntl.FD_CLOEXEC)

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
		self._async_waitpid()

	def _unregister(self):
		SubProcess._unregister(self)
		if self.cgroup is not None:
			self._cgroup_cleanup()
			self.cgroup = None
		if self._pipe_logger is not None:
			self._pipe_logger.cancel()
			self._pipe_logger = None

	def _cancel(self):
		SubProcess._cancel(self)
		self._cgroup_cleanup()

	def _cgroup_cleanup(self):
		if self.cgroup:
			def get_pids(cgroup):
				try:
					with open(os.path.join(cgroup, 'cgroup.procs'), 'r') as f:
						return [int(p) for p in f.read().split()]
				except EnvironmentError:
					# removed by cgroup-release-agent
					return []

			def kill_all(pids, sig):
				for p in pids:
					try:
						os.kill(p, sig)
					except OSError as e:
						if e.errno == errno.EPERM:
							# Reported with hardened kernel (bug #358211).
							writemsg_level(
								"!!! kill: (%i) - Operation not permitted\n" %
								(p,), level=logging.ERROR,
								noiselevel=-1)
						elif e.errno != errno.ESRCH:
							raise

			# step 1: kill all orphans (loop in case of new forks)
			remaining = self._CGROUP_CLEANUP_RETRY_MAX
			while remaining:
				remaining -= 1
				pids = get_pids(self.cgroup)
				if pids:
					kill_all(pids, signal.SIGKILL)
				else:
					break

			if pids:
				msg = []
				msg.append(
					_("Failed to kill pid(s) in '%(cgroup)s': %(pids)s") % dict(
					cgroup=os.path.join(self.cgroup, 'cgroup.procs'),
					pids=' '.join(str(pid) for pid in pids)))

				self._elog('eerror', msg)

			# step 2: remove the cgroup
			try:
				os.rmdir(self.cgroup)
			except OSError:
				# it may be removed already, or busy
				# we can't do anything good about it
				pass

	def _elog(self, elog_funcname, lines):
		elog_func = getattr(EOutput(), elog_funcname)
		for line in lines:
			elog_func(line)
