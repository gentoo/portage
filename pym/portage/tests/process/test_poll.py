# Copyright 1998-2008 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from portage import os
from portage.tests import TestCase
from _emerge.TaskScheduler import TaskScheduler
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess

class PipeReaderTestCase(TestCase):

	def _create_pipe(self):
		return os.pipe()

	def _assertEqual(self, test_string, consumer_value):
		self.assertEqual(test_string, consumer_value)

	def testPipeReader(self):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		test_string = 2 * "blah blah blah\n"

		master_fd, slave_fd = self._create_pipe()
		master_file = os.fdopen(master_fd, 'rb')

		task_scheduler = TaskScheduler(max_jobs=2)
		scheduler = task_scheduler.sched_iface

		class Producer(SpawnProcess):
			def _spawn(self, args, **kwargs):
				rval = SpawnProcess._spawn(self, args, **kwargs)
				os.close(kwargs['fd_pipes'][1])
				return rval

		producer = Producer(
			args=["bash", "-c", "echo -n '%s'" % test_string],
			fd_pipes={1:slave_fd}, scheduler=scheduler)

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=scheduler)

		task_scheduler.add(producer)
		task_scheduler.add(consumer)

		task_scheduler.run()

		if sys.hexversion >= 0x3000000:
			test_string = test_string.encode()

		self._assertEqual(test_string, consumer.getvalue())
