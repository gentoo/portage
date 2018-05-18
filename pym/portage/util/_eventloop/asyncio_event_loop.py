# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal

try:
	import asyncio as _real_asyncio
	from asyncio.events import AbstractEventLoop as _AbstractEventLoop
except ImportError:
	# Allow ImportModulesTestCase to succeed.
	_real_asyncio = None
	_AbstractEventLoop = object


class AsyncioEventLoop(_AbstractEventLoop):
	"""
	Implementation of asyncio.AbstractEventLoop which wraps asyncio's
	event loop and is minimally compatible with _PortageEventLoop.
	"""

	# Use portage's internal event loop in subprocesses, as a workaround
	# for https://bugs.python.org/issue22087, and also
	# https://bugs.python.org/issue29703 which affects pypy3-5.10.1.
	supports_multiprocessing = False

	def __init__(self, loop=None):
		loop = loop or _real_asyncio.get_event_loop()
		self._loop = loop
		self.run_until_complete = loop.run_until_complete
		self.call_soon = loop.call_soon
		self.call_soon_threadsafe = loop.call_soon_threadsafe
		self.call_later = loop.call_later
		self.call_at = loop.call_at
		self.is_running = loop.is_running
		self.is_closed = loop.is_closed
		self.create_future = (loop.create_future
			if hasattr(loop, 'create_future') else self._create_future)
		self.create_task = loop.create_task
		self.add_reader = loop.add_reader
		self.remove_reader = loop.remove_reader
		self.add_writer = loop.add_writer
		self.remove_writer = loop.remove_writer
		self.run_in_executor = loop.run_in_executor
		self.time = loop.time
		self.default_exception_handler = loop.default_exception_handler
		self.call_exception_handler = loop.call_exception_handler
		self.set_debug = loop.set_debug
		self.get_debug = loop.get_debug

	def _create_future(self):
		"""
		Provide AbstractEventLoop.create_future() for python3.4.
		"""
		return _real_asyncio.Future(loop=self._loop)

	@property
	def _asyncio_child_watcher(self):
		"""
		Portage internals use this as a layer of indirection for
		asyncio.get_child_watcher(), in order to support versions of
		python where asyncio is not available.

		@rtype: asyncio.AbstractChildWatcher
		@return: the internal event loop's AbstractChildWatcher interface
		"""
		return _real_asyncio.get_child_watcher()

	@property
	def _asyncio_wrapper(self):
		"""
		Portage internals use this as a layer of indirection in cases
		where a wrapper around an asyncio.AbstractEventLoop implementation
		is needed for purposes of compatiblity.

		@rtype: asyncio.AbstractEventLoop
		@return: the internal event loop's AbstractEventLoop interface
		"""
		return self

	def close(self):
		# Suppress spurious error messages like the following for bug 655656:
		#   Exception ignored when trying to write to the signal wakeup fd:
		#   BlockingIOError: [Errno 11] Resource temporarily unavailable
		self._loop.remove_signal_handler(signal.SIGCHLD)
		self._loop.close()
