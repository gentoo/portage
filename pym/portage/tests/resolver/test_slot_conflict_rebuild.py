# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictRebuildTestCase(TestCase):

	def testSlotConflictRebuild(self):

		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/A:=",
				"RDEPEND": "app-misc/A:="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/D-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/E-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/D:=",
				"RDEPEND": "app-misc/D:="
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/A:0/1=",
				"RDEPEND": "app-misc/A:0/1="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/E-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/D:0/1=",
				"RDEPEND": "app-misc/D:0/1="
			},

		}

		world = ["app-misc/B", "app-misc/C", "app-misc/E"]

		test_cases = (

			# Test bug #439688, where a slot conflict prevents an
			# upgrade and we don't want to trigger unnecessary rebuilds.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["app-misc/D-2", "app-misc/E-0"]),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSlotConflictMassRebuild(self):
		"""
		Bug 486580
		Before this bug was fixed, emerge would backtrack for each package that needs
		a rebuild. This could cause it to hit the backtrack limit and not rebuild all
		needed packages.
		"""
		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B:=",
				"RDEPEND": "app-misc/B:="
			},

			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},

			"app-misc/B-2" : {
				"EAPI": "5",
				"SLOT": "2/2"
			},
		}

		installed = {
			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},
		}

		expected_mergelist = ['app-misc/A-1', 'app-misc/B-2']

		for i in xrange(5):
			ebuilds["app-misc/C%sC-1" % i] = {
				"EAPI": "5",
				"DEPEND": "app-misc/B:=",
				"RDEPEND": "app-misc/B:="
			}

			installed["app-misc/C%sC-1" % i] = {
				"EAPI": "5",
				"DEPEND": "app-misc/B:1/1=",
				"RDEPEND": "app-misc/B:1/1="
			}
			for x in ("DEPEND", "RDEPEND"):
				ebuilds["app-misc/A-1"][x] += " app-misc/C%sC" % i

			expected_mergelist.append("app-misc/C%sC-1" % i)


		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				ignore_mergelist_order=True,
				all_permutations=True,
				options = {"--backtrack": 3, '--deep': True},
				success = True,
				mergelist = expected_mergelist),
		)

		world = []

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=True)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
