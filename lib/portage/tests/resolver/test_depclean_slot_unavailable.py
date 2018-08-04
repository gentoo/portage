# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class DepcleanUnavailableSlotTestCase(TestCase):

	def testDepcleanUnavailableSlot(self):
		"""
		Test bug #445506, where we want to remove the slot
		for which the ebuild is no longer available, even
		though its version is higher.
		"""

		ebuilds = {
			"sys-kernel/gentoo-sources-3.0.53": {
				"SLOT": "3.0.53",
				"KEYWORDS": "x86"
			},
		}

		installed = {
			"sys-kernel/gentoo-sources-3.0.53": {
				"SLOT": "3.0.53",
				"KEYWORDS": "x86"
			},
			"sys-kernel/gentoo-sources-3.2.21": {
				"SLOT": "3.2.21",
				"KEYWORDS": "x86"
			},
		}

		world = ["sys-kernel/gentoo-sources"]

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["sys-kernel/gentoo-sources-3.2.21"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

		# Now make the newer version availale and verify that
		# the lower version is depcleaned.
		ebuilds.update({
			"sys-kernel/gentoo-sources-3.2.21": {
				"SLOT": "3.2.21",
				"KEYWORDS": "x86"
			},
		})

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["sys-kernel/gentoo-sources-3.0.53"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
