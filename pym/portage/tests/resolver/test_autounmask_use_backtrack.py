# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskUseBacktrackTestCase(TestCase):

	def testAutounmaskUseBacktrack(self):
		ebuilds = {
			'dev-libs/A-1': {
				'EAPI': '6',
				'RDEPEND': 'dev-libs/C',
			},
			'dev-libs/A-2': {
				'EAPI': '6',
				'RDEPEND': 'dev-libs/C[y]',
			},
			'dev-libs/A-3': {
				'EAPI': '6',
				'RDEPEND': 'dev-libs/C',
			},
			'dev-libs/B-1': {
				'EAPI': '6',
				'RDEPEND': '<dev-libs/A-3',
			},
			'dev-libs/C-1': {
				'EAPI': '6',
				'IUSE': 'x y z',
			},
			'dev-libs/D-1': {
				'EAPI': '6',
				'RDEPEND': '>=dev-libs/A-2 dev-libs/C[x]',
			},
		}

		installed = {
			'dev-libs/A-1': {
				'EAPI': '6',
				'RDEPEND': 'dev-libs/C',
			},
			'dev-libs/B-1': {
				'EAPI': '6',
				'RDEPEND': '<dev-libs/A-3',
			},
			'dev-libs/C-1': {
				'EAPI': '6',
				'IUSE': 'x y z',
			},
		}

		world = ['dev-libs/B']

		test_cases = (
			# Test bug 632598, where autounmask USE changes triggered
			# unnecessary backtracking. The following case should
			# require a --backtrack setting no larger than 2.
			ResolverPlaygroundTestCase(
				['dev-libs/D'],
				options={
					'--autounmask-backtrack': 'y',
					'--backtrack': 2,
				},
				success=False,
				ambiguous_merge_order=True,
				mergelist=[
					('dev-libs/C-1', 'dev-libs/A-2'),
					'dev-libs/D-1',
				],
				use_changes={'dev-libs/C-1': {'y': True, 'x': True}},
			),
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
