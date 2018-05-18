# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.unix_events import DefaultEventLoopPolicy


class RunUntilCompleteTestCase(TestCase):
	def test_add_done_callback(self):
		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())

		loop = None
		try:
			loop = asyncio._wrap_loop()
			f1 = loop.create_future()
			f2 = loop.create_future()
			f1.add_done_callback(f2.set_result)
			loop.call_soon(lambda: f1.set_result(None))
			loop.run_until_complete(f1)
			self.assertEqual(f1.done(), True)

			# This proves that done callbacks of f1 are executed before
			# loop.run_until_complete(f1) returns, which is how asyncio's
			# default event loop behaves.
			self.assertEqual(f2.done(), True)
		finally:
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())
