# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskOrChoicesTestCase(TestCase):

	def testAutounmaskOrChoices(self):
		ebuilds = {
			'dev-libs/A-1': {
				'EAPI': '7',
				'RDEPEND': '|| ( dev-libs/B dev-libs/C )',
			},
			'dev-libs/C-1': {
				'EAPI': '7',
				'KEYWORDS': '~x86',
			},
			'dev-libs/D-1': {
				'EAPI': '7',
				'RDEPEND': '|| ( dev-libs/E dev-libs/F )',
			},
			'dev-libs/E-1': {
				'EAPI': '7',
				'KEYWORDS': '~x86',
			},
			'dev-libs/F-1': {
				'EAPI': '7',
				'KEYWORDS': 'x86',
			},
		}

		test_cases = (
			# Test bug 327177, where we want to prefer choices with masked
			# packages over those with nonexisting packages.
			ResolverPlaygroundTestCase(
				['dev-libs/A'],
				options={"--autounmask": True},
				success=False,
				mergelist=[
					'dev-libs/C-1',
					'dev-libs/A-1',
				],
				unstable_keywords = ('dev-libs/C-1',),
			),
			# Test that autounmask prefers choices with packages that
			# are not masked.
			ResolverPlaygroundTestCase(
				['dev-libs/D'],
				options={"--autounmask": True},
				success=True,
				mergelist=[
					'dev-libs/F-1',
					'dev-libs/D-1',
				],
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
