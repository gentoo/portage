# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class BdepsTestCase(TestCase):

	def testImageMagickUpdate(self):

		ebuilds = {
			"app-misc/A-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/C",
			},

			"app-misc/B-1" : {
				"EAPI": "6"
			},
			"app-misc/B-2" : {
				"EAPI": "6",
			},

			"app-misc/C-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/D",
			},
			"app-misc/C-2" : {
				"EAPI": "6",
				"DEPEND": "app-misc/D",
			},

			"app-misc/D-1" : {
				"EAPI": "6",
			},
			"app-misc/D-2" : {
				"EAPI": "6",
			},
		}

		installed = {
			"app-misc/A-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/C",
			},

			"app-misc/B-1" : {
				"EAPI": "6",
			},
			"app-misc/C-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/D",
			},

			"app-misc/D-1" : {
				"EAPI": "6",
			},
		}

		binpkgs = {
			"app-misc/A-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/C",
			},

			"app-misc/B-1" : {
				"EAPI": "6",
			},
			"app-misc/B-2" : {
				"EAPI": "6",
			},

			"app-misc/C-1" : {
				"EAPI": "6",
				"DEPEND": "app-misc/D",
			},
			"app-misc/C-2" : {
				"EAPI": "6",
				"DEPEND": "app-misc/D",
			},

			"app-misc/D-1" : {
				"EAPI": "6",
			},
			"app-misc/D-2" : {
				"EAPI": "6",
			},
		}

		world = (
			"app-misc/A",
		)

		test_cases = (

			# Enable --with-bdeps automatically when
			# --usepkg has not been specified.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
				},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					"app-misc/D-2",
					("app-misc/B-2", "app-misc/C-2"),
				]
			),

			# Use --with-bdeps-auto=n to prevent --with-bdeps
			# from being enabled automatically.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--with-bdeps-auto": "n",
				},
				success = True,
				mergelist = [
					"app-misc/D-2",
					"app-misc/C-2",
				]
			),

			# Do not enable --with-bdeps automatically when
			# --usepkg has been specified, since many users of binary
			# packages do not want unnecessary build time dependencies
			# installed. In this case we miss an update to
			# app-misc/D-2, since DEPEND is not pulled in for
			# the [binary]app-misc/C-2 update.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--usepkg": True,
				},
				success = True,
				mergelist = [
					"[binary]app-misc/C-2",
				]
			),

			# Use --with-bdeps=y to pull in build-time dependencies of
			# binary packages.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--usepkg": True,
					"--with-bdeps": "y",
				},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					(
						"[binary]app-misc/D-2",
						"[binary]app-misc/B-2",
						"[binary]app-misc/C-2",
					),
				]
			),

			# For --depclean, do not remove build-time dependencies by
			# default. Specify --with-bdeps-auto=n, in order to
			# demonstrate that it does not affect removal actions.
			ResolverPlaygroundTestCase(
				[],
				options = {
					"--depclean": True,
					"--with-bdeps-auto": "n",
				},
				success = True,
				cleanlist = [],
			),

			# For --depclean, remove build-time dependencies if
			# --with-bdeps=n has been specified.
			ResolverPlaygroundTestCase(
				[],
				options = {
					"--depclean": True,
					"--with-bdeps": "n",
				},
				success = True,
				ignore_cleanlist_order = True,
				cleanlist = [
					"app-misc/D-1",
					"app-misc/B-1",
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed,
			binpkgs=binpkgs, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
