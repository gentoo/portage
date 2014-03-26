# Copyright 2012-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import tempfile

from portage import os
from portage.tests import TestCase
from portage.util._async.PipeLogger import PipeLogger
from portage.util._async.PopenProcess import PopenProcess
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.PipeReader import PipeReader

class PopenPipeTestCase(TestCase):
	"""
	Test PopenProcess, which can be useful for Jython support, since it
	uses the subprocess.Popen instead of os.fork().
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
			pipe_reader=PipeReader(), scheduler=global_event_loop())

		consumer = producer.pipe_reader
		consumer.input_files = {"producer" : producer.proc.stdout}

		producer.start()
		producer.wait()

		self.assertEqual(producer.returncode, os.EX_OK)
		self.assertEqual(consumer.returncode, os.EX_OK)

		return consumer.getvalue().decode('ascii', 'replace')

	def _testPipeLogger(self, test_string):

		producer = PopenProcess(proc=subprocess.Popen(
			["bash", "-c", self._echo_cmd % test_string],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
			scheduler=global_event_loop())

		fd, log_file_path = tempfile.mkstemp()
		try:

			consumer = PipeLogger(background=True,
				input_fd=producer.proc.stdout,
				log_file_path=log_file_path)

			producer.pipe_reader = consumer

			producer.start()
			producer.wait()

			self.assertEqual(producer.returncode, os.EX_OK)
			self.assertEqual(consumer.returncode, os.EX_OK)

			with open(log_file_path, 'rb') as f:
				content = f.read()

		finally:
			os.close(fd)
			os.unlink(log_file_path)

		return content.decode('ascii', 'replace')

	def testPopenPipe(self):
		for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14):
			test_string = x * "a"
			output = self._testPipeReader(test_string)
			self.assertEqual(test_string, output,
				"x = %s, len(output) = %s" % (x, len(output)))

			output = self._testPipeLogger(test_string)
			self.assertEqual(test_string, output,
				"x = %s, len(output) = %s" % (x, len(output)))
