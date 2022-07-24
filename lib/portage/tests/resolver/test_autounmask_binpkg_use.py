# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function
import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class AutounmaskBinpkgUseTestCase(TestCase):
    def testAutounmaskBinpkgUse(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "6",
                "DEPEND": "dev-libs/B[foo]",
                "RDEPEND": "dev-libs/B[foo]",
            },
            "dev-libs/B-1": {
                "EAPI": "6",
                "IUSE": "foo",
            },
        }
        binpkgs = {
            "dev-libs/A-1": {
                "EAPI": "6",
                "DEPEND": "dev-libs/B[foo]",
                "RDEPEND": "dev-libs/B[foo]",
            },
            "dev-libs/B-1": {
                "EAPI": "6",
                "IUSE": "foo",
                "USE": "foo",
            },
        }
        installed = {}

        test_cases = (
            # Bug 619626: Test for unnecessary rebuild due
            # to rejection of binary packages that would
            # be acceptable after appplication of autounmask
            # USE changes.
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                all_permutations=True,
                success=True,
                options={
                    "--usepkg": True,
                },
                mergelist=[
                    "[binary]dev-libs/B-1",
                    "[binary]dev-libs/A-1",
                ],
                use_changes={"dev-libs/B-1": {"foo": True}},
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
                    playground.debug = False
                    playground.cleanup()
