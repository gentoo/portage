# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import array
import errno
import os

from portage.util.futures import asyncio
from _emerge.AsynchronousTask import AsynchronousTask

class AbstractPollTask(AsynchronousTask):

	__slots__ = ("_registered",)

	_bufsize = 4096

	def _read_array(self, f):
		"""
		NOTE: array.fromfile() is used here only for testing purposes,
		because it has bugs in all known versions of Python (including
		Python 2.7 and Python 3.2). See PipeReaderArrayTestCase.

		A benchmark that copies bytes from /dev/zero to /dev/null shows
		that arrays give a 15% performance improvement for Python 2.7.14.
		However, arrays significantly *decrease* performance for Python 3.
		"""
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

	def _read_buf(self, fd):
		"""
		Read self._bufsize into a string of bytes, handling EAGAIN and
		EIO. This will only call os.read() once, so the caller should
		call this method in a loop until either None or an empty string
		of bytes is returned. An empty string of bytes indicates EOF.
		None indicates EAGAIN.

		NOTE: os.read() will be called regardless of the event flags,
			since otherwise data may be lost (see bug #531724).

		@param fd: file descriptor (non-blocking mode required)
		@type fd: int
		@rtype: bytes or None
		@return: A string of bytes, or None
		"""
		# NOTE: array.fromfile() is no longer used here because it has
		# bugs in all known versions of Python (including Python 2.7
		# and Python 3.2).
		buf = None
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

	def _async_wait(self):
		self._unregister()
		super(AbstractPollTask, self)._async_wait()

	def _unregister(self):
		self._registered = False

	def _wait_loop(self, timeout=None):
		loop = self.scheduler
		tasks = [self.async_wait()]
		if timeout is not None:
			tasks.append(asyncio.ensure_future(
				asyncio.sleep(timeout, loop=loop), loop=loop))
		try:
			loop.run_until_complete(asyncio.ensure_future(
				asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED,
				loop=loop), loop=loop))
		finally:
			for task in tasks:
				task.cancel()
