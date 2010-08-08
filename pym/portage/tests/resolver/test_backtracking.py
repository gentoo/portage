# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class BacktrackingTestCase(TestCase):

	def testBacktracking(self):
		ebuilds = {
			"dev-libs/A-1": {},
			"dev-libs/A-2": {},
			"dev-libs/B-1": { "DEPEND": "dev-libs/A" },
			}

		test_cases = (
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1", "dev-libs/B"],
					all_permutations = True,
					mergelist = ["dev-libs/A-1", "dev-libs/B-1"],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
