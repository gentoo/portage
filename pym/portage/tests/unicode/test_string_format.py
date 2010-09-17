# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage import _encodings, _unicode_decode
from portage.exception import PortageException
from portage.tests import TestCase
from _emerge.DependencyArg import DependencyArg
from _emerge.UseFlagDisplay import UseFlagDisplay

if sys.hexversion >= 0x3000000:
	basestring = str

STR_IS_UNICODE = sys.hexversion >= 0x3000000

class StringFormatTestCase(TestCase):
	"""
	Test that string formatting works correctly in the current interpretter,
	which may be either python2 or python3.
	"""

	# In order to get some unicode test strings in a way that works in
	# both python2 and python3, write them here as byte strings and
	# decode them before use. This assumes _encodings['content'] is
	# utf_8.

	unicode_strings = (
		b'\xE2\x80\x98',
		b'\xE2\x80\x99',
	)

	def testDependencyArg(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for arg_bytes in self.unicode_strings:
			arg_unicode = _unicode_decode(arg_bytes, encoding=_encodings['content'])
			dependency_arg = DependencyArg(arg=arg_unicode)

			# Force unicode format string so that __unicode__() is
			# called in python2.
			formatted_str = _unicode_decode("%s") % (dependency_arg,)
			self.assertEqual(formatted_str, arg_unicode)

			if STR_IS_UNICODE:

				# Test the __str__ method which returns unicode in python3
				formatted_str = "%s" % (dependency_arg,)
				self.assertEqual(formatted_str, arg_unicode)

			else:

				# Test the __str__ method which returns encoded bytes in python2
				formatted_bytes = "%s" % (dependency_arg,)
				self.assertEqual(formatted_bytes, arg_bytes)

	def testPortageException(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for arg_bytes in self.unicode_strings:
			arg_unicode = _unicode_decode(arg_bytes, encoding=_encodings['content'])
			e = PortageException(arg_unicode)

			# Force unicode format string so that __unicode__() is
			# called in python2.
			formatted_str = _unicode_decode("%s") % (e,)
			self.assertEqual(formatted_str, arg_unicode)

			if STR_IS_UNICODE:

				# Test the __str__ method which returns unicode in python3
				formatted_str = "%s" % (e,)
				self.assertEqual(formatted_str, arg_unicode)

			else:

				# Test the __str__ method which returns encoded bytes in python2
				formatted_bytes = "%s" % (e,)
				self.assertEqual(formatted_bytes, arg_bytes)

	def testUseFlagDisplay(self):

		self.assertEqual(_encodings['content'], 'utf_8')

		for enabled in (True, False):
			for forced in (True, False):
				for arg_bytes in self.unicode_strings:
					arg_unicode = _unicode_decode(arg_bytes, encoding=_encodings['content'])
					e = UseFlagDisplay(arg_unicode, enabled, forced)

					# Force unicode format string so that __unicode__() is
					# called in python2.
					formatted_str = _unicode_decode("%s") % (e,)
					self.assertEqual(isinstance(formatted_str, basestring), True)

					if STR_IS_UNICODE:

						# Test the __str__ method which returns unicode in python3
						formatted_str = "%s" % (e,)
						self.assertEqual(isinstance(formatted_str, str), True)

					else:

						# Test the __str__ method which returns encoded bytes in python2
						formatted_bytes = "%s" % (e,)
						self.assertEqual(isinstance(formatted_bytes, bytes), True)
