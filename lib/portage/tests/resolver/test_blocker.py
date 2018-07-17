# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SlotConflictWithBlockerTestCase(TestCase):

	def testBlocker(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/X" },
			"dev-libs/B-1": { "DEPEND": "<dev-libs/X-2" },
			"dev-libs/C-1": { "DEPEND": "<dev-libs/X-3" },

			"dev-libs/X-1": { "EAPI": "2", "RDEPEND": "!=dev-libs/Y-1" },
			"dev-libs/X-2": { "EAPI": "2", "RDEPEND": "!=dev-libs/Y-2" },
			"dev-libs/X-3": { "EAPI": "2", "RDEPEND": "!=dev-libs/Y-3" },

			"dev-libs/Y-1": { "SLOT": "1" },
			"dev-libs/Y-2": { "SLOT": "2" },
			"dev-libs/Y-3": { "SLOT": "3" },
			}

		installed = {
			"dev-libs/Y-1": { "SLOT": "1" },
			"dev-libs/Y-2": { "SLOT": "2" },
			"dev-libs/Y-3": { "SLOT": "3" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B", "dev-libs/C"],
				options = { "--backtrack": 0 },
				all_permutations = True,
				success = True,
				ambiguous_merge_order = True,
				mergelist = ["dev-libs/X-1", "[uninstall]dev-libs/Y-1", "!=dev-libs/Y-1", \
					("dev-libs/A-1", "dev-libs/B-1", "dev-libs/C-1")]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
