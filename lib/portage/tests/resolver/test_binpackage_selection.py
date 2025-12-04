# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


# attach build-ids to existing package collection
def with_build_id(pkgs, build):
    return [(cpv, meta | {"BUILD_ID": build}) for cpv, meta in pkgs.items()]


# base class for unit tests of binary package selection options
class BinPkgSelectionTestCase(TestCase):
    pkgs_no_deps = {
        "app-misc/foo-1.0": {},
        "app-misc/bar-1.0": {},
        "app-misc/baz-1.0": {},
    }

    pkgs_no_deps_newer = {
        "app-misc/foo-1.1": {},
        "app-misc/bar-1.1": {},
        "app-misc/baz-1.1": {},
    }

    pkgs_with_deps_newer = {
        "app-misc/foo-1.1": {"RDEPEND": "app-misc/bar"},
        "app-misc/bar-1.1": {"RDEPEND": "app-misc/baz"},
        "app-misc/baz-1.1": {},
    }

    pkgs_other_repo = {
        "app-misc/foo-1.0::other_repo": {},
        "app-misc/bar-1.0::other_repo": {},
        "app-misc/baz-1.0::other_repo": {},
    }

    pkgs_with_deps = {
        "app-misc/foo-1.0": {"RDEPEND": "app-misc/bar"},
        "app-misc/bar-1.0": {"RDEPEND": "app-misc/baz"},
        "app-misc/baz-1.0": {},
    }

    pkgs_with_slots = {
        "app-misc/foo-1.0": {"SLOT": "1"},
        "app-misc/foo-2.0": {"SLOT": "2"},
        "app-misc/bar-1.0": {"SLOT": "1"},
        "app-misc/bar-2.0": {"SLOT": "2"},
        "app-misc/baz-1.0": {"SLOT": "1"},
        "app-misc/baz-2.0": {"SLOT": "2"},
    }

    pkg_atoms = ["app-misc/foo", "app-misc/bar", "app-misc/baz"]

    # runs multiple test cases in the same playground
    def runBinPkgSelectionTest(self, test_cases, **kwargs):
        playground = ResolverPlayground(**kwargs)

        try:
            for n, test_case in enumerate(test_cases):
                with self.subTest(f"Test {n+1}/{len(test_cases)}"):
                    playground.run_TestCase(test_case)
                    self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    # runs multiple test cases in multiple playgrounds with different config
    def runBinPkgSelectionTestUserConfig(self, config, test_cases, **kwargs):
        for n, test_case in enumerate(test_cases.items()):
            lines, tests = test_case
            kwargs.setdefault("user_config", {})[config] = lines

            with self.subTest(f"Playground {n+1}/{len(test_cases)}"):
                self.runBinPkgSelectionTest(tests, **kwargs)


