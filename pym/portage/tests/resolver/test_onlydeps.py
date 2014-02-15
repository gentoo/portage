# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class OnlydepsTestCase(TestCase):

	def testOnlydeps(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/B" },
			"dev-libs/B-1": { },
			}
		installed = {
			"dev-libs/B-1": { },
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B"],
				all_permutations = True,
				success = True,
				options = { "--onlydeps": True },
				mergelist = ["dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
