# test_dep_getcpv.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_atoms.py 5525 2007-01-10 13:35:03Z antarus $

from unittest import TestCase
from portage_dep import dep_getcpv

class DepGetCPV(TestCase):
        """ A simple testcase for isvalidatom
        """

        def testDepGetCPV(self):
		
		prefix_ops = ["<", ">", "=", "~", "!", "<=", 
			      ">=", "!=", "!<", "!>", "!~",""]
		postfix_ops = [ "*", "" ]

		cpvs = ["sys-apps/portage"]

		for cpv in cpvs:
			for prefix in prefix_ops:
				for postfix in postfix_ops:
					self.assertEqual( dep_getcpv( 
						prefix + cpv + postfix ), cpv )
