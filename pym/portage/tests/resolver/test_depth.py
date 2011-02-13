# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class ResolverDepthTestCase(TestCase):

	def testResolverDepth(self):

		ebuilds = {
			"dev-libs/A-1": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/A-2": {"RDEPEND" : "dev-libs/B"},
			"dev-libs/B-1": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/B-2": {"RDEPEND" : "dev-libs/C"},
			"dev-libs/C-1": {},
			"dev-libs/C-2": {},

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
			}

		world = ["dev-libs/A"]

		test_cases = (
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
				mergelist = ['dev-java/icedtea-6.1-r1', 'dev-java/gcj-jdk-4.5-r1', 'virtual/jdk-1.6.0-r1', 'virtual/jdk-1.5.0-r1', 'virtual/jre-1.6.0-r1', 'virtual/jre-1.5.0-r1']),

			ResolverPlaygroundTestCase(
				["virtual/jre:1.5"],
				options = {"--update" : True},
				success = True,
				mergelist = ['dev-java/gcj-jdk-4.5-r1', 'virtual/jdk-1.5.0-r1', 'virtual/jre-1.5.0-r1']),

			ResolverPlaygroundTestCase(
				["virtual/jre:1.6"],
				options = {"--update" : True},
				success = True,
				mergelist = ['dev-java/icedtea-6.1-r1', 'virtual/jdk-1.6.0-r1', 'virtual/jre-1.6.0-r1']),

			# Test that we don't pull in any unnecessary updates
			# when --update is not specified, even though we
			# specified --deep.
			ResolverPlaygroundTestCase(
				["dev-java/ant-core"],
				options = {"--deep" : True},
				success = True,
				mergelist = ["dev-java/ant-core-1.8"]),

			# FIXME: pulls in unwanted updates without --deep: ['dev-java/icedtea-6.1-r1', 'virtual/jdk-1.6.0-r1', 'dev-java/ant-core-1.8']
			#ResolverPlaygroundTestCase(
			#	["dev-java/ant-core"],
			#	options = {"--update" : True},
			#	success = True,
			#	mergelist = ["dev-java/ant-core-1.8"]),

			ResolverPlaygroundTestCase(
				["dev-db/hsqldb"],
				options = {"--deep" : True},
				success = True,
				mergelist = ["dev-db/hsqldb-1.8"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
