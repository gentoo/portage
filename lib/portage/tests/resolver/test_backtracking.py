# Copyright 2010-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class BacktrackingTestCase(TestCase):

	def testBacktracking(self):
		ebuilds = {
			"dev-libs/A-1": {},
			"dev-libs/A-2": {},
			"dev-libs/B-1": { "DEPEND": "dev-libs/A" },
			}

		test_cases = (
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1", "dev-libs/B"],
					all_permutations = True,
					mergelist = ["dev-libs/A-1", "dev-libs/B-1"],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testBacktrackNotNeeded(self):
		ebuilds = {
			"dev-libs/A-1": {},
			"dev-libs/A-2": {},
			"dev-libs/B-1": {},
			"dev-libs/B-2": {},
			"dev-libs/C-1": { "DEPEND": "dev-libs/A dev-libs/B" },
			"dev-libs/D-1": { "DEPEND": "=dev-libs/A-1 =dev-libs/B-1" },
			}

		test_cases = (
				ResolverPlaygroundTestCase(
					["dev-libs/C", "dev-libs/D"],
					all_permutations = True,
					options = { "--backtrack": 1 },
					mergelist = ["dev-libs/A-1", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
					ignore_mergelist_order = True,
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testBacktrackWithoutUpdates(self):
		"""
		If --update is not given we might have to mask the old installed version later.
		"""

		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/Z" },
			"dev-libs/B-1": { "DEPEND": ">=dev-libs/Z-2" },
			"dev-libs/Z-1": { },
			"dev-libs/Z-2": { },
			}

		installed = {
			"dev-libs/Z-1": { "USE": "" },
			}

		test_cases = (
				ResolverPlaygroundTestCase(
					["dev-libs/B", "dev-libs/A"],
					all_permutations = True,
					mergelist = ["dev-libs/Z-2", "dev-libs/B-1", "dev-libs/A-1",],
					ignore_mergelist_order = True,
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testBacktrackMissedUpdates(self):
		"""
		An update is missed due to a dependency on an older version.
		"""

		ebuilds = {
			"dev-libs/A-1": { },
			"dev-libs/A-2": { },
			"dev-libs/B-1": { "RDEPEND": "<=dev-libs/A-1" },
			}

		installed = {
			"dev-libs/A-1": { "USE": "" },
			"dev-libs/B-1": { "USE": "", "RDEPEND": "<=dev-libs/A-1" },
			}

		options = {'--update' : True, '--deep' : True, '--selective' : True}

		test_cases = (
				ResolverPlaygroundTestCase(
					["dev-libs/A", "dev-libs/B"],
					options = options,
					all_permutations = True,
					mergelist = [],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testBacktrackNoWrongRebuilds(self):
		"""
		Ensure we remove backtrack masks if the reason for the mask gets masked itself.
		"""

		ebuilds = {
			"dev-libs/A-1": { },
			"dev-libs/A-2": { },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/D"},
			"dev-libs/C-1": { },
			"dev-libs/C-2": { "RDEPEND": ">=dev-libs/A-2" },
			"dev-libs/D-1": { "RDEPEND": "<dev-libs/A-2" },
			}

		installed = {
			"dev-libs/A-1": { },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/D" },
			"dev-libs/C-1": { },
			"dev-libs/D-1": { "RDEPEND": "<dev-libs/A-2" },
			}

		world = ["dev-libs/B", "dev-libs/C"]

		options = {
			'--backtrack': 6,
			'--deep' : True,
			'--selective' : True,
			'--update' : True,
		}

		test_cases = (
				ResolverPlaygroundTestCase(
					["@world"],
					options = options,
					mergelist = [],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
