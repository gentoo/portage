# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import argparse
import sys
import time
import unittest

from unittest.runner import TextTestResult as _TextTestResult

import repoman
from repoman import REPOMAN_BASE_PATH
from repoman._portage import portage

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage.const import EPREFIX, GLOBAL_CONFIG_PATH, PORTAGE_BIN_PATH

if repoman._not_installed:
	cnf_path = os.path.join(REPOMAN_BASE_PATH, 'cnf')
	cnf_path_repoman = cnf_path
	cnf_etc_path = cnf_path
	cnf_bindir = os.path.join(REPOMAN_BASE_PATH, 'bin')
	cnf_sbindir = cnf_bindir
else:
	cnf_path = os.path.join(EPREFIX or '/', GLOBAL_CONFIG_PATH)
	cnf_path_repoman = os.path.join(EPREFIX or '/',
		sys.prefix.lstrip(os.sep), 'share', 'repoman')
	cnf_etc_path = os.path.join(EPREFIX or '/', 'etc')
	cnf_eprefix = EPREFIX
	cnf_bindir = os.path.join(EPREFIX or '/', 'usr', 'bin')
	cnf_sbindir = os.path.join(EPREFIX or '/', 'usr', 'sbin')


def main():
	suite = unittest.TestSuite()
	basedir = os.path.dirname(os.path.realpath(__file__))

	usage = "usage: %s [options] [tests to run]" % os.path.basename(sys.argv[0])
	parser = argparse.ArgumentParser(usage=usage)
	parser.add_argument("-l", "--list", help="list all tests",
		action="store_true", dest="list_tests")
	options, args = parser.parse_known_args(args=sys.argv)

	if (os.environ.get('NOCOLOR') in ('yes', 'true') or
		os.environ.get('TERM') == 'dumb' or
		not sys.stdout.isatty()):
		portage.output.nocolor()

	if options.list_tests:
		testdir = os.path.dirname(sys.argv[0])
		for mydir in getTestDirs(basedir):
			testsubdir = os.path.basename(mydir)
			for name in getTestNames(mydir):
				print("%s/%s/%s.py" % (testdir, testsubdir, name))
		return os.EX_OK

	if len(args) > 1:
		suite.addTests(getTestFromCommandLine(args[1:], basedir))
	else:
		for mydir in getTestDirs(basedir):
			suite.addTests(getTests(os.path.join(basedir, mydir), basedir))

	result = TextTestRunner(verbosity=2).run(suite)
	if not result.wasSuccessful():
		return 1
	return os.EX_OK

def my_import(name):
	mod = __import__(name)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def getTestFromCommandLine(args, base_path):
	result = []
	for arg in args:
		realpath = os.path.realpath(arg)
		path = os.path.dirname(realpath)
		f = realpath[len(path)+1:]

		if not f.startswith("test") or not f.endswith(".py"):
			raise Exception("Invalid argument: '%s'" % arg)

		mymodule = f[:-3]
		result.extend(getTestsFromFiles(path, base_path, [mymodule]))
	return result

def getTestDirs(base_path):
	TEST_FILE = b'__test__.py'
	testDirs = []

	# the os.walk help mentions relative paths as being quirky
	# I was tired of adding dirs to the list, so now we add __test__.py
	# to each dir we want tested.
	for root, dirs, files in os.walk(base_path):
		try:
			root = _unicode_decode(root,
				encoding=_encodings['fs'], errors='strict')
		except UnicodeDecodeError:
			continue

		if TEST_FILE in files:
			testDirs.append(root)

	testDirs.sort()
	return testDirs

def getTestNames(path):
	files = os.listdir(path)
	files = [f[:-3] for f in files if f.startswith("test") and f.endswith(".py")]
	files.sort()
	return files

def getTestsFromFiles(path, base_path, files):
	parent_path = path[len(base_path)+1:]
	parent_module = ".".join(("repoman", "tests", parent_path))
	parent_module = parent_module.replace('/', '.')
	result = []
	for mymodule in files:
		# Make the trailing / a . for module importing
		modname = ".".join((parent_module, mymodule))
		mod = my_import(modname)
		result.append(unittest.TestLoader().loadTestsFromModule(mod))
	return result

def getTests(path, base_path):
	"""

	path is the path to a given subdir ( 'portage/' for example)
	This does a simple filter on files in that dir to give us modules
	to import

	"""
	return getTestsFromFiles(path, base_path, getTestNames(path))

