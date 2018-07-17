# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class UseFlagsTestCase(TestCase):

	def testUseFlags(self):
		ebuilds = {
			"dev-libs/A-1": { "IUSE": "X", },
			"dev-libs/B-1": { "IUSE": "X Y", },
			}

		installed = {
			"dev-libs/A-1": { "IUSE": "X", },
			"dev-libs/B-1": { "IUSE": "X", },
			}

		binpkgs = installed

		user_config = {
			"package.use": ( "dev-libs/A X", ),
			"use.force": ( "Y", ),
		}

		test_cases = (
			#default: don't reinstall on use flag change
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--selective": True, "--usepkg": True},
				success = True,
				mergelist = []),

			#default: respect use flags for binpkgs
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--usepkg": True},
				success = True,
				mergelist = ["dev-libs/A-1"]),

			#--binpkg-respect-use=n: use binpkgs with different use flags
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--binpkg-respect-use": "n", "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/A-1"]),

			#--reinstall=changed-use: reinstall if use flag changed
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--reinstall": "changed-use", "--usepkg": True},
				success = True,
				mergelist = ["dev-libs/A-1"]),

			#--reinstall=changed-use: don't reinstall on new use flag
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--reinstall": "changed-use", "--usepkg": True},
				success = True,
				mergelist = []),

			#--newuse: reinstall on new use flag
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--newuse": True, "--usepkg": True},
				success = True,
				mergelist = ["dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			binpkgs=binpkgs, installed=installed, user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
