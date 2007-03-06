# test_uniqueArray.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.tests import TestCase
from portage.util import unique_array

class UniqueArrayTestCase(TestCase):
	
	def testUniqueArrayPass(self):
		"""
		test portage.util.uniqueArray()
		"""

		import os

		tests = [ ( ["a","a","a",os,os,[],[],[]], ['a',os,[]] ), 
			  ( [1,1,1,2,3,4,4] , [1,2,3,4]) ]

		for test in tests:
			result = unique_array( test[0] )
			for item in test[1]:
				number = result.count(item)
				self.failIf( number is not 1, msg="%s contains %s of %s, \
					should be only 1" % (result, number, item) )
