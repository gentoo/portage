# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

from portage.process import find_binary
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio
from portage.util.futures._asyncio import create_subprocess_exec
from portage.util.futures.unix_events import DefaultEventLoopPolicy


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
		args_tuple = (b'hello', b'world')
		echo_binary = find_binary("echo")
		self.assertNotEqual(echo_binary, None)
		echo_binary = echo_binary.encode()

		def test(loop):

			async def test_coroutine():

				proc = await create_subprocess_exec(echo_binary, *args_tuple,
					stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

				out, err = await proc.communicate()
				self.assertEqual(tuple(out.split()), args_tuple)
				self.assertEqual(proc.returncode, os.EX_OK)

				proc = await create_subprocess_exec(
						'bash', '-c', 'echo foo; echo bar 1>&2;',
						stdout=subprocess.PIPE, stderr=subprocess.PIPE)

				out, err = await proc.communicate()
				self.assertEqual(out, b'foo\n')
				self.assertEqual(err, b'bar\n')
				self.assertEqual(proc.returncode, os.EX_OK)

				proc = await create_subprocess_exec(
						'bash', '-c', 'echo foo; echo bar 1>&2;',
						stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

				out, err = await proc.communicate()
				self.assertEqual(out, b'foo\nbar\n')
				self.assertEqual(err, None)
				self.assertEqual(proc.returncode, os.EX_OK)

				return 'success'

			self.assertEqual('success',
				loop.run_until_complete(test_coroutine()))

		self._run_test(test)

	def testCat(self):
		stdin_data = b'hello world'
		cat_binary = find_binary("cat")
		self.assertNotEqual(cat_binary, None)
		cat_binary = cat_binary.encode()

		def test(loop):
			proc = loop.run_until_complete(
				create_subprocess_exec(cat_binary,
				stdin=subprocess.PIPE, stdout=subprocess.PIPE,
				loop=loop))

			out, err = loop.run_until_complete(proc.communicate(input=stdin_data))

			self.assertEqual(loop.run_until_complete(proc.wait()), os.EX_OK)
			self.assertEqual(out, stdin_data)

		self._run_test(test)

	def testPipe(self):
		stdin_data = b'hello world'
		cat_binary = find_binary("cat")
		self.assertNotEqual(cat_binary, None)
		cat_binary = cat_binary.encode()

		echo_binary = find_binary("echo")
		self.assertNotEqual(echo_binary, None)
		echo_binary = echo_binary.encode()

		def test(loop):

			pr, pw = os.pipe()

			cat_proc = loop.run_until_complete(create_subprocess_exec(
				cat_binary, stdin=pr, stdout=subprocess.PIPE,
				loop=loop))

			echo_proc = loop.run_until_complete(create_subprocess_exec(
				echo_binary, b'-n', stdin_data, stdout=pw,
				loop=loop))

			os.close(pr)
			os.close(pw)

			out, err = loop.run_until_complete(cat_proc.communicate())

			self.assertEqual(loop.run_until_complete(cat_proc.wait()), os.EX_OK)
			self.assertEqual(loop.run_until_complete(echo_proc.wait()), os.EX_OK)
			self.assertEqual(out, stdin_data)

		self._run_test(test)

	def testReadTransport(self):
		"""
		Test asyncio.create_subprocess_exec(stdout=subprocess.PIPE) which
		requires an AbstractEventLoop.connect_read_pipe implementation
		(and a ReadTransport implementation for it to return).
		"""

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
					stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
					loop=loop))

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

		stdin_data = b'hello world'
		cat_binary = find_binary("cat")
		self.assertNotEqual(cat_binary, None)
		cat_binary = cat_binary.encode()

		def test(loop):
			proc = loop.run_until_complete(
				create_subprocess_exec(
				cat_binary,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
				loop=loop))

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
