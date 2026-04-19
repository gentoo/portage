# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests.resolver.ResolverPlayground import ResolverPlaygroundTestCase
from portage.tests.resolver.test_binpackage_selection import BinPkgSelectionTestCase


class BinPkgPatchTestCaseWithPatches(BinPkgSelectionTestCase):
    files = ["user.patch", "random.diff"]

    def testBinPkgWithPatches(self):
        pkgs = self.pkgs_no_deps | self.pkgs_no_deps_newer | self.pkgs_with_slots
        patches = {
            "app-misc/foo": self.files,
            "app-misc/bar-1.1": self.files,
            "app-misc/baz:2": self.files,
        }

        test_cases = (
            # all binaries of app-misc/foo masked by patches
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/foo-2.0"],
            ),
            ResolverPlaygroundTestCase(
                ["=app-misc/foo-1.1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/foo-1.1"],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/foo:1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/foo-1.0"],
            ),
            # only app-misc/bar-1.1 masked by patches
            ResolverPlaygroundTestCase(
                ["app-misc/bar"],
                success=True,
                options={"--usepkg": True},
                mergelist=["[binary]app-misc/bar-2.0"],
            ),
            ResolverPlaygroundTestCase(
                ["=app-misc/bar-1.1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/bar-1.1"],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/bar:1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["[binary]app-misc/bar-1.0"],
            ),
            # only slot app-misc/baz:2 masked by patches
            ResolverPlaygroundTestCase(
                ["app-misc/baz"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/baz-2.0"],
            ),
            ResolverPlaygroundTestCase(
                ["=app-misc/baz-1.1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["[binary]app-misc/baz-1.1"],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/baz:1"],
                success=True,
                options={"--usepkg": True},
                mergelist=["[binary]app-misc/baz-1.0"],
            ),
            # --usepkg-exclude/include to not change this behaviour
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-exclude": ["foo"]},
                mergelist=["app-misc/foo-2.0"],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-include": ["foo"]},
                mergelist=["app-misc/foo-2.0"],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=pkgs, ebuilds=pkgs, patches=patches
        )

    def testBinPkgExcludePatches(self):
        pkgs = self.pkgs_no_deps
        patches = {
            "app-misc/foo": self.files,
        }

        test_cases = (
            # --usepkg-exclude-patches=n overrides default of respecting patches
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--usepkg-exclude-patches": False},
                mergelist=["[binary]app-misc/foo-1.0"],
            ),
            # patches to be ignored with --usepkgonly
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkgonly": True},
                mergelist=["[binary]app-misc/foo-1.0"],
            ),
            # --usepkg-exclude-patches=y to re-assert default even when it breaks
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=False,
                options={"--usepkgonly": True, "--usepkg-exclude-patches": True},
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=pkgs, ebuilds=pkgs, patches=patches
        )
