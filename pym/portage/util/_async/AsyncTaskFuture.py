# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import signal

from _emerge.AsynchronousTask import AsynchronousTask


class AsyncTaskFuture(AsynchronousTask):
	"""
	Wraps a Future in an AsynchronousTask, which is useful for
	scheduling with TaskScheduler.
	"""
	__slots__ = ('future',)
	def _start(self):
		self.future.add_done_callback(self._done_callback)

	def _cancel(self):
		if not self.future.done():
			self.future.cancel()

	def _done_callback(self, future):
		if future.cancelled():
			self.cancelled = True
			self.returncode = -signal.SIGINT
		elif future.exception() is None:
			self.returncode = os.EX_OK
		else:
			self.returncode = 1
		self._async_wait()
