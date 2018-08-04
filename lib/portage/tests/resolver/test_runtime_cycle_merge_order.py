# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)


class RuntimeCycleMergeOrderTestCase(TestCase):

	def testRuntimeCycleMergeOrder(self):
		ebuilds = {
			'app-misc/plugins-consumer-1' : {
				'EAPI': '6',
				'DEPEND' : 'app-misc/plugin-b:=',
				'RDEPEND' : 'app-misc/plugin-b:=',
			},
			'app-misc/plugin-b-1' : {
				'EAPI': '6',
				'RDEPEND' : 'app-misc/runtime-cycle-b',
				'PDEPEND': 'app-misc/plugins-consumer',
			},
			'app-misc/runtime-cycle-b-1' : {
				'RDEPEND' : 'app-misc/plugin-b app-misc/branch-b',
			},
			'app-misc/branch-b-1' : {
				'RDEPEND' : 'app-misc/leaf-b app-misc/branch-c',
			},
			'app-misc/leaf-b-1' : {},
			'app-misc/branch-c-1' : {
				'RDEPEND' : 'app-misc/runtime-cycle-c app-misc/runtime-c',
			},
			'app-misc/runtime-cycle-c-1' : {
				'RDEPEND' : 'app-misc/branch-c',
			},
			'app-misc/runtime-c-1' : {
				'RDEPEND' : 'app-misc/branch-d',
			},
			'app-misc/branch-d-1' : {
				'RDEPEND' : 'app-misc/leaf-d app-misc/branch-e',
			},
			'app-misc/branch-e-1' : {
				'RDEPEND' : 'app-misc/leaf-e',
			},
			'app-misc/leaf-d-1' : {},
			'app-misc/leaf-e-1' : {},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['app-misc/plugin-b'],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					('app-misc/leaf-b-1', 'app-misc/leaf-d-1', 'app-misc/leaf-e-1'),
					('app-misc/branch-d-1', 'app-misc/branch-e-1'),
					'app-misc/runtime-c-1',
					('app-misc/runtime-cycle-c-1', 'app-misc/branch-c-1'),
					'app-misc/branch-b-1',
					('app-misc/runtime-cycle-b-1', 'app-misc/plugin-b-1'),
					'app-misc/plugins-consumer-1',
				],
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
