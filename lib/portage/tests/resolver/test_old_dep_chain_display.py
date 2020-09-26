# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class OldDepChainDisplayTestCase(TestCase):

	def testOldDepChainDisplay(self):
		ebuilds = {
			"dev-libs/A-1": { "DEPEND": "foo? ( dev-libs/B[-bar] )", "IUSE": "+foo", "EAPI": "2" },
			"dev-libs/A-2": { "DEPEND": "foo? ( dev-libs/C )", "IUSE": "+foo", "EAPI": "1" },
			"dev-libs/B-1": { "IUSE": "bar", "DEPEND": "!bar? ( dev-libs/D[-baz] )", "EAPI": "2" },
			"dev-libs/C-1": { "KEYWORDS": "~x86" },
			"dev-libs/D-1": { "IUSE": "+baz", "EAPI": "1" },
			}

		test_cases = (
			ResolverPlaygroundTestCase(
				["=dev-libs/A-1"],
				options = { "--autounmask": 'n' },
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-2"],
				options = { "--autounmask": 'n' },
				success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
