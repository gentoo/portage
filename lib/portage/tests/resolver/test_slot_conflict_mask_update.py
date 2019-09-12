# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictMaskUpdateTestCase(TestCase):

	def testBacktrackingGoodVersionFirst(self):
		"""
		When backtracking due to slot conflicts, we masked the version that has been pulled
		in first. This is not always a good idea. Mask the highest version instead.
		"""

		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "=dev-libs/C-1 dev-libs/B" },
			"dev-libs/B-1": { "DEPEND": "=dev-libs/C-1" },
			"dev-libs/B-2": { "DEPEND": "=dev-libs/C-2" },
			"dev-libs/C-1": { },
			"dev-libs/C-2": { },
			}

		test_cases = (
				ResolverPlaygroundTestCase(
					["dev-libs/A"],
					mergelist = ["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1",],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
