# Copyright 2020 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousTask import AsynchronousTask
from portage.tests import TestCase
from portage.util.futures import asyncio


class DoneCallbackAfterExitTestCase(TestCase):

	def test_done_callback_after_exit(self):
		"""
		Test that callbacks can be registered via the Future
		add_done_callback method even after the future is done, and
		verify that the callbacks are called.
		"""
		loop = asyncio._wrap_loop()
		future = loop.create_future()
		future.set_result(None)

		for i in range(3):
			event = loop.create_future()
			future.add_done_callback(lambda future: event.set_result(None))
			loop.run_until_complete(event)

	def test_exit_listener_after_exit(self):
		"""
		Test that callbacks can be registered via the AsynchronousTask
		addExitListener method even after the task is done, and
		verify that the callbacks are called.
		"""
		loop = asyncio._wrap_loop()
		task = AsynchronousTask(scheduler=loop)
		task.start()
		loop.run_until_complete(task.async_wait())

		for i in range(3):
			event = loop.create_future()
			task.addStartListener(lambda task: event.set_result(None))
			loop.run_until_complete(event)

			event = loop.create_future()
			task.addExitListener(lambda task: event.set_result(None))
			loop.run_until_complete(event)
