# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class RebuiltBinariesCase(TestCase):
    def testRebuiltBinaries(self):

        user_config = {
            "make.conf": ('FEATURES="binpkg-multi-instance"',),
        }

        binpkgs = (
            (
                "app-misc/A-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "1",
                    "BUILD_TIME": "1",
                },
            ),
            (
                "app-misc/A-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "2",
                    "BUILD_TIME": "2",
                },
            ),
            (
                "app-misc/A-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "3",
                    "BUILD_TIME": "3",
                },
            ),
            (
                "dev-libs/B-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "1",
                    "BUILD_TIME": "1",
                },
            ),
            (
                "dev-libs/B-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "2",
                    "BUILD_TIME": "2",
                },
            ),
            (
                "dev-libs/B-1",
                {
                    "EAPI": "5",
                    "BUILD_ID": "3",
                    "BUILD_TIME": "3",
                },
            ),
        )

        installed = {
            "app-misc/A-1": {
                "EAPI": "5",
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
            },
            "dev-libs/B-1": {
                "EAPI": "5",
                "BUILD_ID": "2",
                "BUILD_TIME": "2",
            },
        }

        world = (
            "app-misc/A",
            "dev-libs/B",
        )

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--deep": True,
                    "--rebuilt-binaries": True,
                    "--update": True,
                    "--usepkgonly": True,
                },
                success=True,
                ignore_mergelist_order=True,
                mergelist=["[binary]dev-libs/B-1-3", "[binary]app-misc/A-1-3"],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                _user_config = user_config.copy()
                _user_config["make.conf"] += ('BINPKG_FORMAT="%s"' % binpkg_format,)
                playground = ResolverPlayground(
                    debug=False,
                    binpkgs=binpkgs,
                    installed=installed,
                    user_config=_user_config,
                    world=world,
                )

                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    # Disable debug so that cleanup works.
                    # playground.debug = False
                    playground.cleanup()
