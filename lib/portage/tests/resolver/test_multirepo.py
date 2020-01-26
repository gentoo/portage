# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class MultirepoTestCase(TestCase):

	def testMultirepo(self):
		ebuilds = {
			#Simple repo selection
			"dev-libs/A-1": { },
			"dev-libs/A-1::repo1": { },
			"dev-libs/A-2::repo1": { },
			"dev-libs/A-1::repo2": { },

			#Packages in exactly one repo
			"dev-libs/B-1": { },
			"dev-libs/C-1::repo1": { },

			#Package in repository 1 and 2, but 1 must be used
			"dev-libs/D-1::repo1": { },
			"dev-libs/D-1::repo2": { },

			"dev-libs/E-1": { },
			"dev-libs/E-1::repo1": { },
			"dev-libs/E-1::repo2": { "SLOT": "1" },

			"dev-libs/F-1::repo1": { "SLOT": "1" },
			"dev-libs/F-1::repo2": { "SLOT": "1" },

			"dev-libs/G-1::repo1": { "EAPI" : "4", "IUSE":"+x +y", "REQUIRED_USE" : "" },
			"dev-libs/G-1::repo2": { "EAPI" : "4", "IUSE":"+x +y", "REQUIRED_USE" : "^^ ( x y )" },

			"dev-libs/H-1": {	"KEYWORDS": "x86", "EAPI" : "3",
								"RDEPEND" : "|| ( dev-libs/I:2 dev-libs/I:1 )" },

			"dev-libs/I-1::repo2": { "SLOT" : "1"},
			"dev-libs/I-2::repo2": { "SLOT" : "2"},

			"dev-libs/K-1::repo2": { },
			}

		installed = {
			"dev-libs/H-1": { "RDEPEND" : "|| ( dev-libs/I:2 dev-libs/I:1 )", "EAPI" : "3" },
			"dev-libs/I-2::repo1": {"SLOT" : "2"},
			"dev-libs/K-1::repo1": { },
			}

		binpkgs = {
			"dev-libs/C-1::repo2": { },
			"dev-libs/I-2::repo1": {"SLOT" : "2"},
			"dev-libs/K-1::repo2": { },
			}

		sets = {
			"multirepotest":
				("dev-libs/A::test_repo",)
		}

		test_cases = (
			#Simple repo selection
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-2::repo1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A::test_repo"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A::repo2"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-1::repo2"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/A-1::repo1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-1::repo1"]),
			ResolverPlaygroundTestCase(
				["@multirepotest"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-1"]),

			#Packages in exactly one repo
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/C-1::repo1"]),

			#Package in repository 1 and 2, but 2 must be used
			ResolverPlaygroundTestCase(
				["dev-libs/D"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/D-1::repo2"]),

			#--usepkg: don't reinstall on new repo without --newrepo
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				options = {"--usepkg": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["[binary]dev-libs/C-1::repo2"]),

			#--usepkgonly: don't reinstall on new repo without --newrepo
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				options = {"--usepkgonly": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["[binary]dev-libs/C-1::repo2"]),

			#--newrepo: pick ebuild if binpkg/ebuild have different repo
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				options = {"--usepkg": True, "--newrepo": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/C-1::repo1"]),

			#--newrepo --usepkgonly: ebuild is ignored
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				options = {"--usepkgonly": True, "--newrepo": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["[binary]dev-libs/C-1::repo2"]),

			#--newrepo: pick ebuild if binpkg/ebuild have different repo
			ResolverPlaygroundTestCase(
				["dev-libs/I"],
				options = {"--usepkg": True, "--newrepo": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/I-2::repo2"]),

			#--newrepo --usepkgonly: if binpkg matches installed, do nothing
			ResolverPlaygroundTestCase(
				["dev-libs/I"],
				options = {"--usepkgonly": True, "--newrepo": True, "--selective": True},
				success = True,
				mergelist = []),

			#--newrepo --usepkgonly: reinstall if binpkg has new repo.
			ResolverPlaygroundTestCase(
				["dev-libs/K"],
				options = {"--usepkgonly": True, "--newrepo": True, "--selective": True},
				success = True,
				check_repo_names = True,
				mergelist = ["[binary]dev-libs/K-1::repo2"]),

			#--usepkgonly: don't reinstall on new repo without --newrepo.
			ResolverPlaygroundTestCase(
				["dev-libs/K"],
				options = {"--usepkgonly": True, "--selective": True},
				success = True,
				mergelist = []),

			#Atoms with slots
			ResolverPlaygroundTestCase(
				["dev-libs/E"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/E-1::repo2"]),
			ResolverPlaygroundTestCase(
				["dev-libs/E:1::repo2"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/E-1::repo2"]),
			ResolverPlaygroundTestCase(
				["dev-libs/E:1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/E-1::repo2"]),
			ResolverPlaygroundTestCase(
				["dev-libs/F:1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/F-1::repo2"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/F-1:1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/F-1::repo2"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/F-1:1::repo1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/F-1::repo1"]),

			# Dependency on installed dev-libs/C-2 ebuild for which ebuild is
			# not available from the same repo should not unnecessarily
			# reinstall the same version from a different repo.
			ResolverPlaygroundTestCase(
				["dev-libs/H"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = []),

			# Dependency on installed dev-libs/I-2 ebuild should trigger reinstall
			# when --newrepo flag is used.
			ResolverPlaygroundTestCase(
				["dev-libs/H"],
				options = {"--update": True, "--deep": True, "--newrepo": True},
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/I-2::repo2"]),

			# Check interaction between repo priority and unsatisfied
			# REQUIRED_USE, for bug #350254.
			ResolverPlaygroundTestCase(
				["=dev-libs/G-1"],
				check_repo_names = True,
				success = False),

			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			binpkgs=binpkgs, installed=installed, sets=sets)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testMultirepoUserConfig(self):
		ebuilds = {
			#package.use test
			"dev-libs/A-1": { "IUSE": "foo" },
			"dev-libs/A-2::repo1": { "IUSE": "foo" },
			"dev-libs/A-3::repo2": { },
			"dev-libs/B-1": { "DEPEND": "dev-libs/A", "EAPI": 2 },
			"dev-libs/B-2": { "DEPEND": "dev-libs/A[foo]", "EAPI": 2 },
			"dev-libs/B-3": { "DEPEND": "dev-libs/A[-foo]", "EAPI": 2 },

			#package.accept_keywords test
			"dev-libs/C-1": { "KEYWORDS": "~x86" },
			"dev-libs/C-1::repo1": { "KEYWORDS": "~x86" },

			#package.license
			"dev-libs/D-1": { "LICENSE": "TEST" },
			"dev-libs/D-1::repo1": { "LICENSE": "TEST" },

			#package.mask
			"dev-libs/E-1": { },
			"dev-libs/E-1::repo1": { },
			"dev-libs/H-1": { },
			"dev-libs/H-1::repo1": { },
			"dev-libs/I-1::repo2": { "SLOT" : "1"},
			"dev-libs/I-2::repo2": { "SLOT" : "2"},
			"dev-libs/J-1": {	"KEYWORDS": "x86", "EAPI" : "3",
								"RDEPEND" : "|| ( dev-libs/I:2 dev-libs/I:1 )" },

			#package.properties
			"dev-libs/F-1": { "PROPERTIES": "bar"},
			"dev-libs/F-1::repo1": { "PROPERTIES": "bar"},

			#package.unmask
			"dev-libs/G-1": { },
			"dev-libs/G-1::repo1": { },

			#package.mask with wildcards
			"dev-libs/Z-1::repo3": { },
			}

		installed = {
			"dev-libs/J-1": { "RDEPEND" : "|| ( dev-libs/I:2 dev-libs/I:1 )", "EAPI" : "3" },
			"dev-libs/I-2::repo1": {"SLOT" : "2"},
			}

		user_config = {
			"package.use":
				(
					"dev-libs/A::repo1 foo",
				),
			"package.accept_keywords":
				(
					"=dev-libs/C-1::test_repo",
				),
			"package.license":
				(
					"=dev-libs/D-1::test_repo TEST",
				),
			"package.mask":
				(
					"dev-libs/E::repo1",
					"dev-libs/H",
					"dev-libs/I::repo1",
					#needed for package.unmask test
					"dev-libs/G",
					#wildcard test
					"*/*::repo3",
				),
			"package.properties":
				(
					"dev-libs/F::repo1 -bar",
				),
			"package.unmask":
				(
					"dev-libs/G::test_repo",
				),
			}

		test_cases = (
			#package.use test
			ResolverPlaygroundTestCase(
				["=dev-libs/B-1"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-3::repo2", "dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/B-2"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/A-2::repo1", "dev-libs/B-2"]),
			ResolverPlaygroundTestCase(
				["=dev-libs/B-3"],
				options = { "--autounmask": 'n' },
				success = False,
				check_repo_names = True),

			#package.accept_keywords test
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/C-1"]),

			#package.license test
			ResolverPlaygroundTestCase(
				["dev-libs/D"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/D-1"]),

			#package.mask test
			ResolverPlaygroundTestCase(
				["dev-libs/E"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/E-1"]),

			# Dependency on installed dev-libs/C-2 ebuild for which ebuild is
			# masked from the same repo should not unnecessarily pull
			# in a different slot. It should just pull in the same slot from
			# a different repo (bug #351828).
			ResolverPlaygroundTestCase(
				["dev-libs/J"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/I-2"]),

			#package.properties test
			ResolverPlaygroundTestCase(
				["dev-libs/F"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/F-1"]),

			#package.mask test
			ResolverPlaygroundTestCase(
				["dev-libs/G"],
				success = True,
				check_repo_names = True,
				mergelist = ["dev-libs/G-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/H"],
				options = { "--autounmask": 'n' },
				success = False),

			#package.mask with wildcards
			ResolverPlaygroundTestCase(
				["dev-libs/Z"],
				options = { "--autounmask": 'n' },
				success = False),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
