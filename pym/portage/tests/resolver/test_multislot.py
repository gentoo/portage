# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class MultSlotTestCase(TestCase):

	def testMultiSlotSelective(self):
		"""
		Test that a package isn't reinstalled due to SLOT dependency
		interaction with USE=multislot (bug #220341).
		"""

		ebuilds = {
			"sys-devel/gcc-4.4.4": { "SLOT": "4.4" },
			}

		installed = {
			"sys-devel/gcc-4.4.4": { "SLOT": "i686-pc-linux-gnu-4.4.4" },
			}

		options = {'--update' : True, '--deep' : True, '--selective' : True}

		test_cases = (
				ResolverPlaygroundTestCase(
					["sys-devel/gcc:4.4"],
					options = options,
					mergelist = [],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
