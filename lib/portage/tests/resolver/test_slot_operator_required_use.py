# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorRequiredUseTestCase(TestCase):

	def testSlotOperatorRequiredUse(self):

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
				"RDEPEND": "app-misc/A:=",
				"IUSE": "x y",
				"REQUIRED_USE": "|| ( x y )"
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:0/1=",
				"IUSE": "x y",
				"USE": "x"
			},

		}

		world = ["app-misc/B"]

		test_cases = (

			# bug 523048
			# Ensure that unsatisfied REQUIRED_USE is reported when
			# it blocks necessary slot-operator rebuilds.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = False,
				required_use_unsatisfied = ['app-misc/B:0']
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
