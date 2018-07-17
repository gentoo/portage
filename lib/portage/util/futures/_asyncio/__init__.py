# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ALL_COMPLETED',
	'FIRST_COMPLETED',
	'FIRST_EXCEPTION',
	'ensure_future',
	'CancelledError',
	'Future',
	'InvalidStateError',
	'TimeoutError',
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
	import asyncio as _real_asyncio
except ImportError:
	_real_asyncio = None

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures.unix_events:_PortageEventLoopPolicy',
)
from portage.util._eventloop.asyncio_event_loop import AsyncioEventLoop as _AsyncioEventLoop
from portage.util._eventloop.global_event_loop import (
	_asyncio_enabled,
	global_event_loop as _global_event_loop,
)
from portage.util.futures.futures import (
	CancelledError,
	Future,
	InvalidStateError,
	TimeoutError,
)
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
			_policy = _PortageEventLoopPolicy()
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
		_policy = policy or _PortageEventLoopPolicy()


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
	loop = _wrap_loop(loop)
	future = loop.create_future()
	handle = loop.call_later(delay, future.set_result, result)
	def cancel_callback(future):
		if future.cancelled():
			handle.cancel()
	future.add_done_callback(cancel_callback)
	return future


def _wrap_loop(loop=None):
	"""
	In order to deal with asyncio event loop compatibility issues,
	use this function to wrap the loop parameter for functions
	that support it. For example, since python3.4 does not have the
	AbstractEventLoop.create_future() method, this helper function
	can be used to add a wrapper that implements the create_future
	method for python3.4.

	@type loop: asyncio.AbstractEventLoop (or compatible)
	@param loop: event loop
	@rtype: asyncio.AbstractEventLoop (or compatible)
	@return: event loop
	"""
	return loop or _global_event_loop()


if _asyncio_enabled:
	# The default loop returned by _wrap_loop should be consistent
	# with global_event_loop, in order to avoid accidental registration
	# of callbacks with a loop that is not intended to run.

	def _wrap_loop(loop=None):
		loop = loop or _global_event_loop()
		return (loop if hasattr(loop, '_asyncio_wrapper')
			else _AsyncioEventLoop(loop=loop))
