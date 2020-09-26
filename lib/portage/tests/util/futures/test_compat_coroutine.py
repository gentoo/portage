# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import (
	coroutine,
	coroutine_return,
)
from portage.util.futures._sync_decorator import _sync_decorator, _sync_methods
from portage.tests import TestCase


class CompatCoroutineTestCase(TestCase):

	def test_returning_coroutine(self):
		@coroutine
		def returning_coroutine(loop=None):
			yield asyncio.sleep(0, loop=loop)
			coroutine_return('success')

		loop = asyncio.get_event_loop()
		self.assertEqual('success',
			asyncio.get_event_loop().run_until_complete(returning_coroutine(loop=loop)))

	def test_raising_coroutine(self):

		class TestException(Exception):
			pass

		@coroutine
		def raising_coroutine(loop=None):
			yield asyncio.sleep(0, loop=loop)
			raise TestException('exception')

		loop = asyncio.get_event_loop()
		self.assertRaises(TestException,
			loop.run_until_complete, raising_coroutine(loop=loop))

	def test_catching_coroutine(self):

		class TestException(Exception):
			pass

		@coroutine
		def catching_coroutine(loop=None):
			loop = asyncio._wrap_loop(loop)
			future = loop.create_future()
			loop.call_soon(future.set_exception, TestException('exception'))
			try:
				yield future
			except TestException:
				self.assertTrue(True)
			else:
				self.assertTrue(False)
			coroutine_return('success')

		loop = asyncio.get_event_loop()
		self.assertEqual('success',
			loop.run_until_complete(catching_coroutine(loop=loop)))

	def test_cancelled_coroutine(self):
		"""
		Verify that a coroutine can handle (and reraise) asyncio.CancelledError
		in order to perform any necessary cleanup. Note that the
		asyncio.CancelledError will only be thrown in the coroutine if there's
		an opportunity (yield) before the generator raises StopIteration.
		"""
		loop = asyncio.get_event_loop()
		ready_for_exception = loop.create_future()
		exception_in_coroutine = loop.create_future()

		@coroutine
		def cancelled_coroutine(loop=None):
			loop = asyncio._wrap_loop(loop)
			while True:
				task = loop.create_future()
				try:
					ready_for_exception.set_result(None)
					yield task
				except BaseException as e:
					# Since python3.8, asyncio.CancelledError inherits
					# from BaseException.
					task.done() or task.cancel()
					exception_in_coroutine.set_exception(e)
					raise
				else:
					exception_in_coroutine.set_result(None)

		future = cancelled_coroutine(loop=loop)
		loop.run_until_complete(ready_for_exception)
		future.cancel()

		self.assertRaises(asyncio.CancelledError,
			loop.run_until_complete, future)

		self.assertRaises(asyncio.CancelledError,
			loop.run_until_complete, exception_in_coroutine)

	def test_cancelled_future(self):
		"""
		When a coroutine raises CancelledError, the coroutine's
		future is cancelled.
		"""

		@coroutine
		def cancelled_future_coroutine(loop=None):
			loop = asyncio._wrap_loop(loop)
			while True:
				future = loop.create_future()
				loop.call_soon(future.cancel)
				yield future

		loop = asyncio.get_event_loop()
		future = loop.run_until_complete(asyncio.wait([cancelled_future_coroutine(loop=loop)], loop=loop))[0].pop()
		self.assertTrue(future.cancelled())

	def test_yield_expression_result(self):
		@coroutine
		def yield_expression_coroutine(loop=None):
			for i in range(3):
				x = yield asyncio.sleep(0, result=i, loop=loop)
				self.assertEqual(x, i)

		loop = asyncio.get_event_loop()
		loop.run_until_complete(yield_expression_coroutine(loop=loop))

	def test_method_coroutine(self):

		class Cubby:

			_empty = object()

			def __init__(self, loop):
				self._loop = loop
				self._value = self._empty
				self._waiters = []

			def _notify(self):
				waiters = self._waiters
				self._waiters = []
				for waiter in waiters:
					waiter.cancelled() or waiter.set_result(None)

			def _wait(self):
				waiter = self._loop.create_future()
				self._waiters.append(waiter)
				return waiter

			@coroutine
			def read(self, loop=None):
				while self._value is self._empty:
					yield self._wait()

				value = self._value
				self._value = self._empty
				self._notify()
				coroutine_return(value)

			@coroutine
			def write(self, value, loop=None):
				while self._value is not self._empty:
					yield self._wait()

				self._value = value
				self._notify()

		@coroutine
		def writer_coroutine(cubby, values, sentinel, loop=None):
			for value in values:
				yield cubby.write(value, loop=loop)
			yield cubby.write(sentinel, loop=loop)

		@coroutine
		def reader_coroutine(cubby, sentinel, loop=None):
			results = []
			while True:
				result = yield cubby.read(loop=loop)
				if result == sentinel:
					break
				results.append(result)
			coroutine_return(results)

		loop = asyncio.get_event_loop()
		cubby = Cubby(loop)
		values = list(range(3))
		writer = asyncio.ensure_future(writer_coroutine(cubby, values, None, loop=loop), loop=loop)
		reader = asyncio.ensure_future(reader_coroutine(cubby, None, loop=loop), loop=loop)
		loop.run_until_complete(asyncio.wait([writer, reader], loop=loop))

		self.assertEqual(reader.result(), values)

		# Test decoration of coroutine methods and functions for
		# synchronous usage, allowing coroutines to smoothly
		# blend with synchronous code.
		sync_cubby = _sync_methods(cubby, loop=loop)
		sync_reader = _sync_decorator(reader_coroutine, loop=loop)
		writer = asyncio.ensure_future(writer_coroutine(cubby, values, None, loop=loop), loop=loop)
		self.assertEqual(sync_reader(cubby, None), values)
		self.assertTrue(writer.done())

		for i in range(3):
			sync_cubby.write(i)
			self.assertEqual(sync_cubby.read(), i)
