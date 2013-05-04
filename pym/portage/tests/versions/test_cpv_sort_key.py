# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.versions import cpv_sort_key

class CpvSortKeyTestCase(TestCase):

	def testCpvSortKey(self):

		tests = [
			(("a/b-2_alpha", "a", "b", "a/b-2", "a/a-1", "a/b-1"),
			 ("a", "a/a-1", "a/b-1", "a/b-2_alpha", "a/b-2", "b")),
		]

		for test in tests:
			self.assertEqual(tuple(sorted(test[0], key=cpv_sort_key())), test[1])
