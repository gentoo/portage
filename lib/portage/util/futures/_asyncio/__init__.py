# Copyright 2018-2021 Gentoo Authors
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
import types
import weakref

import asyncio as _real_asyncio
# pylint: disable=redefined-builtin
from asyncio import (
	ALL_COMPLETED,
	CancelledError,
	FIRST_COMPLETED,
	FIRST_EXCEPTION,
	Future,
	InvalidStateError,
	TimeoutError,
)

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util.futures.unix_events:_PortageEventLoopPolicy',
	'portage.util.futures:compat_coroutine@_compat_coroutine',
)
from portage.util._eventloop.asyncio_event_loop import AsyncioEventLoop as _AsyncioEventLoop


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
	@rtype: asyncio.subprocess.Process (or compatible)
	@return: asyncio.subprocess.Process interface
	"""
	loop = _wrap_loop(kwargs.pop('loop', None))
	# Python 3.4 and later implement PEP 446, which makes newly
	# created file descriptors non-inheritable by default.
	kwargs.setdefault('close_fds', False)
	# Use the real asyncio create_subprocess_exec (loop argument
	# is deprecated since since Python 3.8).
	return ensure_future(_real_asyncio.create_subprocess_exec(*args, **kwargs), loop=loop)


def wait(futures, loop=None, timeout=None, return_when=ALL_COMPLETED):
	"""
	Wraps asyncio.wait() and omits the loop argument which is not
	supported since python 3.10.
	"""
	return _real_asyncio.wait(futures, timeout=timeout, return_when=return_when)


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
	loop = loop or _safe_loop()
	return (loop if hasattr(loop, '_asyncio_wrapper')
		else _AsyncioEventLoop(loop=loop))


def _safe_loop():
	"""
	Return an event loop that's safe to use within the current context.
	For portage internal callers or external API consumers calling from
	the main thread, this returns a globally shared event loop instance.

	For external API consumers calling from a non-main thread, an
	asyncio loop must be registered for the current thread, or else the
	asyncio.get_event_loop() function will raise an error like this:

	  RuntimeError: There is no current event loop in thread 'Thread-1'.

	In order to avoid this RuntimeError, a loop will be automatically
	created like this:

	  asyncio.set_event_loop(asyncio.new_event_loop())

	In order to avoid a ResourceWarning, automatically created loops
	are added to a WeakValueDictionary, and closed via an atexit hook
	if they still exist during exit for the current pid.

	@rtype: asyncio.AbstractEventLoop (or compatible)
	@return: event loop instance
	"""
	loop = _get_running_loop()
	if loop is not None:
		return loop

	thread_key = threading.get_ident()
	with _thread_weakrefs.lock:
		if _thread_weakrefs.pid != portage.getpid():
			_thread_weakrefs.pid = portage.getpid()
			_thread_weakrefs.mainloop = None
			_thread_weakrefs.loops = weakref.WeakValueDictionary()
		try:
			loop = _thread_weakrefs.loops[thread_key]
		except KeyError:
			try:
				_real_asyncio.get_event_loop()
			except RuntimeError:
				_real_asyncio.set_event_loop(_real_asyncio.new_event_loop())
			loop = _thread_weakrefs.loops[thread_key] = _AsyncioEventLoop()

	if _thread_weakrefs.mainloop is None and threading.current_thread() is threading.main_thread():
		_thread_weakrefs.mainloop = loop

	return loop


def _get_running_loop():
	with _thread_weakrefs.lock:
		if _thread_weakrefs.pid == portage.getpid():
			try:
				loop = _thread_weakrefs.loops[threading.get_ident()]
			except KeyError:
				return None
			return loop if loop.is_running() else None


def _thread_weakrefs_atexit():
	with _thread_weakrefs.lock:
		if _thread_weakrefs.pid == portage.getpid():
			while True:
				try:
					thread_key, loop = _thread_weakrefs.loops.popitem()
				except KeyError:
					break
				else:
					loop.close()

_thread_weakrefs = types.SimpleNamespace(lock=threading.Lock(), loops=None, mainloop=None, pid=None)
portage.process.atexit_register(_thread_weakrefs_atexit)
