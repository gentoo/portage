# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)


class CircularRustTestCase(TestCase):
	def testCircularPypyExe(self):

		ebuilds = {
			"dev-lang/rust-1.47.0-r2": {
				"EAPI": "7",
				"SLOT": "stable/1.47",
				"BDEPEND": "|| ( =dev-lang/rust-1.46* =dev-lang/rust-bin-1.46* =dev-lang/rust-1.47* =dev-lang/rust-bin-1.47* )",
			},
			"dev-lang/rust-1.46.0": {
				"EAPI": "7",
				"SLOT": "stable/1.46",
				"BDEPEND": "|| ( =dev-lang/rust-1.45* =dev-lang/rust-bin-1.45* =dev-lang/rust-1.46* =dev-lang/rust-bin-1.46* )",
			},
			"dev-lang/rust-bin-1.47.0": {
				"EAPI": "7",
			},
			"dev-lang/rust-bin-1.46.0": {
				"EAPI": "7",
			},
		}

		installed = {
			"dev-lang/rust-1.46.0": {
				"EAPI": "7",
				"SLOT": "stable/1.46",
				"BDEPEND": "|| ( =dev-lang/rust-1.45* =dev-lang/rust-bin-1.45* =dev-lang/rust-1.46* =dev-lang/rust-bin-1.46* )",
			},
		}

		test_cases = (
			# Test bug 756961, where a circular dependency was reported
			# when a package would replace its own builtime dependency.
			# This needs to be tested with and without --update, since
			# that affects package selection logic significantly,
			# expecially for packages given as arguments.
			ResolverPlaygroundTestCase(
				["=dev-lang/rust-1.46*"],
				mergelist=["dev-lang/rust-1.46.0"],
				success=True,
			),
			ResolverPlaygroundTestCase(
				["=dev-lang/rust-1.46*"],
				options={"--update": True},
				mergelist=[],
				success=True,
			),
			ResolverPlaygroundTestCase(
				["=dev-lang/rust-1.46*"],
				options={"--deep": True, "--update": True},
				mergelist=[],
				success=True,
			),
			ResolverPlaygroundTestCase(
				["dev-lang/rust"],
				mergelist=["dev-lang/rust-1.47.0-r2"],
				success=True,
			),
			ResolverPlaygroundTestCase(
				["dev-lang/rust"],
				options={"--update": True},
				mergelist=["dev-lang/rust-1.47.0-r2"],
				success=True,
			),
			ResolverPlaygroundTestCase(
				["@world"],
				options={"--deep": True, "--update": True},
				mergelist=["dev-lang/rust-1.47.0-r2"],
				success=True,
			),
		)

		world = ["dev-lang/rust"]

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, world=world, debug=False
		)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