# test --getbinpkg-exclude option
class GetBinPkgExcludeTestCase(BinPkgSelectionTestCase):

    def testGetBinPkgExcludeOpt(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps

        binrepos = {"test_binrepo": self.pkgs_no_deps}

        test_cases = (
            # --getbinpkg-exclude to have no effect without --getbinpkg
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkgonly": True, "--getbinpkg-exclude": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # --getbinpkg-exclude with unmatched atom excludes no remote binaries
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["dev-libs/foo"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # --getbinpkg-exclude in conflict with --getbinpkg-include to have no effect
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["foo"],
                    "--getbinpkg-include": ["foo"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # --getbinpkg-exclude in conflict with --getbinpkg-include to not
            # interfere with non-overlapping --getbinpkg-exclude
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["foo", "bar"],
                    "--getbinpkg-include": ["foo"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-exclude with single atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-exclude with multiple atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["foo", "bar"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-exclude with wildcard
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["app-misc/b*"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # combined use of --getbinpkg-exclude and --usepkg-exclude can have
            # a complimentary effect (leaving some remote binaries selected)...
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["app-misc/b*"],
                    "--usepkg-exclude": ["baz"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # ...or an overriding effect with no remote binaries selected. depends
            # on the overlap in the specified atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["app-misc/b*"],
                    "--usepkg-exclude": ["foo"],
                },
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )

    def testGetBinPkgExcludeFallbacks(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps | self.pkgs_no_deps_newer

        binrepos = {"test_binrepo": self.pkgs_no_deps_newer}

        test_cases = (
            # prefer newer ebuild over old local binary where --getbinpkg-exclude
            # prevents fetching newer remote binary and --usepkgonly is not used
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.1",
                    "[binary,remote]app-misc/bar-1.1",
                    "[binary,remote]app-misc/baz-1.1",
                ],
            ),
            # --usepkgonly excludes newer ebuilds and so forces fallback on older
            # local binary where --getbinpkg-exclude is used
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkgonly": True,
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.1",
                    "[binary,remote]app-misc/baz-1.1",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    # currently --getbinpkgonly is equivalent to previous test
                    "--getbinpkgonly": True,
                    "--getbinpkg-exclude": ["foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.1",
                    "[binary,remote]app-misc/baz-1.1",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )

    def testGetBinPkgExcludeSlot(self):
        ebuilds = self.pkgs_with_slots
        binpkgs = self.pkgs_with_slots

        binrepos = {"test_binrepo": self.pkgs_with_slots}

        test_cases = (
            # request all packages and --getbinpkg-exclude with single slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["foo:2"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "[binary,remote]app-misc/bar-2.0",
                    "[binary,remote]app-misc/baz-2.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["foo:2"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "[binary,remote]app-misc/bar-2.0",
                    "[binary,remote]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --getbinpkg-exclude with wildcard slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-exclude": ["app-misc/b*:2"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --getbinpkg-exclude with unmatched slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["app-misc/foo:1"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-2.0",
                    "[binary,remote]app-misc/bar-2.0",
                    "[binary,remote]app-misc/baz-2.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )


# test --getbinpkg-include option
class GetBinPkgIncludeTestCase(BinPkgSelectionTestCase):

    def testGetBinPkgIncludeOpt(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps

        binrepos = {"test_binrepo": self.pkgs_no_deps}

        test_cases = (
            # --getbinpkg-include to have no effect without --getbinpkg
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg-include": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkgonly": True, "--getbinpkg-include": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # --getbinpkg-include with unmatched atom excludes all remote binaries
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["dev-libs/foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-include with single atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["foo"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-include with multiple atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["foo", "bar"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --getbinpkg-include with wildcard
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["app-misc/b*"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # --getbinpkg-include in conflict with --getbinpkg-exclude to not
            # interfere with non-overlapping --getbinpkg-include
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-exclude": ["foo"],
                    "--getbinpkg-include": ["foo", "bar"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary,remote]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # combined use of --getbinpkg-include and --usepkg-include can have
            # a complimentary effect (leaving some remote binaries selected)...
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-include": ["app-misc/b*"],
                    "--usepkg-include": ["baz"],
                },
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "[binary,remote]app-misc/baz-1.0",
                ],
            ),
            # ...or an overriding effect with no remote binaries selected. depends
            # on the overlap in the specified atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--getbinpkg": True,
                    "--getbinpkg-include": ["app-misc/b*"],
                    "--usepkg-include": ["foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )

    def testGetBinPkgIncludeFallbacks(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps | self.pkgs_no_deps_newer

        binrepos = {"test_binrepo": self.pkgs_no_deps_newer}

        test_cases = (
            # prefer newer ebuild over old local binary where --getbinpkg-include
            # prevents fetching newer remote binary and --usepkgonly is not used
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["foo"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-1.1",
                    "app-misc/bar-1.1",
                    "app-misc/baz-1.1",
                ],
            ),
            # --usepkgonly excludes newer ebuilds and so forces fallback on older
            # local binary where --getbinpkg-include is used
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkgonly": True,
                    "--getbinpkg": True,
                    "--getbinpkg-include": ["foo"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-1.1",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    # currently --getbinpkgonly is equivalent to previous test
                    "--getbinpkgonly": True,
                    "--getbinpkg-include": ["foo"],
                },
                mergelist=[
                    "[binary,remote]app-misc/foo-1.1",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )

    def testGetBinPkgIncludeSlot(self):
        ebuilds = self.pkgs_with_slots
        binpkgs = self.pkgs_with_slots

        binrepos = {"test_binrepo": self.pkgs_with_slots}

        test_cases = (
            # request all packages and --getbinpkg-include with single slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["foo:2"]},
                mergelist=[
                    "[binary,remote]app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --getbinpkg-include with wildcard slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--getbinpkg": True, "--getbinpkg-include": ["app-misc/b*:2"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "[binary,remote]app-misc/bar-2.0",
                    "[binary,remote]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --getbinpkg-include with unmatched slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--getbinpkg-include": ["app-misc/foo:1"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, binrepos=binrepos, ebuilds=ebuilds
        )


# test --usepkg-exclude option
class UsePkgExcludeTestCase(BinPkgSelectionTestCase):

    def testUsePkgExcludeOpt(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps
        installed = self.pkgs_no_deps

        test_cases = (
            # --usepkg-exclude to have no effect without --usepkg
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # --usepkg-exclude in conflict with --usepkg-include to have no effect
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkg": True,
                    "--usepkg-exclude": ["foo"],
                    "--usepkg-include": ["foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # --usepkg-exclude with unmatched atom excludes no binaries
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkg": True,
                    "--usepkg-exclude": ["dev-libs/foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-exclude with a single atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-exclude with multiple atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo", "bar"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-exclude with wildcard
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["app-misc/b*"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-exclude with a single atom
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-exclude with multiple atoms
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo", "bar"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-exclude with wildcard
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["app-misc/b*"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # --usepkg-exclude may not intersect requested atoms with --usepkgonly
            ResolverPlaygroundTestCase(
                ["app-misc/foo", "app-misc/bar"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkgonly": True, "--usepkg-exclude": ["baz"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=False,
                options={"--usepkgonly": True, "--usepkg-exclude": ["foo"]},
            ),
            # conflicting --usepkg-include and --usepkg-exclude to not interfere
            # with non-overlapping --usepkg-exclude
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkg": True,
                    "--usepkg-exclude": ["foo", "bar"],
                    "--usepkg-include": ["foo"],
                },
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, ebuilds=ebuilds, installed=installed
        )

    def testUsePkgExcludeDeps(self):
        binpkgs = self.pkgs_with_deps
        ebuilds = self.pkgs_with_deps

        test_cases = (
            # request foo --usepkg-exclude for a single dependency
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-exclude": ["baz"]},
                mergelist=[
                    "app-misc/baz-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            # request foo and --usepkg-exclude for multiple dependencies
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-exclude": ["bar baz"]},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            # request foo and --usepkg-exclude with wildcard matching dependencies
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-exclude": ["app-misc/b*"]},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            # exclude all binary dependencies using --nobindeps
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            # --usebinpkg-exclude to have no effect on --nobindeps
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={
                    "--usepkg": True,
                    "--nobindeps": True,
                    "--usepkg-exclude": ["foo"],
                },
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            # --nobindeps should work for arguments that cannot normally be put
            # on the --usepkg-include list, e.g. versions operators, repo, etc,
            # and also sets, for which see testUsePkgExcludeUpdate().
            ResolverPlaygroundTestCase(
                ["=app-misc/foo-1.0"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                [">app-misc/foo-0.9"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/foo::test_repo"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(test_cases, binpkgs=binpkgs, ebuilds=ebuilds)

    def testUsePkgExcludeSlot(self):
        ebuilds = self.pkgs_with_slots
        binpkgs = self.pkgs_with_slots

        test_cases = (
            # request all packages and --usepkg-exclude with single slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo:2"]},
                mergelist=[
                    "app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --usepkg-exclude with wildcard slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["app-misc/b*:2"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "app-misc/bar-2.0",
                    "app-misc/baz-2.0",
                ],
            ),
            # request all packages and --usepkg-exclude with unmatched slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-exclude": ["app-misc/foo:1"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(test_cases, binpkgs=binpkgs, ebuilds=ebuilds)

    def testUsePkgExcludeUpdate(self):
        ebuilds = self.pkgs_with_deps | self.pkgs_with_deps_newer
        binpkgs = self.pkgs_with_deps | self.pkgs_with_deps_newer
        installed = self.pkgs_with_deps
        world = ("app-misc/foo",)

        test_cases = (
            # world update and --usepkg-exclude with single atom
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--usepkg-exclude": ["baz"],
                },
                mergelist=[
                    "app-misc/baz-1.1",
                    "[binary]app-misc/bar-1.1",
                    "[binary]app-misc/foo-1.1",
                ],
            ),
            # world update and --usepkg-exclude with wildcard
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--usepkg-exclude": ["app-misc/b*"],
                },
                mergelist=[
                    "app-misc/baz-1.1",
                    "app-misc/bar-1.1",
                    "[binary]app-misc/foo-1.1",
                ],
            ),
            # world update with --nobindeps
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--nobindeps": True,
                },
                mergelist=[
                    "app-misc/baz-1.1",
                    "app-misc/bar-1.1",
                    "[binary]app-misc/foo-1.1",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            installed=installed,
            world=world,
        )

    def testUsePkgExcludeReposConf(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps

        test_cases = {
            (
                "[test_repo]",
                "usepkg-exclude = foo",
            ): (
                # reposconf.conf attributes to have no effect without --usepkg
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    mergelist=[
                        "app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
                # request all packages with usepkg-exclude in repos.conf
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True},
                    mergelist=[
                        "app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
                # suppliment repos.conf with --usepkg-exclude on command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-exclude": ["bar"]},
                    mergelist=[
                        "app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
                # override repos.conf with --usepkg-include on command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-include": ["foo"]},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
            ),
            (
                "[test_repo]",
                "usepkg-exclude = foo",
                "usepkg-include = foo",
            ): (
                # conflicted repos.conf attributes to have no effect
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
            ),
            (
                "[test_repo]",
                "usepkg-exclude = foo bar",
                "usepkg-include = foo",
            ): (
                # conflicted repos.conf attributes to not interfere with
                # non-overlapping usepkg-exclude
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
                # remaining atoms in repos.conf sourced lists after conflicting
                # attributes have been filtered still to be overridable using
                # --usepkg-include on command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-include": ["bar"]},
                    mergelist=[
                        "app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
            ),
        }

        self.runBinPkgSelectionTestUserConfig(
            "repos.conf",
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
        )

    def testUsePkgExcludeReposConfDeps(self):
        binpkgs = self.pkgs_with_deps
        ebuilds = self.pkgs_with_deps

        user_config = {
            "repos.conf": (
                "[test_repo]",
                "usepkg-exclude = foo",
            )
        }

        test_cases = (
            # usepkg-exclude in repos.conf to have no effect on --nobindeps
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            user_config=user_config,
        )

    def testUsePkgExcludeMultiRepo(self):
        # see commentary in testGetBinPkgExcludeMultiBinrepo()
        pkgs_no_deps = with_build_id(self.pkgs_no_deps, "1")
        pkgs_other_repo = with_build_id(self.pkgs_other_repo, "2")

        ebuilds = self.pkgs_no_deps | self.pkgs_other_repo
        binpkgs = pkgs_no_deps + pkgs_other_repo

        user_config = {
            "repos.conf": (
                "[test_repo]",
                "usepkg-exclude = foo",
                "[other_repo]",
                "usepkg-exclude = bar",
            )
        }

        # note that repository priority order is not well defined *within* pkgdir
        # and so test cases which assume a plan c/p atom will resolve to a binary
        # for any given repo implicitly can spuriously fail, regardless of priority
        # set in repos.conf.
        #
        # TL;DR = all atoms in these tests cases *must* be ::repo qualified!
        test_cases = (
            # request test_repo for which only app-misc/foo is excluded in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::test_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0-1",
                    "[binary]app-misc/baz-1.0-1",
                ],
            ),
            # request other_repo for which only app-misc/bar is excluded in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::other_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::other_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "[binary]app-misc/foo-1.0-2::other_repo",
                    "app-misc/bar-1.0::other_repo",
                    "[binary]app-misc/baz-1.0-2::other_repo",
                ],
            ),
            # use repo qualifier to request packages from repos for which both
            # app-misc/foo and app-misc/bar are excluded in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0::other_repo",
                    "[binary]app-misc/baz-1.0-1",
                ],
            ),
            # use repo qualifier to request packages from repos for which neither
            # app-misc/foo nor app-misc/bar are excluded in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::other_repo",
                    "app-misc/bar::test_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "[binary]app-misc/foo-1.0-2::other_repo",
                    "[binary]app-misc/bar-1.0-1",
                    "[binary]app-misc/baz-1.0-1",
                ],
            ),
            # use repo qualifier to arrange for neither app-misc/foo nor app-misc/bar
            # to be binary, but override repos.conf for foo using --usepkg-include
            # which implicitly excludes app-misc/baz as the command line option
            # applies to all repositories
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True, "--usepkg-include": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0-1",
                    "app-misc/bar-1.0::other_repo",
                    "app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            user_config=user_config,
        )


# test --usepkg-include option
class UsePkgIncludeTestCase(BinPkgSelectionTestCase):

    def testUsePkgIncludeOpt(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps
        installed = self.pkgs_no_deps

        test_cases = (
            # --usepkg-include to have no effect without --usepkg
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg-include": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # --usepkg-include with unmatched atom excludes all binaries
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkg": True,
                    "--usepkg-include": ["dev-libs/foo"],
                },
                mergelist=[
                    "app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-include with single atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-include with multiple atoms
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["foo", "bar"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request all packages and --usepkg-include with wildcard
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["app-misc/b*"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-include with single atom
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["foo"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-include with multiple atoms
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["app-misc/b*"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "[binary]app-misc/baz-1.0",
                ],
            ),
            # request @installed set and --usepkg-include with wildcard
            ResolverPlaygroundTestCase(
                ["@installed"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["foo", "bar"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # --usepkg-include must encompass all requested atoms with --usepkgonly
            ResolverPlaygroundTestCase(
                ["app-misc/foo", "app-misc/bar"],
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkgonly": True, "--usepkg-include": ["foo", "bar"]},
                mergelist=[
                    "[binary]app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                ],
            ),
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=False,
                options={"--usepkgonly": True, "--usepkg-include": ["foo"]},
            ),
            # conflicting --usepkg-include and --usepkg-exclude to not interfere
            # with non-overlapping --usepkg-include
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={
                    "--usepkg": True,
                    "--usepkg-exclude": ["foo"],
                    "--usepkg-include": ["foo", "bar"],
                },
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, ebuilds=ebuilds, installed=installed
        )

    def testUsePkgIncludeDeps(self):
        binpkgs = self.pkgs_with_deps
        ebuilds = self.pkgs_with_deps

        test_cases = (
            # request for --usepkg-include for a single dependency
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-include": ["bar"]},
                mergelist=[
                    "app-misc/baz-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/foo-1.0",
                ],
            ),
            # request for --usepkg-include for multiple dependencies
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-include": ["bar baz"]},
                mergelist=[
                    "[binary]app-misc/baz-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/foo-1.0",
                ],
            ),
            # request for --usepkg-include with wildcard matching dependencies
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-include": ["app-misc/b*"]},
                mergelist=[
                    "[binary]app-misc/baz-1.0",
                    "[binary]app-misc/bar-1.0",
                    "app-misc/foo-1.0",
                ],
            ),
            # --usebinpkg-include to have no effect on --nobindeps
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={
                    "--usepkg": True,
                    "--nobindeps": True,
                    "--usepkg-include": ["app-misc/b*"],
                },
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(test_cases, binpkgs=binpkgs, ebuilds=ebuilds)

    def testUsePkgIncludeSlot(self):
        ebuilds = self.pkgs_with_slots
        binpkgs = self.pkgs_with_slots

        test_cases = (
            # request all packages and --usepkg-include with single slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["foo:2"]},
                mergelist=[
                    "[binary]app-misc/foo-2.0",
                    "app-misc/bar-2.0",
                    "app-misc/baz-2.0",
                ],
            ),
            # request all packages and --usepkg-include with wildcard slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["app-misc/b*:2"]},
                mergelist=[
                    "app-misc/foo-2.0",
                    "[binary]app-misc/bar-2.0",
                    "[binary]app-misc/baz-2.0",
                ],
            ),
            # request all packages and --usepkg-include with unmatched slot atom
            ResolverPlaygroundTestCase(
                self.pkg_atoms,
                success=True,
                ignore_mergelist_order=True,
                options={"--usepkg": True, "--usepkg-include": ["app-misc/foo:1"]},
                mergelist=[
                    "app-misc/foo-2.0",
                    "app-misc/bar-2.0",
                    "app-misc/baz-2.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(test_cases, binpkgs=binpkgs, ebuilds=ebuilds)

    def testUsePkgIncludeUpdate(self):
        ebuilds = self.pkgs_with_deps | self.pkgs_with_deps_newer
        binpkgs = self.pkgs_with_deps | self.pkgs_with_deps_newer
        installed = self.pkgs_with_deps
        world = ("app-misc/foo",)

        test_cases = (
            # world update and --usepkg-include with single atom
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--usepkg-include": ["baz"],
                },
                mergelist=[
                    "[binary]app-misc/baz-1.1",
                    "app-misc/bar-1.1",
                    "app-misc/foo-1.1",
                ],
            ),
            # world update and --usepkg-include with wildcard
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--usepkg-include": ["app-misc/b*"],
                },
                mergelist=[
                    "[binary]app-misc/baz-1.1",
                    "[binary]app-misc/bar-1.1",
                    "app-misc/foo-1.1",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            installed=installed,
            world=world,
        )

    def testUsePkgIncludeReposConf(self):
        binpkgs = self.pkgs_no_deps
        ebuilds = self.pkgs_no_deps

        test_cases = {
            (
                "[test_repo]",
                "usepkg-include = foo",
            ): (
                # repos.conf attribute to have no effect without --usepkg
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    mergelist=[
                        "app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
                # request all packages with usepkg-include in repos.conf
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
                # suppliment repos.conf with --usepkg-include on command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-include": ["bar"]},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
                # override repos.conf with --usepkg-exclude on  command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-exclude": ["foo"]},
                    mergelist=[
                        "app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
            ),
            (
                "[test_repo]",
                "usepkg-exclude = foo",
                "usepkg-include = foo bar",
            ): (
                # conflicted repos.conf attributes to not interfere with
                # non-overlapping usepkg-include
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True},
                    mergelist=[
                        "app-misc/foo-1.0",
                        "[binary]app-misc/bar-1.0",
                        "app-misc/baz-1.0",
                    ],
                ),
                # remaining atoms in repos.conf sourced lists after conflicting
                # attributes have been filtered still to be overridable using
                # --usepkg-exclude on command line
                ResolverPlaygroundTestCase(
                    self.pkg_atoms,
                    success=True,
                    ignore_mergelist_order=True,
                    options={"--usepkg": True, "--usepkg-exclude": ["bar"]},
                    mergelist=[
                        "[binary]app-misc/foo-1.0",
                        "app-misc/bar-1.0",
                        "[binary]app-misc/baz-1.0",
                    ],
                ),
            ),
        }

        self.runBinPkgSelectionTestUserConfig(
            "repos.conf",
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
        )

    def testUsePkgIncludeReposConfDeps(self):
        binpkgs = self.pkgs_with_deps
        ebuilds = self.pkgs_with_deps

        user_config = {
            "repos.conf": (
                "[test_repo]",
                "usepkg-include = bar",
            )
        }

        test_cases = (
            # usepkg-include in repos.conf to have no effect on --nobindeps
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--nobindeps": True},
                mergelist=[
                    "app-misc/baz-1.0",
                    "app-misc/bar-1.0",
                    "[binary]app-misc/foo-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            user_config=user_config,
        )

    def testUsePkgIncludeMultiRepo(self):
        # see commentary in testGetBinPkgExcludeMultiBinrepo()
        pkgs_no_deps = with_build_id(self.pkgs_no_deps, "1")
        pkgs_other_repo = with_build_id(self.pkgs_other_repo, "2")

        ebuilds = self.pkgs_no_deps | self.pkgs_other_repo
        binpkgs = pkgs_no_deps + pkgs_other_repo

        user_config = {
            "repos.conf": (
                "[test_repo]",
                "usepkg-include = foo",
                "[other_repo]",
                "usepkg-include = bar",
            )
        }

        # all atoms in these tests cases *must* be ::repo qualified! see comments
        # in testUsePkgExcludeMultiRepo()
        test_cases = (
            # request test_repo for which only app-misc/foo is included in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::test_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "[binary]app-misc/foo-1.0-1",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # request other_repo for which only app-misc/bar is included in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::other_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::other_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "app-misc/foo-1.0::other_repo",
                    "[binary]app-misc/bar-1.0-2::other_repo",
                    "app-misc/baz-1.0::other_repo",
                ],
            ),
            # use repo qualifier to request packages from repos for which both
            # app-misc/foo and app-misc/bar are included in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "[binary]app-misc/foo-1.0-1",
                    "[binary]app-misc/bar-1.0-2::other_repo",
                    "app-misc/baz-1.0",
                ],
            ),
            # use repo qualifier to request packages from repos for which neither
            # app-misc/foo nor app-misc/bar are included in repos.conf
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::other_repo",
                    "app-misc/bar::test_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True},
                mergelist=[
                    "app-misc/foo-1.0::other_repo",
                    "app-misc/bar-1.0",
                    "app-misc/baz-1.0",
                ],
            ),
            # use repo qualifier to arrange for both app-misc/foo and app-misc/bar
            # to be binary, but override repos.conf for foo using --usepkg-exclude
            # which has no effect on app-misc/baz
            ResolverPlaygroundTestCase(
                [
                    "app-misc/foo::test_repo",
                    "app-misc/bar::other_repo",
                    "app-misc/baz::test_repo",
                ],
                success=True,
                ignore_mergelist_order=True,
                check_repo_names=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo"]},
                mergelist=[
                    "app-misc/foo-1.0",
                    "[binary]app-misc/bar-1.0-2::other_repo",
                    "app-misc/baz-1.0",
                ],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            user_config=user_config,
        )
