# Copyright 2011-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CompleteGraphTestCase(TestCase):

	def testCompleteGraphUseChange(self):
		"""
		Prevent reverse dependency breakage triggered by USE changes.
		"""

		ebuilds = {
			"dev-libs/libxml2-2.8.0": {
				"EAPI": "2",
				"IUSE": "+icu",
				"SLOT": "2",
			},
			"x11-libs/qt-webkit-4.8.2": {
				"EAPI": "2",
				"IUSE": "icu",
				"RDEPEND" : "dev-libs/libxml2:2[!icu?]",
			},
		}

		installed = {
			"dev-libs/libxml2-2.8.0": {
				"EAPI": "2",
				"IUSE": "+icu",
				"USE": "",
				"SLOT": "2",
			},
			"x11-libs/qt-webkit-4.8.2": {
				"EAPI": "2",
				"IUSE": "icu",
				"RDEPEND" : "dev-libs/libxml2:2[-icu]",
				"USE": "",
			}
		}

		world = ["x11-libs/qt-webkit"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/libxml2"],
				options = {"--complete-graph-if-new-use" : "y" },
				mergelist = ["dev-libs/libxml2-2.8.0"],
				slot_collision_solutions = [{'dev-libs/libxml2-2.8.0': {'icu': False}}],
				success = False,
			),

			ResolverPlaygroundTestCase(
				["dev-libs/libxml2"],
				options = {"--complete-graph-if-new-use" : "n" },
				mergelist = ["dev-libs/libxml2-2.8.0"],
				success = True,
			),

			ResolverPlaygroundTestCase(
				["dev-libs/libxml2"],
				options = {"--ignore-world" : True},
				mergelist = ["dev-libs/libxml2-2.8.0"],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testCompleteGraphVersionChange(self):
		"""
		Prevent reverse dependency breakage triggered by version changes.
		"""

		ebuilds = {
			"sys-libs/x-0.1": {},
			"sys-libs/x-1": {},
			"sys-libs/x-2": {},
			"sys-apps/a-1": {"RDEPEND" : ">=sys-libs/x-1 <sys-libs/x-2"},
		}

		installed = {
			"sys-libs/x-1": {},
			"sys-apps/a-1": {"RDEPEND" : ">=sys-libs/x-1 <sys-libs/x-2"},
		}

		world = ["sys-apps/a"]

		test_cases = (
			ResolverPlaygroundTestCase(
				[">=sys-libs/x-2"],
				options = {"--complete-graph-if-new-ver" : "n", "--rebuild-if-new-slot": "n"},
				mergelist = ["sys-libs/x-2"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				[">=sys-libs/x-2"],
				options = {"--ignore-world" : True},
				mergelist = ["sys-libs/x-2"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				[">=sys-libs/x-2"],
				options = {"--complete-graph-if-new-ver" : "y"},
				mergelist = ["sys-libs/x-2"],
				slot_collision_solutions = [],
				success = False,
			),
			ResolverPlaygroundTestCase(
				["<sys-libs/x-1"],
				options = {"--complete-graph-if-new-ver" : "n", "--rebuild-if-new-slot": "n"},
				mergelist = ["sys-libs/x-0.1"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				["<sys-libs/x-1"],
				options = {"--ignore-world" : True},
				mergelist = ["sys-libs/x-0.1"],
				success = True,
			),
			ResolverPlaygroundTestCase(
				["<sys-libs/x-1"],
				options = {"--complete-graph-if-new-ver" : "y"},
				mergelist = ["sys-libs/x-0.1"],
				slot_collision_solutions = [],
				success = False,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
