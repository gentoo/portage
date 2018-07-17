# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class UseAliasesTestCase(TestCase):
	def testUseAliases(self):
		ebuilds = {
			"dev-libs/A-1": {"DEPEND": "dev-libs/K[x]", "RDEPEND": "dev-libs/K[x]", "EAPI": "5"},
			"dev-libs/B-1": {"DEPEND": "dev-libs/L[x]", "RDEPEND": "dev-libs/L[x]", "EAPI": "5"},
			"dev-libs/C-1": {"DEPEND": "dev-libs/M[xx]", "RDEPEND": "dev-libs/M[xx]", "EAPI": "5"},
			"dev-libs/D-1": {"DEPEND": "dev-libs/N[-x]", "RDEPEND": "dev-libs/N[-x]", "EAPI": "5"},
			"dev-libs/E-1": {"DEPEND": "dev-libs/O[-xx]", "RDEPEND": "dev-libs/O[-xx]", "EAPI": "5"},
			"dev-libs/F-1": {"DEPEND": "dev-libs/P[-xx]", "RDEPEND": "dev-libs/P[-xx]", "EAPI": "5"},
			"dev-libs/G-1": {"DEPEND": "dev-libs/Q[x-y]", "RDEPEND": "dev-libs/Q[x-y]", "EAPI": "5"},
			"dev-libs/H-1": {"DEPEND": "=dev-libs/R-1*[yy]", "RDEPEND": "=dev-libs/R-1*[yy]", "EAPI": "5"},
			"dev-libs/H-2": {"DEPEND": "=dev-libs/R-2*[yy]", "RDEPEND": "=dev-libs/R-2*[yy]", "EAPI": "5"},
			"dev-libs/I-1": {"DEPEND": "dev-libs/S[y-z]", "RDEPEND": "dev-libs/S[y-z]", "EAPI": "5"},
			"dev-libs/I-2": {"DEPEND": "dev-libs/S[y_z]", "RDEPEND": "dev-libs/S[y_z]", "EAPI": "5"},
			"dev-libs/J-1": {"DEPEND": "dev-libs/T[x]", "RDEPEND": "dev-libs/T[x]", "EAPI": "5"},
			"dev-libs/K-1": {"IUSE": "+x", "EAPI": "5"},
			"dev-libs/K-2::repo1": {"IUSE": "+X", "EAPI": "5-progress"},
			"dev-libs/L-1": {"IUSE": "+x", "EAPI": "5"},
			"dev-libs/M-1::repo1": {"IUSE": "X", "EAPI": "5-progress"},
			"dev-libs/N-1": {"IUSE": "x", "EAPI": "5"},
			"dev-libs/N-2::repo1": {"IUSE": "X", "EAPI": "5-progress"},
			"dev-libs/O-1": {"IUSE": "x", "EAPI": "5"},
			"dev-libs/P-1::repo1": {"IUSE": "+X", "EAPI": "5-progress"},
			"dev-libs/Q-1::repo2": {"IUSE": "X.Y", "EAPI": "5-progress"},
			"dev-libs/R-1::repo1": {"IUSE": "Y", "EAPI": "5-progress"},
			"dev-libs/R-2::repo1": {"IUSE": "y", "EAPI": "5-progress"},
			"dev-libs/S-1::repo2": {"IUSE": "Y.Z", "EAPI": "5-progress"},
			"dev-libs/S-2::repo2": {"IUSE": "Y.Z", "EAPI": "5-progress"},
			"dev-libs/T-1::repo1": {"IUSE": "+X", "EAPI": "5"},
		}

		installed = {
			"dev-libs/L-2::repo1": {"IUSE": "+X", "USE": "X", "EAPI": "5-progress"},
			"dev-libs/O-2::repo1": {"IUSE": "X", "USE": "", "EAPI": "5-progress"},
		}

		repo_configs = {
			"repo1": {
				"use.aliases": ("X x xx",),
				"package.use.aliases": (
					"=dev-libs/R-1* Y yy",
					"=dev-libs/R-2* y yy",
				)
			},
			"repo2": {
				"eapi": ("5-progress",),
				"use.aliases": ("X.Y x-y",),
				"package.use.aliases": (
					"=dev-libs/S-1* Y.Z y-z",
					"=dev-libs/S-2* Y.Z y_z",
				),
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				success = True,
				mergelist = ["dev-libs/K-2", "dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				success = True,
				mergelist = ["dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/M-1", "dev-libs/C-1"],
				use_changes = {"dev-libs/M-1": {"X": True}}),
			ResolverPlaygroundTestCase(
				["dev-libs/D"],
				success = True,
				mergelist = ["dev-libs/N-2", "dev-libs/D-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/E"],
				success = True,
				mergelist = ["dev-libs/E-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/F"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/P-1", "dev-libs/F-1"],
				use_changes = {"dev-libs/P-1": {"X": False}}),
			ResolverPlaygroundTestCase(
				["dev-libs/G"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/Q-1", "dev-libs/G-1"],
				use_changes = {"dev-libs/Q-1": {"X.Y": True}}),
			ResolverPlaygroundTestCase(
				["=dev-libs/H-1*"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/R-1", "dev-libs/H-1"],
				use_changes = {"dev-libs/R-1": {"Y": True}}),
			ResolverPlaygroundTestCase(
				["=dev-libs/H-2*"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/R-2", "dev-libs/H-2"],
				use_changes = {"dev-libs/R-2": {"y": True}}),
			ResolverPlaygroundTestCase(
				["=dev-libs/I-1*"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/S-1", "dev-libs/I-1"],
				use_changes = {"dev-libs/S-1": {"Y.Z": True}}),
			ResolverPlaygroundTestCase(
				["=dev-libs/I-2*"],
				options = {"--autounmask": True},
				success = False,
				mergelist = ["dev-libs/S-2", "dev-libs/I-2"],
				use_changes = {"dev-libs/S-2": {"Y.Z": True}}),
			ResolverPlaygroundTestCase(
				["dev-libs/J"],
				success = False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, repo_configs=repo_configs)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
