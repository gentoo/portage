# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SolveNonSlotOperatorSlotConflictsTestCase(TestCase):

	def testSolveNonSlotOperatorSlotConflicts(self):

		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1",
				"PDEPEND": "app-misc/B"
			},

			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2",
				"PDEPEND": "app-misc/B"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:="
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1",
				"PDEPEND": "app-misc/B"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:0/1="
			},

		}

		world = ["app-misc/A"]

		test_cases = (

			# bug 522084
			# In this case, _solve_non_slot_operator_slot_conflicts
			# removed both versions of app-misc/A from the graph, since
			# they didn't have any non-conflict parents (except for
			# @selected which matched both instances). The result was
			# a missed update.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['app-misc/A-2', 'app-misc/B-0']
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
