# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.unix_events import DefaultEventLoopPolicy


def fork_main():
	loop = asyncio._wrap_loop()
	# This fails with python's default event loop policy,
	# see https://bugs.python.org/issue22087.
	loop.run_until_complete(asyncio.sleep(0.1, loop=loop))
	loop.close()


def async_main(fork_exitcode, loop=None):
	loop = asyncio._wrap_loop(loop)
	proc = AsyncFunction(scheduler=loop, target=fork_main)
	proc.start()
	proc.async_wait().add_done_callback(lambda future: fork_exitcode.set_result(future.result()))


class EventLoopInForkTestCase(TestCase):
	"""
	The default asyncio event loop policy does not support loops
	running in forks, see https://bugs.python.org/issue22087.
	Portage's DefaultEventLoopPolicy supports forks.
	"""

	def testEventLoopInForkTestCase(self):
		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())
		loop = None
		try:
			loop = asyncio._wrap_loop()
			fork_exitcode = loop.create_future()
			# Make async_main fork while the loop is running, which would
			# trigger https://bugs.python.org/issue22087 with asyncio's
			# default event loop policy.
			loop.call_soon(async_main, fork_exitcode)
			assert loop.run_until_complete(fork_exitcode) == os.EX_OK
		finally:
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())
