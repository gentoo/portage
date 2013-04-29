# test_stackDictList.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase

class StackDictListTestCase(TestCase):

	def testStackDictList(self):
		from portage.util import stack_dictlist

		tests = [
			({'a': 'b'}, {'x': 'y'}, False, {'a': ['b'], 'x': ['y']}),
			({'KEYWORDS': ['alpha', 'x86']}, {'KEYWORDS': ['-*']}, True, {}),
			({'KEYWORDS': ['alpha', 'x86']}, {'KEYWORDS': ['-x86']}, True, {'KEYWORDS': ['alpha']}),
		]
		for test in tests:
			self.assertEqual(
				stack_dictlist([test[0], test[1]], incremental=test[2]), test[3])
