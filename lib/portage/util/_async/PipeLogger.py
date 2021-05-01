# Copyright 2008-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import errno
import gzip

import portage
from portage import os, _encodings, _unicode_encode
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _writer
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
		("_io_loop_task", "_log_file", "_log_file_nb", "_log_file_real")

	def _start(self):

		log_file_path = self.log_file_path
		if hasattr(log_file_path, 'write'):
			self._log_file_nb = True
			self._log_file = log_file_path
			_set_nonblocking(self._log_file.fileno())
		elif log_file_path is not None:
			try:
				self._log_file = open(
					_unicode_encode(
						log_file_path, encoding=_encodings["fs"], errors="strict"
					),
					mode="ab",
				)

				if log_file_path.endswith(".gz"):
					self._log_file_real = self._log_file
					self._log_file = gzip.GzipFile(
						filename="", mode="ab", fileobj=self._log_file
					)

				portage.util.apply_secpass_permissions(
					log_file_path,
					uid=portage.portage_uid,
					gid=portage.portage_gid,
					mode=0o660,
				)
			except FileNotFoundError:
				if self._was_cancelled():
					self._async_wait()
					return
				raise

		if isinstance(self.input_fd, int):
			self.input_fd = os.fdopen(self.input_fd, 'rb', 0)

		fd = self.input_fd.fileno()

		fcntl.fcntl(fd, fcntl.F_SETFL,
			fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		self._io_loop_task = asyncio.ensure_future(self._io_loop(self.input_fd), loop=self.scheduler)
		self._io_loop_task.add_done_callback(self._io_loop_done)
		self._registered = True

	def _cancel(self):
		self._unregister()
		if self.returncode is None:
			self.returncode = self._cancelled_returncode

	async def _io_loop(self, input_file):
		background = self.background
		stdout_fd = self.stdout_fd
		log_file = self._log_file
		fd = input_file.fileno()

		while True:
			buf = self._read_buf(fd)

			if buf is None:
				# not a POLLIN event, EAGAIN, etc...
				future = self.scheduler.create_future()
				self.scheduler.add_reader(fd, future.set_result, None)
				try:
					await future
				finally:
					# The loop and input file may have been closed.
					if not self.scheduler.is_closed():
						future.done() or future.cancel()
						# Do not call remove_reader in cases where fd has
						# been closed and then re-allocated to a concurrent
						# coroutine as in bug 716636.
						if not input_file.closed:
							self.scheduler.remove_reader(fd)
				continue

			if not buf:
				# EOF
				return

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
				if self._log_file_nb:
					# Use the _writer function which uses os.write, since the
					# log_file.write method looses data when an EAGAIN occurs.
					await _writer(log_file, buf)
				else:
					# For gzip.GzipFile instances, the above _writer function
					# will not work because data written directly to the file
					# descriptor bypasses compression.
					log_file.write(buf)
					log_file.flush()

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
				os.close(self.input_fd)
			elif not self.input_fd.closed:
				self.scheduler.remove_reader(self.input_fd.fileno())
				self.input_fd.close()
			self.input_fd = None

		if self._io_loop_task is not None:
			if not self.scheduler.is_closed():
				self._io_loop_task.done() or self._io_loop_task.cancel()
			self._io_loop_task = None

		if self.stdout_fd is not None:
			os.close(self.stdout_fd)
			self.stdout_fd = None

		if self._log_file is not None:
			if not self._log_file.closed:
				self.scheduler.remove_writer(self._log_file.fileno())
				self._log_file.close()
			self._log_file = None

		if self._log_file_real is not None:
			# Avoid "ResourceWarning: unclosed file" since python 3.2.
			self._log_file_real.close()
			self._log_file_real = None

		self._registered = False
