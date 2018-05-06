# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import multiprocessing
import os

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.unix_events import DefaultEventLoopPolicy


def fork_main(parent_conn, child_conn):
	parent_conn.close()
	loop = asyncio._wrap_loop()
	# This fails with python's default event loop policy,
	# see https://bugs.python.org/issue22087.
	loop.run_until_complete(asyncio.sleep(0.1, loop=loop))
	loop.close()


def async_main(fork_exitcode, loop=None):
	loop = asyncio._wrap_loop(loop)

	# Since python2.7 does not support Process.sentinel, use Pipe to
	# monitor for process exit.
	parent_conn, child_conn = multiprocessing.Pipe()

	def eof_callback(proc):
		loop.remove_reader(parent_conn.fileno())
		parent_conn.close()
		proc.join()
		fork_exitcode.set_result(proc.exitcode)

	proc = multiprocessing.Process(target=fork_main, args=(parent_conn, child_conn))
	loop.add_reader(parent_conn.fileno(), eof_callback, proc)
	proc.start()
	child_conn.close()


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
