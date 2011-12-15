# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.util._pty import _create_pty_or_pipe
from _emerge.PollScheduler import PollScheduler
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess

class PipeReaderTestCase(TestCase):

	def _testPipeReader(self, test_string, use_pty):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		scheduler = PollScheduler().sched_iface
		if use_pty:
			got_pty, master_fd, slave_fd = _create_pty_or_pipe()
		else:
			got_pty = False
			master_fd, slave_fd = os.pipe()
		master_file = os.fdopen(master_fd, 'rb', 0)
		slave_file = os.fdopen(slave_fd, 'wb', 0)
		producer = SpawnProcess(
			args=["bash", "-c", "echo -n '%s'" % test_string],
			env=os.environ, fd_pipes={1:slave_fd},
			scheduler=scheduler)
		producer.start()
		slave_file.close()

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=scheduler)

		consumer.start()

		# This will ensure that both tasks have exited, which
		# is necessary to avoid "ResourceWarning: unclosed file"
		# warnings since Python 3.2 (and also ensures that we
		# don't leave any zombie child processes).
		scheduler.schedule()
		self.assertEqual(producer.returncode, os.EX_OK)
		self.assertEqual(consumer.returncode, os.EX_OK)

		output = consumer.getvalue().decode('ascii', 'replace')
		return (output, got_pty)

	def testPipeReader(self):
		for use_pty in (False, True):
			for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14):
				test_string = x * "a"
				output, got_pty = self._testPipeReader(test_string, use_pty)
				self.assertEqual(test_string, output,
					"x = %s, use_pty = %s, got_pty = %s" % (x, use_pty, got_pty))
