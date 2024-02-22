# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BrokenDepsTestCase(TestCase):
    def testBrokenDeps(self):
        """
        Test the _calc_depclean "dep_check" action which will eventually
        be used to check for unsatisfied deps of installed packages
        for bug 921333.
        """
        ebuilds = {
            "dev-qt/qtcore-5.15.12": {
                "EAPI": "8",
            },
            "dev-qt/qtcore-5.15.11-r1": {
                "EAPI": "8",
            },
            "dev-qt/qtxmlpatterns-5.15.12": {
                "EAPI": "8",
                "DEPEND": "=dev-qt/qtcore-5.15.12*",
                "RDEPEND": "=dev-qt/qtcore-5.15.12*",
            },
            "dev-qt/qtxmlpatterns-5.15.11": {
                "EAPI": "8",
                "DEPEND": "=dev-qt/qtcore-5.15.11*",
                "RDEPEND": "=dev-qt/qtcore-5.15.11*",
            },
            "kde-frameworks/syntax-highlighting-5.113.0": {
                "EAPI": "8",
                "DEPEND": ">=dev-qt/qtxmlpatterns-5.15.9:5",
            },
        }
        installed = {
            "dev-qt/qtcore-5.15.12": {
                "EAPI": "8",
            },
            "dev-qt/qtxmlpatterns-5.15.11": {
                "EAPI": "8",
                "DEPEND": "=dev-qt/qtcore-5.15.11*",
                "RDEPEND": "=dev-qt/qtcore-5.15.11*",
            },
            "kde-frameworks/syntax-highlighting-5.113.0": {
                "EAPI": "8",
                "DEPEND": ">=dev-qt/qtxmlpatterns-5.15.9:5",
            },
        }

        world = ("kde-frameworks/syntax-highlighting",)

        test_cases = (
            ResolverPlaygroundTestCase(
                [],
                action="dep_check",
                success=True,
                unsatisfied_deps={
                    "dev-qt/qtxmlpatterns-5.15.11": {"=dev-qt/qtcore-5.15.11*"}
                },
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
