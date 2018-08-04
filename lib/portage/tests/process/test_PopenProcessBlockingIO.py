# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess

try:
	import threading
except ImportError:
	# dummy_threading will not suffice
	threading = None

from portage import os
from portage.tests import TestCase
from portage.util._async.PopenProcess import PopenProcess
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util._async.PipeReaderBlockingIO import PipeReaderBlockingIO

class PopenPipeBlockingIOTestCase(TestCase):
	"""
	Test PopenProcess, which can be useful for Jython support:
		* use subprocess.Popen since Jython does not support os.fork()
		* use blocking IO with threads, since Jython does not support
		  fcntl non-blocking IO)
	"""

	_echo_cmd = "echo -n '%s'"

	def _testPipeReader(self, test_string):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		producer = PopenProcess(proc=subprocess.Popen(
			["bash", "-c", self._echo_cmd % test_string],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
			pipe_reader=PipeReaderBlockingIO(), scheduler=global_event_loop())

		consumer = producer.pipe_reader
		consumer.input_files = {"producer" : producer.proc.stdout}

		producer.start()
		producer.wait()

		self.assertEqual(producer.returncode, os.EX_OK)
		self.assertEqual(consumer.returncode, os.EX_OK)

		return consumer.getvalue().decode('ascii', 'replace')

	def testPopenPipeBlockingIO(self):

		if threading is None:
			skip_reason = "threading disabled"
			self.portage_skip = "threading disabled"
			self.assertFalse(True, skip_reason)
			return

		for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14):
			test_string = x * "a"
			output = self._testPipeReader(test_string)
			self.assertEqual(test_string, output,
				"x = %s, len(output) = %s" % (x, len(output)))