class TextTestResult(_TextTestResult):
	"""
	We need a subclass of unittest.runner.TextTestResult to handle tests with TODO

	This just adds an addTodo method that can be used to add tests
	that are marked TODO; these can be displayed later
	by the test runner.
	"""

	def __init__(self, stream, descriptions, verbosity):
		super(TextTestResult, self).__init__(stream, descriptions, verbosity)
		self.todoed = []
		self.portage_skipped = []

	def addTodo(self, test, info):
		self.todoed.append((test, info))
		if self.showAll:
			self.stream.writeln("TODO")
		elif self.dots:
			self.stream.write(".")

	def addPortageSkip(self, test, info):
		self.portage_skipped.append((test, info))
		if self.showAll:
			self.stream.writeln("SKIP")
		elif self.dots:
			self.stream.write(".")

	def printErrors(self):
		if self.dots or self.showAll:
			self.stream.writeln()
			self.printErrorList('ERROR', self.errors)
			self.printErrorList('FAIL', self.failures)
			self.printErrorList('TODO', self.todoed)
			self.printErrorList('SKIP', self.portage_skipped)

class TestCase(unittest.TestCase):
	"""
	We need a way to mark a unit test as "ok to fail"
	This way someone can add a broken test and mark it as failed
	and then fix the code later.  This may not be a great approach
	(broken code!!??!11oneone) but it does happen at times.
	"""

	def __init__(self, *pargs, **kwargs):
		unittest.TestCase.__init__(self, *pargs, **kwargs)
		self.todo = False
		self.portage_skip = None
		self.cnf_path = cnf_path
		self.cnf_etc_path = cnf_etc_path
		self.bindir = cnf_bindir
		self.sbindir = cnf_sbindir

	def defaultTestResult(self):
		return TextTestResult()

	def run(self, result=None):
		if result is None: result = self.defaultTestResult()
		result.startTest(self)
		testMethod = getattr(self, self._testMethodName)
		try:
			try:
				self.setUp()
			except SystemExit:
				raise
			except KeyboardInterrupt:
				raise
			except:
				result.addError(self, sys.exc_info())
				return

			ok = False
			try:
				testMethod()
				ok = True
			except unittest.SkipTest as e:
				result.addPortageSkip(self, "%s: SKIP: %s" %
					(testMethod, str(e)))
			except self.failureException:
				if self.portage_skip is not None:
					if self.portage_skip is True:
						result.addPortageSkip(self, "%s: SKIP" % testMethod)
					else:
						result.addPortageSkip(self, "%s: SKIP: %s" %
							(testMethod, self.portage_skip))
				elif self.todo:
					result.addTodo(self, "%s: TODO" % testMethod)
				else:
					result.addFailure(self, sys.exc_info())
			except (KeyboardInterrupt, SystemExit):
				raise
			except:
				result.addError(self, sys.exc_info())

			try:
				self.tearDown()
			except SystemExit:
				raise
			except KeyboardInterrupt:
				raise
			except:
				result.addError(self, sys.exc_info())
				ok = False
			if ok:
				result.addSuccess(self)
		finally:
			result.stopTest(self)

	def assertRaisesMsg(self, msg, excClass, callableObj, *args, **kwargs):
		"""Fail unless an exception of class excClass is thrown
		   by callableObj when invoked with arguments args and keyword
		   arguments kwargs. If a different type of exception is
		   thrown, it will not be caught, and the test case will be
		   deemed to have suffered an error, exactly as for an
		   unexpected exception.
		"""
		try:
			callableObj(*args, **kwargs)
		except excClass:
			return
		else:
			if hasattr(excClass, '__name__'): excName = excClass.__name__
			else: excName = str(excClass)
			raise self.failureException("%s not raised: %s" % (excName, msg))

	def assertExists(self, path):
		"""Make sure |path| exists"""
		if not os.path.exists(path):
			msg = ['path is missing: %s' % (path,)]
			while path != '/':
				path = os.path.dirname(path)
				if not path:
					# If we're given something like "foo", abort once we get to "".
					break
				result = os.path.exists(path)
				msg.append('\tos.path.exists(%s): %s' % (path, result))
				if result:
					msg.append('\tcontents: %r' % os.listdir(path))
					break
			raise self.failureException('\n'.join(msg))

	def assertNotExists(self, path):
		"""Make sure |path| does not exist"""
		if os.path.exists(path):
			raise self.failureException('path exists when it should not: %s' % path)

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

test_cps = ['sys-apps/portage', 'virtual/portage']
test_versions = ['1.0', '1.0-r1', '2.3_p4', '1.0_alpha57']
test_slots = [None, '1', 'gentoo-sources-2.6.17', 'spankywashere']
test_usedeps = ['foo', '-bar', ('foo', 'bar'),
	('foo', '-bar'), ('foo?', '!bar?')]
