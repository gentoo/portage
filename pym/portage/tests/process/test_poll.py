# Copyright 1998-2008 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_spawn.py 8474 2007-11-09 03:35:38Z zmedico $

import errno, os, sys
from portage.tests import TestCase
from _emerge import PipeReader, SpawnProcess, TaskScheduler

class PollTestCase(TestCase):

	def testPipeReader(self):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		test_string = 2 * "blah blah blah\n"

		master_fd, slave_fd = os.pipe()
 		master_file = os.fdopen(master_fd, 'r')

		task_scheduler = TaskScheduler(max_jobs=2)
		scheduler = task_scheduler.sched_iface

		producer = SpawnProcess(
			args=["bash", "-c", "echo -n '%s'" % test_string],
			fd_pipes={1:slave_fd}, scheduler=scheduler)

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=scheduler)

		task_scheduler.add(producer)
		task_scheduler.add(consumer)

		def producer_start_cb(task):
			os.close(slave_fd)

		producer.addStartListener(producer_start_cb)
		task_scheduler.run()

		self.assertEqual(test_string, consumer.getvalue())
