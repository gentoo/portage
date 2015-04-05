# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SonameSkipUpdateTestCase(TestCase):

	def testSonameSkipUpdate(self):

		binpkgs = {
			"app-misc/A-1" : {
				"RDEPEND": "dev-libs/B",
				"DEPEND": "dev-libs/B",
				"REQUIRES": "x86_32: libB.so.1",
			},
			"dev-libs/B-2" : {
				"PROVIDES": "x86_32: libB.so.2",
			},
			"dev-libs/B-1" : {
				"PROVIDES": "x86_32: libB.so.1",
			},
		}

		installed = {
			"app-misc/A-1" : {
				"RDEPEND": "dev-libs/B",
				"DEPEND": "dev-libs/B",
				"REQUIRES": "x86_32: libB.so.1",
			},
			"dev-libs/B-1" : {
				"PROVIDES": "x86_32: libB.so.1",
			},
		}

		world = ("app-misc/A",)

		test_cases = (

			# Test that --ignore-soname-deps allows the upgrade,
			# even though it will break an soname dependency of
			# app-misc/A-1.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "y",
					"--update": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/B-2",
				]
			),

			# Test that upgrade to B-2 is skipped with --usepkgonly
			# because it will break an soname dependency that
			# cannot be satisfied by the available binary packages.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = []
			),

		)

		playground = ResolverPlayground(debug=False,
			binpkgs=binpkgs, installed=installed,
			world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
