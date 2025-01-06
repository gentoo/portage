# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import pytest

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BootstrapChainTestCase(TestCase):
    @pytest.mark.xfail(reason="bug #947587")
    def testBootstrapChainWithShortcut(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "8",
                "SLOT": "1",
                "IUSE": "B",
                "BDEPEND": "B? ( || ( <dev-libs/B-2 dev-libs/A:1[B] ) )",
            },
            "dev-libs/A-2": {
                "EAPI": "8",
                "SLOT": "2",
                "IUSE": "B",
                "BDEPEND": "B? ( || ( <dev-libs/B-3 dev-libs/A:2[B] <dev-libs/A-2[B] ) )",
            },
            "dev-libs/A-3": {
                "EAPI": "8",
                "SLOT": "3",
                "IUSE": "B",
                "BDEPEND": "B? ( || ( <dev-libs/B-4 dev-libs/A:3[B] <dev-libs/A-3[B] ) )",
            },
            "dev-libs/A-4": {
                "EAPI": "8",
                "SLOT": "4",
                "IUSE": "B",
                "BDEPEND": "B? ( || ( <dev-libs/B-5 dev-libs/A:4[B] <dev-libs/A-4[B] ) )",
            },
            "dev-libs/B-1": {},
            "dev-libs/B-2": {},
            "dev-libs/B-3": {},
            "dev-libs/B-4": {},
        }

        installed = {
            "dev-libs/A-4": {
                "SLOT": "4",
                "IUSE": "B",
                "USE": "",
                "BDEPEND": "B? ( || ( <dev-libs/B-5 <dev-libs/A:4[B] dev-libs/A-4[B]) )",
            },
        }

        user_config = {
            "package.use": ("dev-libs/A B",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A:4"],
                success=True,
                mergelist=["dev-libs/B-4", "dev-libs/A-4"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, user_config=user_config, debug=True
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
