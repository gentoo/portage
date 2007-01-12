# test_stackLists.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_vercmp.py 5213 2006-12-08 00:12:41Z antarus $

from unittest import TestCase
from portage_util import stack_lists

class StackListsTestCase(TestCase):
	
	def testStackLists(self):
		
		tests = [ ( [ ['a','b','c'], ['d','e','f'] ], ['a','c','b','e','d','f'], False ),
			  ( [ ['a','x'], ['b','x'] ], ['a','x','b'], False ),
			  ( [ ['a','b','c'], ['-*'] ], [], True ),
			  ( [ ['a'], ['-a'] ], [], True ) ]

		for test in tests:
			result = stack_lists( test[0], test[2] )
			self.failIf( result != test[1],
				msg="Got %s != %s from stack_lists( %s, %s )" \
				% ( result, test[1], test[0], test[2] ) )
