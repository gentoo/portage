# Copyright 2014-2024 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class UseFlagsTestCase(TestCase):
    def testUseFlags(self):
        ebuilds = {
            "dev-libs/A-1": {
                "IUSE": "X",
            },
            "dev-libs/B-1": {
                "IUSE": "X Y",
            },
            "dev-libs/C-1": {"IUSE": "abi_x86_32", "EAPI": "7"},
            "dev-libs/D-1": {
                "IUSE": "abi_x86_32",
                "EAPI": "7",
                "RDEPEND": "dev-libs/C[abi_x86_32?]",
            },
        }

        installed = {
            "dev-libs/A-1": {
                "IUSE": "X",
            },
            "dev-libs/B-1": {
                "IUSE": "X",
            },
            "dev-libs/C-1": {"IUSE": "abi_x86_32", "USE": "abi_x86_32", "EAPI": "7"},
            "dev-libs/D-1": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
                "EAPI": "7",
                "RDEPEND": "dev-libs/C[abi_x86_32]",
            },
        }

        binpkgs = installed

        user_config = {
            "package.use": (
                "dev-libs/A X",
                "dev-libs/D abi_x86_32",
            ),
            "use.force": ("Y",),
        }

        test_cases = (
            # default: don't reinstall on use flag change
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--selective": True, "--usepkg": True},
                success=True,
                mergelist=[],
            ),
            # default: respect use flags for binpkgs
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--usepkg": True},
                success=True,
                mergelist=["dev-libs/A-1"],
            ),
            # For bug 773469, we wanted --binpkg-respect-use=y to trigger a
            # slot collision. Instead, a combination of default --autounmask-use
            # combined with --autounmask-backtrack=y from EMERGE_DEFAULT_OPTS
            # triggered this behavior which appeared confusingly similar to
            # --binpkg-respect-use=n behavior.
            # ResolverPlaygroundTestCase(
            # 	["dev-libs/C", "dev-libs/D"],
            # 	options={"--usepkg": True, "--binpkg-respect-use": "y", "--autounmask-backtrack": "y"},
            # 	success=True,
            # 	use_changes={"dev-libs/C-1": {"abi_x86_32": True}},
            # 	mergelist=["[binary]dev-libs/C-1", "[binary]dev-libs/D-1"],
            ResolverPlaygroundTestCase(
                ["dev-libs/C", "dev-libs/D"],
                options={
                    "--usepkg": True,
                    "--binpkg-respect-use": "y",
                    "--autounmask-backtrack": "y",
                },
                success=False,
                slot_collision_solutions=[{"dev-libs/C-1": {"abi_x86_32": True}}],
                mergelist=["dev-libs/C-1", "[binary]dev-libs/D-1"],
            ),
            # --binpkg-respect-use=n: use binpkgs with different use flags
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--binpkg-respect-use": "n", "--usepkg": True},
                success=True,
                mergelist=["[binary]dev-libs/A-1"],
            ),
            # --reinstall=changed-use: reinstall if use flag changed
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--reinstall": "changed-use", "--usepkg": True},
                success=True,
                mergelist=["dev-libs/A-1"],
            ),
            # --reinstall=changed-use: don't reinstall on new use flag
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                options={"--reinstall": "changed-use", "--usepkg": True},
                success=True,
                mergelist=[],
            ),
            # --newuse: reinstall on new use flag
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                options={"--newuse": True, "--usepkg": True},
                success=True,
                mergelist=["dev-libs/B-1"],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                user_config["make.conf"] = (f'BINPKG_FORMAT="{binpkg_format}"',)
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    binpkgs=binpkgs,
                    installed=installed,
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

    def testBlockerBinpkgRespectUse(self):
        """
        Test for bug #916336 where we tried to check properties of a blocker
        object which isn't a Package to be merged.
        """

        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "7",
                "IUSE": "abi_x86_32",
                "RDEPEND": "dev-libs/B",
            },
            "dev-libs/B-1": {
                "EAPI": "7",
                "IUSE": "abi_x86_32",
            },
            "dev-libs/A-2": {
                "EAPI": "7",
                "IUSE": "abi_x86_32",
                "RDEPEND": "!<dev-libs/B-2",
            },
            "dev-libs/B-2": {
                "EAPI": "7",
                "IUSE": "abi_x86_32",
            },
        }
        installed = {
            "dev-libs/A-1": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
            },
            "dev-libs/B-1": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
            },
        }
        binpkgs = ebuilds.copy()

        user_config = {
            "make.conf": (
                'FEATURES="binpkg-multi-instance"',
                'USE="abi_x86_32 abi_x86_32"',
            ),
        }

        world = ("dev-libs/A",)

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={
                    "--verbose": "y",
                    "--update": True,
                    "--deep": True,
                    "--complete-graph": True,
                    "--usepkg": True,
                    "--autounmask": "n",
                    "--autounmask-backtrack": "n",
                    "--autounmask-use": "n",
                },
                success=True,
                mergelist=["dev-libs/A-2", "[uninstall]dev-libs/B-1", "!<dev-libs/B-2"],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                user_config["make.conf"] += (f'BINPKG_FORMAT="{binpkg_format}"',)
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    binpkgs=binpkgs,
                    installed=installed,
                    user_config=user_config,
                    world=world,
                )

                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()

    def testNoMergeBinpkgRespectUse(self):
        """
        Testcase for bug #916614 where an incomplete depgraph may be fed into
        _show_ignored_binaries_respect_use.

        We use a mix of +/-abi_x86_32 to trigger the binpkg-respect-use notice
        and depend on a non-existent package in one of the available ebuilds we
        queue to reinstall to trigger an aborted calculation.
        """
        ebuilds = {
            "dev-libs/A-2": {
                "EAPI": "7",
                "IUSE": "abi_x86_32",
            },
            "dev-libs/B-1": {
                "IUSE": "abi_x86_32",
                "RDEPEND": "=dev-libs/A-1",
            },
        }

        installed = {
            "dev-libs/B-1": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
            },
            "dev-libs/A-1": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
            },
        }

        binpkgs = {
            "dev-libs/A-2": {
                "IUSE": "abi_x86_32",
                "USE": "abi_x86_32",
            },
            "dev-libs/B-1": {
                "IUSE": "abi_x86_32",
                "USE": "",
                "BUILD_ID": "2",
                "BUILD_TIME": "2",
            },
        }

        user_config = {
            "make.conf": (
                'FEATURES="binpkg-multi-instance"',
                'USE="abi_x86_32 abi_x86_32"',
            ),
        }

        world = ("dev-libs/A",)

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@installed"],
                options={
                    "--verbose": "y",
                    "--emptytree": True,
                    "--usepkg": True,
                },
                success=False,
                mergelist=None,
                slot_collision_solutions=None,
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                user_config["make.conf"] += (f'BINPKG_FORMAT="{binpkg_format}"',)
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    binpkgs=binpkgs,
                    installed=installed,
                    user_config=user_config,
                    world=world,
                )

                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()
