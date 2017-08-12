# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskKeepKeywordsTestCase(TestCase):

	def testAutounmaskKeepKeywordsTestCase(self):
		ebuilds = {
			'app-misc/A-2': {
				'EAPI': '6',
				'RDEPEND': 'app-misc/B',
			},
			'app-misc/A-1': {
				'EAPI': '6',
				'RDEPEND': 'app-misc/C[foo]',
			},
			'app-misc/B-1': {
				'EAPI': '6',
				'KEYWORDS': '~x86',
			},
			'app-misc/C-1': {
				'EAPI': '6',
				'IUSE': 'foo',
			},
		}
		installed = {
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = False,
				options = {
					'--autounmask-keep-keywords': 'n',
				},
				mergelist = [
				    'app-misc/B-1',
				    'app-misc/A-2',
				],
				unstable_keywords={'app-misc/B-1'},
			),
			# --autounmask-keep-keywords prefers app-misc/A-1 because
			# it can be installed without accepting unstable
			# keywords
			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = False,
				options = {
					'--autounmask-keep-keywords': 'y',
				},
				mergelist = [
				    'app-misc/C-1',
				    'app-misc/A-1',
				],
				use_changes = {'app-misc/C-1': {'foo': True}},
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
