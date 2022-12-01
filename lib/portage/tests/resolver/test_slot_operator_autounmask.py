# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class SlotOperatorAutoUnmaskTestCase(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def testSubSlot(self):
        ebuilds = {
            "dev-libs/icu-49": {"EAPI": "5", "SLOT": "0/49"},
            "dev-libs/icu-4.8": {"EAPI": "5", "SLOT": "0/48"},
            "dev-libs/libxml2-2.7.8": {
                "EAPI": "5",
                "DEPEND": "dev-libs/icu:=",
                "RDEPEND": "dev-libs/icu:=",
                "KEYWORDS": "~x86",
            },
        }
        binpkgs = {
            "dev-libs/icu-49": {"EAPI": "5", "SLOT": "0/49"},
            "dev-libs/icu-4.8": {"EAPI": "5", "SLOT": "0/48"},
            "dev-libs/libxml2-2.7.8": {
                "EAPI": "5",
                "DEPEND": "dev-libs/icu:0/48=",
                "RDEPEND": "dev-libs/icu:0/48=",
            },
        }
        installed = {
            "dev-libs/icu-4.8": {"EAPI": "5", "SLOT": "0/48"},
            "dev-libs/libxml2-2.7.8": {
                "EAPI": "5",
                "DEPEND": "dev-libs/icu:0/48=",
                "RDEPEND": "dev-libs/icu:0/48=",
            },
        }

        world = ["dev-libs/libxml2"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/icu"],
                options={"--autounmask": True, "--oneshot": True},
                success=False,
                mergelist=["dev-libs/icu-49", "dev-libs/libxml2-2.7.8"],
                unstable_keywords=["dev-libs/libxml2-2.7.8"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/icu"],
                options={"--oneshot": True, "--ignore-built-slot-operator-deps": "y"},
                success=True,
                mergelist=["dev-libs/icu-49"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/icu"],
                options={"--autounmask": True, "--oneshot": True, "--usepkg": True},
                success=False,
                mergelist=["[binary]dev-libs/icu-49", "dev-libs/libxml2-2.7.8"],
                unstable_keywords=["dev-libs/libxml2-2.7.8"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/icu"],
                options={"--autounmask": True, "--oneshot": True, "--usepkgonly": True},
                success=True,
                mergelist=["[binary]dev-libs/icu-4.8"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/icu"],
                options={
                    "--oneshot": True,
                    "--usepkgonly": True,
                    "--ignore-built-slot-operator-deps": "y",
                },
                success=True,
                mergelist=["[binary]dev-libs/icu-49"],
            ),
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--update": True,
                    "--deep": True,
                    "--ignore-built-slot-operator-deps": "y",
                },
                success=True,
                mergelist=["dev-libs/icu-49"],
            ),
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--update": True, "--deep": True, "--usepkgonly": True},
                success=True,
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkgonly": True,
                    "--ignore-built-slot-operator-deps": "y",
                },
                success=True,
                mergelist=["[binary]dev-libs/icu-49"],
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
                    world=world,
                    debug=False,
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
                    playground.cleanup()
