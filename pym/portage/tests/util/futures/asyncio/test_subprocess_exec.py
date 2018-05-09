# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

try:
	from asyncio import create_subprocess_exec
except ImportError:
	create_subprocess_exec = None

from portage.process import find_binary
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util.futures.unix_events import DefaultEventLoopPolicy
from _emerge.PipeReader import PipeReader


def reader(input_file, loop=None):
	"""
	Asynchronously read a binary input file.

	@param input_file: binary input file
	@type input_file: file
	@param loop: event loop
	@type loop: EventLoop
	@return: bytes
	@rtype: asyncio.Future (or compatible)
	"""
	loop = asyncio._wrap_loop(loop)
	future = loop.create_future()
	_Reader(future, input_file, loop)
	return future


class _Reader(object):
	def __init__(self, future, input_file, loop):
		self._future = future
		self._pipe_reader = PipeReader(
			input_files={'input_file':input_file}, scheduler=loop)

		self._future.add_done_callback(self._cancel_callback)
		self._pipe_reader.addExitListener(self._eof)
		self._pipe_reader.start()

	def _cancel_callback(self, future):
		if future.cancelled():
			self._cancel()

	def _eof(self, pipe_reader):
		self._pipe_reader = None
		self._future.set_result(pipe_reader.getvalue())

	def _cancel(self):
		if self._pipe_reader is not None and self._pipe_reader.poll() is None:
			self._pipe_reader.removeExitListener(self._eof)
			self._pipe_reader.cancel()
			self._pipe_reader = None


class SubprocessExecTestCase(TestCase):
	def _run_test(self, test):
		initial_policy = asyncio.get_event_loop_policy()
		if not isinstance(initial_policy, DefaultEventLoopPolicy):
			asyncio.set_event_loop_policy(DefaultEventLoopPolicy())

		loop = asyncio._wrap_loop()
		try:
			test(loop)
		finally:
			asyncio.set_event_loop_policy(initial_policy)
			if loop not in (None, global_event_loop()):
				loop.close()
				self.assertFalse(global_event_loop().is_closed())

	def testEcho(self):
		if create_subprocess_exec is None:
			self.skipTest('create_subprocess_exec not implemented for python2')

		args_tuple = (b'hello', b'world')
		echo_binary = find_binary("echo")
		self.assertNotEqual(echo_binary, None)
		echo_binary = echo_binary.encode()

		# Use os.pipe(), since this loop does not implement the
		# ReadTransport necessary for subprocess.PIPE support.
		stdout_pr, stdout_pw = os.pipe()
		stdout_pr = os.fdopen(stdout_pr, 'rb', 0)
		stdout_pw = os.fdopen(stdout_pw, 'wb', 0)
		files = [stdout_pr, stdout_pw]

		def test(loop):
			output = None
			try:
				with open(os.devnull, 'rb', 0) as devnull:
					proc = loop.run_until_complete(
						create_subprocess_exec(
						echo_binary, *args_tuple,
						stdin=devnull, stdout=stdout_pw, stderr=stdout_pw))

				# This belongs exclusively to the subprocess now.
				stdout_pw.close()

				output = asyncio.ensure_future(
					reader(stdout_pr, loop=loop), loop=loop)

				self.assertEqual(
					loop.run_until_complete(proc.wait()), os.EX_OK)
				self.assertEqual(
					tuple(loop.run_until_complete(output).split()), args_tuple)
			finally:
				if output is not None and not output.done():
					output.cancel()
				for f in files:
					f.close()

		self._run_test(test)

	def testCat(self):
		if create_subprocess_exec is None:
			self.skipTest('create_subprocess_exec not implemented for python2')

		stdin_data = b'hello world'
		cat_binary = find_binary("cat")
		self.assertNotEqual(cat_binary, None)
		cat_binary = cat_binary.encode()

		# Use os.pipe(), since this loop does not implement the
		# ReadTransport necessary for subprocess.PIPE support.
		stdout_pr, stdout_pw = os.pipe()
		stdout_pr = os.fdopen(stdout_pr, 'rb', 0)
		stdout_pw = os.fdopen(stdout_pw, 'wb', 0)

		stdin_pr, stdin_pw = os.pipe()
		stdin_pr = os.fdopen(stdin_pr, 'rb', 0)
		stdin_pw = os.fdopen(stdin_pw, 'wb', 0)

		files = [stdout_pr, stdout_pw, stdin_pr, stdin_pw]

		def test(loop):
			output = None
			try:
				proc = loop.run_until_complete(
					create_subprocess_exec(
					cat_binary,
					stdin=stdin_pr, stdout=stdout_pw, stderr=stdout_pw))

				# These belong exclusively to the subprocess now.
				stdout_pw.close()
				stdin_pr.close()

				output = asyncio.ensure_future(
					reader(stdout_pr, loop=loop), loop=loop)

				with ForkExecutor(loop=loop) as executor:
					writer = asyncio.ensure_future(loop.run_in_executor(
						executor, stdin_pw.write, stdin_data), loop=loop)

					# This belongs exclusively to the writer now.
					stdin_pw.close()
					loop.run_until_complete(writer)

				self.assertEqual(loop.run_until_complete(proc.wait()), os.EX_OK)
				self.assertEqual(loop.run_until_complete(output), stdin_data)
			finally:
				if output is not None and not output.done():
					output.cancel()
				for f in files:
					f.close()

		self._run_test(test)

	def testReadTransport(self):
		"""
		Test asyncio.create_subprocess_exec(stdout=subprocess.PIPE) which
		requires an AbstractEventLoop.connect_read_pipe implementation
		(and a ReadTransport implementation for it to return).
		"""
		if create_subprocess_exec is None:
			self.skipTest('create_subprocess_exec not implemented for python2')

		args_tuple = (b'hello', b'world')
		echo_binary = find_binary("echo")
		self.assertNotEqual(echo_binary, None)
		echo_binary = echo_binary.encode()

		def test(loop):
			with open(os.devnull, 'rb', 0) as devnull:
				proc = loop.run_until_complete(
					create_subprocess_exec(
					echo_binary, *args_tuple,
					stdin=devnull,
					stdout=subprocess.PIPE, stderr=subprocess.STDOUT))

			self.assertEqual(
				tuple(loop.run_until_complete(proc.stdout.read()).split()),
				args_tuple)
			self.assertEqual(loop.run_until_complete(proc.wait()), os.EX_OK)

		self._run_test(test)

	def testWriteTransport(self):
		"""
		Test asyncio.create_subprocess_exec(stdin=subprocess.PIPE) which
		requires an AbstractEventLoop.connect_write_pipe implementation
		(and a WriteTransport implementation for it to return).
		"""
		if create_subprocess_exec is None:
			self.skipTest('create_subprocess_exec not implemented for python2')

		stdin_data = b'hello world'
		cat_binary = find_binary("cat")
		self.assertNotEqual(cat_binary, None)
		cat_binary = cat_binary.encode()

		def test(loop):
			proc = loop.run_until_complete(
				create_subprocess_exec(
				cat_binary,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT))

			# This buffers data when necessary to avoid blocking.
			proc.stdin.write(stdin_data)
			# Any buffered data is written asynchronously after the
			# close method is called.
			proc.stdin.close()

			self.assertEqual(
				loop.run_until_complete(proc.stdout.read()),
				stdin_data)
			self.assertEqual(loop.run_until_complete(proc.wait()), os.EX_OK)

		self._run_test(test)
