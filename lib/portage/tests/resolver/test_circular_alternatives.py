# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class CircularAlternativesTestCase(TestCase):
    def testAnyOfAlternative(self):
        """
        A || ( ) choice that does not close the cycle is selected, even
        though it is not the first one (bug 515630).
        """
        ebuilds = {
            "sys-devel/pseudo-gcc-0": {
                "EAPI": "8",
                "DEPEND": "sys-libs/pseudo-glibc",
                "RDEPEND": "sys-libs/pseudo-glibc",
            },
            "sys-devel/pseudo-gcc-stage1-0": {"EAPI": "8"},
            "sys-libs/pseudo-glibc-0": {
                "EAPI": "8",
                "DEPEND": "|| ( sys-devel/pseudo-gcc sys-devel/pseudo-gcc-stage1 )",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["sys-devel/pseudo-gcc"],
                success=True,
                mergelist=[
                    "sys-devel/pseudo-gcc-stage1-0",
                    "sys-libs/pseudo-glibc-0",
                    "sys-devel/pseudo-gcc-0",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["sys-libs/pseudo-glibc"],
                success=True,
                mergelist=["sys-devel/pseudo-gcc-stage1-0", "sys-libs/pseudo-glibc-0"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
