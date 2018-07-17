# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class OnlydepsMinimalTestCase(TestCase):

	def testOnlydepsMinimal(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/B",
			                  "RDEPEND": "dev-libs/C",
			                  "PDEPEND": "dev-libs/D" },
			"dev-libs/B-1": { },
			"dev-libs/C-1": { },
			"dev-libs/D-1": { },
			}
		installed = {
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				all_permutations = True,
				success = True,
				options = { "--onlydeps": True,
				            "--onlydeps-with-rdeps": "y" },
				ambiguous_merge_order = True,
				mergelist = [("dev-libs/B-1",
				             "dev-libs/C-1",
				             "dev-libs/D-1")]),
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				all_permutations = True,
				success = True,
				options = { "--onlydeps": True,
				            "--onlydeps-with-rdeps": "n" },
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
