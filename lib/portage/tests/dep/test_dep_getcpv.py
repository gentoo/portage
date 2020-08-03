# test_dep_getcpv.py -- Portage Unit Testing Functionality
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import dep_getcpv

class DepGetCPV(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testDepGetCPV(self):

		prefix_ops = [
			"<", ">", "=", "~", "<=",
			">=", "!=", "!<", "!>", "!~"
		]

		bad_prefix_ops = [">~", "<~", "~>", "~<"]
		postfix_ops = [("=", "*"),]

		cpvs = ["sys-apps/portage-2.1", "sys-apps/portage-2.1",
				"sys-apps/portage-2.1"]
		slots = [None, ":foo", ":2"]
		for cpv in cpvs:
			for slot in slots:
				for prefix in prefix_ops:
					mycpv = prefix + cpv
					if slot:
						mycpv += slot
					self.assertEqual(dep_getcpv(mycpv), cpv)

				for prefix, postfix in postfix_ops:
					mycpv = prefix + cpv + postfix
					if slot:
						mycpv += slot
					self.assertEqual(dep_getcpv(mycpv), cpv)
