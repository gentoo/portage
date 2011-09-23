# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CircularChoicesTestCase(TestCase):

	def testDirectCircularDependency(self):

		ebuilds = {
			"dev-lang/gwydion-dylan-2.4.0": {"DEPEND": "|| ( dev-lang/gwydion-dylan dev-lang/gwydion-dylan-bin )" },
			"dev-lang/gwydion-dylan-bin-2.4.0": {},
		}

		test_cases = (
			# Automatically pull in gwydion-dylan-bin to solve a circular dep
			ResolverPlaygroundTestCase(
				["dev-lang/gwydion-dylan"],
				mergelist = ['dev-lang/gwydion-dylan-bin-2.4.0', 'dev-lang/gwydion-dylan-2.4.0'],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class VirtualCircularChoicesTestCase(TestCase):
	def testDirectVirtualCircularDependency(self):

		# Bug #384107
		self.todo = True

		ebuilds = {
			"dev-java/icedtea-6.1.10.3": { "SLOT" : "6", "DEPEND": "virtual/jdk" },
			"dev-java/icedtea6-bin-1.10.3": {},
			"virtual/jdk-1.6.0": { "SLOT" : "1.6", "RDEPEND": "|| ( dev-java/icedtea6-bin =dev-java/icedtea-6* )" },
		}

		test_cases = (
			# Automatically pull in icedtea6-bin to solve a circular dep
			ResolverPlaygroundTestCase(
				["dev-java/icedtea"],
				mergelist = ["dev-java/icedtea6-bin-1.10.3", "virtual/jdk-1.6.0", "dev-java/icedtea-6.1.10.3"],
				success = True,
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
