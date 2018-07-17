# test_uniqueArray.py -- Portage Unit Testing Functionality
# Copyright 2006-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.util import unique_array

class UniqueArrayTestCase(TestCase):

	def testUniqueArrayPass(self):
		"""
		test portage.util.uniqueArray()
		"""

		tests = [
			(['a', 'a', 'a', os, os, [], [], []], ['a', os, []]),
			([1, 1, 1, 2, 3, 4, 4], [1, 2, 3, 4])
		]

		for test in tests:
			result = unique_array(test[0])
			for item in test[1]:
				number = result.count(item)
				self.assertFalse(number != 1, msg=("%s contains %s of %s, "
					"should be only 1") % (result, number, item))
