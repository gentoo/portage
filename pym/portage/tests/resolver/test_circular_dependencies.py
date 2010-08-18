# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class CircularDependencyTestCase(TestCase):

	def testCircularDependency(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "foo? ( =dev-libs/B-1 )", "IUSE": "+foo", "EAPI": 1 }, 
			"dev-libs/A-2": { "DEPEND": "=dev-libs/B-1" }, 
			"dev-libs/A-3": { "DEPEND": "foo? ( =dev-libs/B-2 )", "IUSE": "+foo", "EAPI": 1 }, 
			"dev-libs/B-1": { "DEPEND": "dev-libs/C dev-libs/D" }, 
			"dev-libs/B-2": { "DEPEND": "bar? ( dev-libs/C dev-libs/D )", "IUSE": "+bar", "EAPI": 1 }, 
			"dev-libs/C-1": { "DEPEND": "dev-libs/A" }, 
			"dev-libs/D-1": { "DEPEND": "dev-libs/E " }, 
			"dev-libs/E-1": { "DEPEND": "dev-libs/F" }, 
			"dev-libs/F-1": { "DEPEND": "dev-libs/B" }, 
			
			"dev-libs/Z-1": { "DEPEND": "!baz? ( dev-libs/Y )", "IUSE": "baz" }, 
			"dev-libs/Y-1": { "DEPEND": "dev-libs/Z" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["=dev-libs/A-1"],
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-2"],
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-3"],
				success = False),
			ResolverPlaygroundTestCase(
				["dev-libs/Z"],
				success = False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
