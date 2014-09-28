# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class AutounmaskUseBreakageTestCase(TestCase):

	def testAutounmaskUseBreakage(self):

		ebuilds = {

			"app-misc/A-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/D[-foo]",
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/D[foo]"
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": ">=app-misc/D-1"
			},

			"app-misc/D-0" : {
				"EAPI": "5",
				"IUSE": "foo"
			},

			"app-misc/D-1" : {
				"EAPI": "5",
				"IUSE": "bar"
			},

		}

		test_cases = (

			# Bug 510270
			# _solve_non_slot_operator_slot_conflicts throws
			# IndexError: tuple index out of range
			# due to autounmask USE breakage.
			ResolverPlaygroundTestCase(
				["app-misc/C", "app-misc/B", "app-misc/A"],
				all_permutations = True,
				success = False,
				ambiguous_slot_collision_solutions = True,
				slot_collision_solutions = [None, []]
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
