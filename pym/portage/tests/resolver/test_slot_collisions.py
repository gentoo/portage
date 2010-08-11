# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SlotCollisionTestCase(TestCase):

	def testSlotCollision(self):

		ebuilds = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo" }, 
			"dev-libs/B-1": { "IUSE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "EAPI": 2 },

			"app-misc/Z-1": { },
			"app-misc/Z-2": { },
			"app-misc/Y-1": { "DEPEND": "=app-misc/Z-1" },
			"app-misc/X-1": { "DEPEND": "=app-misc/Z-2" },

			"sci-libs/K-1": { "IUSE": "+foo", "EAPI": 1 },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]", "EAPI": 2 },
			"sci-libs/M-1": { "DEPEND": "sci-libs/K[foo=]", "IUSE": "+foo", "EAPI": 2 },
			}
		installed = {
			"dev-libs/A-1": { "PDEPEND": "foo? ( dev-libs/B )", "IUSE": "foo", "USE": "foo" }, 
			"dev-libs/B-1": { "IUSE": "foo", "USE": "foo" },
			"dev-libs/C-1": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A[foo=] dev-libs/B[foo=]", "IUSE": "foo", "USE": "foo", "EAPI": 2 },
			
			"sci-libs/K-1": { "IUSE": "foo", "USE": "" },
			"sci-libs/L-1": { "DEPEND": "sci-libs/K[-foo]" },
			}

		test_cases = (
			#A qt-*[qt3support] like mess.
			ResolverPlaygroundTestCase(
				["dev-libs/A", "dev-libs/B", "dev-libs/C", "dev-libs/D"],
				success = False,
				mergelist = ["dev-libs/A-1", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
				ignore_mergelist_order = True,
				slot_collision_solutions = [ {"dev-libs/A-1": {"foo": True}, "dev-libs/D-1": {"foo": True}} ]),

			#A version based conflict, nothing we can do.
			ResolverPlaygroundTestCase(
				["app-misc/X", "app-misc/Y"],
				success = False,
				mergelist = ["app-misc/Z-1", "app-misc/Z-2", "app-misc/X-1", "app-misc/Y-1"],
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
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
