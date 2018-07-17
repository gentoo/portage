# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground, ResolverPlaygroundTestCase)

class ChangedDepsTestCase(TestCase):

	def testChangedDeps(self):

		ebuilds = {
			"app-misc/A-0": {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
			},
			"app-misc/B-0": {
			}
		}

		binpkgs = {
			"app-misc/A-0": {},
		}

		installed = {
			"app-misc/A-0": {},
		}

		world= (
			"app-misc/A",
		)

		test_cases = (

			# --dynamic-deps=n causes the original deps to be respected
			ResolverPlaygroundTestCase(
				["@world"],
				success = True,
				options = {
					"--update": True,
					"--deep": True,
					"--dynamic-deps": "n",
					"--usepkg": True,
				},
				mergelist = []
			),

			# --dynamic-deps causes app-misc/B to get pulled in
			ResolverPlaygroundTestCase(
				["@world"],
				success = True,
				options = {
					"--update": True,
					"--deep": True,
					"--dynamic-deps": "y",
					"--usepkg": True,
				},
				mergelist = ["app-misc/B-0"]
			),

			# --changed-deps causes app-misc/A to be rebuilt
			ResolverPlaygroundTestCase(
				["@world"],
				success = True,
				options = {
					"--update": True,
					"--deep": True,
					"--changed-deps": "y",
					"--usepkg": True,
				},
				mergelist = ["app-misc/B-0", "app-misc/A-0"]
			),

			# --usepkgonly prevents automatic --binpkg-changed-deps
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				options = {
					"--changed-deps": "y",
					"--usepkgonly": True,
				},
				mergelist = ["[binary]app-misc/A-0"]
			),

			# Test automatic --binpkg-changed-deps, which cases the
			# binpkg with stale deps to be ignored (with warning
			# message)
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				options = {
					"--usepkg": True,
				},
				mergelist = ["app-misc/B-0", "app-misc/A-0"]
			),
		)
		test_cases = (

			# Forcibly disable --binpkg-changed-deps, which causes
			# --changed-deps to be overridden by --binpkg-changed-deps
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				options = {
					"--binpkg-changed-deps": "n",
					"--changed-deps": "y",
					"--usepkg": True,
				},
				mergelist = ["[binary]app-misc/A-0"]
			),
		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds,
			binpkgs=binpkgs, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.cleanup()
