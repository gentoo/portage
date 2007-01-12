# test_varExpand.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_vercmp.py 5213 2006-12-08 00:12:41Z antarus $

from unittest import TestCase, TestLoader
from portage_util import varexpand

class VarExpandTestCase(TestCase):
	
	def testVarExpandPass(self):

		varDict = { "a":"5", "b":"7", "c":"-5" }
		for key in varDict.keys():
			result = varexpand( "$%s" % key, varDict )
			
			self.failIf( result != varDict[key],
				msg="Got %s != %s, from varexpand( %s, %s )" % \
					( result, varDict[key], "$%s" % key, varDict ) )
			result = varexpand( "${%s}" % key, varDict )
			self.failIf( result != varDict[key],
				msg="Got %s != %s, from varexpand( %s, %s )" % \
					( result, varDict[key], "${%s}" % key, varDict ) )

	def testVarExpandDoubleQuotes(self):
		
		varDict = { "a":"5" }
		tests = [ ("\"${a}\"", "5") ]
		for test in tests:
			result = varexpand( test[0], varDict )
			self.failIf( result != test[1],
				msg="Got %s != %s from varexpand( %s, %s )" \
				% ( result, test[1], test[0], varDict ) )

	def testVarExpandSingleQuotes(self):
		
		varDict = { "a":"5" }
		tests = [ ("\'${a}\'", "${a}") ]
		for test in tests:
			result = varexpand( test[0], varDict )
			self.failIf( result != test[1],
				msg="Got %s != %s from varexpand( %s, %s )" \
				% ( result, test[1], test[0], varDict ) )

	def testVarExpandFail(self):

		varDict = { "a":"5", "b":"7", "c":"15" }

		testVars = [ "fail" ]

		for var in testVars:
			result = varexpand( "$%s" % var, varDict )
			self.failIf( len(result),
				msg="Got %s == %s, from varexpand( %s, %s )" \
					% ( result, var, "$%s" % var, varDict ) )

			result = varexpand( "${%s}" % var, varDict )
			self.failIf( len(result),
				msg="Got %s == %s, from varexpand( %s, %s )" \
					% ( result, var, "${%s}" % var, varDict ) )
