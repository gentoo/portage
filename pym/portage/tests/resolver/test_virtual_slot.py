# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class VirtualSlotResolverTestCase(TestCase):

	def testLicenseMaskedVirtualSlotUpdate(self):

		ebuilds = {
			"dev-java/oracle-jdk-bin-1.7.0" : {"SLOT": "1.7", "LICENSE": "TEST"},
			"dev-java/sun-jdk-1.6.0" : {"SLOT": "1.6", "LICENSE": "TEST"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"virtual/jdk-1.6.0": {"SLOT": "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"virtual/jdk-1.7.0": {"SLOT": "1.7", "RDEPEND": "|| ( =dev-java/oracle-jdk-bin-1.7.0* )"},
		}

		installed = {
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"virtual/jdk-1.6.0": {"SLOT" : "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
		}

		world = ("app-misc/java-app",)

		test_cases = (
			# Bug #382557 - Don't pull in the virtual/jdk-1.7.0 slot update
			# since its dependencies can only be satisfied by a package that
			# is masked by license.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update" : True, "--deep" : True},
				success = True,
				mergelist = []),
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
