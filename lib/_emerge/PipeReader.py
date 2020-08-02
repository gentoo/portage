# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask

class PipeReader(AbstractPollTask):

	"""
	Reads output from one or more files and saves it in memory,
	for retrieval via the getvalue() method. This is driven by
	the scheduler's poll() loop, so it runs entirely within the
	current process.
	"""

	__slots__ = ("input_files",) + \
		("_read_data", "_use_array")

	def _start(self):
		self._read_data = []

		for f in self.input_files.values():
			fd = f if isinstance(f, int) else f.fileno()
			fcntl.fcntl(fd, fcntl.F_SETFL,
				fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

			if self._use_array:
				self.scheduler.add_reader(fd, self._array_output_handler, f)
			else:
				self.scheduler.add_reader(fd, self._output_handler, fd)

		self._registered = True

	def _cancel(self):
		self._unregister()
		if self.returncode is None:
			self.returncode = self._cancelled_returncode

	def getvalue(self):
		"""Retrieve the entire contents"""
		return b''.join(self._read_data)

	def close(self):
		"""Free the memory buffer."""
		self._read_data = None

	def _output_handler(self, fd):

		while True:
			data = self._read_buf(fd)
			if data is None:
				break
			if data:
				self._read_data.append(data)
			else:
				self._unregister()
				self.returncode = self.returncode or os.EX_OK
				self._async_wait()
				break

	def _array_output_handler(self, f):

		while True:
			data = self._read_array(f)
			if data is None:
				break
			if data:
				self._read_data.append(data)
			else:
				self._unregister()
				self.returncode = self.returncode or os.EX_OK
				self._async_wait()
				break

		return True

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self.input_files is not None:
			for f in self.input_files.values():
				if isinstance(f, int):
					self.scheduler.remove_reader(f)
					os.close(f)
				else:
					self.scheduler.remove_reader(f.fileno())
					f.close()
			self.input_files = None
