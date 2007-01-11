# test_match_from_list.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_atoms.py 5525 2007-01-10 13:35:03Z antarus $

from unittest import TestCase
from portage_dep import get_operator

class GetOperator(TestCase):

	def testGetOperator(self):

		# get_operator does not validate operators
		tests = [ ( "~", "~" ), ( "=", "=" ), ( ">", ">" ),
			  ( ">=", ">=" ), ( "<=", "<=" ) , ( "", None ),
			  ( ">~", ">" ), ("~<", "~"), ( "=~", "=" ),
			  ( "=>", "=" ), ("=<", "=") ]

		testCP = "sys-apps/portage"

		for test in tests:
			result = get_operator( test[0] + testCP )
			self.failIf( result != test[1],
				msg="Expected %s from get_operator( %s ), got \
					%s" % ( test[1], test[0] + testCP, result ) )

		result = get_operator( "=sys-apps/portage*" )
		self.failIf( result != "=*",
				msg="Expected %s from get_operator( %s ), got \
					%s" % ( "=*", "=sys-apps/portage*", result ) )
