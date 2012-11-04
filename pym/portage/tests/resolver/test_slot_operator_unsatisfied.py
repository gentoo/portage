# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorUnsatisfiedTestCase(TestCase):

	def testSlotOperatorUnsatisfied(self):

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
		}

		installed = {
			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/A:0/1=",
				"RDEPEND": "app-misc/A:0/1="
			},
		}

		world = ["app-misc/B"]

		test_cases = (

			# Demonstrate bug #439694, where a broken slot-operator
			# sub-slot dependency needs to trigger a rebuild.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["app-misc/B-0"]),

			# This doesn't trigger a rebuild, since there's no version
			# change to trigger complete graph mode, and initially
			# unsatisfied deps are ignored in complete graph mode anyway.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["app-misc/A-2"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
