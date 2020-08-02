# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys

from portage import os
from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _writer
from portage.util.futures.compat_coroutine import coroutine
from portage.util.futures.unix_events import _set_nonblocking


class AsyncFunctionTestCase(TestCase):

	@staticmethod
	def _read_from_stdin(pw):
		os.close(pw)
		return ''.join(sys.stdin)

	@coroutine
	def _testAsyncFunctionStdin(self, loop):
		test_string = '1\n2\n3\n'
		pr, pw = os.pipe()
		fd_pipes = {0:pr}
		reader = AsyncFunction(scheduler=loop, fd_pipes=fd_pipes, target=self._read_from_stdin, args=(pw,))
		reader.start()
		os.close(pr)
		_set_nonblocking(pw)
		with open(pw, mode='wb', buffering=0) as pipe_write:
			yield _writer(pipe_write, test_string.encode('utf_8'), loop=loop)
		self.assertEqual((yield reader.async_wait()), os.EX_OK)
		self.assertEqual(reader.result, test_string)

	def testAsyncFunctionStdin(self):
		loop = asyncio._wrap_loop()
		loop.run_until_complete(self._testAsyncFunctionStdin(loop))
