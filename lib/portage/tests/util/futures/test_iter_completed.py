# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import time
from portage.tests import TestCase
from portage.util._async.ForkProcess import ForkProcess
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.iter_completed import (
	iter_completed,
	async_iter_completed,
)


class SleepProcess(ForkProcess):
	__slots__ = ('future', 'seconds')
	def _start(self):
		self.addExitListener(self._future_done)
		ForkProcess._start(self)

	def _future_done(self, task):
		if not self.future.cancelled():
			self.future.set_result(self.seconds)

	def _run(self):
		time.sleep(self.seconds)


class IterCompletedTestCase(TestCase):

	def testIterCompleted(self):

		# Mark this as todo, since we don't want to fail if heavy system
		# load causes the tasks to finish in an unexpected order.
		self.todo = True

		loop = global_event_loop()
		tasks = [
			SleepProcess(seconds=0.200),
			SleepProcess(seconds=0.100),
			SleepProcess(seconds=0.001),
		]

		expected_order = sorted(task.seconds for task in tasks)

		def future_generator():
			for task in tasks:
				task.future = loop.create_future()
				task.scheduler = loop
				task.start()
				yield task.future

		for seconds, future in zip(expected_order, iter_completed(future_generator(),
			max_jobs=True, max_load=None, loop=loop)):
			self.assertEqual(seconds, future.result())

	def testAsyncCancel(self):

		loop = global_event_loop()
		input_futures = set()
		future_count = 3

		def future_generator():
			for i in range(future_count):
				future = loop.create_future()
				loop.call_soon(lambda future: None if future.done()
					else future.set_result(None), future)
				input_futures.add(future)
				yield future

		for future_done_set in async_iter_completed(future_generator(),
			max_jobs=True, max_load=True, loop=loop):
			future_done_set.cancel()
			break

		# With max_jobs=True, async_iter_completed should have executed
		# the generator until it raised StopIteration.
		self.assertEqual(future_count, len(input_futures))

		loop.run_until_complete(asyncio.wait(input_futures, loop=loop))

		# The futures may have results or they may have been cancelled
		# by TaskScheduler, and behavior varies depending on the python
		# interpreter.
		for future in input_futures:
			future.cancelled() or future.result()
