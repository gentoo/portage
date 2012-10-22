# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import array
import errno
import logging
import os

from portage.util import writemsg_level
from _emerge.AsynchronousTask import AsynchronousTask

class AbstractPollTask(AsynchronousTask):

	__slots__ = ("scheduler",) + \
		("_registered",)

	_bufsize = 4096

	@property
	def _exceptional_events(self):
		return self.scheduler.IO_ERR | self.scheduler.IO_NVAL

	@property
	def _registered_events(self):
		return self.scheduler.IO_IN | self.scheduler.IO_HUP | \
			self._exceptional_events

	def isAlive(self):
		return bool(self._registered)

	def _read_array(self, f, event):
		"""
		NOTE: array.fromfile() is used here only for testing purposes,
		because it has bugs in all known versions of Python (including
		Python 2.7 and Python 3.2). See PipeReaderArrayTestCase.

		| POLLIN | RETURN
		| BIT    | VALUE
		| ---------------------------------------------------
		| 1      | Read self._bufsize into an instance of
		|        | array.array('B') and return it, handling
		|        | EOFError and IOError. An empty array
		|        | indicates EOF.
		| ---------------------------------------------------
		| 0      | None
		"""
		buf = None
		if event & self.scheduler.IO_IN:
			buf = array.array('B')
			try:
				buf.fromfile(f, self._bufsize)
			except EOFError:
				pass
			except TypeError:
				# Python 3.2:
				# TypeError: read() didn't return bytes
				pass
			except IOError as e:
				# EIO happens with pty on Linux after the
				# slave end of the pty has been closed.
				if e.errno == errno.EIO:
					# EOF: return empty string of bytes
					pass
				elif e.errno == errno.EAGAIN:
					# EAGAIN: return None
					buf = None
				else:
					raise

		if buf is not None:
			try:
				# Python >=3.2
				buf = buf.tobytes()
			except AttributeError:
				buf = buf.tostring()

		return buf

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
		if event & self.scheduler.IO_IN:
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
				self.wait()
			elif event & self.scheduler.IO_HUP:
				self._unregister()
				self.wait()

	def _wait(self):
		if self.returncode is not None:
			return self.returncode
		self._wait_loop()
		return self.returncode

	def _wait_loop(self, timeout=None):

		if timeout is None:
			while self._registered:
				self.scheduler.iteration()
			return

		def timeout_cb():
			timeout_cb.timed_out = True
			return False
		timeout_cb.timed_out = False
		timeout_cb.timeout_id = self.scheduler.timeout_add(timeout, timeout_cb)

		try:
			while self._registered and not timeout_cb.timed_out:
				self.scheduler.iteration()
		finally:
			self.scheduler.source_remove(timeout_cb.timeout_id)
