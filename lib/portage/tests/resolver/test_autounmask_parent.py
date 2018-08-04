# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskParentTestCase(TestCase):

	def testAutounmaskParentUse(self):

		ebuilds = {
			"dev-libs/B-1": {
				"EAPI": "5",
				"DEPEND": "dev-libs/D[foo(-)?,bar(-)?]",
				"IUSE": "+bar +foo",
			},
			"dev-libs/D-1": {},
		}

		test_cases = (
			# Test bug 566704
			ResolverPlaygroundTestCase(
				["=dev-libs/B-1"],
				options={"--autounmask": True},
				success=False,
				use_changes={
					"dev-libs/B-1": {
						"foo": False,
						"bar": False,
					}
				}),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
