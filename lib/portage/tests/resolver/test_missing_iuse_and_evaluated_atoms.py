# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class MissingIUSEandEvaluatedAtomsTestCase(TestCase):

	def testMissingIUSEandEvaluatedAtoms(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "dev-libs/B[foo?]", "IUSE": "foo bar", "EAPI": 2 },
			"dev-libs/A-2": { "DEPEND": "dev-libs/B[foo?,bar]", "IUSE": "foo bar", "EAPI": 2 },
			"dev-libs/B-1": { "IUSE": "bar" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["=dev-libs/A-1"],
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-2"],
				success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
