# Copyright 2008-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import fcntl
import errno
import gzip

import portage
from portage import os, _encodings, _unicode_encode
from _emerge.AbstractPollTask import AbstractPollTask

class PipeLogger(AbstractPollTask):

	"""
	This can be used for logging output of a child process,
	optionally outputing to log_file_path and/or stdout_fd.  It can
	also monitor for EOF on input_fd, which may be used to detect
	termination of a child process. If log_file_path ends with
	'.gz' then the log file is written with compression.
	"""

	__slots__ = ("input_fd", "log_file_path", "stdout_fd") + \
		("_log_file", "_log_file_real", "_reg_id")

	def _start(self):

		log_file_path = self.log_file_path
		if log_file_path is not None:

			self._log_file = open(_unicode_encode(log_file_path,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
			if log_file_path.endswith('.gz'):
				self._log_file_real = self._log_file
				self._log_file = gzip.GzipFile(filename='', mode='ab',
					fileobj=self._log_file)

			portage.util.apply_secpass_permissions(log_file_path,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0o660)

		fcntl.fcntl(self.input_fd, fcntl.F_SETFL,
			fcntl.fcntl(self.input_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		self._reg_id = self.scheduler.io_add_watch(self.input_fd,
			self._registered_events, self._output_handler)
		self._registered = True

	def _cancel(self):
		self._unregister()
		if self.returncode is None:
			self.returncode = self._cancelled_returncode

	def _wait(self):
		if self.returncode is not None:
			return self.returncode
		self._wait_loop()
		self.returncode = os.EX_OK
		return self.returncode

	def _output_handler(self, fd, event):

		background = self.background
		stdout_fd = self.stdout_fd
		log_file = self._log_file 

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
				if not background and stdout_fd is not None:
					write_successful = False
					failures = 0
					while True:
						try:
							if not write_successful:
								os.write(stdout_fd, buf)
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
							fcntl.fcntl(stdout_fd, fcntl.F_SETFL,
								fcntl.fcntl(stdout_fd,
								fcntl.F_GETFL) ^ os.O_NONBLOCK)

				if log_file is not None:
					log_file.write(buf)
					log_file.flush()

		self._unregister_if_appropriate(event)

		return True

	def _unregister(self):

		if self._reg_id is not None:
			self.scheduler.source_remove(self._reg_id)
			self._reg_id = None

		if self.input_fd is not None:
			os.close(self.input_fd)
			self.input_fd = None

		if self.stdout_fd is not None:
			os.close(self.stdout_fd)
			self.stdout_fd = None

		if self._log_file is not None:
			self._log_file.close()
			self._log_file = None

		if self._log_file_real is not None:
			# Avoid "ResourceWarning: unclosed file" since python 3.2.
			self._log_file_real.close()
			self._log_file_real = None

		self._registered = False
