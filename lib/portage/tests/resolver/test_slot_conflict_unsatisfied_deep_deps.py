# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SlotConflictUnsatisfiedDeepDepsTestCase(TestCase):

	def testSlotConflictUnsatisfiedDeepDeps(self):

		ebuilds = {
			"dev-libs/A-1": { },
			"dev-libs/A-2": { "KEYWORDS": "~x86" },
			"dev-libs/B-1": { "DEPEND": "dev-libs/A" },
			"dev-libs/C-1": { "DEPEND": ">=dev-libs/A-2" },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A" },
		}

		installed = {
			"dev-libs/broken-1": {
				"RDEPEND": "dev-libs/A dev-libs/initially-unsatisfied"
			},
		}

		world = (
			"dev-libs/A",
			"dev-libs/B",
			"dev-libs/C",
			"dev-libs/D",
			"dev-libs/broken"
		)

		test_cases = (
			# Test bug #520950, where unsatisfied deps of installed
			# packages are supposed to be ignored when they are beyond
			# the depth requested by the user.
			ResolverPlaygroundTestCase(
				["dev-libs/B", "dev-libs/C", "dev-libs/D"],
				all_permutations=True,
				options={
					"--autounmask": "y",
					"--complete-graph": True
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=[],
				success=False),

			ResolverPlaygroundTestCase(
				["@world"],
				options={
					"--autounmask": "y",
					"--complete-graph": True
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=["dev-libs/broken"],
				success=False),

			# Test --selective with --deep = 0
			ResolverPlaygroundTestCase(
				["@world"],
				options={
					"--autounmask": "y",
					"--complete-graph": True,
					"--selective": True,
					"--deep": 0
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=[],
				success=False),

			# Test --deep = 1
			ResolverPlaygroundTestCase(
				["@world"],
				options={
					"--autounmask": "y",
					"--autounmask-backtrack": "y",
					"--complete-graph": True,
					"--selective": True,
					"--deep": 1
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=["dev-libs/initially-unsatisfied"],
				success=False),

			# With --autounmask-backtrack=y:
			#[ebuild  N    ~] dev-libs/A-2
			#[ebuild  N     ] dev-libs/C-1
			#[ebuild  N     ] dev-libs/D-1
			#[ebuild  N     ] dev-libs/B-1
			#
			#The following keyword changes are necessary to proceed:
			# (see "package.accept_keywords" in the portage(5) man page for more details)
			## required by dev-libs/C-1::test_repo
			## required by @selected
			## required by @world (argument)
			#=dev-libs/A-2 ~x86
			#
			#!!! Problems have been detected with your world file
			#!!! Please run emaint --check world
			#
			#
			#!!! Ebuilds for the following packages are either all
			#!!! masked or don't exist:
			#dev-libs/broken
			#
			#emerge: there are no ebuilds to satisfy "dev-libs/initially-unsatisfied".
			#(dependency required by "dev-libs/broken-1::test_repo" [installed])
			#(dependency required by "@selected" [set])
			#(dependency required by "@world" [argument])

			# Without --autounmask-backtrack=y:
			#!!! Multiple package instances within a single package slot have been pulled
			#!!! into the dependency graph, resulting in a slot conflict:
			#
			#dev-libs/A:0
			#
			#  (dev-libs/A-1:0/0::test_repo, ebuild scheduled for merge) pulled in by
			#    (no parents that aren't satisfied by other packages in this slot)
			#
			#  (dev-libs/A-2:0/0::test_repo, ebuild scheduled for merge) pulled in by
			#    >=dev-libs/A-2 required by (dev-libs/C-1:0/0::test_repo, ebuild scheduled for merge)
			#    ^^           ^
			#
			#The following keyword changes are necessary to proceed:
			# (see "package.accept_keywords" in the portage(5) man page for more details)
			## required by dev-libs/C-1::test_repo
			## required by @selected
			## required by @world (argument)
			#=dev-libs/A-2 ~x86
			#
			#emerge: there are no ebuilds to satisfy "dev-libs/initially-unsatisfied".
			#(dependency required by "dev-libs/broken-1::test_repo" [installed])
			#(dependency required by "@selected" [set])
			#(dependency required by "@world" [argument])

			# Test --deep = True
			ResolverPlaygroundTestCase(
				["@world"],
				options={
					"--autounmask": "y",
					"--autounmask-backtrack": "y",
					"--complete-graph": True,
					"--selective": True,
					"--deep": True
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=["dev-libs/initially-unsatisfied"],
				success=False),

			# The effects of --autounmask-backtrack are the same as the previous test case.
			# Both test cases can randomly succeed with --autounmask-backtrack=n, when
			# "backtracking due to unsatisfied dep" randomly occurs before the autounmask
			# unstable keyword change. It would be possible to eliminate backtracking here
			# by recognizing that there are no alternatives to satisfy the dev-libs/broken
			# atom in the world file. Then the test cases will consistently succeed with
			# --autounmask-backtrack=n.
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
