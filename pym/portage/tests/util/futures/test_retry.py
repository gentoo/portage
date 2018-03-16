# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import functools

try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.backoff import RandomExponentialBackoff
from portage.util.futures.futures import TimeoutError
from portage.util.futures.retry import retry
from portage.util.futures.wait import wait
from portage.util.monotonic import monotonic


class SucceedLaterException(Exception):
	pass


class SucceedLater(object):
	"""
	A callable object that succeeds some duration of time has passed.
	"""
	def __init__(self, duration):
		self._succeed_time = monotonic() + duration

	def __call__(self):
		remaining = self._succeed_time - monotonic()
		if remaining > 0:
			raise SucceedLaterException('time until success: {} seconds'.format(remaining))
		return 'success'


class SucceedNeverException(Exception):
	pass


class SucceedNever(object):
	"""
	A callable object that never succeeds.
	"""
	def __call__(self):
		raise SucceedNeverException('expected failure')


class HangForever(object):
	"""
	A callable object that sleeps forever.
	"""
	def __call__(self):
		threading.Event().wait()


class RetryTestCase(TestCase):
	def testSucceedLater(self):
		loop = global_event_loop()
		func = SucceedLater(1)
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_max=9999,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		result = loop.run_until_complete(decorated_func())
		self.assertEqual(result, 'success')

	def testSucceedNever(self):
		loop = global_event_loop()
		func = SucceedNever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_max=4, try_timeout=None,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception().__cause__, SucceedNeverException))

	def testSucceedNeverReraise(self):
		loop = global_event_loop()
		func = SucceedNever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(reraise=True, try_max=4, try_timeout=None,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception(), SucceedNeverException))

	def testHangForever(self):
		loop = global_event_loop()
		func = HangForever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_max=2, try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception().__cause__, TimeoutError))

	def testHangForeverReraise(self):
		loop = global_event_loop()
		func = HangForever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(reraise=True, try_max=2, try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception(), TimeoutError))

	def testCancelRetry(self):
		loop = global_event_loop()
		func = SucceedNever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_timeout=0.1,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		future = decorated_func()
		loop.call_later(0.3, future.cancel)
		done, pending = loop.run_until_complete(wait([future]))
		self.assertEqual(len(done), 1)
		self.assertTrue(done[0].cancelled())

	def testOverallTimeoutWithException(self):
		loop = global_event_loop()
		func = SucceedNever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_timeout=0.1, overall_timeout=0.3,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception().__cause__, SucceedNeverException))

	def testOverallTimeoutWithTimeoutError(self):
		loop = global_event_loop()
		# results in TimeoutError because it hangs forever
		func = HangForever()
		func_coroutine = functools.partial(loop.run_in_executor, None, func)
		decorator = retry(try_timeout=0.1, overall_timeout=0.3,
			delay_func=RandomExponentialBackoff(multiplier=0.1, base=2))
		decorated_func = decorator(func_coroutine)
		done, pending = loop.run_until_complete(wait([decorated_func()]))
		self.assertEqual(len(done), 1)
		self.assertTrue(isinstance(done[0].exception().__cause__, TimeoutError))
