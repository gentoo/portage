# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class EAPITestCase(TestCase):

	def testEAPI(self):

		ebuilds = {
			#EAPI-1: IUSE-defaults
			"dev-libs/A-1.0": { "EAPI": 0, "IUSE": "+foo" },
			"dev-libs/A-1.1": { "EAPI": 1, "IUSE": "+foo" },
			"dev-libs/A-1.2": { "EAPI": 2, "IUSE": "+foo" },
			"dev-libs/A-1.3": { "EAPI": 3, "IUSE": "+foo" },
			"dev-libs/A-1.4": { "EAPI": "4", "IUSE": "+foo" },

			#EAPI-1: slot deps
			"dev-libs/A-2.0": { "EAPI": 0, "DEPEND": "dev-libs/B:0" },
			"dev-libs/A-2.1": { "EAPI": 1, "DEPEND": "dev-libs/B:0" },
			"dev-libs/A-2.2": { "EAPI": 2, "DEPEND": "dev-libs/B:0" },
			"dev-libs/A-2.3": { "EAPI": 3, "DEPEND": "dev-libs/B:0" },
			"dev-libs/A-2.4": { "EAPI": "4", "DEPEND": "dev-libs/B:0" },

			#EAPI-2: use deps
			"dev-libs/A-3.0": { "EAPI": 0, "DEPEND": "dev-libs/B[foo]" },
			"dev-libs/A-3.1": { "EAPI": 1, "DEPEND": "dev-libs/B[foo]" },
			"dev-libs/A-3.2": { "EAPI": 2, "DEPEND": "dev-libs/B[foo]" },
			"dev-libs/A-3.3": { "EAPI": 3, "DEPEND": "dev-libs/B[foo]" },
			"dev-libs/A-3.4": { "EAPI": "4", "DEPEND": "dev-libs/B[foo]" },

			#EAPI-2: strong blocks
			"dev-libs/A-4.0": { "EAPI": 0, "DEPEND": "!!dev-libs/B" },
			"dev-libs/A-4.1": { "EAPI": 1, "DEPEND": "!!dev-libs/B" },
			"dev-libs/A-4.2": { "EAPI": 2, "DEPEND": "!!dev-libs/B" },
			"dev-libs/A-4.3": { "EAPI": 3, "DEPEND": "!!dev-libs/B" },
			"dev-libs/A-4.4": { "EAPI": "4", "DEPEND": "!!dev-libs/B" },

			#EAPI-4: slot operator deps
			#~ "dev-libs/A-5.0": { "EAPI": 0, "DEPEND": "dev-libs/B:*" },
			#~ "dev-libs/A-5.1": { "EAPI": 1, "DEPEND": "dev-libs/B:*" },
			#~ "dev-libs/A-5.2": { "EAPI": 2, "DEPEND": "dev-libs/B:*" },
			#~ "dev-libs/A-5.3": { "EAPI": 3, "DEPEND": "dev-libs/B:*" },
			#~ "dev-libs/A-5.4": { "EAPI": "4", "DEPEND": "dev-libs/B:*" },

			#EAPI-4: use dep defaults
			"dev-libs/A-6.0": { "EAPI": 0, "DEPEND": "dev-libs/B[bar(+)]" },
			"dev-libs/A-6.1": { "EAPI": 1, "DEPEND": "dev-libs/B[bar(+)]" },
			"dev-libs/A-6.2": { "EAPI": 2, "DEPEND": "dev-libs/B[bar(+)]" },
			"dev-libs/A-6.3": { "EAPI": 3, "DEPEND": "dev-libs/B[bar(+)]" },
			"dev-libs/A-6.4": { "EAPI": "4", "DEPEND": "dev-libs/B[bar(+)]" },

			#EAPI-4: REQUIRED_USE
			"dev-libs/A-7.0": { "EAPI": 0, "IUSE": "foo bar", "REQUIRED_USE": "|| ( foo bar )" },
			"dev-libs/A-7.1": { "EAPI": 1, "IUSE": "foo +bar", "REQUIRED_USE": "|| ( foo bar )" },
			"dev-libs/A-7.2": { "EAPI": 2, "IUSE": "foo +bar", "REQUIRED_USE": "|| ( foo bar )" },
			"dev-libs/A-7.3": { "EAPI": 3, "IUSE": "foo +bar", "REQUIRED_USE": "|| ( foo bar )" },
			"dev-libs/A-7.4": { "EAPI": "4", "IUSE": "foo +bar", "REQUIRED_USE": "|| ( foo bar )" },

			"dev-libs/B-1": {"EAPI": 1, "IUSE": "+foo"},

			#EAPI-7: implicit || ( ) no longer satisfies deps
			"dev-libs/C-1": { "EAPI": "6", "IUSE": "foo", "RDEPEND": "|| ( foo? ( dev-libs/B ) )" },
			"dev-libs/C-2": { "EAPI": "7", "IUSE": "foo", "RDEPEND": "|| ( foo? ( dev-libs/B ) )" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(["=dev-libs/A-1.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-1.1"], success = True, mergelist = ["dev-libs/A-1.1"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-1.2"], success = True, mergelist = ["dev-libs/A-1.2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-1.3"], success = True, mergelist = ["dev-libs/A-1.3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-1.4"], success = True, mergelist = ["dev-libs/A-1.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-2.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-2.1"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-2.1"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-2.2"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-2.2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-2.3"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-2.3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-2.4"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-2.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-3.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-3.1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-3.2"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-3.2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-3.3"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-3.3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-3.4"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-3.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-4.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-4.1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-4.2"], success = True, mergelist = ["dev-libs/A-4.2"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-4.3"], success = True, mergelist = ["dev-libs/A-4.3"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-4.4"], success = True, mergelist = ["dev-libs/A-4.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-5.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-5.1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-5.2"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-5.3"], success = False),
			# not implemented: EAPI-4: slot operator deps
			#~ ResolverPlaygroundTestCase(["=dev-libs/A-5.4"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-5.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-6.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-6.1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-6.2"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-6.3"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-6.4"], success = True, mergelist = ["dev-libs/B-1", "dev-libs/A-6.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/A-7.0"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-7.1"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-7.2"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-7.3"], success = False),
			ResolverPlaygroundTestCase(["=dev-libs/A-7.4"], success = True, mergelist = ["dev-libs/A-7.4"]),

			ResolverPlaygroundTestCase(["=dev-libs/C-1"], success = True, mergelist = ["dev-libs/C-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/C-2"], success = False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
