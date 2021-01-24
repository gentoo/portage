# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.util._async.PipeLogger import PipeLogger
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _reader, _writer
from portage.util.futures.unix_events import _set_nonblocking


class PipeLoggerTestCase(TestCase):

	async def _testPipeLoggerToPipe(self, test_string, loop):
		"""
		Test PipeLogger writing to a pipe connected to a PipeReader.
		This verifies that PipeLogger does not deadlock when writing
		to a pipe that's drained by a PipeReader running in the same
		process (requires non-blocking write).
		"""

		input_fd, writer_pipe = os.pipe()
		_set_nonblocking(writer_pipe)
		writer_pipe = os.fdopen(writer_pipe, 'wb', 0)
		writer = asyncio.ensure_future(_writer(writer_pipe, test_string.encode('ascii')))
		writer.add_done_callback(lambda writer: writer_pipe.close())

		pr, pw = os.pipe()

		consumer = PipeLogger(background=True,
			input_fd=input_fd,
			log_file_path=os.fdopen(pw, 'wb', 0),
			scheduler=loop)
		consumer.start()

		# Before starting the reader, wait here for a moment, in order
		# to exercise PipeLogger's handling of EAGAIN during write.
		await asyncio.wait([writer], timeout=0.01)

		reader = _reader(pr)
		await writer
		content = await reader
		await consumer.async_wait()

		self.assertEqual(consumer.returncode, os.EX_OK)

		return content.decode('ascii', 'replace')

	def testPipeLogger(self):
		loop = asyncio._wrap_loop()

		for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14, 2**17, 2**17 + 1):
			test_string = x * "a"
			output = loop.run_until_complete(self._testPipeLoggerToPipe(test_string, loop))
			self.assertEqual(test_string, output,
				"x = %s, len(output) = %s" % (x, len(output)))
