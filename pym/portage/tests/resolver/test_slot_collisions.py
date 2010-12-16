# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SlotCollisionTestCase(TestCase):

	def testSlotCollision(self):

		EAPI_4 = '4_pre1'

		ebuilds = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo" }, 
			"dev-libs/B-1": { "IUSE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "EAPI": 2 },
			"dev-libs/E-1": {  },
			"dev-libs/E-2": { "IUSE": "foo" },

			"app-misc/Z-1": { },
			"app-misc/Z-2": { },
			"app-misc/Y-1": { "DEPEND": "=app-misc/Z-1" },
			"app-misc/Y-2": { "DEPEND": ">app-misc/Z-1" },
			"app-misc/X-1": { "DEPEND": "=app-misc/Z-2" },
			"app-misc/X-2": { "DEPEND": "<app-misc/Z-2" },

			"sci-libs/K-1": { "IUSE": "+foo", "EAPI": 1 },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]", "EAPI": 2 },
			"sci-libs/M-1": { "DEPEND": "sci-libs/K[foo=]", "IUSE": "+foo", "EAPI": 2 },

			"app-misc/A-1": { "IUSE": "foo +bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": EAPI_4 },
			"app-misc/B-1": { "DEPEND": "=app-misc/A-1[foo=]", "IUSE": "foo", "EAPI": 2 },
			"app-misc/C-1": { "DEPEND": "=app-misc/A-1[foo]", "EAPI": 2 },
			"app-misc/E-1": { "RDEPEND": "dev-libs/E[foo?]", "IUSE": "foo", "EAPI": "2" },
			"app-misc/F-1": { "RDEPEND": "=dev-libs/E-1", "IUSE": "foo", "EAPI": "2" },
			}
		installed = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo", "USE": "foo" }, 
			"dev-libs/B-1": { "IUSE": "foo", "USE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "USE": "foo", "EAPI": 2 },
			
			"sci-libs/K-1": { "IUSE": "foo", "USE": "" },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]" },

			"app-misc/A-1": { "IUSE": "+foo bar", "USE": "foo", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": EAPI_4 },
			}

		test_cases = (
			#A qt-*[qt3support] like mess.
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B", "dev-libs/C", "dev-libs/D"],
				success = False,
				mergelist = ["dev-libs/A-1", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = [ {"dev-libs/A-1": {"foo": True}, "dev-libs/D-1": {"foo": True}} ]),

			#A version based conflicts, nothing we can do.
			ResolverPlaygroundTestCase(
				["=app-misc/X-1", "=app-misc/Y-1"],
				success = False,
				mergelist = ["app-misc/Z-1", "app-misc/Z-2", "app-misc/X-1", "app-misc/Y-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),
			ResolverPlaygroundTestCase(
				["=app-misc/X-2", "=app-misc/Y-2"],
				success = False,
				mergelist = ["app-misc/Z-1", "app-misc/Z-2", "app-misc/X-2", "app-misc/Y-2"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),

			ResolverPlaygroundTestCase(
				["=app-misc/E-1", "=app-misc/F-1"],
				success = False,
				mergelist = ["dev-libs/E-1", "dev-libs/E-2", "app-misc/E-1", "app-misc/F-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = []
				),

			#Simple cases.
			ResolverPlaygroundTestCase(
				["sci-libs/L", "sci-libs/M"],
				success = False,
				mergelist = ["sci-libs/L-1", "sci-libs/M-1", "sci-libs/K-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = [{"sci-libs/K-1": {"foo": False}, "sci-libs/M-1": {"foo": False}}]
				),

			#Conflict with REQUIRED_USE
			ResolverPlaygroundTestCase(
				["=app-misc/C-1", "=app-misc/B-1"],
				all_permutations = True,
				slot_collision_solutions = [],
				mergelist = ["app-misc/A-1", "app-misc/C-1", "app-misc/B-1"],
				ignore_mergelist_order = True,
				success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
