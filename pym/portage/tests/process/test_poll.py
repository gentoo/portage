# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.util._pty import _create_pty_or_pipe
from _emerge.TaskScheduler import TaskScheduler
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess

class PipeReaderTestCase(TestCase):

	_use_array = False
	_use_pty = False
	_echo_cmd = "echo -n '%s'"

	def _testPipeReader(self, test_string):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		if self._use_pty:
			got_pty, master_fd, slave_fd = _create_pty_or_pipe()
			if not got_pty:
				os.close(slave_fd)
				os.close(master_fd)
				skip_reason = "pty not acquired"
				self.portage_skip = skip_reason
				self.fail(skip_reason)
				return
		else:
			master_fd, slave_fd = os.pipe()

		# WARNING: It is very important to use unbuffered mode here,
		# in order to avoid issue 5380 with python3.
		master_file = os.fdopen(master_fd, 'rb', 0)
		slave_file = os.fdopen(slave_fd, 'wb', 0)
		task_scheduler = TaskScheduler(max_jobs=2)
		producer = SpawnProcess(
			args=["bash", "-c", self._echo_cmd % test_string],
			env=os.environ, fd_pipes={1:slave_fd},
			scheduler=task_scheduler.sched_iface)
		task_scheduler.add(producer)
		slave_file.close()

		consumer = PipeReader(
			input_files={"producer" : master_file},
			scheduler=task_scheduler.sched_iface, _use_array=self._use_array)

		task_scheduler.add(consumer)

		# This will ensure that both tasks have exited, which
		# is necessary to avoid "ResourceWarning: unclosed file"
		# warnings since Python 3.2 (and also ensures that we
		# don't leave any zombie child processes).
		task_scheduler.run()
		self.assertEqual(producer.returncode, os.EX_OK)
		self.assertEqual(consumer.returncode, os.EX_OK)

		return consumer.getvalue().decode('ascii', 'replace')

	def testPipeReader(self):
		for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14):
			test_string = x * "a"
			output = self._testPipeReader(test_string)
			self.assertEqual(test_string, output,
				"x = %s, len(output) = %s" % (x, len(output)))

class PipeReaderPtyTestCase(PipeReaderTestCase):
	_use_pty = True

class PipeReaderArrayTestCase(PipeReaderTestCase):

	_use_array = True
	# sleep allows reliable triggering of the failure mode on fast computers
	_echo_cmd = "sleep 0.1 ; echo -n '%s'"

	def __init__(self, *args, **kwargs):
		super(PipeReaderArrayTestCase, self).__init__(*args, **kwargs)
		# http://bugs.python.org/issue5380
		# https://bugs.pypy.org/issue956
		self.todo = True

class PipeReaderPtyArrayTestCase(PipeReaderArrayTestCase):
	_use_pty = True
