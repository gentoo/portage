# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ALL_COMPLETED',
	'FIRST_COMPLETED',
	'FIRST_EXCEPTION',
	'ensure_future',
	'get_child_watcher',
	'get_event_loop',
	'set_child_watcher',
	'get_event_loop_policy',
	'set_event_loop_policy',
	'sleep',
	'Task',
	'wait',
)

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures.unix_events:DefaultEventLoopPolicy',
)
from portage.util.futures.futures import Future
from portage.util.futures._asyncio.tasks import (
	ALL_COMPLETED,
	FIRST_COMPLETED,
	FIRST_EXCEPTION,
	wait,
)


_lock = threading.Lock()
_policy = None


def get_event_loop_policy():
	"""
	Get the current event loop policy.

	@rtype: asyncio.AbstractEventLoopPolicy (or compatible)
	@return: the current event loop policy
	"""
	global _lock, _policy
	with _lock:
		if _policy is None:
			_policy = DefaultEventLoopPolicy()
		return _policy


def set_event_loop_policy(policy):
	"""
	Set the current event loop policy. If policy is None, the default
	policy is restored.

	@type policy: asyncio.AbstractEventLoopPolicy or None
	@param policy: new event loop policy
	"""
	global _lock, _policy
	with _lock:
		_policy = policy or DefaultEventLoopPolicy()


def get_event_loop():
	"""
	Equivalent to calling get_event_loop_policy().get_event_loop().

	@rtype: asyncio.AbstractEventLoop (or compatible)
	@return: the event loop for the current context
	"""
	return get_event_loop_policy().get_event_loop()


def get_child_watcher():
    """Equivalent to calling get_event_loop_policy().get_child_watcher()."""
    return get_event_loop_policy().get_child_watcher()


def set_child_watcher(watcher):
    """Equivalent to calling
    get_event_loop_policy().set_child_watcher(watcher)."""
    return get_event_loop_policy().set_child_watcher(watcher)


class Task(Future):
	"""
	Schedule the execution of a coroutine: wrap it in a future. A task
	is a subclass of Future.
	"""
	def __init__(self, coro, loop=None):
		raise NotImplementedError


def ensure_future(coro_or_future, loop=None):
	"""
	Wrap a coroutine or an awaitable in a future.

	If the argument is a Future, it is returned directly.

	@type coro_or_future: coroutine or Future
	@param coro_or_future: coroutine or future to wrap
	@type loop: asyncio.AbstractEventLoop (or compatible)
	@param loop: event loop
	@rtype: asyncio.Future (or compatible)
	@return: an instance of Future
	"""
	if isinstance(coro_or_future, Future):
		return coro_or_future
	raise NotImplementedError


def sleep(delay, result=None, loop=None):
	"""
	Create a future that completes after a given time (in seconds). If
	result is provided, it is produced to the caller when the future
	completes.

	@type delay: int or float
	@param delay: delay seconds
	@type result: object
	@param result: result of the future
	@type loop: asyncio.AbstractEventLoop (or compatible)
	@param loop: event loop
	@rtype: asyncio.Future (or compatible)
	@return: an instance of Future
	"""
	loop = loop or get_event_loop()
	future = loop.create_future()
	handle = loop.call_later(delay, future.set_result, result)
	def cancel_callback(future):
		if future.cancelled():
			handle.cancel()
	future.add_done_callback(cancel_callback)
	return future
