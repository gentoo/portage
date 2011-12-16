# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import logging
import os

from portage.util import writemsg_level
from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.PollConstants import PollConstants
class AbstractPollTask(AsynchronousTask):

	__slots__ = ("scheduler",) + \
		("_registered",)

	_bufsize = 4096
	_exceptional_events = PollConstants.POLLERR | PollConstants.POLLNVAL
	_registered_events = PollConstants.POLLIN | PollConstants.POLLHUP | \
		_exceptional_events

	def isAlive(self):
		return bool(self._registered)

	def _read_buf(self, fd, event):
		"""
		| POLLIN | RETURN
		| BIT    | VALUE
		| ---------------------------------------------------
		| 1      | Read self._bufsize into a string of bytes,
		|        | handling EAGAIN and EIO. An empty string
		|        | of bytes indicates EOF.
		| ---------------------------------------------------
		| 0      | None
		"""
		# NOTE: array.fromfile() is no longer used here because it has
		# bugs in all known versions of Python (including Python 2.7
		# and Python 3.2).
		buf = None
		if event & PollConstants.POLLIN:
			try:
				buf = os.read(fd, self._bufsize)
			except OSError as e:
				# EIO happens with pty on Linux after the
				# slave end of the pty has been closed.
				if e.errno == errno.EIO:
					# EOF: return empty string of bytes
					buf = b''
				elif e.errno == errno.EAGAIN:
					# EAGAIN: return None
					buf = None
				else:
					raise

		return buf

	def _unregister(self):
		raise NotImplementedError(self)

	def _log_poll_exception(self, event):
		writemsg_level(
			"!!! %s received strange poll event: %s\n" % \
			(self.__class__.__name__, event,),
			level=logging.ERROR, noiselevel=-1)

	def _unregister_if_appropriate(self, event):
		if self._registered:
			if event & self._exceptional_events:
				self._log_poll_exception(event)
				self._unregister()
				self.cancel()
			elif event & PollConstants.POLLHUP:
				self._unregister()
				self.wait()

