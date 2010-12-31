# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class UseDepDefaultsTestCase(TestCase):

	def testUseDepDefaultse(self):

		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/B[foo]", "RDEPEND": "dev-libs/B[foo]", "EAPI": "2" },
			"dev-libs/A-2": { "DEPEND": "dev-libs/B[foo(+)]", "RDEPEND": "dev-libs/B[foo(+)]", "EAPI": "4" },
			"dev-libs/A-3": { "DEPEND": "dev-libs/B[foo(-)]", "RDEPEND": "dev-libs/B[foo(-)]", "EAPI": "4" },
			"dev-libs/B-1": { "IUSE": "+foo", "EAPI": "1" },
			"dev-libs/B-2": {},
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["=dev-libs/A-1"],
				success = True,
				mergelist = ["dev-libs/B-1", "dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-2"],
				success = True,
				mergelist = ["dev-libs/B-2", "dev-libs/A-2"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-3"],
				success = True,
				mergelist = ["dev-libs/B-1", "dev-libs/A-3"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
