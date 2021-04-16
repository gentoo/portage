# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import signal

import asyncio as _real_asyncio
from asyncio.events import AbstractEventLoop as _AbstractEventLoop
from asyncio.unix_events import AbstractChildWatcher as _AbstractChildWatcher

import portage


class AsyncioEventLoop(_AbstractEventLoop):
	"""
	Implementation of asyncio.AbstractEventLoop which wraps asyncio's
	event loop and is minimally compatible with _PortageEventLoop.
	"""

	def __init__(self, loop=None):
		loop = loop or _real_asyncio.get_event_loop()
		self._loop = loop
		self.run_until_complete = (self._run_until_complete
			if portage._internal_caller else loop.run_until_complete)
		self.call_soon = loop.call_soon
		self.call_soon_threadsafe = loop.call_soon_threadsafe
		self.call_later = loop.call_later
		self.call_at = loop.call_at
		self.is_running = loop.is_running
		self.is_closed = loop.is_closed
		self.close = loop.close
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
		self._wakeup_fd = -1
		self._child_watcher = None

		if portage._internal_caller:
			loop.set_exception_handler(self._internal_caller_exception_handler)

	@staticmethod
	def _internal_caller_exception_handler(loop, context):
		"""
		An exception handler which drops to a pdb shell if std* streams
		refer to a tty, and otherwise kills the process with SIGTERM.

		In order to avoid potential interference with API consumers, this
		implementation is only used when portage._internal_caller is True.
		"""
		loop.default_exception_handler(context)
		if 'exception' in context:
			# Normally emerge will wait for all coroutines to complete
			# after SIGTERM has been received. However, an unhandled
			# exception will prevent the interrupted coroutine from
			# completing, therefore use the default SIGTERM handler
			# in order to ensure that emerge exits immediately (though
			# uncleanly).
			signal.signal(signal.SIGTERM, signal.SIG_DFL)
			os.kill(portage.getpid(), signal.SIGTERM)

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
		if self._child_watcher is None:
			self._child_watcher = _ChildWatcherThreadSafetyWrapper(self, _real_asyncio.get_child_watcher())
		return self._child_watcher

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

	def _run_until_complete(self, future):
		"""
		An implementation of AbstractEventLoop.run_until_complete that supresses
		spurious error messages like the following reported in bug 655656:

		    Exception ignored when trying to write to the signal wakeup fd:
		    BlockingIOError: [Errno 11] Resource temporarily unavailable

		In order to avoid potential interference with API consumers, this
		implementation is only used when portage._internal_caller is True.
		"""
		if self._wakeup_fd != -1:
			signal.set_wakeup_fd(self._wakeup_fd)
			self._wakeup_fd = -1
			# Account for any signals that may have arrived between
			# set_wakeup_fd calls.
			os.kill(portage.getpid(), signal.SIGCHLD)
		try:
			return self._loop.run_until_complete(future)
		finally:
			try:
				self._wakeup_fd = signal.set_wakeup_fd(-1)
			except ValueError:
				# This is intended to fail when not called in the main thread.
				pass


class _ChildWatcherThreadSafetyWrapper(_AbstractChildWatcher):
	def __init__(self, loop, real_watcher):
		self._loop = loop
		self._real_watcher = real_watcher

	def close(self):
		pass

	def __enter__(self):
		return self

	def __exit__(self, a, b, c):
		pass

	def _child_exit(self, pid, status, callback, *args):
		self._loop.call_soon_threadsafe(callback, pid, status, *args)

	def add_child_handler(self, pid, callback, *args):
		self._real_watcher.add_child_handler(pid, self._child_exit, callback, *args)

	def remove_child_handler(self, pid):
		return self._real_watcher.remove_child_handler(pid)
