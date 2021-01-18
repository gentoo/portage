# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage.process import find_binary, spawn
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.unix_events import DefaultEventLoopPolicy


class ChildWatcherTestCase(TestCase):
	def testChildWatcher(self):
		true_binary = find_binary("true")
		self.assertNotEqual(true_binary, None)

		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())

		loop = None
		try:
			try:
				asyncio.set_child_watcher(None)
			except NotImplementedError:
				pass
			else:
				self.assertTrue(False)

			args_tuple = ('hello', 'world')

			loop = asyncio._wrap_loop()
			future = loop.create_future()

			def callback(pid, returncode, *args):
				future.set_result((pid, returncode, args))

			async def watch_pid():

				with asyncio.get_child_watcher() as watcher:
					pids = spawn([true_binary], returnpid=True)
					watcher.add_child_handler(pids[0], callback, *args_tuple)
					self.assertEqual(
						(await future),
						(pids[0], os.EX_OK, args_tuple))

			loop.run_until_complete(watch_pid())
		finally:
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())
