# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests.resolver.ResolverPlayground import ResolverPlaygroundTestCase
from portage.tests.resolver.test_binpackage_selection import BinPkgSelectionTestCase


class BinPkgPatchTestCaseWithPatches(BinPkgSelectionTestCase):

    def testBinPkgWithPatches(self):
        pkgs = self.pkgs_no_deps | self.pkgs_no_deps_newer | self.pkgs_with_slots
        files = ["user.patch", "random.diff"]
        patches = {
            "app-misc/foo": files,
            "app-misc/bar-1.1": files,
            "app-misc/baz:2": files,
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
