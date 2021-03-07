# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'AbstractChildWatcher',
	'DefaultEventLoopPolicy',
)

import asyncio as _real_asyncio
from asyncio import events
from asyncio.unix_events import AbstractChildWatcher

import fcntl
import os

from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)


class _PortageEventLoop(events.AbstractEventLoop):
	"""
	Implementation of asyncio.AbstractEventLoop which wraps portage's
	internal event loop.
	"""

	def __init__(self, loop):
		"""
		@type loop: EventLoop
		@param loop: an instance of portage's internal event loop
		"""
		self._loop = loop
		self.run_until_complete = loop.run_until_complete
		self.call_soon = loop.call_soon
		self.call_soon_threadsafe = loop.call_soon_threadsafe
		self.call_later = loop.call_later
		self.call_at = loop.call_at
		self.is_running = loop.is_running
		self.is_closed = loop.is_closed
		self.close = loop.close
		self.create_future = loop.create_future
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

	@property
	def _asyncio_child_watcher(self):
		"""
		In order to avoid accessing the internal _loop attribute, portage
		internals should use this property when possible.

		@rtype: asyncio.AbstractChildWatcher
		@return: the internal event loop's AbstractChildWatcher interface
		"""
		return self._loop._asyncio_child_watcher

	@property
	def _asyncio_wrapper(self):
		"""
		In order to avoid accessing the internal _loop attribute, portage
		internals should use this property when possible.

		@rtype: asyncio.AbstractEventLoop
		@return: the internal event loop's AbstractEventLoop interface
		"""
		return self


if hasattr(os, 'set_blocking'):
	def _set_nonblocking(fd):
		os.set_blocking(fd, False)
else:
	def _set_nonblocking(fd):
		flags = fcntl.fcntl(fd, fcntl.F_GETFL)
		flags = flags | os.O_NONBLOCK
		fcntl.fcntl(fd, fcntl.F_SETFL, flags)


class _PortageChildWatcher(AbstractChildWatcher):
	def __init__(self, loop):
		"""
		@type loop: EventLoop
		@param loop: an instance of portage's internal event loop
		"""
		self._loop = loop
		self._callbacks = {}

	def close(self):
		pass

	def __enter__(self):
		return self

	def __exit__(self, a, b, c):
		pass

	def _child_exit(self, pid, status, data):
		self._callbacks.pop(pid)
		callback, args = data
		callback(pid, self._compute_returncode(status), *args)

	def _compute_returncode(self, status):
		if os.WIFSIGNALED(status):
			return -os.WTERMSIG(status)
		if os.WIFEXITED(status):
			return os.WEXITSTATUS(status)
		return status

	def add_child_handler(self, pid, callback, *args):
		"""
		Register a new child handler.

		Arrange for callback(pid, returncode, *args) to be called when
		process 'pid' terminates. Specifying another callback for the same
		process replaces the previous handler.
		"""
		source_id = self._callbacks.get(pid)
		if source_id is not None:
			self._loop.source_remove(source_id)
		self._callbacks[pid] = self._loop.child_watch_add(
			pid, self._child_exit, data=(callback, args))

	def remove_child_handler(self, pid):
		"""
		Removes the handler for process 'pid'.

		The function returns True if the handler was successfully removed,
		False if there was nothing to remove.
		"""
		source_id = self._callbacks.pop(pid, None)
		if source_id is not None:
			return self._loop.source_remove(source_id)
		return False


class _PortageEventLoopPolicy(events.AbstractEventLoopPolicy):
	"""
	Implementation of asyncio.AbstractEventLoopPolicy based on portage's
	internal event loop. This supports running event loops in forks,
	which is not supported by the default asyncio event loop policy,
	see https://bugs.python.org/issue22087.
	"""
	def get_event_loop(self):
		"""
		Get the event loop for the current context.

		Returns an event loop object implementing the AbstractEventLoop
		interface.

		@rtype: asyncio.AbstractEventLoop (or compatible)
		@return: the current event loop policy
		"""
		return _global_event_loop()._asyncio_wrapper

	def get_child_watcher(self):
		"""Get the watcher for child processes."""
		return _global_event_loop()._asyncio_child_watcher


class _AsyncioEventLoopPolicy(_PortageEventLoopPolicy):
	"""
	A subclass of _PortageEventLoopPolicy which raises
	NotImplementedError if it is set as the real asyncio event loop
	policy, since this class is intended to *wrap* the real asyncio
	event loop policy.
	"""
	def _check_recursion(self):
		if _real_asyncio.get_event_loop_policy() is self:
			raise NotImplementedError('this class is only a wrapper')

	def get_event_loop(self):
		self._check_recursion()
		return super(_AsyncioEventLoopPolicy, self).get_event_loop()

	def get_child_watcher(self):
		self._check_recursion()
		return super(_AsyncioEventLoopPolicy, self).get_child_watcher()


DefaultEventLoopPolicy = _AsyncioEventLoopPolicy
