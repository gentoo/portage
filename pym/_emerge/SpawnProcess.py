# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess
import sys
from portage.cache.mappings import slot_dict_class
import portage
from portage import _encodings
from portage import _unicode_encode
from portage import os
from portage.const import BASH_BINARY
import fcntl
import errno
import gzip

class SpawnProcess(SubProcess):

	"""
	Constructor keyword args are passed into portage.process.spawn().
	The required "args" keyword argument will be passed as the first
	spawn() argument.
	"""

	_spawn_kwarg_names = ("env", "opt_name", "fd_pipes",
		"uid", "gid", "groups", "umask", "logfile",
		"path_lookup", "pre_exec")

	__slots__ = ("args",) + \
		_spawn_kwarg_names + ("_log_file_real", "_selinux_type",)

	_file_names = ("log", "process", "stdout")
	_files_dict = slot_dict_class(_file_names, prefix="")

	def _start(self):

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes

		self._files = self._files_dict()
		files = self._files

		master_fd, slave_fd = self._pipe(fd_pipes)
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)
		files.process = master_fd

		logfile = None
		if self._can_log(slave_fd):
			logfile = self.logfile

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

		fd_pipes.setdefault(0, sys.__stdin__.fileno())
		fd_pipes.setdefault(1, sys.__stdout__.fileno())
		fd_pipes.setdefault(2, sys.__stderr__.fileno())

		# flush any pending output
		stdout_filenos = (sys.__stdout__.fileno(), sys.__stderr__.fileno())
		for fd in fd_pipes.values():
			if fd in stdout_filenos:
				sys.__stdout__.flush()
				sys.__stderr__.flush()
				break

		if logfile is not None:

			fd_pipes_orig = fd_pipes.copy()
			fd_pipes[1] = slave_fd
			fd_pipes[2] = slave_fd

			files.log = open(_unicode_encode(logfile,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
			if logfile.endswith('.gz'):
				self._log_file_real = files.log
				files.log = gzip.GzipFile(filename='', mode='ab',
					fileobj=files.log)

			portage.util.apply_secpass_permissions(logfile,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0o660)

			if not self.background:
				files.stdout = os.dup(fd_pipes_orig[1])

			output_handler = self._output_handler

		else:

			# Create a dummy pipe so the scheduler can monitor
			# the process from inside a poll() loop.
			fd_pipes[self._dummy_pipe_fd] = slave_fd
			if self.background:
				fd_pipes[1] = slave_fd
				fd_pipes[2] = slave_fd
			output_handler = self._dummy_handler

		kwargs = {}
		for k in self._spawn_kwarg_names:
			v = getattr(self, k)
			if v is not None:
				kwargs[k] = v

		kwargs["fd_pipes"] = fd_pipes
		kwargs["returnpid"] = True
		kwargs.pop("logfile", None)

		self._reg_id = self.scheduler.register(files.process,
			self._registered_events, output_handler)
		self._registered = True

		retval = self._spawn(self.args, **kwargs)

		os.close(slave_fd)
		if null_input is not None:
			os.close(null_input)

		if isinstance(retval, int):
			# spawn failed
			self._unregister()
			self._set_returncode((self.pid, retval))
			self.wait()
			return

		self.pid = retval[0]
		portage.process.spawned_pids.remove(self.pid)

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

	def _output_handler(self, fd, event):

		files = self._files
		while True:
			buf = self._read_buf(fd, event)

			if buf is None:
				# not a POLLIN event, EAGAIN, etc...
				break

			if not buf:
				# EOF
				self._unregister()
				self.wait()
				break

			else:
				if not self.background:
					write_successful = False
					failures = 0
					while True:
						try:
							if not write_successful:
								os.write(files.stdout, buf)
								write_successful = True
							break
						except OSError as e:
							if e.errno != errno.EAGAIN:
								raise
							del e
							failures += 1
							if failures > 50:
								# Avoid a potentially infinite loop. In
								# most cases, the failure count is zero
								# and it's unlikely to exceed 1.
								raise

							# This means that a subprocess has put an inherited
							# stdio file descriptor (typically stdin) into
							# O_NONBLOCK mode. This is not acceptable (see bug
							# #264435), so revert it. We need to use a loop
							# here since there's a race condition due to
							# parallel processes being able to change the
							# flags on the inherited file descriptor.
							# TODO: When possible, avoid having child processes
							# inherit stdio file descriptors from portage
							# (maybe it can't be avoided with
							# PROPERTIES=interactive).
							fcntl.fcntl(files.stdout, fcntl.F_SETFL,
								fcntl.fcntl(files.stdout,
								fcntl.F_GETFL) ^ os.O_NONBLOCK)

				files.log.write(buf)
				files.log.flush()

		self._unregister_if_appropriate(event)

		return True

	def _dummy_handler(self, fd, event):
		"""
		This method is mainly interested in detecting EOF, since
		the only purpose of the pipe is to allow the scheduler to
		monitor the process from inside a poll() loop.
		"""

		while True:
			buf = self._read_buf(fd, event)

			if buf is None:
				# not a POLLIN event, EAGAIN, etc...
				break

			if not buf:
				# EOF
				self._unregister()
				self.wait()
				break

		self._unregister_if_appropriate(event)

		return True

	def _unregister(self):
		super(SpawnProcess, self)._unregister()
		if self._log_file_real is not None:
			# Avoid "ResourceWarning: unclosed file" since python 3.2.
			self._log_file_real.close()
			self._log_file_real = None
