# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class TargetRootTestCase(TestCase):

	def testTargetRoot(self):
		ebuilds = {
			"dev-lang/python-3.2": {
				"EAPI": "5-hdepend",
				"IUSE": "targetroot",
				"HDEPEND": "targetroot? ( ~dev-lang/python-3.2 )",
			}, 
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {},
				success = True,
				mergelist = ["dev-lang/python-3.2", "dev-lang/python-3.2{targetroot}"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, targetroot=True,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {},
				success = True,
				mergelist = ["dev-lang/python-3.2"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, targetroot=False,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
