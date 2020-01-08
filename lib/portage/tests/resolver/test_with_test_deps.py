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
			},
			"app-misc/D-0": {
				"EAPI": "5",
				"IUSE": "test",
				"DEPEND": "test? ( app-misc/E )"
			},
			"app-misc/E-0": {
				"EAPI": "5",
				"IUSE": "test",
				"DEPEND": "test? ( app-misc/D )"
			},
			"app-misc/F-0": {
				"EAPI": "5",
				"IUSE": "+test",
				"DEPEND": "test? ( app-misc/G )"
			},
			"app-misc/G-0": {
				"EAPI": "5",
				"IUSE": "+test",
				"DEPEND": "test? ( app-misc/F )"
			},
		}

		test_cases = (
			# Test that --with-test-deps only pulls in direct
			# test deps of packages matched by arguments.
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				options = { "--onlydeps": True, "--with-test-deps": True },
				mergelist = ["app-misc/B-0"]),

			# Test that --with-test-deps allows circular dependencies.
			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = True,
				options = {'--with-test-deps': True},
				mergelist = [('app-misc/D-0', 'app-misc/E-0')],
				ambiguous_merge_order=True),

			# Test that --with-test-deps does not allow circular dependencies
			# when USE=test is explicitly enabled.
			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = False,
				options = {'--with-test-deps': True},
				circular_dependency_solutions = {'app-misc/G-0': {frozenset({('test', False)})}, 'app-misc/F-0': {frozenset({('test', False)})}},
			)
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.cleanup()
