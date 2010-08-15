# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SimpleResolverTestCase(TestCase):

	def testSimple(self):
		ebuilds = {
			"dev-libs/A-1": {}, 
			"dev-libs/A-2": { "KEYWORDS": "~x86" },
			"dev-libs/B-1.2": {},
			}
		installed = {
			"dev-libs/B-1.1": {},
			}

		test_cases = (
			ResolverPlaygroundTestCase(["dev-libs/A"], success = True, mergelist = ["dev-libs/A-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-2"], success = False),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--noreplace": True},
				success = True,
				mergelist = []),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--update": True},
				success = True,
				mergelist = ["dev-libs/B-1.2"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
