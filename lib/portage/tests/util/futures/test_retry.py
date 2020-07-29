# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from concurrent.futures import ThreadPoolExecutor

try:
	import threading
except ImportError:
	import dummy_threading as threading

import time

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

	def __call__(self):
		loop = global_event_loop()
		result = loop.create_future()
		remaining = self._succeed_time - time.monotonic()
		if remaining > 0:
			loop.call_soon_threadsafe(lambda: None if result.done() else
				result.set_exception(SucceedLaterException(
				'time until success: {} seconds'.format(remaining))))
		else:
			loop.call_soon_threadsafe(lambda: None if result.done() else
				result.set_result('success'))
		return result


class SucceedNeverException(Exception):
	pass


class SucceedNever:
	"""
	A callable object that never succeeds.
	"""
	def __call__(self):
		loop = global_event_loop()
		result = loop.create_future()
		loop.call_soon_threadsafe(lambda: None if result.done() else
			result.set_exception(SucceedNeverException('expected failure')))
		return result


class HangForever:
	"""
	A callable object that sleeps forever.
	"""
	def __call__(self):
		return global_event_loop().create_future()


class RetryTestCase(TestCase):

	def _wrap_coroutine_func(self, coroutine_func):
		"""
		Derived classes may override this method in order to implement
		alternative forms of execution.
		"""
		return coroutine_func

	def testSucceedLater(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(SucceedLater(1))
		decorator = retry(try_max=9999,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		result = loop.run_until_complete(decorated_func())
		self.assertEqual(result, 'success')

	def testSucceedNever(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(SucceedNever())
		decorator = retry(try_max=4, try_timeout=None,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception().__cause__, SucceedNeverException))

	def testSucceedNeverReraise(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(SucceedNever())
		decorator = retry(reraise=True, try_max=4, try_timeout=None,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception(), SucceedNeverException))

	def testHangForever(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(HangForever())
		decorator = retry(try_max=2, try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception().__cause__, asyncio.TimeoutError))

	def testHangForeverReraise(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(HangForever())
		decorator = retry(reraise=True, try_max=2, try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception(), asyncio.TimeoutError))

	def testCancelRetry(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(SucceedNever())
		decorator = retry(try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		future = decorated_func()
		loop.call_later(0.3, future.cancel)
		done, pending = loop.run_until_complete(asyncio.wait([future], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(done.pop().cancelled())

	def testOverallTimeoutWithException(self):
		loop = global_event_loop()
		func_coroutine = self._wrap_coroutine_func(SucceedNever())
		decorator = retry(try_timeout=0.1, overall_timeout=0.3,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception().__cause__, SucceedNeverException))

	def testOverallTimeoutWithTimeoutError(self):
		loop = global_event_loop()
		# results in TimeoutError because it hangs forever
		func_coroutine = self._wrap_coroutine_func(HangForever())
		decorator = retry(try_timeout=0.1, overall_timeout=0.3,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine, loop=loop)
		done, pending = loop.run_until_complete(asyncio.wait([decorated_func()], loop=loop))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done.pop().exception().__cause__, asyncio.TimeoutError))


class RetryForkExecutorTestCase(RetryTestCase):
	"""
	Wrap each coroutine function with AbstractEventLoop.run_in_executor,
	in order to test the event loop's default executor. The executor
	may use either a thread or a subprocess, and either case is
	automatically detected and handled.
	"""
	def __init__(self, *pargs, **kwargs):
		super(RetryForkExecutorTestCase, self).__init__(*pargs, **kwargs)
		self._executor = None

	def _setUpExecutor(self):
		self._executor = ForkExecutor()

	def _tearDownExecutor(self):
		if self._executor is not None:
			self._executor.shutdown(wait=True)
			self._executor = None

	def setUp(self):
		self._setUpExecutor()

	def tearDown(self):
		self._tearDownExecutor()

	def _wrap_coroutine_func(self, coroutine_func):
		parent_loop = global_event_loop()

		# Since ThreadPoolExecutor does not propagate cancellation of a
		# parent_future to the underlying coroutine, use kill_switch to
		# propagate task cancellation to wrapper, so that HangForever's
		# thread returns when retry eventually cancels parent_future.
		def wrapper(kill_switch):
			loop = global_event_loop()
			if loop is parent_loop:
				# thread in main process
				result = coroutine_func()
				event = threading.Event()
				loop.call_soon_threadsafe(result.add_done_callback,
					lambda result: event.set())
				loop.call_soon_threadsafe(kill_switch.add_done_callback,
					lambda kill_switch: event.set())
				event.wait()
				return result.result()

			# child process
			try:
				return loop.run_until_complete(coroutine_func())
			finally:
				loop.close()

		def execute_wrapper():
			kill_switch = parent_loop.create_future()
			parent_future = asyncio.ensure_future(
				parent_loop.run_in_executor(self._executor, wrapper, kill_switch),
				loop=parent_loop)
			parent_future.add_done_callback(
				lambda parent_future: None if kill_switch.done()
				else kill_switch.set_result(None))
			return parent_future

		return execute_wrapper


class RetryThreadExecutorTestCase(RetryForkExecutorTestCase):
	def _setUpExecutor(self):
		self._executor = ThreadPoolExecutor(max_workers=1)
