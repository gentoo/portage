# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SlotCollisionTestCase(TestCase):

	def testSlotCollision(self):

		ebuilds = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo" },
			"dev-libs/B-1": { "IUSE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "EAPI": 2 },
			"dev-libs/E-1": {  },
			"dev-libs/E-2": { "IUSE": "foo" },

			"app-misc/Z-1": { },
			"app-misc/Z-2": { },
			"app-misc/Y-1": { "DEPEND": "=app-misc/Z-1" },
			"app-misc/Y-2": { "DEPEND": ">app-misc/Z-1" },
			"app-misc/X-1": { "DEPEND": "=app-misc/Z-2" },
			"app-misc/X-2": { "DEPEND": "<app-misc/Z-2" },

			"sci-libs/K-1": { "IUSE": "+foo", "EAPI": 1 },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]", "EAPI": 2 },
			"sci-libs/M-1": { "DEPEND": "sci-libs/K[foo=]", "IUSE": "+foo", "EAPI": 2 },

			"sci-libs/Q-1": { "SLOT": "1", "IUSE": "+bar foo", "EAPI": 1 },
			"sci-libs/Q-2": { "SLOT": "2", "IUSE": "+bar +foo", "EAPI": 2, "PDEPEND": "sci-libs/Q:1[bar?,foo?]" },
			"sci-libs/P-1": { "DEPEND": "sci-libs/Q:1[foo=]", "IUSE": "foo", "EAPI": 2 },

			"sys-libs/A-1": { "RDEPEND": "foo? ( sys-libs/J[foo=] )", "IUSE": "+foo", "EAPI": "4" },
			"sys-libs/B-1": { "RDEPEND": "bar? ( sys-libs/J[bar=] )", "IUSE": "+bar", "EAPI": "4" },
			"sys-libs/C-1": { "RDEPEND": "sys-libs/J[bar]", "EAPI": "4" },
			"sys-libs/D-1": { "RDEPEND": "sys-libs/J[bar?]", "IUSE": "bar", "EAPI": "4" },
			"sys-libs/E-1": { "RDEPEND": "sys-libs/J[foo(+)?]", "IUSE": "+foo", "EAPI": "4" },
			"sys-libs/F-1": { "RDEPEND": "sys-libs/J[foo(+)]", "EAPI": "4" },
			"sys-libs/J-1": { "IUSE": "+foo", "EAPI": "4" },
			"sys-libs/J-2": { "IUSE": "+bar", "EAPI": "4" },

			"app-misc/A-1": { "IUSE": "foo +bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },
			"app-misc/B-1": { "DEPEND": "=app-misc/A-1[foo=]", "IUSE": "foo", "EAPI": 2 },
			"app-misc/C-1": { "DEPEND": "=app-misc/A-1[foo]", "EAPI": 2 },
			"app-misc/E-1": { "RDEPEND": "dev-libs/E[foo?]", "IUSE": "foo", "EAPI": "2" },
			"app-misc/F-1": { "RDEPEND": "=dev-libs/E-1", "IUSE": "foo", "EAPI": "2" },

			"dev-lang/perl-5.12": {"SLOT": "0/5.12", "EAPI": "5"},
			"dev-lang/perl-5.16": {"SLOT": "0/5.16", "EAPI": "5"},
			}
		installed = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo", "USE": "foo" },
			"dev-libs/B-1": { "IUSE": "foo", "USE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "USE": "foo", "EAPI": 2 },

			"sci-libs/K-1": { "IUSE": "foo", "USE": "" },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]" },

			"sci-libs/Q-1": { "SLOT": "1", "IUSE": "+bar +foo", "USE": "bar foo", "EAPI": 1 },
			"sci-libs/Q-2": { "SLOT": "2", "IUSE": "+bar +foo", "USE": "bar foo", "EAPI": 2, "PDEPEND": "sci-libs/Q:1[bar?,foo?]" },

			"app-misc/A-1": { "IUSE": "+foo bar", "USE": "foo", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },
			}

		test_cases = (
			#A qt-*[qt3support] like mess.
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B", "dev-libs/C", "dev-libs/D"],
				options = { "--autounmask": 'n' },
				success = False,
				mergelist = ["dev-libs/A-1", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = [ {"dev-libs/A-1": {"foo": True}, "dev-libs/D-1": {"foo": True}} ]),

			ResolverPlaygroundTestCase(
				["sys-libs/A", "sys-libs/B", "sys-libs/C", "sys-libs/D", "sys-libs/E", "sys-libs/F"],
				options = { "--autounmask": 'n' },
				success = False,
				ignore_mergelist_order = True,
				slot_collision_solutions = [],
				mergelist = ['sys-libs/J-2', 'sys-libs/J-1', 'sys-libs/A-1', 'sys-libs/B-1', 'sys-libs/C-1', 'sys-libs/D-1', 'sys-libs/E-1', 'sys-libs/F-1'],
				),

			#A version based conflicts, nothing we can do.
			ResolverPlaygroundTestCase(
				["=app-misc/X-1", "=app-misc/Y-1"],
				success = False,
				mergelist = ["app-misc/Z-1", "app-misc/Z-2", "app-misc/X-1", "app-misc/Y-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),
			ResolverPlaygroundTestCase(
				["=app-misc/X-2", "=app-misc/Y-2"],
				success = False,
				mergelist = ["app-misc/Z-1", "app-misc/Z-2", "app-misc/X-2", "app-misc/Y-2"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),

			ResolverPlaygroundTestCase(
				["=app-misc/E-1", "=app-misc/F-1"],
				success = False,
				mergelist = ["dev-libs/E-1", "dev-libs/E-2", "app-misc/E-1", "app-misc/F-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),

			# sub-slot
			ResolverPlaygroundTestCase(
				["dev-lang/perl:0/5.12", "dev-lang/perl:0/5.16", "=dev-lang/perl-5.12*"],
				success = False,
				mergelist = ["dev-lang/perl-5.12", "dev-lang/perl-5.16"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),

			#Simple cases.
			ResolverPlaygroundTestCase(
				["sci-libs/L", "sci-libs/M"],
				success = False,
				mergelist = ["sci-libs/L-1", "sci-libs/M-1", "sci-libs/K-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = [{"sci-libs/K-1": {"foo": False}, "sci-libs/M-1": {"foo": False}}]
				),

			#Avoid duplicates.
			ResolverPlaygroundTestCase(
				["sci-libs/P", "sci-libs/Q:2"],
				success = False,
				options = { "--update": True, "--complete-graph": True, "--autounmask": 'n' },
				mergelist = ["sci-libs/P-1", "sci-libs/Q-1"],
				ignore_mergelist_order = True,
				all_permutations=True,
				slot_collision_solutions = [{"sci-libs/Q-1": {"foo": True}, "sci-libs/P-1": {"foo": True}}]
				),

			)
			# NOTE: For this test case, ResolverPlaygroundTestCase attributes
			# vary randomly between runs, so it's expected to fail randomly.
			#Conflict with REQUIRED_USE
			#ResolverPlaygroundTestCase(
			#	["=app-misc/C-1", "=app-misc/B-1"],
			#	all_permutations = True,
			#	slot_collision_solutions = None,
			#	use_changes={"app-misc/A-1": {"foo": True}},
			#	mergelist = ["app-misc/A-1", "app-misc/C-1", "app-misc/B-1"],
			#	ignore_mergelist_order = True,
			#	success = False),
			#)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testConnectedCollision(self):
		"""
		Ensure that we are able to solve connected slot conflicts
		which cannot be solved each on their own.
		"""
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "=dev-libs/X-1" },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/X" },

			"dev-libs/X-1": { "RDEPEND": "=dev-libs/Y-1" },
			"dev-libs/X-2": { "RDEPEND": "=dev-libs/Y-2" },

			"dev-libs/Y-1": { "PDEPEND": "=dev-libs/X-1" },
			"dev-libs/Y-2": { "PDEPEND": "=dev-libs/X-2" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B"],
				all_permutations = True,
				options = { "--backtrack": 0 },
				success = True,
				ambiguous_merge_order = True,
				mergelist = ["dev-libs/Y-1", "dev-libs/X-1", ("dev-libs/A-1", "dev-libs/B-1")]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testDeeplyConnectedCollision(self):
		"""
		Like testConnectedCollision, except that there is another
		level of dependencies between the two conflicts.
		"""
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "=dev-libs/X-1" },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/X" },

			"dev-libs/X-1": { "RDEPEND": "dev-libs/K" },
			"dev-libs/X-2": { "RDEPEND": "dev-libs/L" },

			"dev-libs/K-1": { "RDEPEND": "=dev-libs/Y-1" },
			"dev-libs/L-1": { "RDEPEND": "=dev-libs/Y-2" },

			"dev-libs/Y-1": { "PDEPEND": "=dev-libs/X-1" },
			"dev-libs/Y-2": { "PDEPEND": "=dev-libs/X-2" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B"],
				all_permutations = True,
				options = { "--backtrack": 0 },
				success = True,
				ignore_mergelist_order = True,
				mergelist = ["dev-libs/Y-1", "dev-libs/X-1", "dev-libs/K-1", \
					"dev-libs/A-1", "dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSelfDEPENDRemovalCrash(self):
		"""
		Make sure we don't try to remove a packages twice. This happened
		in the past when a package had a DEPEND on itself.
		"""
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "=dev-libs/X-1" },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/X" },

			"dev-libs/X-1": { },
			"dev-libs/X-2": { "DEPEND": ">=dev-libs/X-2" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B"],
				all_permutations = True,
				success = True,
				ignore_mergelist_order = True,
				mergelist = ["dev-libs/X-1", "dev-libs/A-1", "dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
