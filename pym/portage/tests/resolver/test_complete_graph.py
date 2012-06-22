# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CompleteGraphTestCase(TestCase):

	def testCompleteGraphVersionChange(self):
		"""
		Prevent reverse dependency breakage triggered by version changes.
		"""

		ebuilds = {
			"sys-libs/x-0.1": {},
			"sys-libs/x-1": {},
			"sys-libs/x-2": {},
			"sys-apps/a-1": {"RDEPEND" : ">=sys-libs/x-1 <sys-libs/x-2"},
		}

		installed = {
			"sys-libs/x-1": {},
			"sys-apps/a-1": {"RDEPEND" : ">=sys-libs/x-1 <sys-libs/x-2"},
		}

		world = ["sys-apps/a"]

		test_cases = (
			ResolverPlaygroundTestCase(
				[">=sys-libs/x-2"],
				options = {"--complete-graph-if-new-ver" : "n", "--rebuild-if-new-slot-abi": "n"},
				mergelist = ["sys-libs/x-2"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				[">=sys-libs/x-2"],
				options = {"--complete-graph-if-new-ver" : "y"},
				mergelist = ["sys-libs/x-2"],
				slot_collision_solutions = [],
				success = False,
			),
			ResolverPlaygroundTestCase(
				["<sys-libs/x-1"],
				options = {"--complete-graph-if-new-ver" : "n", "--rebuild-if-new-slot-abi": "n"},
				mergelist = ["sys-libs/x-0.1"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				["<sys-libs/x-1"],
				options = {"--complete-graph-if-new-ver" : "y"},
				mergelist = ["sys-libs/x-0.1"],
				slot_collision_solutions = [],
				success = False,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
