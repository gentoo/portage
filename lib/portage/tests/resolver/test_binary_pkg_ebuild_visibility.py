# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class BinaryPkgEbuildVisibilityTestCase(TestCase):

	def testBinaryPkgEbuildVisibility(self):

		binpkgs = {
			"app-misc/foo-3" : {},
			"app-misc/foo-2" : {},
			"app-misc/foo-1" : {},
		}

		ebuilds = {
			"app-misc/foo-2" : {},
			"app-misc/foo-1" : {},
		}

		installed = {
			"app-misc/foo-1" : {},
		}

		world = ["app-misc/foo"]

		test_cases = (

			# Test bug #612960, where --use-ebuild-visibility failed
			# to reject binary packages for which ebuilds were not
			# available.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--use-ebuild-visibility": 'y',
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-2',
				],
			),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-3',
				],
			),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--usepkg": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-2',
				],
			),

			ResolverPlaygroundTestCase(
				["=app-misc/foo-3"],
				options = {
					"--use-ebuild-visibility": 'y',
					"--usepkgonly": True,
				},
				success = False,
			),

			ResolverPlaygroundTestCase(
				["app-misc/foo"],
				options = {
					"--use-ebuild-visibility": 'y',
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-2',
				],
			),

			ResolverPlaygroundTestCase(
				["app-misc/foo"],
				options = {
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-3',
				],
			),

			# The default behavior is to enforce ebuild visibility as
			# long as a visible package is available to satisfy the
			# current atom. In the following test case, ebuild visibility
			# is ignored in order to satisfy the =app-misc/foo-3 atom.
			ResolverPlaygroundTestCase(
				["=app-misc/foo-3"],
				options = {
					"--usepkg": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/foo-3',
				],
			),

			# Verify that --use-ebuild-visibility works with --usepkg
			# when no other visible package is available.
			ResolverPlaygroundTestCase(
				["=app-misc/foo-3"],
				options = {
					"--use-ebuild-visibility": "y",
					"--usepkg": True,
				},
				success = False,
			),
		)

		playground = ResolverPlayground(binpkgs=binpkgs, ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
