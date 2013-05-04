# test_stackLists.py -- Portage Unit Testing Functionality
# Copyright 2006-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util import stack_lists

class StackListsTestCase(TestCase):

	def testStackLists(self):

		tests = [
			([['a', 'b', 'c'], ['d', 'e', 'f']], ['a', 'c', 'b', 'e', 'd', 'f'], False),
			([['a', 'x'], ['b', 'x']], ['a', 'x', 'b'], False),
			([['a', 'b', 'c'], ['-*']], [], True),
			([['a'], ['-a']], [], True)
		]

		for test in tests:
			result = stack_lists(test[0], test[2])
			self.assertEqual(set(result), set(test[1]))
