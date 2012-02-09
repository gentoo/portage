# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask
from portage.cache.mappings import slot_dict_class

class FifoIpcDaemon(AbstractPollTask):

	__slots__ = ("input_fifo", "output_fifo",) + \
		("_files", "_reg_id",)

	_file_names = ("pipe_in",)
	_files_dict = slot_dict_class(_file_names, prefix="")

	def _start(self):
		self._files = self._files_dict()

		# File streams are in unbuffered mode since we do atomic
		# read and write of whole pickles.
		self._files.pipe_in = \
			os.open(self.input_fifo, os.O_RDONLY|os.O_NONBLOCK)

		self._reg_id = self.scheduler.register(
			self._files.pipe_in,
			self._registered_events, self._input_handler)

		self._registered = True

	def _reopen_input(self):
		"""
		Re-open the input stream, in order to suppress
		POLLHUP events (bug #339976).
		"""
		self.scheduler.unregister(self._reg_id)
		os.close(self._files.pipe_in)
		self._files.pipe_in = \
			os.open(self.input_fifo, os.O_RDONLY|os.O_NONBLOCK)
		self._reg_id = self.scheduler.register(
			self._files.pipe_in,
			self._registered_events, self._input_handler)

	def isAlive(self):
		return self._registered

	def _cancel(self):
		if self.returncode is None:
			self.returncode = 1
		self._unregister()

	def _wait(self):
		if self.returncode is not None:
			return self.returncode
		self._wait_loop()
		if self.returncode is None:
			self.returncode = os.EX_OK
		return self.returncode

	def _input_handler(self, fd, event):
		raise NotImplementedError(self)

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self._reg_id is not None:
			self.scheduler.unregister(self._reg_id)
			self._reg_id = None

		if self._files is not None:
			for f in self._files.values():
				os.close(f)
			self._files = None
