# test_dep_getslot.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import dep_getslot

class DepGetSlot(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testDepGetSlot(self):

		slot_char = ":"
		slots = ("a", "1.2", "1", "IloveVapier", None)
		cpvs = ["sys-apps/portage"]
		versions = ["2.1.1", "2.1-r1"]
		for cpv in cpvs:
			for version in versions:
				for slot in slots:
					mycpv = cpv
					if version:
						mycpv = '=' + mycpv + '-' + version
					if slot is not None:
						self.assertEqual(dep_getslot(
							mycpv + slot_char + slot), slot)
					else:
						self.assertEqual(dep_getslot(mycpv), slot)
