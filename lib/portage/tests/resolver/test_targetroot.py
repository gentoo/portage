# Copyright 2012-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class TargetRootTestCase(TestCase):

	def testTargetRoot(self):
		ebuilds = {
			"dev-lang/python-3.2": {
				"EAPI": "7",
				"BDEPEND": "~dev-lang/python-3.2",
			},
			"dev-libs/A-1": {
				"EAPI": "4",
				"DEPEND": "dev-libs/B",
				"RDEPEND": "dev-libs/C",
			},
			"dev-libs/B-1": {},
			"dev-libs/C-1": {},
		}

		installed = {
			"dev-lang/python-3.2": {
				"EAPI": "7",
				"BDEPEND": "~dev-lang/python-3.2",
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {},
				success = True,
				mergelist = ["dev-lang/python-3.2{targetroot}"]),
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {"--root-deps": True},
				success = True,
				mergelist = ["dev-lang/python-3.2{targetroot}"]),
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {"--root-deps": "rdeps"},
				success = True,
				mergelist = ["dev-lang/python-3.2{targetroot}"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {},
				ambiguous_merge_order = True,
				success = True,
				mergelist = [("dev-libs/B-1", "dev-libs/C-1{targetroot}"), "dev-libs/A-1{targetroot}"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--root-deps": True},
				ambiguous_merge_order = True,
				success = True,
				mergelist = [("dev-libs/B-1{targetroot}", "dev-libs/C-1{targetroot}"), "dev-libs/A-1{targetroot}"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--root-deps": "rdeps"},
				ambiguous_merge_order = True,
				success = True,
				mergelist = [("dev-libs/C-1{targetroot}"), "dev-libs/A-1{targetroot}"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, targetroot=True,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-lang/python"],
				options = {},
				success = True,
				mergelist = ["dev-lang/python-3.2"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, targetroot=False,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
