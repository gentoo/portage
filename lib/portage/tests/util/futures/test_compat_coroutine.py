# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import (
	coroutine,
	coroutine_return,
)
from portage.tests import TestCase


class CompatCoroutineTestCase(TestCase):

	def test_returning_coroutine(self):
		@coroutine
		def returning_coroutine():
			yield asyncio.sleep(0)
			coroutine_return('success')

		self.assertEqual('success',
			asyncio.get_event_loop().run_until_complete(returning_coroutine()))

	def test_raising_coroutine(self):

		class TestException(Exception):
			pass

		@coroutine
		def raising_coroutine():
			yield asyncio.sleep(0)
			raise TestException('exception')

		self.assertRaises(TestException,
			asyncio.get_event_loop().run_until_complete, raising_coroutine())

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

		@coroutine
		def cancelled_coroutine(loop=None):
			loop = asyncio._wrap_loop(loop)
			while True:
				yield loop.create_future()

		loop = asyncio.get_event_loop()
		future = cancelled_coroutine(loop=loop)
		loop.call_soon(future.cancel)

		self.assertRaises(asyncio.CancelledError,
			loop.run_until_complete, future)

	def test_cancelled_future(self):

		@coroutine
		def cancelled_future_coroutine(loop=None):
			loop = asyncio._wrap_loop(loop)
			while True:
				future = loop.create_future()
				loop.call_soon(future.cancel)
				yield future

		loop = asyncio.get_event_loop()
		self.assertRaises(asyncio.CancelledError,
			loop.run_until_complete, cancelled_future_coroutine(loop=loop))

	def test_yield_expression_result(self):
		@coroutine
		def yield_expression_coroutine():
			for i in range(3):
				x = yield asyncio.sleep(0, result=i)
				self.assertEqual(x, i)

		asyncio.get_event_loop().run_until_complete(yield_expression_coroutine())

	def test_method_coroutine(self):

		class Cubby(object):

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
			def read(self):
				while self._value is self._empty:
					yield self._wait()

				value = self._value
				self._value = self._empty
				self._notify()
				coroutine_return(value)

			@coroutine
			def write(self, value):
				while self._value is not self._empty:
					yield self._wait()

				self._value = value
				self._notify()

		@coroutine
		def writer_coroutine(cubby, values, sentinel):
			for value in values:
				yield cubby.write(value)
			yield cubby.write(sentinel)

		@coroutine
		def reader_coroutine(cubby, sentinel):
			results = []
			while True:
				result = yield cubby.read()
				if result == sentinel:
					break
				results.append(result)
			coroutine_return(results)

		loop = asyncio.get_event_loop()
		cubby = Cubby(loop)
		values = list(range(3))
		writer = asyncio.ensure_future(writer_coroutine(cubby, values, None), loop=loop)
		reader = asyncio.ensure_future(reader_coroutine(cubby, None), loop=loop)
		loop.run_until_complete(asyncio.wait([writer, reader]))

		self.assertEqual(reader.result(), values)
