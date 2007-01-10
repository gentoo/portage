# test_vercmp.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_vercmp.py 5213 2006-12-08 00:12:41Z antarus $

from unittest import TestCase, TestLoader

class UtilTestCase(TestCase):
	
	def testUniqueArray(self):
		pass
		
	def testVarexpand(self):
		pass
		
	def testStackLists(self):
		pass
	
	def testStackDicts(self):
		pass
	
	def testStackDictList(self):
		from portage_util import stack_dictlist
		
		tests = [ ({'a':'b'},{'x':'y'},False,{'a':['b'],'x':['y']}) ]
		tests.append(( {'KEYWORDS':['alpha','x86']},{'KEYWORDS':['-*']},True,{} ))
		tests.append(( {'KEYWORDS':['alpha','x86']},{'KEYWORDS':['-x86']},True,{'KEYWORDS':['alpha']} ))
		for test in tests:
			self.failUnless(stack_dictlist([test[0],test[1]],incremental=test[2]) == test[3],
				msg="%s and %s combined, was expecting: %s and got: %s" % (test[0],test[1],test[3],
				stack_dictlist([test[0],test[1]],incremental=test[2])) )

	def testNormalizePath(self):
		
		from portage_util import normalize_path
		path = "///foo/bar/baz"
		good = "/foo/bar/baz"
		self.failUnless(normalize_path(path) == good, msg="NormalizePath(%s) failed to produce %s" % (path, good))

