# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import sys
import time
import unittest
from unittest import TestResult

from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import _unicode_decode

def main():

	TEST_FILE = _unicode_encode('__test__',
		encoding=_encodings['fs'], errors='strict')
	svn_dirname = _unicode_encode('.svn',
		encoding=_encodings['fs'], errors='strict')
	suite = unittest.TestSuite()
	basedir = os.path.dirname(os.path.realpath(__file__))
	testDirs = []

  # the os.walk help mentions relative paths as being quirky
	# I was tired of adding dirs to the list, so now we add __test__
	# to each dir we want tested.
	for root, dirs, files in os.walk(basedir):
		if svn_dirname in dirs:
			dirs.remove(svn_dirname)
		try:
			root = _unicode_decode(root,
				encoding=_encodings['fs'], errors='strict')
		except UnicodeDecodeError:
			continue

		if TEST_FILE in files:
			testDirs.append(root)

	for mydir in testDirs:
		suite.addTests(getTests(os.path.join(basedir, mydir), basedir) )
	return TextTestRunner(verbosity=2).run(suite)

def my_import(name):
	mod = __import__(name)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def getTests(path, base_path):
	"""

	path is the path to a given subdir ( 'portage/' for example)
	This does a simple filter on files in that dir to give us modules
	to import

	"""
	files = os.listdir(path)
	files = [ f[:-3] for f in files if f.startswith("test") and f.endswith(".py") ]
	parent_path = path[len(base_path)+1:]
	parent_module = ".".join(("portage", "tests", parent_path))
	parent_module = parent_module.replace('/', '.')
	result = []
	for mymodule in files:
		# Make the trailing / a . for module importing
		modname = ".".join((parent_module, mymodule))
		mod = my_import(modname)
		result.append(unittest.TestLoader().loadTestsFromModule(mod))
	return result

class TextTestResult(TestResult):
	"""
	We need a subclass of unittest.TestResult to handle tests with TODO
	Most of this class is copied from the unittest._TextTestResult that's
	included with python-2.6 (but not included with python-2.7).

	This just adds an addTodo method that can be used to add tests
	that are marked TODO; these can be displayed later
	by the test runner.
	"""

	separator1 = '=' * 70
	separator2 = '-' * 70

	def __init__(self, stream, descriptions, verbosity):
		unittest.TestResult.__init__(self)
		self.stream = stream
		self.showAll = verbosity > 1
		self.dots = verbosity == 1
		self.descriptions = descriptions
		self.todoed = []

	def addTodo(self, test, info):
		self.todoed.append((test,info))
		if self.showAll:
			self.stream.writeln("TODO")
		elif self.dots:
			self.stream.write(".")

	def printErrors(self):
		if self.dots or self.showAll:
			self.stream.writeln()
			self.printErrorList('ERROR', self.errors)
			self.printErrorList('FAIL', self.failures)
			self.printErrorList('TODO', self.todoed)

	def getDescription(self, test):
		if self.descriptions:
			return test.shortDescription() or str(test)
		else:
			return str(test)

	def startTest(self, test):
		TestResult.startTest(self, test)
		if self.showAll:
			self.stream.write(self.getDescription(test))
			self.stream.write(" ... ")
			self.stream.flush()

	def addSuccess(self, test):
		TestResult.addSuccess(self, test)
		if self.showAll:
			self.stream.writeln("ok")
		elif self.dots:
			self.stream.write('.')
			self.stream.flush()

	def addError(self, test, err):
		TestResult.addError(self, test, err)
		if self.showAll:
			self.stream.writeln("ERROR")
		elif self.dots:
			self.stream.write('E')
			self.stream.flush()

	def addFailure(self, test, err):
		TestResult.addFailure(self, test, err)
		if self.showAll:
			self.stream.writeln("FAIL")
		elif self.dots:
			self.stream.write('F')
			self.stream.flush()

	def printErrorList(self, flavour, errors):
		for test, err in errors:
			self.stream.writeln(self.separator1)
			self.stream.writeln("%s: %s" % (flavour,self.getDescription(test)))
			self.stream.writeln(self.separator2)
			self.stream.writeln("%s" % err)

class TestCase(unittest.TestCase):
	"""
	We need a way to mark a unit test as "ok to fail"
	This way someone can add a broken test and mark it as failed
	and then fix the code later.  This may not be a great approach
	(broken code!!??!11oneone) but it does happen at times.
	"""
	
	def __init__(self, methodName='runTest'):
		# This method exists because unittest.py in python 2.4 stores
		# the methodName as __testMethodName while 2.5 uses
		# _testMethodName.
		self._testMethodName = methodName
		unittest.TestCase.__init__(self, methodName)
		self.todo = False
		
	def defaultTestResult(self):
		return TextTestResult()

	def run(self, result=None):
		if result is None: result = self.defaultTestResult()
		result.startTest(self)
		testMethod = getattr(self, self._testMethodName)
		try:
			try:
				self.setUp()
			except KeyboardInterrupt:
				raise
			except:
				result.addError(self, sys.exc_info())
				return
			ok = False
			try:
				testMethod()
				ok = True
			except self.failureException:
				if self.todo:
					result.addTodo(self,"%s: TODO" % testMethod)
				else:
					result.addFailure(self, sys.exc_info())
			except (KeyboardInterrupt, SystemExit):
				raise
			except:
				result.addError(self, sys.exc_info())
			try:
				self.tearDown()
			except KeyboardInterrupt:
				raise
			except:
				result.addError(self, sys.exc_info())
				ok = False
			if ok: result.addSuccess(self)
		finally:
			result.stopTest(self)
			
class TextTestRunner(unittest.TextTestRunner):
	"""
	We subclass unittest.TextTestRunner to output SKIP for tests that fail but are skippable
	"""
	
	def _makeResult(self):
	        return TextTestResult(self.stream, self.descriptions, self.verbosity)

	def run(self, test):
		"""
		Run the given test case or test suite.
		"""
		result = self._makeResult()
		startTime = time.time()
		test(result)
		stopTime = time.time()
		timeTaken = stopTime - startTime
		result.printErrors()
		self.stream.writeln(result.separator2)
		run = result.testsRun
		self.stream.writeln("Ran %d test%s in %.3fs" %
							(run, run != 1 and "s" or "", timeTaken))
		self.stream.writeln()
		if not result.wasSuccessful():
			self.stream.write("FAILED (")
			failed = len(result.failures)
			errored = len(result.errors)
			if failed:
				self.stream.write("failures=%d" % failed)
			if errored:
				if failed: self.stream.write(", ")
				self.stream.write("errors=%d" % errored)
			self.stream.writeln(")")
		else:
			self.stream.writeln("OK")
		return result
	
test_cps = ['sys-apps/portage','virtual/portage']
test_versions = ['1.0', '1.0-r1','2.3_p4','1.0_alpha57']
test_slots = [ None, '1','gentoo-sources-2.6.17','spankywashere']
test_usedeps = ['foo','-bar', ('foo','bar'),
	('foo','-bar'), ('foo?', '!bar?') ]
