# Copyright 2008-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import fcntl
import errno
import gzip
import sys

import portage
from portage import os, _encodings, _unicode_encode
from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine
from portage.util.futures.unix_events import _set_nonblocking
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
		("_io_loop_task", "_log_file", "_log_file_real")

	def _start(self):

		log_file_path = self.log_file_path
		if hasattr(log_file_path, 'write'):
			self._log_file = log_file_path
			_set_nonblocking(self._log_file.fileno())
		elif log_file_path is not None:
			self._log_file = open(_unicode_encode(log_file_path,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
			if log_file_path.endswith('.gz'):
				self._log_file_real = self._log_file
				self._log_file = gzip.GzipFile(filename='', mode='ab',
					fileobj=self._log_file)

			portage.util.apply_secpass_permissions(log_file_path,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0o660)

		if isinstance(self.input_fd, int):
			fd = self.input_fd
		else:
			fd = self.input_fd.fileno()

		fcntl.fcntl(fd, fcntl.F_SETFL,
			fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		# FD_CLOEXEC is enabled by default in Python >=3.4.
		if sys.hexversion < 0x3040000:
			try:
				fcntl.FD_CLOEXEC
			except AttributeError:
				pass
			else:
				fcntl.fcntl(fd, fcntl.F_SETFD,
					fcntl.fcntl(fd, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)

		self._io_loop_task = asyncio.ensure_future(self._io_loop(fd), loop=self.scheduler)
		self._io_loop_task.add_done_callback(self._io_loop_done)
		self._registered = True

	def _cancel(self):
		self._unregister()
		if self.returncode is None:
			self.returncode = self._cancelled_returncode

	@coroutine
	def _io_loop(self, fd):
		background = self.background
		stdout_fd = self.stdout_fd
		log_file = self._log_file 

		while True:
			buf = self._read_buf(fd)

			if buf is None:
				# not a POLLIN event, EAGAIN, etc...
				future = self.scheduler.create_future()
				self.scheduler.add_reader(fd, future.set_result, None)
				try:
					yield future
				finally:
					self.scheduler.remove_reader(fd)
					future.done() or future.cancel()
				continue

			if not buf:
				# EOF
				return

			else:
				if not background and stdout_fd is not None:
					failures = 0
					stdout_buf = buf
					while stdout_buf:
						try:
							stdout_buf = \
								stdout_buf[os.write(stdout_fd, stdout_buf):]
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
					write_buf = buf
					while True:
						try:
							if write_buf is not None:
								log_file.write(write_buf)
								write_buf = None
							log_file.flush()
						except EnvironmentError as e:
							if e.errno != errno.EAGAIN:
								raise
							future = self.scheduler.create_future()
							self.scheduler.add_writer(self._log_file.fileno(), future.set_result, None)
							try:
								yield future
							finally:
								self.scheduler.remove_writer(self._log_file.fileno())
								future.done() or future.cancel()
						else:
							break

	def _io_loop_done(self, future):
		try:
			future.result()
		except asyncio.CancelledError:
			self.cancel()
			self._was_cancelled()
		self.returncode = self.returncode or os.EX_OK
		self._async_wait()

	def _unregister(self):
		if self.input_fd is not None:
			if isinstance(self.input_fd, int):
				self.scheduler.remove_reader(self.input_fd)
				os.close(self.input_fd)
			else:
				self.scheduler.remove_reader(self.input_fd.fileno())
				self.input_fd.close()
			self.input_fd = None

		if self._io_loop_task is not None:
			self._io_loop_task.done() or self._io_loop_task.cancel()
			self._io_loop_task = None

		if self.stdout_fd is not None:
			os.close(self.stdout_fd)
			self.stdout_fd = None

		if self._log_file is not None:
			self.scheduler.remove_writer(self._log_file.fileno())
			self._log_file.close()
			self._log_file = None

		if self._log_file_real is not None:
			# Avoid "ResourceWarning: unclosed file" since python 3.2.
			self._log_file_real.close()
			self._log_file_real = None

		self._registered = False
