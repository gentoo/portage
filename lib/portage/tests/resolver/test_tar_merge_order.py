# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class TarMergeOrderTestCase(TestCase):
    def testTarMergeOrder(self):
        """
        Test for bug #922629 where binary app-arch/tar[acl] was merged
        before its dependency sys-apps/acl (with virtual/acl merged but
        unsatisfied).

        It poorly interacted with @system containing app-alternatives/tar
        as a circular dependency on app-arch/tar.

        Bisect found that commit 49e01d041c74680a81860b819daff812d83df02f
        triggered the issue.
        """

        ebuilds = {
            "app-alternatives/tar-0-1": {
                "EAPI": "8",
                "RDEPEND": """
                    !<app-arch/tar-1.34-r2
                    gnu? ( >=app-arch/tar-1.34-r2 )
                    libarchive? ( app-arch/libarchive )
                """,
                "IUSE": "+gnu libarchive",
                "REQUIRED_USE": "^^ ( gnu libarchive )",
            },
            "app-arch/libarchive-3.7.4": {"EAPI": "8"},
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
            },
            "virtual/acl-0-r2": {
                "EAPI": "8",
                "RDEPEND": ">=sys-apps/acl-2.2.52-r1",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
            },
            "sys-apps/acl-2.3.2-r1": {
                "EAPI": "8",
                "DEPEND": ">=sys-apps/attr-2.4.47-r1",
                "RDEPEND": ">=sys-apps/attr-2.4.47-r1",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
            },
        }

        installed = {
            "app-alternatives/tar-0-1": {
                "EAPI": "8",
                "RDEPEND": """
                    !<app-arch/tar-1.34-r2
                    gnu? ( >=app-arch/tar-1.34-r2 )
                    libarchive? ( app-arch/libarchive )
                """,
                "IUSE": "+gnu libarchive",
                "USE": "gnu",
                "REQUIRED_USE": "^^ ( gnu libarchive )",
            },
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
                "USE": "",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
                "USE": "xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
                "USE": "",
            },
        }

        binpkgs = {
            "app-alternatives/tar-0-1": {
                "EAPI": "8",
                "RDEPEND": """
                    !<app-arch/tar-1.34-r2
                    gnu? ( >=app-arch/tar-1.34-r2 )
                    libarchive? ( app-arch/libarchive )
                """,
                "IUSE": "+gnu libarchive",
                "USE": "gnu",
                "REQUIRED_USE": "^^ ( gnu libarchive )",
            },
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
                "USE": "acl nls xattr",
            },
            "virtual/acl-0-r2": {
                "EAPI": "8",
                "RDEPEND": ">=sys-apps/acl-2.2.52-r1",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
                "USE": "acl nls xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
                "USE": "nls",
            },
        }

        world = []

        user_config = {
            "package.use": (
                "app-arch/tar acl nls xattr",
                "sys-apps/acl nls",
                "sys-apps/attr nls",
                "sys-devel/gettext acl nls xattr",
            ),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=binpkgs,
            world=world,
            user_config=user_config,
        )
        settings = playground.settings
        profile_path = settings.profile_path

        # Add app-alternatives/tar to @system too
        with open(os.path.join(profile_path, "packages"), "w") as f:
            f.writelines(["*app-alternatives/tar\n", "*app-arch/tar\n"])
        test_cases = (
            # Check without binpkgs first
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={"--emptytree": True},
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "virtual/acl-0-r2",
                    "sys-apps/attr-2.5.2-r1",
                    "sys-devel/gettext-0.22.4",
                    "app-arch/tar-1.35",
                    "app-alternatives/tar-0",
                ],
            ),
            # In the bug, only --emptytree was broken, so check
            # some cases without it.
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--usepkg": True,
                },
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]app-arch/tar-1.35",
                    "[binary]app-alternatives/tar-0",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["app-arch/tar"],
                success=True,
                options={
                    "--oneshot": True,
                    "--usepkg": True,
                },
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]app-arch/tar-1.35",
                ],
            ),
            # binpkg --emptytree case which broke
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--emptytree": True,
                    "--usepkg": True,
                },
                mergelist=[
                    "[binary]sys-apps/attr-2.5.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]sys-devel/gettext-0.22.4",
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]app-arch/tar-1.35",
                    "[binary]app-alternatives/tar-0",
                ],
            ),
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testTarMergeOrderWithoutAlternatives(self):
        """
        Variant of test for bug #922629 where binary app-arch/tar[acl] was merged
        before its dependency sys-apps/acl (with virtual/acl merged but
        unsatisfied).

        This variant lacks the problematic app-alternatives/tar to check we handle
        the simpler case correctly.
        """

        ebuilds = {
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
            },
            "virtual/acl-0-r2": {
                "EAPI": "8",
                "RDEPEND": ">=sys-apps/acl-2.2.52-r1",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
            },
            "sys-apps/acl-2.3.2-r1": {
                "EAPI": "8",
                "DEPEND": ">=sys-apps/attr-2.4.47-r1",
                "RDEPEND": ">=sys-apps/attr-2.4.47-r1",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
            },
        }

        installed = {
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
                "USE": "",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
                "USE": "xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
                "USE": "",
            },
        }

        binpkgs = {
            "app-arch/tar-1.35": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "BDEPEND": """
                    nls? ( sys-devel/gettext )
                """,
                "IUSE": "acl nls xattr",
                "USE": "acl nls xattr",
            },
            "virtual/acl-0-r2": {
                "EAPI": "8",
                "RDEPEND": ">=sys-apps/acl-2.2.52-r1",
            },
            "sys-devel/gettext-0.22.4": {
                "EAPI": "8",
                "RDEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "DEPEND": """
                    acl? ( virtual/acl )
                    xattr? ( sys-apps/attr )
                """,
                "IUSE": "acl nls xattr",
                "USE": "acl nls xattr",
            },
            "sys-apps/attr-2.5.2-r1": {
                "EAPI": "8",
                "BDEPEND": "nls? ( sys-devel/gettext )",
                "IUSE": "nls",
                "USE": "nls",
            },
        }

        world = []

        user_config = {
            "package.use": (
                "app-arch/tar acl nls xattr",
                "sys-apps/acl nls",
                "sys-apps/attr nls",
                "sys-devel/gettext acl nls xattr",
            ),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=binpkgs,
            world=world,
            user_config=user_config,
        )
        settings = playground.settings
        profile_path = settings.profile_path

        with open(os.path.join(profile_path, "packages"), "w") as f:
            f.writelines(["*app-arch/tar\n"])
        test_cases = (
            # Check without binpkgs first
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={"--emptytree": True, "--verbose": True},
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "virtual/acl-0-r2",
                    "sys-apps/attr-2.5.2-r1",
                    "sys-devel/gettext-0.22.4",
                    "app-arch/tar-1.35",
                ],
            ),
            # In the bug, only --emptytree was broken, so check
            # some cases without it.
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--usepkg": True,
                },
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]app-arch/tar-1.35",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["app-arch/tar"],
                success=True,
                options={
                    "--oneshot": True,
                    "--usepkg": True,
                },
                mergelist=[
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]app-arch/tar-1.35",
                ],
            ),
            # binpkg --emptytree case which broke
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={
                    "--emptytree": True,
                    "--usepkg": True,
                },
                mergelist=[
                    "[binary]sys-apps/attr-2.5.2-r1",
                    "[binary]virtual/acl-0-r2",
                    "[binary]sys-devel/gettext-0.22.4",
                    "sys-apps/acl-2.3.2-r1",
                    "[binary]app-arch/tar-1.35",
                ],
            ),
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
