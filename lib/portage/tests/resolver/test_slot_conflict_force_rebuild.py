# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictForceRebuildTestCase(TestCase):

	def testSlotConflictForceRebuild(self):

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
				"RDEPEND": "app-misc/A"
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
				"RDEPEND": "app-misc/A:0/1="
			},

		}

		world = ["app-misc/B", "app-misc/C"]

		test_cases = (

			# Test bug #521990, where forced_rebuilds omits ebuilds that
			# had have had their slot operator atoms removed from the
			# ebuilds, even though the corresponding installed
			# instances had really forced rebuilds due to being built
			# with slot-operators in their deps.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {},
				success = True,
				ambiguous_merge_order = True,
				mergelist = ['app-misc/A-2', ('app-misc/B-0', 'app-misc/C-0')],
				forced_rebuilds = {
					'app-misc/A-2': ['app-misc/B-0', 'app-misc/C-0']
				}
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
