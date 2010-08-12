# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import array
import pickle
from portage import os
from _emerge.AbstractPollTask import AbstractPollTask
from _emerge.PollConstants import PollConstants
from portage.cache.mappings import slot_dict_class

class FifoIpcDaemon(AbstractPollTask):

	"""
    This class serves as an IPC daemon, which ebuild processes can use
    to communicate with portage's main python process.

    Here are a few possible uses:

    1) Robust subshell/subprocess die support. This allows the ebuild
       environment to reliably die without having to rely on signal IPC.

    2) Delegation of portageq calls to the main python process, eliminating
       performance and userpriv permission issues.

    3) Reliable ebuild termination in cases when the ebuild has accidentally
       left orphan processes running in the backgraound (as in bug 278895).
	"""

	__slots__ = ("input_fifo", "output_fifo",) + \
		("_files", "_reg_id",)

	_file_names = ("pipe_in",)
	_files_dict = slot_dict_class(_file_names, prefix="")

	def _start(self):
		self._files = self._files_dict()
		input_fd = os.open(self.input_fifo, os.O_RDONLY|os.O_NONBLOCK)
		self._files.pipe_in = os.fdopen(input_fd, 'rb')

		self._reg_id = self.scheduler.register(
			self._files.pipe_in.fileno(),
			self._registered_events, self._input_handler)

		self._registered = True

	def isAlive(self):
		return self._registered

	def cancel(self):
		if self.returncode is None:
			self.returncode = 1
			self.cancelled = True
		self._unregister()
		self.wait()

	def _wait(self):
		if self.returncode is not None:
			return self.returncode

		if self._registered:
			self.scheduler.schedule(self._reg_id)
			self._unregister()

		if self.returncode is None:
			self.returncode = os.EX_OK

		return self.returncode

	def _input_handler(self, fd, event):

		if event & PollConstants.POLLIN:

			buf = array.array('B')
			try:
				buf.fromfile(self._files.pipe_in, self._bufsize)
			except (EOFError, IOError):
				pass

			if buf:
				obj = pickle.loads(buf.tostring())
				if isinstance(obj, list) and \
					obj and \
					obj[0] == 'exit':
					output_fd = os.open(self.output_fifo, os.O_WRONLY|os.O_NONBLOCK)
					output_file = os.fdopen(output_fd, 'wb')
					pickle.dump('OK', output_file)
					output_file.close()
					self._unregister()
					self.wait()

		self._unregister_if_appropriate(event)
		return self._registered

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
				f.close()
			self._files = None
