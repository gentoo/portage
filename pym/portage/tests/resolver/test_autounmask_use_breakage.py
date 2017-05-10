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
				options={"--autounmask-backtrack": "y"},
				all_permutations = True,
				success = False,
				ambiguous_slot_collision_solutions = True,
				slot_collision_solutions = [None, []]
			),

			# With --autounmask-backtrack=y:
			#emerge: there are no ebuilds built with USE flags to satisfy "app-misc/D[foo]".
			#!!! One of the following packages is required to complete your request:
			#- app-misc/D-0::test_repo (Change USE: +foo)
			#(dependency required by "app-misc/B-0::test_repo" [ebuild])
			#(dependency required by "app-misc/B" [argument])

			# Without --autounmask-backtrack=y:
			#[ebuild  N     ] app-misc/D-0  USE="foo"
			#[ebuild  N     ] app-misc/D-1  USE="-bar"
			#[ebuild  N     ] app-misc/C-0
			#[ebuild  N     ] app-misc/B-0
			#[ebuild  N     ] app-misc/A-0
			#
			#!!! Multiple package instances within a single package slot have been pulled
			#!!! into the dependency graph, resulting in a slot conflict:
			#
			#app-misc/D:0
			#
			#  (app-misc/D-0:0/0::test_repo, ebuild scheduled for merge) pulled in by
			#    app-misc/D[-foo] required by (app-misc/A-0:0/0::test_repo, ebuild scheduled for merge)
			#               ^^^^
			#    app-misc/D[foo] required by (app-misc/B-0:0/0::test_repo, ebuild scheduled for merge)
			#               ^^^
			#
			#  (app-misc/D-1:0/0::test_repo, ebuild scheduled for merge) pulled in by
			#    >=app-misc/D-1 required by (app-misc/C-0:0/0::test_repo, ebuild scheduled for merge)
			#    ^^           ^
			#
			#The following USE changes are necessary to proceed:
			# (see "package.use" in the portage(5) man page for more details)
			## required by app-misc/B-0::test_repo
			## required by app-misc/B (argument)
			#=app-misc/D-0 foo

			# NOTE: The --autounmask-backtrack=n output is preferable here,
			# because it highlights the unsolvable dependency conflict.
			# It would be better if it eliminated the autounmask suggestion,
			# since that suggestion won't solve the conflict.
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
