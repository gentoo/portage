# Copyright 2018-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from concurrent.futures import Future, ThreadPoolExecutor
import contextlib
import sys

import threading

import weakref
import time

import pytest

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.backoff import RandomExponentialBackoff
from portage.util.futures import asyncio
from portage.util.futures.retry import retry
from portage.util.futures.executor.fork import ForkExecutor


class SucceedLaterException(Exception):
    pass


class SucceedLater:
    """
    A callable object that succeeds some duration of time has passed.
    """

    def __init__(self, duration):
        self._succeed_time = time.monotonic() + duration

    async def __call__(self):
        remaining = self._succeed_time - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)
        return "success"


class SucceedNeverException(Exception):
    pass


class SucceedNever:
    """
    A callable object that never succeeds.
    """

    async def __call__(self):
        raise SucceedNeverException("expected failure")


class HangForever:
    """
    A callable object that sleeps forever.
    """

    async def __call__(self):
        while True:
            await asyncio.sleep(9)


class RetryTestCase(TestCase):
    @contextlib.contextmanager
    def _wrap_coroutine_func(self, coroutine_func):
        """
        Derived classes may override this method in order to implement
        alternative forms of execution.
        """
        yield coroutine_func

    def testSucceedLater(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(SucceedLater(1)) as func_coroutine:
            decorator = retry(
                try_max=9999,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            result = loop.run_until_complete(decorated_func())
            self.assertEqual(result, "success")

    def testSucceedNever(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(SucceedNever()) as func_coroutine:
            decorator = retry(
                try_max=4,
                try_timeout=None,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            self.assertTrue(
                isinstance(done.pop().exception().__cause__, SucceedNeverException)
            )

    def testSucceedNeverReraise(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(SucceedNever()) as func_coroutine:
            decorator = retry(
                reraise=True,
                try_max=4,
                try_timeout=None,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            self.assertTrue(isinstance(done.pop().exception(), SucceedNeverException))

    @pytest.mark.skipif(
        sys.version_info >= (3, 14), reason="fails with python 3.14.0a3"
    )
    def testHangForever(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(HangForever()) as func_coroutine:
            decorator = retry(
                try_max=2,
                try_timeout=0.1,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            self.assertTrue(
                isinstance(done.pop().exception().__cause__, asyncio.TimeoutError)
            )

    @pytest.mark.skipif(
        sys.version_info >= (3, 14), reason="fails with python 3.14.0a3"
    )
    def testHangForeverReraise(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(HangForever()) as func_coroutine:
            decorator = retry(
                reraise=True,
                try_max=2,
                try_timeout=0.1,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            self.assertTrue(isinstance(done.pop().exception(), asyncio.TimeoutError))

    @pytest.mark.skipif(
        sys.version_info >= (3, 14), reason="fails with python 3.14.0a3"
    )
    def testCancelRetry(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(SucceedNever()) as func_coroutine:
            decorator = retry(
                try_timeout=0.1,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            future = decorated_func()
            loop.call_later(0.3, future.cancel)
            done, pending = loop.run_until_complete(asyncio.wait([future], loop=loop))
            self.assertEqual(len(done), 1)
            self.assertTrue(done.pop().cancelled())

    @pytest.mark.skipif(
        sys.version_info >= (3, 14), reason="fails with python 3.14.0a3"
    )
    def testOverallTimeoutWithException(self):
        loop = global_event_loop()
        with self._wrap_coroutine_func(SucceedNever()) as func_coroutine:
            decorator = retry(
                try_timeout=0.1,
                overall_timeout=0.3,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            cause = done.pop().exception().__cause__
            self.assertTrue(
                isinstance(
                    cause,
                    (asyncio.TimeoutError, SucceedNeverException),
                ),
                msg=f"Cause was {cause.__class__.__name__}",
            )

    @pytest.mark.skipif(
        sys.version_info >= (3, 14), reason="fails with python 3.14.0a3"
    )
    def testOverallTimeoutWithTimeoutError(self):
        loop = global_event_loop()
        # results in TimeoutError because it hangs forever
        with self._wrap_coroutine_func(HangForever()) as func_coroutine:
            decorator = retry(
                try_timeout=0.1,
                overall_timeout=0.3,
                delay_func=RandomExponentialBackoff(multiplier=0.1, base=2),
            )
            decorated_func = decorator(func_coroutine, loop=loop)
            done, pending = loop.run_until_complete(
                asyncio.wait([decorated_func()], loop=loop)
            )
            self.assertEqual(len(done), 1)
            self.assertTrue(
                isinstance(done.pop().exception().__cause__, asyncio.TimeoutError)
            )


class RetryForkExecutorTestCase(RetryTestCase):
    """
    Wrap each coroutine function with AbstractEventLoop.run_in_executor,
    in order to test the event loop's default executor. The executor
    may use either a thread or a subprocess, and either case is
    automatically detected and handled.
    """

    def __init__(self, *pargs, **kwargs):
        super().__init__(*pargs, **kwargs)
        self._executor = None

    def _setUpExecutor(self):
        self._executor = ForkExecutor()

    def _tearDownExecutor(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def setUp(self):
        super().setUp()
        self._setUpExecutor()

    def tearDown(self):
        self._tearDownExecutor()

    @contextlib.contextmanager
    def _wrap_coroutine_func(self, coroutine_func):
        uses_subprocess = isinstance(self._executor, ForkExecutor)
        parent_loop = global_event_loop()
        pending = weakref.WeakValueDictionary()

        # Since ThreadPoolExecutor does not propagate cancellation of a
        # parent_future to the underlying coroutine, use kill_switch to
        # propagate task cancellation to wrapper, so that HangForever's
        # thread returns when retry eventually cancels parent_future.
        if uses_subprocess:
            wrapper = _run_coroutine_in_subprocess(coroutine_func)
        else:

            def wrapper(kill_switch):
                # thread in main process
                def done_callback(result):
                    result.cancelled() or result.exception() or result.result()
                    kill_switch.set()

                def start_coroutine(future):
                    result = asyncio.ensure_future(coroutine_func(), loop=parent_loop)
                    pending[id(result)] = result
                    result.add_done_callback(done_callback)
                    future.set_result(result)

                future = Future()
                parent_loop.call_soon_threadsafe(start_coroutine, future)
                kill_switch.wait()
                if not future.done():
                    future.cancel()
                    raise asyncio.CancelledError
                elif not future.result().done():
                    future.result().cancel()
                    raise asyncio.CancelledError
                else:
                    return future.result().result()

        def execute_wrapper():
            # Use kill_switch for threads because they can't be killed
            # like processes. Do not pass kill_switch to subprocesses
            # because it is not picklable.
            kill_switch = None if uses_subprocess else threading.Event()
            wrapper_args = [kill_switch] if kill_switch else []
            parent_future = asyncio.ensure_future(
                parent_loop.run_in_executor(self._executor, wrapper, *wrapper_args),
                loop=parent_loop,
            )

            def kill_callback(parent_future):
                if kill_switch is not None and not kill_switch.is_set():
                    kill_switch.set()

            parent_future.add_done_callback(kill_callback)
            return parent_future

        try:
            yield execute_wrapper
        finally:
            while True:
                try:
                    _, future = pending.popitem()
                except KeyError:
                    break
                try:
                    parent_loop.run_until_complete(future)
                except (Exception, asyncio.CancelledError):
                    pass
                future.cancelled() or future.exception() or future.result()


class _run_coroutine_in_subprocess:
    def __init__(self, coroutine_func):
        self._coroutine_func = coroutine_func

    def __call__(self):
        # child process
        loop = global_event_loop()
        try:
            return loop.run_until_complete(self._coroutine_func())
        finally:
            loop.close()


class RetryThreadExecutorTestCase(RetryForkExecutorTestCase):
    def _setUpExecutor(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
