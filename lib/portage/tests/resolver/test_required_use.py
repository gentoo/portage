# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class RequiredUSETestCase(TestCase):

	def testRequiredUSE(self):
		"""
		Only simple REQUIRED_USE values here. The parser is tested under in dep/testCheckRequiredUse
		"""

		ebuilds = {
			"dev-libs/A-1" : {"EAPI": "4", "IUSE": "foo bar",   "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-2" : {"EAPI": "4", "IUSE": "foo +bar",  "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-3" : {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-4" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "|| ( foo bar )"},
			"dev-libs/A-5" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "|| ( )"},

			"dev-libs/B-1" : {"EAPI": "4", "IUSE": "foo bar",   "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-2" : {"EAPI": "4", "IUSE": "foo +bar",  "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-3" : {"EAPI": "4", "IUSE": "+foo bar",  "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-4" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( foo bar )"},
			"dev-libs/B-5" : {"EAPI": "4", "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( )"},

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

			"dev-libs/D-1" : {"EAPI": "4", "IUSE": "+w +x +y z",    "REQUIRED_USE": "w? ( x || ( y z ) )"},
			"dev-libs/D-2" : {"EAPI": "4", "IUSE": "+w +x +y +z",   "REQUIRED_USE": "w? ( x || ( y z ) )"},
			"dev-libs/D-3" : {"EAPI": "4", "IUSE": "+w +x y z",     "REQUIRED_USE": "w? ( x || ( y z ) )"},
			"dev-libs/D-4" : {"EAPI": "4", "IUSE": "+w x +y +z",    "REQUIRED_USE": "w? ( x || ( y z ) )"},
			"dev-libs/D-5" : {"EAPI": "4", "IUSE": "w x y z",       "REQUIRED_USE": "w? ( x || ( y z ) )"},

			"dev-libs/E-1" : {"EAPI": "5", "IUSE": "foo bar",   "REQUIRED_USE": "?? ( foo bar )"},
			"dev-libs/E-2" : {"EAPI": "5", "IUSE": "foo +bar",  "REQUIRED_USE": "?? ( foo bar )"},
			"dev-libs/E-3" : {"EAPI": "5", "IUSE": "+foo bar",  "REQUIRED_USE": "?? ( foo bar )"},
			"dev-libs/E-4" : {"EAPI": "5", "IUSE": "+foo +bar", "REQUIRED_USE": "?? ( foo bar )"},
			"dev-libs/E-5" : {"EAPI": "5", "IUSE": "+foo +bar", "REQUIRED_USE": "?? ( )"},

			"dev-libs/F-1" : {"EAPI": "7", "IUSE": "+foo +bar", "REQUIRED_USE": "|| ( )"},
			"dev-libs/F-2" : {"EAPI": "7", "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( )"},
			"dev-libs/F-3" : {"EAPI": "7", "IUSE": "+foo +bar", "REQUIRED_USE": "?? ( )"},
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

			ResolverPlaygroundTestCase(["=dev-libs/D-1"],  success = True, mergelist=["dev-libs/D-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/D-2"],  success = True, mergelist=["dev-libs/D-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/D-3"],  success = False),
			ResolverPlaygroundTestCase(["=dev-libs/D-4"],  success = False),
			ResolverPlaygroundTestCase(["=dev-libs/D-5"],  success = True, mergelist=["dev-libs/D-5"]),

			ResolverPlaygroundTestCase(["=dev-libs/E-1"], success = True, mergelist=["dev-libs/E-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/E-2"], success = True, mergelist=["dev-libs/E-2"]),
			ResolverPlaygroundTestCase(["=dev-libs/E-3"], success = True, mergelist=["dev-libs/E-3"]),
			ResolverPlaygroundTestCase(["=dev-libs/E-4"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/E-5"], success = True, mergelist=["dev-libs/E-5"]),

			ResolverPlaygroundTestCase(["=dev-libs/F-1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/F-2"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/F-3"], success = True, mergelist=["dev-libs/F-3"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testRequiredUseOrDeps(self):

		ebuilds = {
			"dev-libs/A-1": { "IUSE": "+x +y", "REQUIRED_USE": "^^ ( x y )", "EAPI": "4" },
			"dev-libs/B-1": { "IUSE": "+x +y", "REQUIRED_USE": "",           "EAPI": "4" },
			"app-misc/p-1": { "RDEPEND": "|| ( =dev-libs/A-1 =dev-libs/B-1 )" },
			}

		test_cases = (
				# This should fail and show a REQUIRED_USE error for
				# dev-libs/A-1, since this choice it preferred.
				ResolverPlaygroundTestCase(
					["=app-misc/p-1"],
					success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
