# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CircularChoicesTestCase(TestCase):

	def testDirectCircularDependency(self):

		ebuilds = {
			"dev-lang/gwydion-dylan-2.4.0": {"DEPEND": "|| ( dev-lang/gwydion-dylan dev-lang/gwydion-dylan-bin )" },
			"dev-lang/gwydion-dylan-bin-2.4.0": {},
		}

		test_cases = (
			# Automatically pull in gwydion-dylan-bin to solve a circular dep
			ResolverPlaygroundTestCase(
				["dev-lang/gwydion-dylan"],
				mergelist = ['dev-lang/gwydion-dylan-bin-2.4.0', 'dev-lang/gwydion-dylan-2.4.0'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
