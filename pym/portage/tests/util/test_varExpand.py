# test_varExpand.py -- Portage Unit Testing Functionality
# Copyright 2006-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util import varexpand

class VarExpandTestCase(TestCase):

	def testVarExpandPass(self):

		varDict = {"a": "5", "b": "7", "c": "-5"}
		for key in varDict:
			result = varexpand("$%s" % key, varDict)

			self.assertFalse(result != varDict[key],
				msg="Got %s != %s, from varexpand(%s, %s)" %
					(result, varDict[key], "$%s" % key, varDict))
			result = varexpand("${%s}" % key, varDict)
			self.assertFalse(result != varDict[key],
				msg="Got %s != %s, from varexpand(%s, %s)" %
					(result, varDict[key], "${%s}" % key, varDict))

	def testVarExpandBackslashes(self):
		r"""
		We want to behave like bash does when expanding a variable
		assignment in a sourced file, in which case it performs
		backslash removal for \\ and \$ but nothing more. It also
		removes escaped newline characters. Note that we don't
		handle escaped quotes here, since getconfig() uses shlex
		to handle that earlier.
		"""

		varDict = {}
		tests = [
			("\\", "\\"),
			("\\\\", "\\"),
			("\\\\\\", "\\\\"),
			("\\\\\\\\", "\\\\"),
			("\\$", "$"),
			("\\\\$", "\\$"),
			("\\a", "\\a"),
			("\\b", "\\b"),
			("\\n", "\\n"),
			("\\r", "\\r"),
			("\\t", "\\t"),
			("\\\n", ""),
			("\\\"", "\\\""),
			("\\'", "\\'"),
		]
		for test in tests:
			result = varexpand(test[0], varDict)
			self.assertFalse(result != test[1],
				msg="Got %s != %s from varexpand(%s, %s)"
				% (result, test[1], test[0], varDict))

	def testVarExpandDoubleQuotes(self):

		varDict = {"a": "5"}
		tests = [("\"${a}\"", "\"5\"")]
		for test in tests:
			result = varexpand(test[0], varDict)
			self.assertFalse(result != test[1],
				msg="Got %s != %s from varexpand(%s, %s)"
				% (result, test[1], test[0], varDict))

	def testVarExpandSingleQuotes(self):

		varDict = {"a": "5"}
		tests = [("\'${a}\'", "\'${a}\'")]
		for test in tests:
			result = varexpand(test[0], varDict)
			self.assertFalse(result != test[1],
				msg="Got %s != %s from varexpand(%s, %s)"
				% (result, test[1], test[0], varDict))

	def testVarExpandFail(self):

		varDict = {"a": "5", "b": "7", "c": "15"}

		testVars = ["fail"]

		for var in testVars:
			result = varexpand("$%s" % var, varDict)
			self.assertFalse(len(result),
				msg="Got %s == %s, from varexpand(%s, %s)"
					% (result, var, "$%s" % var, varDict))

			result = varexpand("${%s}" % var, varDict)
			self.assertFalse(len(result),
				msg="Got %s == %s, from varexpand(%s, %s)"
					% (result, var, "${%s}" % var, varDict))
