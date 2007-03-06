# test_dep_getcpv.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.tests import TestCase
from portage.dep import dep_getcpv

class DepGetCPV(TestCase):
	""" A simple testcase for isvalidatom
	"""

	def testDepGetCPV(self):
		
		prefix_ops = ["<", ">", "=", "~", "!", "<=", 
			      ">=", "!=", "!<", "!>", "!~",""]

		bad_prefix_ops = [ ">~", "<~", "~>", "~<" ]
		postfix_ops = [ "*", "" ]

		cpvs = ["sys-apps/portage", "sys-apps/portage-2.1", "sys-apps/portage-2.1",
				"sys-apps/portage-2.1"]
		slots = [None,":",":2"]
		for cpv in cpvs:
			for slot in slots:
				for prefix in prefix_ops:
					for postfix in postfix_ops:
						if slot:
							self.assertEqual( dep_getcpv( 
								prefix + cpv + slot + postfix ), cpv )
						else:
							self.assertEqual( dep_getcpv( 
								prefix + cpv + postfix ), cpv )
				for prefix in bad_prefix_ops:
					for postfix in postfix_ops:
						if slot:
							self.assertNotEqual( dep_getcpv(
								prefix + cpv + slot + postfix ), cpv )
						else:
							self.assertNotEqual( dep_getcpv(
								prefix + cpv + postfix ), cpv )