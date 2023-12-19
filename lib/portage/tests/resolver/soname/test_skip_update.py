# Copyright 2015-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
from unittest.mock import patch

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class SonameSkipUpdateTestCase(TestCase):
    def testSonameSkipUpdateNoPruneRebuilds(self):
        """
        Make sure that there are fewer backtracking runs required if we
        disable prune_rebuilds backtracking, which shows that
        _eliminate_rebuilds works for the purposes of bug 915494.
        """
        with patch(
            "_emerge.depgraph._dynamic_depgraph_config._ENABLE_PRUNE_REBUILDS",
            new=False,
        ):
            self.testSonameSkipUpdate(backtrack=2)

    def testSonameSkipUpdate(self, backtrack=3):
        binpkgs = {
            "app-misc/A-1": {
                # Simulate injected libc dep which should not trigger
                # reinstall due to use of strip_libc_deps in
                # depgraph._eliminate_rebuilds dep comparison.
                "RDEPEND": "dev-libs/B >=sys-libs/glibc-2.37",
                "DEPEND": "dev-libs/B",
                "REQUIRES": "x86_32: libB.so.1",
            },
            "dev-libs/B-2": {
                "PROVIDES": "x86_32: libB.so.2",
            },
            "dev-libs/B-1": {
                "PROVIDES": "x86_32: libB.so.1",
            },
            "sys-libs/glibc-2.37-r7": {
                "PROVIDES": "x86_32: libc.so.6",
            },
            "virtual/libc-1-r1": {"RDEPEND": "sys-libs/glibc"},
        }

        installed = {
            "app-misc/A-1": {
                "RDEPEND": "dev-libs/B",
                "DEPEND": "dev-libs/B",
                "REQUIRES": "x86_32: libB.so.1",
            },
            "dev-libs/B-1": {
                "PROVIDES": "x86_32: libB.so.1",
            },
            "sys-libs/glibc-2.37-r7": {
                "PROVIDES": "x86_32: libc.so.6",
            },
            "virtual/libc-1-r1": {
                "RDEPEND": "sys-libs/glibc",
            },
        }

        world = ("app-misc/A",)

        test_cases = (
            # Test that --ignore-soname-deps allows the upgrade,
            # even though it will break an soname dependency of
            # app-misc/A-1.
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--deep": True,
                    "--ignore-soname-deps": "y",
                    "--update": True,
                    "--usepkgonly": True,
                    "--backtrack": backtrack,
                },
                success=True,
                mergelist=[
                    "[binary]dev-libs/B-2",
                ],
            ),
            # Test that upgrade to B-2 is skipped with --usepkgonly
            # because it will break an soname dependency that
            # cannot be satisfied by the available binary packages.
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--deep": True,
                    "--ignore-soname-deps": "n",
                    "--update": True,
                    "--usepkgonly": True,
                    "--backtrack": backtrack,
                },
                success=True,
                mergelist=[],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                playground = ResolverPlayground(
                    debug=False,
                    binpkgs=binpkgs,
                    installed=installed,
                    world=world,
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
                    # Disable debug so that cleanup works.
                    playground.debug = False
                    playground.cleanup()
