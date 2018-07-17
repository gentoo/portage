# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SonameReinstallTestCase(TestCase):

	def testSonameReinstall(self):

		binpkgs = {
			"app-misc/A-1" : {
				"RDEPEND": "dev-libs/B",
				"DEPEND": "dev-libs/B",
				"REQUIRES": "x86_32: libB.so.2",
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

			# Test that --ignore-soname-deps prevents the above
			# rebuild from being triggered.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/B-2",
					"[binary]app-misc/A-1",
				]
			),

			# Test that --ignore-soname-deps prevents the above
			# reinstall from being triggered.
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
