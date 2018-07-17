# test_vercmp.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.versions import vercmp

class VerCmpTestCase(TestCase):
	""" A simple testCase for portage.versions.vercmp()
	"""

	def testVerCmpGreater(self):

		tests = [
			("6.0", "5.0"), ("5.0", "5"),
			("1.0-r1", "1.0-r0"),
			("1.0-r1", "1.0"),
			("999999999999999999999999999999", "999999999999999999999999999998"),
			("1.0.0", "1.0"),
			("1.0.0", "1.0b"),
			("1b", "1"),
			("1b_p1", "1_p1"),
			("1.1b", "1.1"),
			("12.2.5", "12.2b"),
		]
		for test in tests:
			self.assertFalse(vercmp(test[0], test[1]) <= 0, msg="%s < %s? Wrong!" % (test[0], test[1]))

	def testVerCmpLess(self):
		"""
		pre < alpha < beta < rc < p -> test each of these, they are inductive (or should be..)
		"""
		tests = [
			("4.0", "5.0"), ("5", "5.0"), ("1.0_pre2", "1.0_p2"),
			("1.0_alpha2", "1.0_p2"), ("1.0_alpha1", "1.0_beta1"), ("1.0_beta3", "1.0_rc3"),
			("1.001000000000000000001", "1.001000000000000000002"),
			("1.00100000000", "1.0010000000000000001"),
			("999999999999999999999999999998", "999999999999999999999999999999"),
			("1.01", "1.1"),
			("1.0-r0", "1.0-r1"),
			("1.0", "1.0-r1"),
			("1.0", "1.0.0"),
			("1.0b", "1.0.0"),
			("1_p1", "1b_p1"),
			("1", "1b"),
			("1.1", "1.1b"),
			("12.2b", "12.2.5"),
		]
		for test in tests:
			self.assertFalse(vercmp(test[0], test[1]) >= 0, msg="%s > %s? Wrong!" % (test[0], test[1]))

	def testVerCmpEqual(self):

		tests = [
			("4.0", "4.0"),
			("1.0", "1.0"),
			("1.0-r0", "1.0"),
			("1.0", "1.0-r0"),
			("1.0-r0", "1.0-r0"),
			("1.0-r1", "1.0-r1")
		]
		for test in tests:
			self.assertFalse(vercmp(test[0], test[1]) != 0, msg="%s != %s? Wrong!" % (test[0], test[1]))

	def testVerNotEqual(self):

		tests = [
			("1", "2"), ("1.0_alpha", "1.0_pre"), ("1.0_beta", "1.0_alpha"),
			("0", "0.0"),
			("1.0-r0", "1.0-r1"),
			("1.0-r1", "1.0-r0"),
			("1.0", "1.0-r1"),
			("1.0-r1", "1.0"),
			("1.0", "1.0.0"),
			("1_p1", "1b_p1"),
			("1b", "1"),
			("1.1b", "1.1"),
			("12.2b", "12.2"),
		]
		for test in tests:
			self.assertFalse(vercmp(test[0], test[1]) == 0, msg="%s == %s? Wrong!" % (test[0], test[1]))
