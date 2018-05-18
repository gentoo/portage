# Copyright 2014-2018 Gentoo Foundation
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

			"app-misc/D-1" : {
				"EAPI": "6",
				"RDEPEND": "app-misc/E",
			},

			"app-misc/E-1" : {
				"EAPI": "6",
				"RDEPEND": "app-misc/F:=",
			},

			"app-misc/F-1" : {
				"EAPI": "6",
				"SLOT": "0/1"
			},

			"app-misc/F-2" : {
				"EAPI": "6",
				"SLOT": "0/2"
			},
		}

		binpkgs = {
			"app-misc/E-1" : {
				"EAPI": "6",
				"RDEPEND": "app-misc/F:0/1=",
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

			"app-misc/F-2" : {
				"EAPI": "6",
				"SLOT": "0/2"
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

			# Test bug #652938, where a binary package built against an
			# older subslot triggered downgrade of an installed package.
			# In this case we want to reject the app-misc/E-1 binary
			# package, and rebuild it against the installed instance of
			# app-misc/F.
			ResolverPlaygroundTestCase(
				["app-misc/D"],
				options = {'--usepkg': True},
				success = True,
				mergelist = ['app-misc/E-1', 'app-misc/D-1']
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
