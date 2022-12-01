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


class SonameProvidedTestCase(TestCase):
    def testSonameProvided(self):

        binpkgs = {
            "app-misc/A-1": {
                "EAPI": "5",
                "PROVIDES": "x86_32: libA.so.1",
            },
            "app-misc/B-1": {
                "DEPEND": "app-misc/A",
                "RDEPEND": "app-misc/A",
                "REQUIRES": "x86_32: libA.so.2",
            },
            "app-misc/B-0": {
                "DEPEND": "app-misc/A",
                "RDEPEND": "app-misc/A",
                "REQUIRES": "x86_32: libA.so.1",
            },
        }

        installed = {
            "app-misc/A-1": {
                "EAPI": "5",
                "PROVIDES": "x86_32: libA.so.1",
            },
            "app-misc/B-0": {
                "DEPEND": "app-misc/A",
                "RDEPEND": "app-misc/A",
                "REQUIRES": "x86_32: libA.so.1",
            },
        }

        world = ["app-misc/B"]

        profile = {
            "soname.provided": ("x86_32 libA.so.2",),
        }

        test_cases = (
            # Allow update due to soname dependency satisfied by
            # soname.provided.
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--deep": True,
                    "--ignore-soname-deps": "n",
                    "--update": True,
                    "--usepkgonly": True,
                },
                success=True,
                mergelist=["[binary]app-misc/B-1"],
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                playground = ResolverPlayground(
                    binpkgs=binpkgs,
                    debug=False,
                    profile=profile,
                    installed=installed,
                    world=world,
                    user_config={
                        "make.conf": ('BINPKG_FORMAT="%s"' % binpkg_format,),
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
