# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import \
	ResolverPlayground, ResolverPlaygroundTestCase

class WithTestDepsTestCase(TestCase):

	def testWithTestDeps(self):
		ebuilds = {
			"app-misc/A-0": {
				"EAPI": "5",
				"IUSE": "test",
				"DEPEND": "test? ( app-misc/B )"
			},
			"app-misc/B-0": {
				"EAPI": "5",
				"IUSE": "test",
				"DEPEND": "test? ( app-misc/C )"
			},
			"app-misc/C-0": {
				"EAPI": "5",
			}
		}

		test_cases = (
			# Test that --with-test-deps only pulls in direct
			# test deps of packages matched by arguments.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				options = { "--onlydeps": True, "--with-test-deps": True },
				mergelist = ["app-misc/B-0"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.cleanup()
