# Copyright 2011-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class ResolverDepthTestCase(TestCase):

	def testResolverDepth(self):

		profile = {
			"package.mask":
				(
					# Mask an installed package (for which an update is
					# available) in order to test for bug 712298, where
					# --update caused --deep=<depth> to be violated for
					# such a package.
					"<dev-libs/B-2",
				),
		}

		ebuilds = {
			"dev-libs/A-1": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/A-2": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/B-1": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/B-2": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/C-1": {},
			"dev-libs/C-2": {},

			"virtual/libusb-0"         : {"EAPI" :"2", "SLOT" : "0", "RDEPEND" : "|| ( >=dev-libs/libusb-0.1.12-r1:0 dev-libs/libusb-compat >=sys-freebsd/freebsd-lib-8.0[usb] )"},
			"virtual/libusb-1"         : {"EAPI" :"2", "SLOT" : "1", "RDEPEND" : ">=dev-libs/libusb-1.0.4:1"},
			"dev-libs/libusb-0.1.13"   : {},
			"dev-libs/libusb-1.0.5"    : {"SLOT":"1"},
			"dev-libs/libusb-compat-1" : {},
			"sys-freebsd/freebsd-lib-8": {"IUSE" : "+usb"},

			"sys-fs/udev-164"          : {"EAPI" : "1", "RDEPEND" : "virtual/libusb:0"},

			"virtual/jre-1.5.0"        : {"SLOT" : "1.5", "RDEPEND" : "|| ( =dev-java/sun-jre-bin-1.5.0* =virtual/jdk-1.5.0* )"},
			"virtual/jre-1.5.0-r1"     : {"SLOT" : "1.5", "RDEPEND" : "|| ( =dev-java/sun-jre-bin-1.5.0* =virtual/jdk-1.5.0* )"},
			"virtual/jre-1.6.0"        : {"SLOT" : "1.6", "RDEPEND" : "|| ( =dev-java/sun-jre-bin-1.6.0* =virtual/jdk-1.6.0* )"},
			"virtual/jre-1.6.0-r1"     : {"SLOT" : "1.6", "RDEPEND" : "|| ( =dev-java/sun-jre-bin-1.6.0* =virtual/jdk-1.6.0* )"},
			"virtual/jdk-1.5.0"        : {"SLOT" : "1.5", "RDEPEND" : "|| ( =dev-java/sun-jdk-1.5.0* dev-java/gcj-jdk )"},
			"virtual/jdk-1.5.0-r1"     : {"SLOT" : "1.5", "RDEPEND" : "|| ( =dev-java/sun-jdk-1.5.0* dev-java/gcj-jdk )"},
			"virtual/jdk-1.6.0"        : {"SLOT" : "1.6", "RDEPEND" : "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"virtual/jdk-1.6.0-r1"     : {"SLOT" : "1.6", "RDEPEND" : "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"dev-java/gcj-jdk-4.5"     : {},
			"dev-java/gcj-jdk-4.5-r1"  : {},
			"dev-java/icedtea-6.1"     : {},
			"dev-java/icedtea-6.1-r1"  : {},
			"dev-java/sun-jdk-1.5"     : {"SLOT" : "1.5"},
			"dev-java/sun-jdk-1.6"     : {"SLOT" : "1.6"},
			"dev-java/sun-jre-bin-1.5" : {"SLOT" : "1.5"},
			"dev-java/sun-jre-bin-1.6" : {"SLOT" : "1.6"},

			"dev-java/ant-core-1.8"   : {"DEPEND"  : ">=virtual/jdk-1.4"},
			"dev-db/hsqldb-1.8"       : {"RDEPEND" : ">=virtual/jre-1.6"},
			}

		installed = {
			"dev-libs/A-1": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/B-1": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/C-1": {},

			"virtual/jre-1.5.0"       : {"SLOT" : "1.5", "RDEPEND" : "|| ( =virtual/jdk-1.5.0* =dev-java/sun-jre-bin-1.5.0* )"},
			"virtual/jre-1.6.0"       : {"SLOT" : "1.6", "RDEPEND" : "|| ( =virtual/jdk-1.6.0* =dev-java/sun-jre-bin-1.6.0* )"},
			"virtual/jdk-1.5.0"       : {"SLOT" : "1.5", "RDEPEND" : "|| ( =dev-java/sun-jdk-1.5.0* dev-java/gcj-jdk )"},
			"virtual/jdk-1.6.0"       : {"SLOT" : "1.6", "RDEPEND" : "|| ( =dev-java/icedtea-6* =dev-java/sun-jdk-1.6.0* )"},
			"dev-java/gcj-jdk-4.5"    : {},
			"dev-java/icedtea-6.1"    : {},

			"virtual/libusb-0"         : {"EAPI" :"2", "SLOT" : "0", "RDEPEND" : "|| ( >=dev-libs/libusb-0.1.12-r1:0 dev-libs/libusb-compat >=sys-freebsd/freebsd-lib-8.0[usb] )"},
			}

		world = ["dev-libs/A"]

		test_cases = (
			# Test for bug 712298, where --update caused --deep=<depth>
			# to be violated for dependencies that were masked. In this
			# case, the installed dev-libs/B-1 dependency is masked.
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 0},
				success = True,
				mergelist = ["dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 1},
				success = True,
				mergelist = ["dev-libs/B-2", "dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--update": True, "--deep": 2},
				success = True,
				mergelist = ["dev-libs/C-2", "dev-libs/B-2", "dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/C-2", "dev-libs/B-2", "dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--emptytree": True},
				success = True,
				mergelist = ["dev-libs/C-2", "dev-libs/B-2", "dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--selective": True, "--deep": True},
				success = True,
				mergelist = []),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--deep": 2},
				success = True,
				mergelist = ["dev-libs/A-2"]),

			ResolverPlaygroundTestCase(
				["virtual/jre"],
				options = {},
				success = True,
				mergelist = ['virtual/jre-1.6.0-r1']),

			ResolverPlaygroundTestCase(
				["virtual/jre"],
				options = {"--deep" : True},
				success = True,
				mergelist = ['virtual/jre-1.6.0-r1']),

			# Test bug #141118, where we avoid pulling in
			# redundant deps, satisfying nested virtuals
			# as efficiently as possible.
			ResolverPlaygroundTestCase(
				["virtual/jre"],
				options = {"--selective" : True, "--deep" : True},
				success = True,
				mergelist = []),

			# Test bug #150361, where depgraph._greedy_slots()
			# is triggered by --update with AtomArg.
			ResolverPlaygroundTestCase(
				["virtual/jre"],
				options = {"--update" : True},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [('virtual/jre-1.6.0-r1', 'virtual/jre-1.5.0-r1')]),

			# Recursively traversed virtual dependencies, and their
			# direct dependencies, are considered to have the same
			# depth as direct dependencies.
			ResolverPlaygroundTestCase(
				["virtual/jre"],
				options = {"--update" : True, "--deep" : 1},
				success = True,
				ambiguous_merge_order = True,
				merge_order_assertions=(('dev-java/icedtea-6.1-r1', 'virtual/jdk-1.6.0-r1'), ('virtual/jdk-1.6.0-r1', 'virtual/jre-1.6.0-r1'),
					('dev-java/gcj-jdk-4.5-r1', 'virtual/jdk-1.5.0-r1'), ('virtual/jdk-1.5.0-r1', 'virtual/jre-1.5.0-r1')),
				mergelist = [('dev-java/icedtea-6.1-r1', 'dev-java/gcj-jdk-4.5-r1', 'virtual/jdk-1.6.0-r1', 'virtual/jdk-1.5.0-r1', 'virtual/jre-1.6.0-r1', 'virtual/jre-1.5.0-r1')]),

			ResolverPlaygroundTestCase(
				["virtual/jre:1.5"],
				options = {"--update" : True},
				success = True,
				mergelist = ['virtual/jre-1.5.0-r1']),

			ResolverPlaygroundTestCase(
				["virtual/jre:1.6"],
				options = {"--update" : True},
				success = True,
				mergelist = ['virtual/jre-1.6.0-r1']),

			# Test that we don't pull in any unnecessary updates
			# when --update is not specified, even though we
			# specified --deep.
			ResolverPlaygroundTestCase(
				["dev-java/ant-core"],
				options = {"--deep" : True},
				success = True,
				mergelist = ["dev-java/ant-core-1.8"]),

			ResolverPlaygroundTestCase(
				["dev-java/ant-core"],
				options = {"--update" : True},
				success = True,
				mergelist = ["dev-java/ant-core-1.8"]),

			# Recursively traversed virtual dependencies, and their
			# direct dependencies, are considered to have the same
			# depth as direct dependencies.
			ResolverPlaygroundTestCase(
				["dev-java/ant-core"],
				options = {"--update" : True, "--deep" : 1},
				success = True,
				mergelist = ['dev-java/icedtea-6.1-r1', 'virtual/jdk-1.6.0-r1', 'dev-java/ant-core-1.8']),

			ResolverPlaygroundTestCase(
				["dev-db/hsqldb"],
				options = {"--deep" : True},
				success = True,
				mergelist = ["dev-db/hsqldb-1.8"]),

			# Don't traverse deps of an installed package with --deep=0,
			# even if it's a virtual.
			ResolverPlaygroundTestCase(
				["virtual/libusb:0"],
				options = {"--selective" : True, "--deep" : 0},
				success = True,
				mergelist = []),

			# Satisfy unsatisfied dep of installed package with --deep=1.
			ResolverPlaygroundTestCase(
				["virtual/libusb:0"],
				options = {"--selective" : True, "--deep" : 1},
				success = True,
				mergelist = ['dev-libs/libusb-0.1.13']),

			# Pull in direct dep of virtual, even with --deep=0.
			ResolverPlaygroundTestCase(
				["sys-fs/udev"],
				options = {"--deep" : 0},
				success = True,
				mergelist = ['dev-libs/libusb-0.1.13', 'sys-fs/udev-164']),

			# Test --nodeps with direct virtual deps.
			ResolverPlaygroundTestCase(
				["sys-fs/udev"],
				options = {"--nodeps" : True},
				success = True,
				mergelist = ["sys-fs/udev-164"]),

			# Test that --nodeps overrides --deep.
			ResolverPlaygroundTestCase(
				["sys-fs/udev"],
				options = {"--nodeps" : True, "--deep" : True},
				success = True,
				mergelist = ["sys-fs/udev-164"]),

			# Test that --nodeps overrides --emptytree.
			ResolverPlaygroundTestCase(
				["sys-fs/udev"],
				options = {"--nodeps" : True, "--emptytree" : True},
				success = True,
				mergelist = ["sys-fs/udev-164"]),

			# Test --emptytree with virtuals.
			ResolverPlaygroundTestCase(
				["sys-fs/udev"],
				options = {"--emptytree" : True},
				success = True,
				mergelist = ['dev-libs/libusb-0.1.13', 'virtual/libusb-0', 'sys-fs/udev-164']),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			profile=profile, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
