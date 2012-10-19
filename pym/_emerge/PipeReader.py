# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask
import fcntl

class PipeReader(AbstractPollTask):

	"""
	Reads output from one or more files and saves it in memory,
	for retrieval via the getvalue() method. This is driven by
	the scheduler's poll() loop, so it runs entirely within the
	current process.
	"""

	__slots__ = ("input_files",) + \
		("_read_data", "_reg_ids", "_use_array")

	def _start(self):
		self._reg_ids = set()
		self._read_data = []

		if self._use_array:
			output_handler = self._array_output_handler
		else:
			output_handler = self._output_handler

		for f in self.input_files.values():
			fcntl.fcntl(f.fileno(), fcntl.F_SETFL,
				fcntl.fcntl(f.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK)
			self._reg_ids.add(self.scheduler.io_add_watch(f.fileno(),
				self._registered_events, output_handler))
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

	def getvalue(self):
		"""Retrieve the entire contents"""
		return b''.join(self._read_data)

	def close(self):
		"""Free the memory buffer."""
		self._read_data = None

	def _output_handler(self, fd, event):

		while True:
			data = self._read_buf(fd, event)
			if data is None:
				break
			if data:
				self._read_data.append(data)
			else:
				self._unregister()
				self.wait()
				break

		self._unregister_if_appropriate(event)

		return True

	def _array_output_handler(self, fd, event):

		for f in self.input_files.values():
			if f.fileno() == fd:
				break

		while True:
			data = self._read_array(f, event)
			if data is None:
				break
			if data:
				self._read_data.append(data)
			else:
				self._unregister()
				self.wait()
				break

		self._unregister_if_appropriate(event)

		return True

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self._reg_ids is not None:
			for reg_id in self._reg_ids:
				self.scheduler.source_remove(reg_id)
			self._reg_ids = None

		if self.input_files is not None:
			for f in self.input_files.values():
				f.close()
			self.input_files = None

