# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.output import colorize
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class MultirepoTestCase(TestCase):
    def testMultirepo(self):
        ebuilds = {
            # Simple repo selection
            "dev-libs/A-1": {},
            "dev-libs/A-1::repo1": {},
            "dev-libs/A-2::repo1": {},
            "dev-libs/A-1::repo2": {},
            # Packages in exactly one repo
            "dev-libs/B-1": {},
            "dev-libs/C-1::repo1": {},
            # Package in repository 1 and 2, but 1 must be used
            "dev-libs/D-1::repo1": {},
            "dev-libs/D-1::repo2": {},
            "dev-libs/E-1": {},
            "dev-libs/E-1::repo1": {},
            "dev-libs/E-1::repo2": {"SLOT": "1"},
            "dev-libs/F-1::repo1": {"SLOT": "1"},
            "dev-libs/F-1::repo2": {"SLOT": "1"},
            "dev-libs/G-1::repo1": {"EAPI": "4", "IUSE": "+x +y", "REQUIRED_USE": ""},
            "dev-libs/G-1::repo2": {
                "EAPI": "4",
                "IUSE": "+x +y",
                "REQUIRED_USE": "^^ ( x y )",
            },
            "dev-libs/H-1": {
                "KEYWORDS": "x86",
                "EAPI": "3",
                "RDEPEND": "|| ( dev-libs/I:2 dev-libs/I:1 )",
            },
            "dev-libs/I-1::repo2": {"SLOT": "1"},
            "dev-libs/I-2::repo2": {"SLOT": "2"},
            "dev-libs/K-1::repo2": {},
        }

        installed = {
            "dev-libs/H-1": {
                "RDEPEND": "|| ( dev-libs/I:2 dev-libs/I:1 )",
                "EAPI": "3",
            },
            "dev-libs/I-2::repo1": {"SLOT": "2"},
            "dev-libs/K-1::repo1": {},
        }

        binpkgs = {
            "dev-libs/C-1::repo2": {},
            "dev-libs/I-2::repo1": {"SLOT": "2"},
            "dev-libs/K-1::repo2": {},
        }

        sets = {"multirepotest": ("dev-libs/A::test_repo",)}

        test_cases = (
            # Simple repo selection
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-2::repo1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/A::test_repo"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/A::repo2"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/A-1::repo1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-1::repo1"],
            ),
            ResolverPlaygroundTestCase(
                ["@multirepotest"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-1"],
            ),
            # Packages in exactly one repo
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/C-1::repo1"],
            ),
            # Package in repository 1 and 2, but 2 must be used
            ResolverPlaygroundTestCase(
                ["dev-libs/D"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/D-1::repo2"],
            ),
            # --usepkg: don't reinstall on new repo without --newrepo
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                options={"--usepkg": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/C-1::repo2"],
            ),
            # --usepkgonly: don't reinstall on new repo without --newrepo
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                options={"--usepkgonly": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/C-1::repo2"],
            ),
            # --newrepo: pick ebuild if binpkg/ebuild have different repo
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                options={"--usepkg": True, "--newrepo": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/C-1::repo1"],
            ),
            # --newrepo --usepkgonly: ebuild is ignored
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                options={"--usepkgonly": True, "--newrepo": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/C-1::repo2"],
            ),
            # --newrepo: pick ebuild if binpkg/ebuild have different repo
            ResolverPlaygroundTestCase(
                ["dev-libs/I"],
                options={"--usepkg": True, "--newrepo": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/I-2::repo2"],
            ),
            # --newrepo --usepkgonly: if binpkg matches installed, do nothing
            ResolverPlaygroundTestCase(
                ["dev-libs/I"],
                options={"--usepkgonly": True, "--newrepo": True, "--selective": True},
                success=True,
                mergelist=[],
            ),
            # --newrepo --usepkgonly: reinstall if binpkg has new repo.
            ResolverPlaygroundTestCase(
                ["dev-libs/K"],
                options={"--usepkgonly": True, "--newrepo": True, "--selective": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/K-1::repo2"],
            ),
            # --usepkgonly: don't reinstall on new repo without --newrepo.
            ResolverPlaygroundTestCase(
                ["dev-libs/K"],
                options={"--usepkgonly": True, "--selective": True},
                success=True,
                mergelist=[],
            ),
            # Atoms with slots
            ResolverPlaygroundTestCase(
                ["dev-libs/E"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/E-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/E:1::repo2"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/E-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/E:1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/E-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F:1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/F-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/F-1:1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/F-1::repo2"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/F-1:1::repo1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/F-1::repo1"],
            ),
            # Dependency on installed dev-libs/C-2 ebuild for which ebuild is
            # not available from the same repo should not unnecessarily
            # reinstall the same version from a different repo.
            ResolverPlaygroundTestCase(
                ["dev-libs/H"],
                options={"--update": True, "--deep": True},
                success=True,
                mergelist=[],
            ),
            # Dependency on installed dev-libs/I-2 ebuild should trigger reinstall
            # when --newrepo flag is used.
            ResolverPlaygroundTestCase(
                ["dev-libs/H"],
                options={"--update": True, "--deep": True, "--newrepo": True},
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/I-2::repo2"],
            ),
            # Check interaction between repo version priority and unsatisfied
            # REQUIRED_USE, for bug #350254.
            ResolverPlaygroundTestCase(
                ["=dev-libs/G-1"], check_repo_names=True, success=False
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    binpkgs=binpkgs,
                    installed=installed,
                    sets=sets,
                    user_config={
                        "make.conf": (f'BINPKG_FORMAT="{binpkg_format}"',),
                    },
                )

                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()

    def testMultirepoUserConfig(self):
        ebuilds = {
            # package.use test
            "dev-libs/A-1": {"IUSE": "foo"},
            "dev-libs/A-2::repo1": {"IUSE": "foo"},
            "dev-libs/A-3::repo2": {},
            "dev-libs/B-1": {"DEPEND": "dev-libs/A", "EAPI": 2},
            "dev-libs/B-2": {"DEPEND": "dev-libs/A[foo]", "EAPI": 2},
            "dev-libs/B-3": {"DEPEND": "dev-libs/A[-foo]", "EAPI": 2},
            # package.accept_keywords test
            "dev-libs/C-1": {"KEYWORDS": "~x86"},
            "dev-libs/C-1::repo1": {"KEYWORDS": "~x86"},
            # package.license
            "dev-libs/D-1": {"LICENSE": "TEST"},
            "dev-libs/D-1::repo1": {"LICENSE": "TEST"},
            # package.mask
            "dev-libs/E-1": {},
            "dev-libs/E-1::repo1": {},
            "dev-libs/H-1": {},
            "dev-libs/H-1::repo1": {},
            "dev-libs/I-1::repo2": {"SLOT": "1"},
            "dev-libs/I-2::repo2": {"SLOT": "2"},
            "dev-libs/J-1": {
                "KEYWORDS": "x86",
                "EAPI": "3",
                "RDEPEND": "|| ( dev-libs/I:2 dev-libs/I:1 )",
            },
            # package.properties
            "dev-libs/F-1": {"PROPERTIES": "bar"},
            "dev-libs/F-1::repo1": {"PROPERTIES": "bar"},
            # package.unmask
            "dev-libs/G-1": {},
            "dev-libs/G-1::repo1": {},
            # package.mask with wildcards
            "dev-libs/Z-1::repo3": {},
            # package-priority
            "dev-libs/PPA-1": {},
            "dev-libs/PPA-2::pp-repo1": {},
            "dev-libs/PPA-3::pp-repo2": {},
            "dev-libs/PPB-1": {"DEPEND": "=dev-libs/PPA-1"},
            "dev-libs/PPC-1": {"DEPEND": "=dev-libs/PPA-3"},
        }

        installed = {
            "dev-libs/J-1": {
                "RDEPEND": "|| ( dev-libs/I:2 dev-libs/I:1 )",
                "EAPI": "3",
            },
            "dev-libs/I-2::repo1": {"SLOT": "2"},
            "dev-libs/PPA-1": {},
        }

        binpkgs = {
            "dev-libs/PPA-1::pp-repo4": {},
            "dev-libs/PPA-2::pp-repo1": {},
            "dev-libs/PPA-4::pp-repo2": {},
            "dev-libs/PPD-1::pp-repo2": {},
        }

        user_config = {
            "package.use": ("dev-libs/A::repo1 foo",),
            "package.accept_keywords": ("=dev-libs/C-1::test_repo",),
            "package.license": ("=dev-libs/D-1::test_repo TEST",),
            "package.mask": (
                "dev-libs/E::repo1",
                "dev-libs/H",
                "dev-libs/I::repo1",
                # needed for package.unmask test
                "dev-libs/G",
                # wildcard test
                "*/*::repo3",
            ),
            "package.properties": ("dev-libs/F::repo1 -bar",),
            "package.unmask": ("dev-libs/G::test_repo",),
            "repos.conf": (
                "[pp-repo1]",
                "package-priority = 1",
                "[pp-repo2]",
                "package-priority = -1",
            ),
        }

        test_cases = (
            # package.use test
            ResolverPlaygroundTestCase(
                ["=dev-libs/B-1"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-3::repo2", "dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/B-2"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/A-2::repo1", "dev-libs/B-2"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/B-3"],
                options={"--autounmask": "n"},
                success=False,
                check_repo_names=True,
            ),
            # package.accept_keywords test
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/C-1"],
            ),
            # package.license test
            ResolverPlaygroundTestCase(
                ["dev-libs/D"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/D-1"],
            ),
            # package.mask test
            ResolverPlaygroundTestCase(
                ["dev-libs/E"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/E-1"],
            ),
            # Dependency on installed dev-libs/C-2 ebuild for which ebuild is
            # masked from the same repo should not unnecessarily pull
            # in a different slot. It should just pull in the same slot from
            # a different repo (bug #351828).
            ResolverPlaygroundTestCase(
                ["dev-libs/J"],
                options={"--update": True, "--deep": True},
                success=True,
                mergelist=["dev-libs/I-2"],
            ),
            # package.properties test
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/F-1"],
            ),
            # package.mask test
            ResolverPlaygroundTestCase(
                ["dev-libs/G"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/G-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/H"], options={"--autounmask": "n"}, success=False
            ),
            # package.mask with wildcards
            ResolverPlaygroundTestCase(
                ["dev-libs/Z"], options={"--autounmask": "n"}, success=False
            ),
            # PP: v2 in ::repo1 beats v3 in ::repo2.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPA"],
                success=True,
                check_repo_names=True,
                mergelist=["dev-libs/PPA-2::pp-repo1"],
            ),
            # PP: Explicitly requesting deprioritized ::pp-repo2 fails.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPA::pp-repo2"],
                success=False,
            ),
            # PP: Explicitly requesting a non ::pp-repo1 version fails.
            ResolverPlaygroundTestCase(
                ["=dev-libs/PPA-3"],
                success=False,
            ),
            # PP: Explicitly requesting unprioritized ::test_repo fails.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPA::test_repo"],
                success=False,
            ),
            # PP: Installed deprioritized packages are okay when selective.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPA::test_repo"],
                options={"--selective": True},
                success=True,
                mergelist=[],
            ),
            # PP: Installed deprioritized packages are okay as dependencies.
            # Also prioritized repos do not mask packages solely in other repos.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPB"],
                success=True,
                mergelist=["dev-libs/PPB-1"],
            ),
            # PP: Uninstalled deprioritized packages are not okay as deps.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPC"],
                success=False,
            ),
            # PP: Requesting a binpkg from an unconfigured repo succeeds.
            ResolverPlaygroundTestCase(
                ["=dev-libs/PPA-1"],
                options={"--usepkgonly": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/PPA-1::pp-repo4"],
            ),
            # PP: Requesting binpkg from a configured prioritized repo succeeds.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPA"],
                options={"--usepkgonly": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/PPA-2::pp-repo1"],
            ),
            # PP: Requesting binpkg from a configured deprioritized repo fails.
            ResolverPlaygroundTestCase(
                ["=dev-libs/PPA-4"],
                options={"--usepkgonly": True},
                success=False,
            ),
            # PP: Requesting a binpkg with no source succeeds.
            ResolverPlaygroundTestCase(
                ["dev-libs/PPD"],
                options={"--usepkgonly": True},
                success=True,
                check_repo_names=True,
                mergelist=["[binary]dev-libs/PPD-1::pp-repo2"],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                user_config["make.conf"] = (f'BINPKG_FORMAT="{binpkg_format}"',)
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    installed=installed,
                    binpkgs=binpkgs,
                    user_config=user_config,
                )

                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()
