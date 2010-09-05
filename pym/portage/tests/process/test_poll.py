# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from _emerge.TaskScheduler import TaskScheduler
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess

class PipeReaderTestCase(TestCase):

	def testPipeReader(self):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		test_string = 2 * "blah blah blah\n"

		task_scheduler = TaskScheduler()
		master_fd, slave_fd = os.pipe()
		master_file = os.fdopen(master_fd, 'rb')
		slave_file = os.fdopen(slave_fd, 'wb')
		producer = SpawnProcess(
			args=["bash", "-c", "echo -n '%s'" % test_string],
			env=os.environ, fd_pipes={1:slave_fd},
			scheduler=task_scheduler.sched_iface)
		producer.start()
		slave_file.close()

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=task_scheduler.sched_iface)

		task_scheduler.add(consumer)
		task_scheduler.run()
		output = consumer.getvalue().decode('ascii', 'replace')
		self.assertEqual(test_string, output)
