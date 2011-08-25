# Copyright 1999-2011 Gentoo Foundation
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
		_spawn_kwarg_names + ("_selinux_type",)

	_file_names = ("log", "process", "stdout")
	_files_dict = slot_dict_class(_file_names, prefix="")

	def _start(self):

		if self.cancelled:
			return

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes
		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes.setdefault(1, sys.stdout.fileno())
		fd_pipes.setdefault(2, sys.stderr.fileno())

		# flush any pending output
		for fd in fd_pipes.values():
			if fd == sys.stdout.fileno():
				sys.stdout.flush()
			if fd == sys.stderr.fileno():
				sys.stderr.flush()

		self._files = self._files_dict()
		files = self._files

		master_fd, slave_fd = self._pipe(fd_pipes)
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		logfile = None
		if self._can_log(slave_fd):
			logfile = self.logfile

		null_input = None
		fd_pipes_orig = fd_pipes.copy()
		if self.background:
			# TODO: Use job control functions like tcsetpgrp() to control
			# access to stdin. Until then, use /dev/null so that any
			# attempts to read from stdin will immediately return EOF
			# instead of blocking indefinitely.
			null_input = open('/dev/null', 'rb')
			fd_pipes[0] = null_input.fileno()
		else:
			fd_pipes[0] = fd_pipes_orig[0]

		# WARNING: It is very important to use unbuffered mode here,
		# in order to avoid issue 5380 with python3.
		files.process = os.fdopen(master_fd, 'rb', 0)
		if logfile is not None:

			fd_pipes[1] = slave_fd
			fd_pipes[2] = slave_fd

			files.log = open(_unicode_encode(logfile,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
			if logfile.endswith('.gz'):
				files.log = gzip.GzipFile(filename='', mode='ab',
					fileobj=files.log)

			portage.util.apply_secpass_permissions(logfile,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0o660)

			if not self.background:
				files.stdout = os.fdopen(os.dup(fd_pipes_orig[1]), 'wb')

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

		self._reg_id = self.scheduler.register(files.process.fileno(),
			self._registered_events, output_handler)
		self._registered = True

		retval = self._spawn(self.args, **kwargs)

		os.close(slave_fd)
		if null_input is not None:
			null_input.close()

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
		buf = self._read_buf(files.process, event)

		if buf is not None:

			if buf:
				if not self.background:
					write_successful = False
					failures = 0
					while True:
						try:
							if not write_successful:
								buf.tofile(files.stdout)
								write_successful = True
							files.stdout.flush()
							break
						except IOError as e:
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
							fcntl.fcntl(files.stdout.fileno(), fcntl.F_SETFL,
								fcntl.fcntl(files.stdout.fileno(),
								fcntl.F_GETFL) ^ os.O_NONBLOCK)

				try:
					buf.tofile(files.log)
				except TypeError:
					# array.tofile() doesn't work with GzipFile
					try:
						# Python >=3.2
						data = buf.tobytes()
					except AttributeError:
						data = buf.tostring()
					files.log.write(data)
				files.log.flush()
			else:
				self._unregister()
				self.wait()

		self._unregister_if_appropriate(event)

	def _dummy_handler(self, fd, event):
		"""
		This method is mainly interested in detecting EOF, since
		the only purpose of the pipe is to allow the scheduler to
		monitor the process from inside a poll() loop.
		"""

		buf = self._read_buf(self._files.process, event)

		if buf is not None:

			if buf:
				pass
			else:
				self._unregister()
				self.wait()

		self._unregister_if_appropriate(event)

