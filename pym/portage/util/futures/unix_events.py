# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'DefaultEventLoopPolicy',
)

from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)
from portage.util.futures import (
	asyncio,
	events,
)
from portage.util.futures.futures import Future


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
		self.call_soon = loop.call_soon
		self.call_soon_threadsafe = loop.call_soon_threadsafe
		self.call_later = loop.call_later
		self.call_at = loop.call_at
		self.is_closed = loop.is_closed
		self.close = loop.close
		self.create_future = loop.create_future
		self.add_reader = loop.add_reader
		self.remove_reader = loop.remove_reader
		self.add_writer = loop.add_writer
		self.remove_writer = loop.remove_writer
		self.run_in_executor = loop.run_in_executor
		self.time = loop.time
		self.set_debug = loop.set_debug
		self.get_debug = loop.get_debug

	def run_until_complete(self, future):
		"""
		Run the event loop until a Future is done.

		@type future: asyncio.Future
		@param future: a Future to wait for
		@rtype: object
		@return: the Future's result
		@raise: the Future's exception
		"""
		return self._loop.run_until_complete(
			asyncio.ensure_future(future, loop=self))

	def create_task(self, coro):
		"""
		Schedule a coroutine object.

		@type coro: coroutine
		@param coro: a coroutine to schedule
		@rtype: asyncio.Task
		@return: a task object
		"""
		return asyncio.Task(coro, loop=self)


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


DefaultEventLoopPolicy = _PortageEventLoopPolicy
