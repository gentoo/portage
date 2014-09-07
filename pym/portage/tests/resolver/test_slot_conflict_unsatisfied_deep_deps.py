# Copyright 2014 Gentoo Foundation
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
					"--complete-graph": True,
					"--selective": True,
					"--deep": 1
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=["dev-libs/initially-unsatisfied"],
				success=False),

			# Test --deep = True
			ResolverPlaygroundTestCase(
				["@world"],
				options={
					"--autounmask": "y",
					"--complete-graph": True,
					"--selective": True,
					"--deep": True
				},
				mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order=True,
				unstable_keywords=["dev-libs/A-2"],
				unsatisfied_deps=["dev-libs/initially-unsatisfied"],
				success=False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
