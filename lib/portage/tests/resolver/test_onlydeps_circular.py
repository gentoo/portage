# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import \
	ResolverPlayground, ResolverPlaygroundTestCase

class OnlydepsTestCase(TestCase):

	def testOnlydeps(self):
		ebuilds = {
			"app-misc/A-1": {
				"EAPI": "5",
				"SLOT": "1",
				"DEPEND": "|| ( app-misc/B app-misc/A:1 )"
			},
			"app-misc/A-2": {
				"EAPI": "5",
				"SLOT": "2",
			},
			"app-misc/B-0": {
				"EAPI": "5",
			}
		}

		installed = {
			"app-misc/A-2": {
				"EAPI": "5",
				"SLOT": "2",
			}
		}

		test_cases = (
			# bug 524916 - direct circular dep should not pull
			# in an onlydeps node when possible
			ResolverPlaygroundTestCase(
				["app-misc/A:1"],
				success = True,
				options = { "--onlydeps": True },
				mergelist = ["app-misc/B-0"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.cleanup()
