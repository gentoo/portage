# Copyright 2026 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests.ebuild.MockUserPatches import MockUserPatches
from portage.tests.resolver.ResolverPlayground import ResolverPlaygroundTestCase
from portage.tests.resolver.test_binpackage_selection import BinPkgSelectionTestCase


class BinPkgUserPatchTestCase(BinPkgSelectionTestCase):
    files = {
        "user.patch": ("foo"),
        "random.diff": ("foobaz not a patch"),
    }

    def testBinPkgUserPatchMasking(self):
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

    def testBinPkgUserPatchesOption(self):
        pkgs = self.pkgs_no_deps
        patches = {
            "app-misc/foo": self.files,
        }

        test_cases = (
            # --usepkgonly has no solution when user patches mask binpkgs
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=False,
                options={"--usepkgonly": True},
            ),
            # --binpkg-user-patches=y is default and behaves as above
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=False,
                options={"--usepkgonly": True, "--binpkg-user-patches": "y"},
            ),
            # --binpkg-user-patches=n allows use of user-patched binpkg
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True, "--binpkg-user-patches": "n"},
                mergelist=["[binary]app-misc/foo-1.0"],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=pkgs, ebuilds=pkgs, patches=patches
        )

    def testBinPkgUserPatchedBinPkgs(self):
        ebuilds = self.pkgs_no_deps
        patches = {
            "app-misc/foo": {
                "user.patch": MockUserPatches.Patch1,
                "random.diff": MockUserPatches.Patch2,
            },
            "app-misc/bar": {
                "user.patch": MockUserPatches.Patch3,
                "random.diff": MockUserPatches.Patch4,
            },
            "app-misc/bar-1.0": {
                "user.patch": b"",
            },
        }

        # add USER_PATCHES hash values to binpkg metadata, such that:
        #  - app-misc/foo-1.0 matches playground user patches
        #  - app-misc/bar-1.0 is missing one user patch
        #  - app-misc/baz-1.0 has extra user patches
        binpkgs = self.pkgs_no_deps.copy() | {
            "app-misc/foo-1.0": {
                "USER_PATCHES": MockUserPatches.expected_hash(
                    patches,
                    ["app-misc/foo/user.patch", "app-misc/foo/random.diff"],
                ),
            },
            "app-misc/bar-1.0": {
                "USER_PATCHES": MockUserPatches.expected_hash(
                    patches,
                    ["app-misc/bar/user.patch", "app-misc/bar/random.diff"],
                ),
            },
            "app-misc/baz-1.0": {
                "USER_PATCHES": "eca0a060b489636225b4fa64d267dabbe44273067ac679f20820bddc6b6a90ac",
            },
        }

        test_cases = (
            # app-misc/foo-1.0 from binpkg as binary has correct user patches
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=True,
                options={"--usepkg": True},
                mergelist=["[binary]app-misc/foo-1.0"],
            ),
            # app-misc/bar-1.0 from ebuild as binary has different patches
            ResolverPlaygroundTestCase(
                ["app-misc/bar"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/bar-1.0"],
            ),
            # app-misc/baz-1.0 from ebuild as binary has patches (config has none)
            ResolverPlaygroundTestCase(
                ["app-misc/baz"],
                success=True,
                options={"--usepkg": True},
                mergelist=["app-misc/baz-1.0"],
            ),
        )

        self.runBinPkgSelectionTest(
            test_cases, binpkgs=binpkgs, ebuilds=ebuilds, patches=patches
        )
