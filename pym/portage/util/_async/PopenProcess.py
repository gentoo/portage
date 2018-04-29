# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess

class PopenProcess(SubProcess):

	__slots__ = ("pipe_reader", "proc",)

	def _start(self):

		self.pid = self.proc.pid
		self._registered = True

		if self.pipe_reader is None:
			self._async_waitpid()
		else:
			try:
				self.pipe_reader.scheduler = self.scheduler
			except AttributeError:
				pass
			self.pipe_reader.addExitListener(self._pipe_reader_exit)
			self.pipe_reader.start()

	def _pipe_reader_exit(self, pipe_reader):
		self._async_waitpid()

	def _async_waitpid(self):
		if self.returncode is None:
			self.scheduler._asyncio_child_watcher.\
				add_child_handler(self.pid, self._async_waitpid_cb)
		else:
			self._unregister()
			self._async_wait()

	def _async_waitpid_cb(self, pid, returncode):
		if self.proc.returncode is None:
			# Suppress warning messages like this:
			# ResourceWarning: subprocess 1234 is still running
			self.proc.returncode = returncode
		self._unregister()
		self.returncode = returncode
		self._async_wait()

	def _poll(self):
		# Simply rely on _async_waitpid_cb to set the returncode.
		return self.returncode
