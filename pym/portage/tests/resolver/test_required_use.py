# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class RequiredUSETestCase(TestCase):

	def testRequiredUSE(self):
		"""
		Only simple REQUIRED_USE values here. The parser is tested under in dep/testCheckRequiredUse
		"""
		EAPI_4 = '4_pre1'

		ebuilds = {
			"dev-libs/A-1": {"EAPI": EAPI_4, "IUSE": "foo bar", "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-2": {"EAPI": EAPI_4, "IUSE": "foo +bar", "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-3": {"EAPI": EAPI_4, "IUSE": "+foo bar", "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-4": {"EAPI": EAPI_4, "IUSE": "+foo +bar", "REQUIRED_USE": "|| ( foo bar )"},

			"dev-libs/B-1": {"EAPI": EAPI_4, "IUSE": "foo bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-2": {"EAPI": EAPI_4, "IUSE": "foo +bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-3": {"EAPI": EAPI_4, "IUSE": "+foo bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-4": {"EAPI": EAPI_4, "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( foo bar )"},
			}

		test_cases = (
			ResolverPlaygroundTestCase(["=dev-libs/A-1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-2"], success = True, mergelist=["dev-libs/A-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-3"], success = True, mergelist=["dev-libs/A-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-4"], success = True, mergelist=["dev-libs/A-4"]),

			ResolverPlaygroundTestCase(["=dev-libs/B-1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/B-2"], success = True, mergelist=["dev-libs/B-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/B-3"], success = True, mergelist=["dev-libs/B-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/B-4"], success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
