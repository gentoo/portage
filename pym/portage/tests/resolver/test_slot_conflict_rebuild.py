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

		}

		world = ["app-misc/B", "app-misc/C"]

		test_cases = (

			# Demonstrate bug #439688, where a slot conflict prevents
			# an upgrade and triggers unnecessary rebuilds.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["app-misc/A-1", "app-misc/B-0"]),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
