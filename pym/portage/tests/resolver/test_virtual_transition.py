# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class VirtualTransitionTestCase(TestCase):

	def testVirtualTransition(self):
		ebuilds = {
			"kde-base/kcron-4.7.1" : {"RDEPEND": "virtual/cron" },
			"sys-process/vixie-cron-4.1-r11": {},
			"virtual/cron-0" : {"RDEPEND": "sys-process/vixie-cron" },
		}
		installed = {
			"kde-base/kcron-4.7.1" : {"RDEPEND": "virtual/cron" },
			"sys-process/vixie-cron-4.1-r11" : {"PROVIDE" : "virtual/cron"},
		}

		world = ["kde-base/kcron", "sys-process/vixie-cron"]

		test_cases = (

			# Pull in a new-style virtual, even though there is an installed
			# old-style virtual to satisfy the virtual/cron dep. This case
			# is common, due to PROVIDE being removed (without revision bump)
			# from lots of ebuilds.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["virtual/cron-0"]),

			# Make sure that depclean is satisfied with the installed
			# old-style virutal.
			ResolverPlaygroundTestCase(
				[],
				options = {"--depclean": True},
				success = True,
				cleanlist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
