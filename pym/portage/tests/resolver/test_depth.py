# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class ResolverDepthTestCase(TestCase):

	def testResolverDepth(self):

		ebuilds = {
			"dev-libs/A-1": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/A-2": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/B-1": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/B-2": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/C-1": {},
			"dev-libs/C-2": {},
			}

		installed = {
			"dev-libs/A-1": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/B-1": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/C-1": {},
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 0},
				success = True,
				mergelist = ["dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 1},
				success = True,
				mergelist = ["dev-libs/B-2", "dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 3},
				success = True,
				mergelist = ["dev-libs/C-2", "dev-libs/B-2", "dev-libs/A-2"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
