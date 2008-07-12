# Copyright 1998-2008 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_spawn.py 8474 2007-11-09 03:35:38Z zmedico $

import errno, os, sys
import fcntl
import termios
import portage
from portage.output import get_term_size, set_term_size
from portage.tests import TestCase
from _emerge import PipeReader, SpawnProcess, TaskScheduler

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

		self._assertEqual(test_string, consumer.getvalue())

class PtyReaderTestCase(PipeReaderTestCase):

	def _assertEqual(self, test_string, consumer_value):
		if test_string != consumer_value:
			# This test is expected to fail on some operating systems
			# such as Darwin that do not support poll() on pty devices.
			self.todo = True
		self.assertEqual(test_string, consumer_value)

	def _create_pipe(self):
		got_pty = False

		if portage._disable_openpty:
			master_fd, slave_fd = os.pipe()
		else:
			from pty import openpty
			try:
				master_fd, slave_fd = openpty()
				got_pty = True
			except EnvironmentError, e:
				portage._disable_openpty = True
				portage.writemsg("openpty failed: '%s'\n" % str(e),
					noiselevel=-1)
				del e
				master_fd, slave_fd = os.pipe()

		if got_pty:
			# Disable post-processing of output since otherwise weird
			# things like \n -> \r\n transformations may occur.
			mode = termios.tcgetattr(slave_fd)
			mode[1] &= ~termios.OPOST
			termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

		if got_pty and sys.stdout.isatty():
			rows, columns = get_term_size()
			set_term_size(rows, columns, slave_fd)

		return (master_fd, slave_fd)
