# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import pty
import shutil
import socket
import tempfile

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.unix_events import (
	DefaultEventLoopPolicy,
	_set_nonblocking,
)


class _PipeClosedTestCase:

	def test_pipe(self):
		read_end, write_end = os.pipe()
		self._do_test(read_end, write_end)

	def test_pty_device(self):
		try:
			read_end, write_end = pty.openpty()
		except EnvironmentError:
			self.skipTest('pty not available')
		self._do_test(read_end, write_end)

	def test_domain_socket(self):
		read_end, write_end = socket.socketpair()
		self._do_test(read_end.detach(), write_end.detach())

	def test_named_pipe(self):
		tempdir = tempfile.mkdtemp()
		try:
			fifo_path = os.path.join(tempdir, 'fifo')
			os.mkfifo(fifo_path)
			self._do_test(os.open(fifo_path, os.O_NONBLOCK|os.O_RDONLY),
				os.open(fifo_path, os.O_NONBLOCK|os.O_WRONLY))
		finally:
			shutil.rmtree(tempdir)


class ReaderPipeClosedTestCase(_PipeClosedTestCase, TestCase):
	"""
	Test that a reader callback is called after the other end of
	the pipe has been closed.
	"""
	def _do_test(self, read_end, write_end):
		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())

		loop = asyncio._wrap_loop()
		read_end = os.fdopen(read_end, 'rb', 0)
		write_end = os.fdopen(write_end, 'wb', 0)
		try:
			def reader_callback():
				if not reader_callback.called.done():
					reader_callback.called.set_result(None)

			reader_callback.called = loop.create_future()
			loop.add_reader(read_end.fileno(), reader_callback)

			# Allow the loop to check for IO events, and assert
			# that our future is still not done.
			loop.run_until_complete(asyncio.sleep(0, loop=loop))
			self.assertFalse(reader_callback.called.done())

			# Demonstrate that the callback is called afer the
			# other end of the pipe has been closed.
			write_end.close()
			loop.run_until_complete(reader_callback.called)
		finally:
			loop.remove_reader(read_end.fileno())
			write_end.close()
			read_end.close()
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())


class WriterPipeClosedTestCase(_PipeClosedTestCase, TestCase):
	"""
	Test that a writer callback is called after the other end of
	the pipe has been closed.
	"""
	def _do_test(self, read_end, write_end):
		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())

		loop = asyncio._wrap_loop()
		read_end = os.fdopen(read_end, 'rb', 0)
		write_end = os.fdopen(write_end, 'wb', 0)
		try:
			def writer_callback():
				if not writer_callback.called.done():
					writer_callback.called.set_result(None)

			writer_callback.called = loop.create_future()
			_set_nonblocking(write_end.fileno())
			loop.add_writer(write_end.fileno(), writer_callback)

			# With pypy we've seen intermittent spurious writer callbacks
			# here, so retry until the correct state is achieved.
			tries = 10
			while tries:
				tries -= 1

				# Fill up the pipe, so that no writer callbacks should be
				# received until the state has changed.
				while True:
					try:
						os.write(write_end.fileno(), 512 * b'0')
					except EnvironmentError as e:
						if e.errno != errno.EAGAIN:
							raise
						break

				# Allow the loop to check for IO events, and assert
				# that our future is still not done.
				loop.run_until_complete(asyncio.sleep(0, loop=loop))
				if writer_callback.called.done():
					writer_callback.called = loop.create_future()
				else:
					break

			self.assertFalse(writer_callback.called.done())

			# Demonstrate that the callback is called afer the
			# other end of the pipe has been closed.
			read_end.close()
			loop.run_until_complete(writer_callback.called)
		finally:
			loop.remove_writer(write_end.fileno())
			write_end.close()
			read_end.close()
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())
