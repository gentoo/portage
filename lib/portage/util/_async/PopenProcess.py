# Copyright 2012-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess

class PopenProcess(SubProcess):

	__slots__ = ("pipe_reader", "proc",)

	def _start(self):

		self.pid = self.proc.pid
		self._registered = True

		if self.pipe_reader is None:
			self.scheduler.call_soon(self._async_waitpid)
		else:
			try:
				self.pipe_reader.scheduler = self.scheduler
			except AttributeError:
				pass
			self.pipe_reader.addExitListener(self._pipe_reader_exit)
			self.pipe_reader.start()

	def _pipe_reader_exit(self, pipe_reader):
		self._async_waitpid()

	def _async_waitpid_cb(self, *args, **kwargs):
		SubProcess._async_waitpid_cb(self, *args, **kwargs)
		if self.proc.returncode is None:
			# Suppress warning messages like this:
			# ResourceWarning: subprocess 1234 is still running
			self.proc.returncode = self.returncode
