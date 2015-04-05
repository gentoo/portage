# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import \
	ResolverPlayground, ResolverPlaygroundTestCase

class SlotOperatorUpdateProbeParentDowngradeTestCase(TestCase):

	def testSlotOperatorUpdateProbeParentDowngrade(self):

		ebuilds = {
			"net-nds/openldap-2.4.40-r3": {
				"EAPI": "5",
				"RDEPEND": "<sys-libs/db-6.0:= " + \
					"|| ( sys-libs/db:5.3 sys-libs/db:5.1 )"
			},
			"net-nds/openldap-2.4.40": {
				"EAPI": "5",
				"RDEPEND": "sys-libs/db"
			},
			"sys-libs/db-6.0": {
				"SLOT": "6.0",
			},
			"sys-libs/db-5.3": {
				"SLOT": "5.3",
			},
		}

		installed = {
			"net-nds/openldap-2.4.40-r3": {
				"EAPI": "5",
				"RDEPEND": "<sys-libs/db-6.0:5.3/5.3= " + \
					"|| ( sys-libs/db:5.3 sys-libs/db:5.1 )"
			},
			"sys-libs/db-6.0": {
				"SLOT": "6.0",
			},
			"sys-libs/db-5.3": {
				"SLOT": "5.3",
			},
		}

		world = (
			"net-nds/openldap",
		)

		test_cases = (
			# bug 528610 - openldap rebuild was triggered
			# inappropriately, due to slot_operator_update_probe
			# selecting an inappropriate replacement parent of
			# a lower version than desired.
			ResolverPlaygroundTestCase(
				["@world"],
				success = True,
				options = { "--update": True, "--deep": True },
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.cleanup()
