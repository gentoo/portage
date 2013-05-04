# test_stackDicts.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util import stack_dicts


class StackDictsTestCase(TestCase):

	def testStackDictsPass(self):

		tests = [
			([{'a': 'b'}, {'b': 'c'}], {'a': 'b', 'b': 'c'}, False, [], False),
			([{'a': 'b'}, {'a': 'c'}], {'a': 'b c'}, True, [], False),
			([{'a': 'b'}, {'a': 'c'}], {'a': 'b c'}, False, ['a'], False),
			([{'a': 'b'}, None], {'a': 'b'}, False, [], True),
			([None], {}, False, [], False),
			([None, {}], {}, False, [], True)
		]
		for test in tests:
			result = stack_dicts(test[0], test[2], test[3], test[4])
			self.assertEqual(result, test[1])

	def testStackDictsFail(self):

		tests = [
			([None, {}], None, False, [], True),
			([{'a': 'b'}, {'a': 'c'}], {'a': 'b c'}, False, [], False)
		]
		for test in tests:
			result = stack_dicts(test[0], test[2], test[3], test[4])
			self.assertNotEqual(result, test[1])
