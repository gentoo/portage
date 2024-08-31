# Copyright 2018-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
    "ALL_COMPLETED",
    "FIRST_COMPLETED",
    "FIRST_EXCEPTION",
    "ensure_future",
    "CancelledError",
    "Future",
    "InvalidStateError",
    "Lock",
    "TimeoutError",
    "get_child_watcher",
    "get_event_loop",
    "set_child_watcher",
    "get_event_loop_policy",
    "set_event_loop_policy",
    "run",
    "shield",
    "sleep",
    "wait",
    "wait_for",
)

import sys
import types
import warnings
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
    iscoroutinefunction,
    Lock as _Lock,
    shield,
    TimeoutError,
    wait_for,
)

import threading
from typing import Optional

import portage

portage.proxy.lazyimport.lazyimport(
    globals(),
    "portage.util.futures.unix_events:_PortageEventLoopPolicy",
)
from portage.util._eventloop.asyncio_event_loop import (
    AsyncioEventLoop as _AsyncioEventLoop,
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


# Emulate run since it's the preferred python API.
def run(coro):
    return _safe_loop().run_until_complete(coro)


run.__doc__ = _real_asyncio.run.__doc__


def create_subprocess_exec(*args, loop=None, **kwargs):
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
    # Python 3.4 and later implement PEP 446, which makes newly
    # created file descriptors non-inheritable by default.
    kwargs.setdefault("close_fds", False)
    # Use the real asyncio create_subprocess_exec (loop argument
    # is deprecated since since Python 3.8).
    return ensure_future(
        _real_asyncio.create_subprocess_exec(*args, **kwargs), loop=loop
    )


def wait(futures, loop=None, timeout=None, return_when=ALL_COMPLETED):
    """
    Wraps asyncio.wait() and omits the loop argument which is not
    supported since python 3.10.
    """
    return _real_asyncio.wait(futures, timeout=timeout, return_when=return_when)


class Lock(_Lock):
    """
    Inject loop parameter for python3.9 or less in order to avoid
    "got Future <Future pending> attached to a different loop" errors.
    """

    def __init__(self, **kwargs):
        if sys.version_info >= (3, 10):
            kwargs.pop("loop", None)
        elif "loop" not in kwargs:
            kwargs["loop"] = _safe_loop()._loop
        super().__init__(**kwargs)


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
    if loop is None:
        return _real_asyncio.ensure_future(coro_or_future)

    loop = _wrap_loop(loop)
    if isinstance(loop._asyncio_wrapper, _AsyncioEventLoop):
        # Use the real asyncio loop and ensure_future.
        return _real_asyncio.ensure_future(
            coro_or_future, loop=loop._asyncio_wrapper._loop
        )

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
    @rtype: collections.abc.Coroutine or asyncio.Future
    @return: an instance of Coroutine or Future
    """
    if loop is None:
        return _real_asyncio.sleep(delay, result=result)

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
    if hasattr(loop, "_asyncio_wrapper"):
        return loop

    # This returns a running loop if it exists, and otherwise returns
    # a loop associated with the current thread.
    safe_loop = _safe_loop(create=loop is None)
    if safe_loop is not None and (loop is None or safe_loop._loop is loop):
        return safe_loop

    if safe_loop is None:
        msg = f"_wrap_loop argument '{loop}' not associated with thread '{threading.get_ident()}'"
    else:
        msg = f"_wrap_loop argument '{loop}' different frome loop '{safe_loop._loop}' already associated with thread '{threading.get_ident()}'"

    if portage._internal_caller:
        raise AssertionError(msg)

    # It's not known whether external API consumers will trigger this case,
    # so if it happens then emit a UserWarning before returning a temporary
    # AsyncioEventLoop instance.
    warnings.warn(msg, UserWarning, stacklevel=2)

    # We could possibly add a weak reference in _thread_weakrefs.loops when
    # safe_loop is None, but if safe_loop is not None, then there is a
    # collision in _thread_weakrefs.loops that would need to be resolved.
    return _AsyncioEventLoop(loop=loop)


def _safe_loop(create: Optional[bool] = True) -> Optional[_AsyncioEventLoop]:
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

    @type create: bool
    @param create: Create a loop by default if a loop is not already associated
        with the current thread. If create is False, then return None if a loop
        is not already associated with the current thread.
    @rtype: AsyncioEventLoop or None
    @return: event loop instance, or None if the create parameter is False and
        a loop is not already associated with the current thread.
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
            if loop.is_closed():
                # Discard wrapped asyncio.run loop that was closed.
                del _thread_weakrefs.loops[thread_key]
                if loop is _thread_weakrefs.mainloop:
                    _thread_weakrefs.mainloop = None
                loop = None
                raise KeyError(thread_key)
        except KeyError:
            if not create:
                return None
            try:
                try:
                    _loop = _real_asyncio.get_running_loop()
                except AttributeError:
                    _loop = _real_asyncio.get_event_loop()
            except RuntimeError:
                _loop = _real_asyncio.new_event_loop()
                _real_asyncio.set_event_loop(_loop)
            loop = _thread_weakrefs.loops[thread_key] = _AsyncioEventLoop(loop=_loop)

    if (
        _thread_weakrefs.mainloop is None
        and threading.current_thread() is threading.main_thread()
    ):
        _thread_weakrefs.mainloop = loop

    return loop


def _get_running_loop():
    """
    This calls the real asyncio get_running_loop() and wraps that with
    portage's internal AsyncioEventLoop wrapper. If there is no running
    asyncio event loop but portage has a reference to another running
    loop in this thread, then use that instead.

    This behavior enables portage internals to use the real asyncio.run
    while remaining compatible with internal code that does not use the
    real asyncio.run.
    """
    try:
        _loop = _real_asyncio.get_running_loop()
    except RuntimeError:
        _loop = None

    with _thread_weakrefs.lock:
        if _thread_weakrefs.pid == portage.getpid():
            try:
                loop = _thread_weakrefs.loops[threading.get_ident()]
            except KeyError:
                pass
            else:
                if _loop is loop._loop:
                    return loop
                elif _loop is None:
                    return loop if loop.is_running() else None

        if _loop is None:
            return None

        # If _loop it not None here it means it was probably a temporary
        # loop created by asyncio.run. Still keep a weak reference in case
        # we need to lookup this _AsyncioEventLoop instance later to add
        # _coroutine_exithandlers in the atexit_register function.
        if _thread_weakrefs.pid != portage.getpid():
            _thread_weakrefs.pid = portage.getpid()
            _thread_weakrefs.mainloop = None
            _thread_weakrefs.loops = weakref.WeakValueDictionary()

        loop = _thread_weakrefs.loops[threading.get_ident()] = _AsyncioEventLoop(
            loop=_loop
        )

        return loop


def _thread_weakrefs_atexit():
    while True:
        loop = None
        thread_key = None
        restore_loop = None
        with _thread_weakrefs.lock:
            if _thread_weakrefs.pid != portage.getpid():
                return

            try:
                thread_key, loop = _thread_weakrefs.loops.popitem()
            except KeyError:
                return
            else:
                # Temporarily associate it as the loop for the current thread so
                # that it can be looked up during run_coroutine_exitfuncs calls.
                # Also create a reference to a different loop if one is associated
                # with this thread so we can restore it later.
                try:
                    restore_loop = _thread_weakrefs.loops[threading.get_ident()]
                except KeyError:
                    pass
                _thread_weakrefs.loops[threading.get_ident()] = loop

        # Release the lock while closing the loop, since it may call
        # run_coroutine_exitfuncs interally.
        if loop is not None:
            loop.close()
            with _thread_weakrefs.lock:
                try:
                    if _thread_weakrefs.loops[threading.get_ident()] is loop:
                        del _thread_weakrefs.loops[threading.get_ident()]
                except KeyError:
                    pass
                if restore_loop is not None:
                    _thread_weakrefs.loops[threading.get_ident()] = restore_loop


_thread_weakrefs = types.SimpleNamespace(
    lock=threading.Lock(), loops=None, mainloop=None, pid=None
)
portage.process.atexit_register(_thread_weakrefs_atexit)
