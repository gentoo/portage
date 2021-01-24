# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys

import portage
from portage import os
from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _writer
from portage.util.futures.unix_events import _set_nonblocking


class AsyncFunctionTestCase(TestCase):

	@staticmethod
	def _read_from_stdin(pw):
		os.close(pw)
		return ''.join(sys.stdin)

	async def _testAsyncFunctionStdin(self, loop):
		test_string = '1\n2\n3\n'
		pr, pw = os.pipe()
		fd_pipes = {0:pr}
		reader = AsyncFunction(scheduler=loop, fd_pipes=fd_pipes, target=self._read_from_stdin, args=(pw,))
		reader.start()
		os.close(pr)
		_set_nonblocking(pw)
		with open(pw, mode='wb', buffering=0) as pipe_write:
			await _writer(pipe_write, test_string.encode('utf_8'))
		self.assertEqual((await reader.async_wait()), os.EX_OK)
		self.assertEqual(reader.result, test_string)

	def testAsyncFunctionStdin(self):
		loop = asyncio._wrap_loop()
		loop.run_until_complete(self._testAsyncFunctionStdin(loop=loop))

	def _test_getpid_fork(self):
		"""
		Verify that portage.getpid() cache is updated in a forked child process.
		"""
		loop = asyncio._wrap_loop()
		proc = AsyncFunction(scheduler=loop, target=portage.getpid)
		proc.start()
		proc.wait()
		self.assertEqual(proc.pid, proc.result)

	def test_getpid_fork(self):
		self._test_getpid_fork()

	def test_getpid_double_fork(self):
		"""
		Verify that portage.getpid() cache is updated correctly after
		two forks.
		"""
		loop = asyncio._wrap_loop()
		proc = AsyncFunction(scheduler=loop, target=self._test_getpid_fork)
		proc.start()
		self.assertEqual(proc.wait(), 0)
