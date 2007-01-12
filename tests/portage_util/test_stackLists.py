# test_stackLists.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

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
			self.assertEqual( result , test[1] )
