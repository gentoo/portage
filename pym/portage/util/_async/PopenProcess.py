# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess

class PopenProcess(SubProcess):

	__slots__ = ("pipe_reader", "proc",)

	def _start(self):

		self.pid = self.proc.pid
		self._registered = True

		if self.pipe_reader is None:
			self._reg_id = self.scheduler.child_watch_add(
				self.pid, self._child_watch_cb)
		else:
			try:
				self.pipe_reader.scheduler = self.scheduler
			except AttributeError:
				pass
			self.pipe_reader.addExitListener(self._pipe_reader_exit)
			self.pipe_reader.start()

	def _pipe_reader_exit(self, pipe_reader):
		self._reg_id = self.scheduler.child_watch_add(
			self.pid, self._child_watch_cb)

	def _child_watch_cb(self, pid, condition, user_data=None):
		self._reg_id = None
		self._waitpid_cb(pid, condition)
		self.wait()
