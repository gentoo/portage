# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""Tests for the portage.util._xattr module"""

from unittest import mock

import subprocess

import portage
from portage.tests import TestCase
from portage.util._xattr import (xattr as _xattr, _XattrSystemCommands,
                                 _XattrStub)


orig_popen = subprocess.Popen
def MockSubprocessPopen(stdin):
	"""Helper to mock (closely) a subprocess.Popen call

	The module has minor tweaks in behavior when it comes to encoding and
	python versions, so use a real subprocess.Popen call to fake out the
	runtime behavior.  This way we don't have to also implement different
	encodings as that gets ugly real fast.
	"""
	# pylint: disable=protected-access
	proc = orig_popen(['cat'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
	proc.stdin.write(portage._unicode_encode(stdin, portage._encodings['stdio']))
	return proc


class SystemCommandsTest(TestCase):
	"""Test _XattrSystemCommands"""

	OUTPUT = '\n'.join((
		'# file: /bin/ping',
		'security.capability=0sAQAAAgAgAAAAAAAAAAAAAAAAAAA=',
		'user.foo="asdf"',
		'',
	))

	def _setUp(self):
		return _XattrSystemCommands

	def _testGetBasic(self):
		"""Verify the get() behavior"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify basic behavior, and namespace arg works as expected.
			xattr.get('/some/file', 'user.foo')
			xattr.get('/some/file', 'foo', namespace='user')
			self.assertEqual(call_mock.call_args_list[0], call_mock.call_args_list[1])

			# Verify nofollow behavior.
			call_mock.reset()
			xattr.get('/some/file', 'user.foo', nofollow=True)
			self.assertIn('-h', call_mock.call_args[0][0])

	def testGetParsing(self):
		"""Verify get() parses output sanely"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify output parsing.
			call_mock.return_value = MockSubprocessPopen('\n'.join([
				'# file: /some/file',
				'user.foo="asdf"',
				'',
			]))
			call_mock.reset()
			self.assertEqual(xattr.get('/some/file', 'user.foo'), b'"asdf"')

	def testGetAllBasic(self):
		"""Verify the get_all() behavior"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify basic behavior.
			xattr.get_all('/some/file')

			# Verify nofollow behavior.
			call_mock.reset()
			xattr.get_all('/some/file', nofollow=True)
			self.assertIn('-h', call_mock.call_args[0][0])

	def testGetAllParsing(self):
		"""Verify get_all() parses output sanely"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify output parsing.
			call_mock.return_value = MockSubprocessPopen(self.OUTPUT)
			exp = [
				(b'security.capability', b'0sAQAAAgAgAAAAAAAAAAAAAAAAAAA='),
				(b'user.foo', b'"asdf"'),
			]
			self.assertEqual(exp, xattr.get_all('/some/file'))

	def testSetBasic(self):
		"""Verify the set() behavior"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify basic behavior, and namespace arg works as expected.
			xattr.set('/some/file', 'user.foo', 'bar')
			xattr.set('/some/file', 'foo', 'bar', namespace='user')
			self.assertEqual(call_mock.call_args_list[0], call_mock.call_args_list[1])

	def testListBasic(self):
		"""Verify the list() behavior"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify basic behavior.
			xattr.list('/some/file')

			# Verify nofollow behavior.
			call_mock.reset()
			xattr.list('/some/file', nofollow=True)
			self.assertIn('-h', call_mock.call_args[0][0])

	def testListParsing(self):
		"""Verify list() parses output sanely"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify output parsing.
			call_mock.return_value = MockSubprocessPopen(self.OUTPUT)
			exp = [b'security.capability', b'user.foo']
			self.assertEqual(exp, xattr.list('/some/file'))

	def testRemoveBasic(self):
		"""Verify the remove() behavior"""
		xattr = self._setUp()
		with mock.patch.object(subprocess, 'Popen') as call_mock:
			# Verify basic behavior, and namespace arg works as expected.
			xattr.remove('/some/file', 'user.foo')
			xattr.remove('/some/file', 'foo', namespace='user')
			self.assertEqual(call_mock.call_args_list[0], call_mock.call_args_list[1])

			# Verify nofollow behavior.
			call_mock.reset()
			xattr.remove('/some/file', 'user.foo', nofollow=True)
			self.assertIn('-h', call_mock.call_args[0][0])


class StubTest(TestCase):
	"""Test _XattrStub"""

	def testBasic(self):
		"""Verify the stub is stubby"""
		# Would be nice to verify raised errno is OperationNotSupported.
		self.assertRaises(OSError, _XattrStub.get, '/', '')
		self.assertRaises(OSError, _XattrStub.set, '/', '', '')
		self.assertRaises(OSError, _XattrStub.get_all, '/')
		self.assertRaises(OSError, _XattrStub.remove, '/', '')
		self.assertRaises(OSError, _XattrStub.list, '/')


class StandardTest(TestCase):
	"""Test basic xattr API"""

	MODULES = (_xattr, _XattrSystemCommands, _XattrStub)
	FUNCS = ('get', 'get_all', 'set', 'remove', 'list')

	def testApi(self):
		"""Make sure the exported API matches"""
		for mod in self.MODULES:
			for f in self.FUNCS:
				self.assertTrue(hasattr(mod, f),
					'%s func missing in %s' % (f, mod))
