# Copyright 2017-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)


class AutounmaskUseSlotConflictTestCase(TestCase):
	def testAutounmaskUseSlotConflict(self):
		self.todo = True

		ebuilds = {
			"sci-libs/K-1": {"IUSE": "+foo", "EAPI": 1},
			"sci-libs/L-1": {"DEPEND": "sci-libs/K[-foo]", "EAPI": 2},
			"sci-libs/M-1": {"DEPEND": "sci-libs/K[foo=]", "IUSE": "+foo", "EAPI": 2},
		}

		installed = {}

		test_cases = (
			# Test bug 615824, where an automask USE change results in
			# a conflict which is not reported. In order to install L,
			# foo must be disabled for both K and M, but autounmask
			# disables foo for K and leaves it enabled for M.
			ResolverPlaygroundTestCase(
				["sci-libs/L", "sci-libs/M"],
				options={"--backtrack": 0},
				success=False,
				mergelist=[
					"sci-libs/L-1",
					"sci-libs/M-1",
					"sci-libs/K-1",
				],
				ignore_mergelist_order=True,
				slot_collision_solutions=[
					{"sci-libs/K-1": {"foo": False}, "sci-libs/M-1": {"foo": False}}
				],
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
