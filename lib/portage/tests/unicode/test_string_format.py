# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2


from portage import _encodings, _unicode_encode
from portage.exception import PortageException
from portage.tests import TestCase
from _emerge.DependencyArg import DependencyArg
from _emerge.UseFlagDisplay import UseFlagDisplay


class StringFormatTestCase(TestCase):
	"""
	Test that string formatting works correctly in the current interpretter,
	which may be either python2 or python3.
	"""

	unicode_strings = (
		'\u2018',
		'\u2019',
	)

	def testDependencyArg(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for arg_unicode in self.unicode_strings:
			arg_bytes = _unicode_encode(arg_unicode, encoding=_encodings['content'])
			dependency_arg = DependencyArg(arg=arg_unicode)

			formatted_str = "%s" % (dependency_arg,)
			self.assertEqual(formatted_str, arg_unicode)

			# Test the __str__ method which returns unicode in python3
			formatted_str = "%s" % (dependency_arg,)
			self.assertEqual(formatted_str, arg_unicode)

	def testPortageException(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for arg_unicode in self.unicode_strings:
			arg_bytes = _unicode_encode(arg_unicode, encoding=_encodings['content'])
			e = PortageException(arg_unicode)

			formatted_str = "%s" % (e,)
			self.assertEqual(formatted_str, arg_unicode)

			# Test the __str__ method which returns unicode in python3
			formatted_str = "%s" % (e,)
			self.assertEqual(formatted_str, arg_unicode)

	def testUseFlagDisplay(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for enabled in (True, False):
			for forced in (True, False):
				for arg_unicode in self.unicode_strings:
					e = UseFlagDisplay(arg_unicode, enabled, forced)

					formatted_str = "%s" % (e,)
					self.assertEqual(isinstance(formatted_str, str), True)

					# Test the __str__ method which returns unicode in python3
					formatted_str = "%s" % (e,)
					self.assertEqual(isinstance(formatted_str, str), True)
