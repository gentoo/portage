# Copyright 2018-2020 Gentoo Authors
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

import subprocess
import sys

import asyncio as _real_asyncio

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures.unix_events:_PortageEventLoopPolicy',
	'portage.util.futures:compat_coroutine@_compat_coroutine',
	'portage.util._eventloop.EventLoop:EventLoop@_EventLoop',
)
from portage.util._eventloop.asyncio_event_loop import AsyncioEventLoop as _AsyncioEventLoop
from portage.util._eventloop.global_event_loop import (
	global_event_loop as _global_event_loop,
)
# pylint: disable=redefined-builtin
from portage.util.futures.futures import (
	CancelledError,
	Future,
	InvalidStateError,
	TimeoutError,
)
# pylint: enable=redefined-builtin
from portage.util.futures._asyncio.process import _Process
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


def create_subprocess_exec(*args, **kwargs):
	"""
	Create a subprocess.

	@param args: program and arguments
	@type args: str
	@param stdin: stdin file descriptor
	@type stdin: file or int
	@param stdout: stdout file descriptor
	@type stdout: file or int
	@param stderr: stderr file descriptor
	@type stderr: file or int
	@param close_fds: close file descriptors
	@type close_fds: bool
	@param loop: asyncio.AbstractEventLoop (or compatible)
	@type loop: event loop
	@type kwargs: varies
	@param kwargs: subprocess.Popen parameters
	@rtype: asyncio.Future (or compatible)
	@return: subset of asyncio.subprocess.Process interface
	"""
	loop = _wrap_loop(kwargs.pop('loop', None))
	# Python 3.4 and later implement PEP 446, which makes newly
	# created file descriptors non-inheritable by default.
	kwargs.setdefault('close_fds', False)
	if isinstance(loop._asyncio_wrapper, _AsyncioEventLoop):
		# Use the real asyncio create_subprocess_exec (loop argument
		# is deprecated since since Python 3.8).
		return _real_asyncio.create_subprocess_exec(*args, **kwargs)

	result = loop.create_future()

	result.set_result(_Process(subprocess.Popen(
		args,
		stdin=kwargs.pop('stdin', None),
		stdout=kwargs.pop('stdout', None),
		stderr=kwargs.pop('stderr', None), **kwargs), loop))

	return result


def iscoroutinefunction(func):
	"""
	Return True if func is a decorated coroutine function,
	supporting both asyncio.coroutine and compat_coroutine since
	their behavior is identical for all practical purposes.
	"""
	if _compat_coroutine._iscoroutinefunction(func):
		return True
	if _real_asyncio.iscoroutinefunction(func):
		return True
	return False


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
	loop = _wrap_loop(loop)
	if isinstance(loop._asyncio_wrapper, _AsyncioEventLoop):
		# Use the real asyncio loop and ensure_future.
		return _real_asyncio.ensure_future(
			coro_or_future, loop=loop._asyncio_wrapper._loop)

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
	# The default loop returned by _wrap_loop should be consistent
	# with global_event_loop, in order to avoid accidental registration
	# of callbacks with a loop that is not intended to run.
	loop = loop or _global_event_loop()
	return (loop if hasattr(loop, '_asyncio_wrapper')
		else _AsyncioEventLoop(loop=loop))


def _safe_loop():
	"""
	Return an event loop that's safe to use within the current context.
	For portage internal callers, this returns a globally shared event
	loop instance. For external API consumers, this constructs a
	temporary event loop instance that's safe to use in a non-main
	thread (it does not override the global SIGCHLD handler).

	@rtype: asyncio.AbstractEventLoop (or compatible)
	@return: event loop instance
	"""
	if portage._internal_caller:
		return _global_event_loop()
	return _EventLoop(main=False)
