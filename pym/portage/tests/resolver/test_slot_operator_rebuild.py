# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorRebuildTestCase(TestCase):

	def testSlotOperatorRebuild(self):

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
				"RDEPEND": "app-misc/A:="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X app-misc/A:= )"
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:0/1="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X app-misc/A:0/1= )"
			},

		}

		world = ["app-misc/B", "app-misc/C"]

		test_cases = (

			# Test bug #522652, where the unsatisfiable app-misc/X
			# atom is selected, and the dependency is placed into
			# _initially_unsatisfied_deps where it is ignored, causing
			# the app-misc/C-0 rebuild to be missed.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {"--dynamic-deps": "n"},
				success = True,
				ambiguous_merge_order = True,
				mergelist = ['app-misc/A-2', ('app-misc/B-0', 'app-misc/C-0')]
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
