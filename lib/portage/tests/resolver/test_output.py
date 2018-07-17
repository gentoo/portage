# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class MergelistOutputTestCase(TestCase):

	def testMergelistOutput(self):
		"""
		This test doesn't check if the output is correct, but makes sure
		that we don't backtrace somewhere in the output code.
		"""
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/B dev-libs/C", "IUSE": "+foo", "EAPI": 1 },
			"dev-libs/B-1": { "DEPEND": "dev-libs/D", "IUSE": "foo +bar", "EAPI": 1 },
			"dev-libs/C-1": { "DEPEND": "dev-libs/E", "IUSE": "foo bar" },
			"dev-libs/D-1": { "IUSE": "" },
			"dev-libs/E-1": {},

			#reinstall for flags
			"dev-libs/Z-1": { "IUSE": "+foo", "EAPI": 1 },
			"dev-libs/Y-1": { "IUSE": "foo", "EAPI": 1 },
			"dev-libs/X-1": {},
			"dev-libs/W-1": { "IUSE": "+foo", "EAPI": 1 },
			}

		installed = {
			"dev-libs/Z-1": { "USE": "", "IUSE": "foo" },
			"dev-libs/Y-1": { "USE": "foo", "IUSE": "+foo", "EAPI": 1 },
			"dev-libs/X-1": { "USE": "foo", "IUSE": "+foo", "EAPI": 1 },
			"dev-libs/W-1": { },
		}

		option_cobos = (
			(),
			("verbose",),
			("tree",),
			("tree", "unordered-display",),
			("verbose",),
			("verbose", "tree",),
			("verbose", "tree", "unordered-display",),
		)

		test_cases = []
		for options in option_cobos:
			testcase_opts = {}
			for opt in options:
				testcase_opts["--" + opt] = True

			test_cases.append(ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = testcase_opts,
				success = True,
				ignore_mergelist_order=True,
				mergelist = ["dev-libs/D-1", "dev-libs/E-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"]))

			test_cases.append(ResolverPlaygroundTestCase(
				["dev-libs/Z"],
				options = testcase_opts,
				success = True,
				mergelist = ["dev-libs/Z-1"]))

			test_cases.append(ResolverPlaygroundTestCase(
				["dev-libs/Y"],
				options = testcase_opts,
				success = True,
				mergelist = ["dev-libs/Y-1"]))

			test_cases.append(ResolverPlaygroundTestCase(
				["dev-libs/X"],
				options = testcase_opts,
				success = True,
				mergelist = ["dev-libs/X-1"]))

			test_cases.append(ResolverPlaygroundTestCase(
				["dev-libs/W"],
				options = testcase_opts,
				success = True,
				mergelist = ["dev-libs/W-1"]))

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
