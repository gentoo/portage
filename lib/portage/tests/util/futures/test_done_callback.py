# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop


class FutureDoneCallbackTestCase(TestCase):

	def testFutureDoneCallback(self):

		event_loop = global_event_loop()

		def done_callback(finished):
			done_callback_called.set_result(True)

		done_callback_called = event_loop.create_future()
		finished = event_loop.create_future()
		finished.add_done_callback(done_callback)
		event_loop.call_soon(finished.set_result, True)
		event_loop.run_until_complete(done_callback_called)

		def done_callback2(finished):
			done_callback2_called.set_result(True)

		done_callback_called = event_loop.create_future()
		done_callback2_called = event_loop.create_future()
		finished = event_loop.create_future()
		finished.add_done_callback(done_callback)
		finished.add_done_callback(done_callback2)
		finished.remove_done_callback(done_callback)
		event_loop.call_soon(finished.set_result, True)
		event_loop.run_until_complete(done_callback2_called)

		self.assertFalse(done_callback_called.done())
