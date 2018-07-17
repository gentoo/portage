# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SimpleDepcleanTestCase(TestCase):

	def testSimpleDepclean(self):

		ebuilds = {
			"dev-libs/A-1": {
				"EAPI": "5",
				"RDEPEND": "dev-libs/B:=",
			},
			"dev-libs/B-1": {
				"EAPI": "5",
				"RDEPEND": "dev-libs/A",
			},
			"dev-libs/C-1": {},
		}

		installed = {
			"dev-libs/A-1": {
				"EAPI": "5",
				"RDEPEND": "dev-libs/B:0/0=",
			},
			"dev-libs/B-1": {
				"EAPI": "5",
				"RDEPEND": "dev-libs/A",
			},
			"dev-libs/C-1": {},
		}

		world = (
			"dev-libs/C",
		)

		test_cases = (
			# Remove dev-libs/A-1 first because of dev-libs/B:0/0= (built
			# slot-operator dep).
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				ordered=True,
				cleanlist=["dev-libs/A-1", "dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
