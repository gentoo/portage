# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import array

from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.PollConstants import PollConstants
class AbstractPollTask(AsynchronousTask):

	__slots__ = ("scheduler",) + \
		("_registered",)

	_bufsize = 4096
	_exceptional_events = PollConstants.POLLERR | PollConstants.POLLNVAL
	_registered_events = PollConstants.POLLIN | PollConstants.POLLHUP | \
		_exceptional_events

	def _read_buf(self, f, event):
		"""
		| POLLIN | RETURN
		| BIT    | VALUE
		| ---------------------------------------------------
		| 1      | Read self._bufsize into an instance of
		|        | array.array('B') and return it, ignoring
		|        | EOFError and IOError. An empty array
		|        | indicates EOF.
		| ---------------------------------------------------
		| 0      | None
		"""
		buf = None
		if event & PollConstants.POLLIN:
			buf = array.array('B')
			try:
				buf.fromfile(f, self._bufsize)
			except (EOFError, IOError):
				pass
		return buf

	def _unregister(self):
		raise NotImplementedError(self)

	def _unregister_if_appropriate(self, event):
		if self._registered:
			if event & self._exceptional_events:
				self._unregister()
				self.cancel()
			elif event & PollConstants.POLLHUP:
				self._unregister()
				self.wait()

