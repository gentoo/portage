# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import pty
import shutil
import socket
import tempfile

from portage import os
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from _emerge.PipeReader import PipeReader

class PipeReaderTestCase(TestCase):

	_use_array = False
	_echo_cmd = "echo -n '%s'"

	def test_pipe(self):
		def make_pipes():
			return os.pipe(), None
		self._do_test(make_pipes)

	def test_pty_device(self):
		def make_pipes():
			try:
				return pty.openpty(), None
			except EnvironmentError:
				self.skipTest('pty not available')
		self._do_test(make_pipes)

	def test_domain_socket(self):
		def make_pipes():
			read_end, write_end = socket.socketpair()
			return (read_end.detach(), write_end.detach()), None
		self._do_test(make_pipes)

	def test_named_pipe(self):
		def make_pipes():
			tempdir = tempfile.mkdtemp()
			fifo_path = os.path.join(tempdir, 'fifo')
			os.mkfifo(fifo_path)
			return ((os.open(fifo_path, os.O_NONBLOCK|os.O_RDONLY),
				os.open(fifo_path, os.O_NONBLOCK|os.O_WRONLY)),
				functools.partial(shutil.rmtree, tempdir))
		self._do_test(make_pipes)

	def _testPipeReader(self, master_fd, slave_fd, test_string):
		"""
		Use a poll loop to read data from a pipe and assert that
		the data written to the pipe is identical to the data
		read from the pipe.
		"""

		# WARNING: It is very important to use unbuffered mode here,
		# in order to avoid issue 5380 with python3.
		master_file = os.fdopen(master_fd, 'rb', 0)
		scheduler = global_event_loop()

		consumer = PipeReader(
			input_files={"producer" : master_file},
			_use_array=self._use_array,
			scheduler=scheduler)
		consumer.start()

		producer = scheduler.run_until_complete(asyncio.create_subprocess_exec(
			"bash", "-c", self._echo_cmd % test_string,
			stdout=slave_fd,
			loop=scheduler))

		os.close(slave_fd)
		scheduler.run_until_complete(producer.wait())
		scheduler.run_until_complete(consumer.async_wait())

		self.assertEqual(producer.returncode, os.EX_OK)
		self.assertEqual(consumer.returncode, os.EX_OK)

		return consumer.getvalue().decode('ascii', 'replace')

	def _do_test(self, make_pipes):
		for x in (1, 2, 5, 6, 7, 8, 2**5, 2**10, 2**12, 2**13, 2**14):
			test_string = x * "a"
			(read_end, write_end), cleanup = make_pipes()
			try:
				output = self._testPipeReader(read_end, write_end, test_string)
				self.assertEqual(test_string, output,
					"x = %s, len(output) = %s" % (x, len(output)))
			finally:
				if cleanup is not None:
					cleanup()


class PipeReaderArrayTestCase(PipeReaderTestCase):

	_use_array = True
	# sleep allows reliable triggering of the failure mode on fast computers
	_echo_cmd = "sleep 0.1 ; echo -n '%s'"

	def __init__(self, *args, **kwargs):
		super(PipeReaderArrayTestCase, self).__init__(*args, **kwargs)
		# https://bugs.python.org/issue5380
		# https://bugs.pypy.org/issue956
		self.todo = True
