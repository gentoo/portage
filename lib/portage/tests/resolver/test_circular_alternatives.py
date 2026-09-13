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

    def testOlderVersion(self):
        """
        An older version whose dependencies do not close the cycle is
        selected (bug 407351). A-1.9 is older than A-1.10, though not
        when compared as strings.
        """
        ebuilds = {
            "dev-libs/A-1.9": {"EAPI": "8"},
            "dev-libs/A-1.10": {"EAPI": "8", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=True,
                mergelist=["dev-libs/A-1.9", "dev-libs/B-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testNoDowngradeOfInstalled(self):
        """
        The older version is not used when it would downgrade what is
        already installed. B needs A[foo], so the installed A-2 does not
        satisfy it.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "IUSE": "+foo"},
            "dev-libs/A-3": {"EAPI": "8", "IUSE": "+foo", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A[foo]"},
        }

        installed = {
            "dev-libs/A-2": {"EAPI": "8", "IUSE": "foo", "USE": ""},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=False,
                circular_dependency_solutions={},
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testArgument(self):
        """
        A package named on the command line can be replaced by an older
        version, unless the argument requires the newer one.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8"},
            "dev-libs/A-2": {"EAPI": "8", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A", "dev-libs/B"],
                success=True,
                mergelist=["dev-libs/A-1", "dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/A-2", "dev-libs/B"],
                success=False,
                circular_dependency_solutions={},
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testParentAtom(self):
        """
        An older version that some parent does not accept is skipped, and
        another member of the cycle is replaced instead.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8"},
            "dev-libs/A-2": {"EAPI": "8", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8"},
            "dev-libs/B-2": {"EAPI": "8", "DEPEND": "dev-libs/A"},
            "dev-libs/C-1": {"EAPI": "8", "DEPEND": ">=dev-libs/A-2 dev-libs/B"},
            "dev-libs/D-1": {"EAPI": "8", "DEPEND": "dev-libs/A >=dev-libs/B-2"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-2", "dev-libs/C-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/D"],
                success=True,
                mergelist=["dev-libs/A-1", "dev-libs/B-2", "dev-libs/D-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
