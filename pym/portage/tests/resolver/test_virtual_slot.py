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

	def testVirtualSlotUpdate(self):

		ebuilds = {
			"dev-java/oracle-jdk-bin-1.7.0" : {"SLOT": "1.7", "LICENSE": "TEST"},
			"dev-java/sun-jdk-1.6.0" : {"SLOT": "1.6", "LICENSE": "TEST"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"dev-java/icedtea-7" : {"SLOT": "7"},
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"virtual/jdk-1.6.0": {"SLOT": "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"virtual/jdk-1.7.0": {"SLOT": "1.7", "RDEPEND": "|| ( =dev-java/icedtea-7* =dev-java/oracle-jdk-bin-1.7.0* )"},
		}

		installed = {
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"virtual/jdk-1.6.0": {"SLOT" : "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
		}

		world = ("app-misc/java-app",)

		test_cases = (
			# Pull in the virtual/jdk-1.7.0 slot update since its dependencies
			# can only be satisfied by an unmasked package.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update" : True, "--deep" : True},
				success = True,
				mergelist = ["dev-java/icedtea-7", "virtual/jdk-1.7.0"]),

			# Bug #275945 - Don't pull in the virtual/jdk-1.7.0 slot update
			# unless --update is enabled.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--selective" : True, "--deep" : True},
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

	def testVirtualSubslotUpdate(self):

		ebuilds = {
			"virtual/pypy-2.3.1" : {
				"EAPI": "5",
				"SLOT": "0/2.3",
				"RDEPEND": "|| ( >=dev-python/pypy-2.3.1:0/2.3 >=dev-python/pypy-bin-2.3.1:0/2.3 ) "
			},
			"virtual/pypy-2.4.0" : {
				"EAPI": "5",
				"SLOT": "0/2.4",
				"RDEPEND": "|| ( >=dev-python/pypy-2.4.0:0/2.4 >=dev-python/pypy-bin-2.4.0:0/2.4 ) "
			},
			"dev-python/pypy-2.3.1": {
				"EAPI": "5",
				"SLOT": "0/2.3"
			},
			"dev-python/pypy-2.4.0": {
				"EAPI": "5",
				"SLOT": "0/2.4"
			},
			"dev-python/pygments-1.6_p20140324-r1": {
				"EAPI": "5",
				"DEPEND": "virtual/pypy:0="
			}
		}

		installed = {
			"virtual/pypy-2.3.1" : {
				"EAPI": "5",
				"SLOT": "0/2.3",
				"RDEPEND": "|| ( >=dev-python/pypy-2.3.1:0/2.3 >=dev-python/pypy-bin-2.3.1:0/2.3 ) "
			},
			"dev-python/pypy-2.3.1": {
				"EAPI": "5",
				"SLOT": "0/2.3"
			},
			"dev-python/pygments-1.6_p20140324-r1": {
				"EAPI": "5",
				"DEPEND": "virtual/pypy:0/2.3=",
				"RDEPEND": "virtual/pypy:0/2.3=",
			}
		}

		world = ["dev-python/pygments"]

		test_cases = (
			# bug 526160 - test for missed pypy sub-slot update
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--dynamic-deps": "y"},
				success=True,
				mergelist = ['dev-python/pypy-2.4.0',
					'virtual/pypy-2.4.0',
					'dev-python/pygments-1.6_p20140324-r1']),

			# Repeat above test, but with --dynamic-deps disabled.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--dynamic-deps": "n"},
				success=True,
				mergelist = ['dev-python/pypy-2.4.0',
					'virtual/pypy-2.4.0',
					'dev-python/pygments-1.6_p20140324-r1']),
		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testVirtualSlotDepclean(self):

		ebuilds = {
			"dev-java/oracle-jdk-bin-1.7.0" : {"SLOT": "1.7", "LICENSE": "TEST"},
			"dev-java/sun-jdk-1.6.0" : {"SLOT": "1.6", "LICENSE": "TEST"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"dev-java/icedtea-7" : {"SLOT": "7"},
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"virtual/jdk-1.6.0": {"SLOT": "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"virtual/jdk-1.7.0": {"SLOT": "1.7", "RDEPEND": "|| ( =dev-java/icedtea-7* =dev-java/oracle-jdk-bin-1.7.0* )"},
		}

		installed = {
			"app-misc/java-app-1": {"RDEPEND": ">=virtual/jdk-1.6.0"},
			"dev-java/icedtea-6.1.10.3" : {"SLOT": "6"},
			"dev-java/icedtea-7" : {"SLOT": "7"},
			"virtual/jdk-1.6.0": {"SLOT" : "1.6", "RDEPEND": "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"virtual/jdk-1.7.0": {"SLOT": "1.7", "RDEPEND": "|| ( =dev-java/icedtea-7* =dev-java/oracle-jdk-bin-1.7.0* )"},
		}

		world = ("virtual/jdk:1.6", "app-misc/java-app",)

		test_cases = (
			# Make sure that depclean doesn't remove a new slot even though
			# it is redundant in the sense that the older slot will satisfy
			# all dependencies.
			ResolverPlaygroundTestCase(
				[],
				options = {"--depclean" : True},
				success = True,
				cleanlist = []),

			# Prune redundant lower slots, even if they are in world.
			ResolverPlaygroundTestCase(
				[],
				options = {"--prune" : True},
				success = True,
				cleanlist = ['virtual/jdk-1.6.0', 'dev-java/icedtea-6.1.10.3']),
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
