# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import cpvequal
from portage.exception import PortageException

class TestStandalone(TestCase):
	""" Test some small functions portage.dep
	"""

	def testCPVequal(self):

		test_cases = (
			("sys-apps/portage-2.1", "sys-apps/portage-2.1", True),
			("sys-apps/portage-2.1", "sys-apps/portage-2.0", False),
			("sys-apps/portage-2.1", "sys-apps/portage-2.1-r1", False),
			("sys-apps/portage-2.1-r1", "sys-apps/portage-2.1", False),
			("sys-apps/portage-2.1_alpha3", "sys-apps/portage-2.1", False),
			("sys-apps/portage-2.1_alpha3_p6", "sys-apps/portage-2.1_alpha3", False),
			("sys-apps/portage-2.1_alpha3", "sys-apps/portage-2.1", False),
			("sys-apps/portage-2.1", "sys-apps/X-2.1", False),
			("sys-apps/portage-2.1", "portage-2.1", False),
		)

		test_cases_xfail = (
			("sys-apps/portage", "sys-apps/portage"),
			("sys-apps/portage-2.1-6", "sys-apps/portage-2.1-6"),
		)

		for cpv1, cpv2, expected_result in test_cases:
			self.assertEqual(cpvequal(cpv1, cpv2), expected_result,
				"cpvequal('%s', '%s') != %s" % (cpv1, cpv2, expected_result))

		for cpv1, cpv2 in test_cases_xfail:
			self.assertRaisesMsg("cpvequal(%s, %s)" % (cpv1, cpv2),
				PortageException, cpvequal, cpv1, cpv2)
