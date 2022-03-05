# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class UnnecessarySlotrUpgradeTestCase(TestCase):
    def testUnnecessarySlotUpgrade(self):
        ebuilds = {
            "app-misc/a-1": {
                "EAPI": "8",
                "RDEPEND": "|| ( dev-lang/python:3.10 dev-lang/python:3.9 ) || ( dev-lang/python:3.10 dev-lang/python:3.9 )",
            },
            "dev-lang/python-3.9": {"SLOT": "3.9"},
            "dev-lang/python-3.10": {"SLOT": "3.10"},
        }

        installed = {
            "dev-lang/python-3.9": {"SLOT": "3.9"},
        }

        test_cases = (
            # Test bug 828136, where an unnecessary python slot upgrade
            # was triggered.
            ResolverPlaygroundTestCase(
                [
                    "app-misc/a",
                ],
                success=True,
                mergelist=(
                    "dev-lang/python-3.10",
                    "app-misc/a-1",
                ),
            ),
        )

        playground = ResolverPlayground(
            debug=False, ebuilds=ebuilds, installed=installed
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
