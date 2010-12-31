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
			"dev-libs/A-5": {"EAPI": EAPI_4, "IUSE": "+foo +bar", "REQUIRED_USE": "|| ( )"},

			"dev-libs/B-1": {"EAPI": EAPI_4, "IUSE": "foo bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-2": {"EAPI": EAPI_4, "IUSE": "foo +bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-3": {"EAPI": EAPI_4, "IUSE": "+foo bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-4": {"EAPI": EAPI_4, "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-5": {"EAPI": EAPI_4, "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( )"},

			"dev-libs/C-1" : {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "foo? ( !bar )"},
			"dev-libs/C-2" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "foo? ( !bar )"},
			"dev-libs/C-3" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "foo? ( bar )"},
			"dev-libs/C-4" : {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "foo? ( bar )"},
			"dev-libs/C-5" : {"EAPI": "4", "IUSE": "foo bar",   "REQUIRED_USE": "foo? ( bar )"},
			"dev-libs/C-6" : {"EAPI": "4", "IUSE": "foo +bar",  "REQUIRED_USE": "foo? ( bar )"},
			"dev-libs/C-7" : {"EAPI": "4", "IUSE": "foo +bar",  "REQUIRED_USE": "!foo? ( bar )"},
			"dev-libs/C-8" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "!foo? ( bar )"},
			"dev-libs/C-9" : {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "!foo? ( bar )"},
			"dev-libs/C-10": {"EAPI": "4", "IUSE": "foo bar",   "REQUIRED_USE": "!foo? ( bar )"},
			"dev-libs/C-11": {"EAPI": "4", "IUSE": "foo bar",   "REQUIRED_USE": "!foo? ( !bar )"},
			"dev-libs/C-12": {"EAPI": "4", "IUSE": "foo +bar",  "REQUIRED_USE": "!foo? ( !bar )"},
			"dev-libs/C-13": {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "!foo? ( !bar )"},
			"dev-libs/C-14": {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "!foo? ( !bar )"},
			}

		test_cases = (
			ResolverPlaygroundTestCase(["=dev-libs/A-1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-2"], success = True, mergelist=["dev-libs/A-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-3"], success = True, mergelist=["dev-libs/A-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-4"], success = True, mergelist=["dev-libs/A-4"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-5"], success = True, mergelist=["dev-libs/A-5"]),

			ResolverPlaygroundTestCase(["=dev-libs/B-1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/B-2"], success = True, mergelist=["dev-libs/B-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/B-3"], success = True, mergelist=["dev-libs/B-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/B-4"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/B-5"], success = True, mergelist=["dev-libs/B-5"]),

			ResolverPlaygroundTestCase(["=dev-libs/C-1"],  success = True, mergelist=["dev-libs/C-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-2"],  success = False),
			ResolverPlaygroundTestCase(["=dev-libs/C-3"],  success = True, mergelist=["dev-libs/C-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-4"],  success = False),
			ResolverPlaygroundTestCase(["=dev-libs/C-5"],  success = True, mergelist=["dev-libs/C-5"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-6"],  success = True, mergelist=["dev-libs/C-6"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-7"],  success = True, mergelist=["dev-libs/C-7"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-8"],  success = True, mergelist=["dev-libs/C-8"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-9"],  success = True, mergelist=["dev-libs/C-9"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-10"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/C-11"], success = True, mergelist=["dev-libs/C-11"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-12"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/C-13"], success = True, mergelist=["dev-libs/C-13"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-14"], success = True, mergelist=["dev-libs/C-14"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
