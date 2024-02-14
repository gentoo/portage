# Copyright 2024 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class EmptytreeReinstallUnsatisfiabilityTestCase(TestCase):
    def testEmptytreeReinstallUnsatisfiability(self):
        """
        Tests to check if emerge fails and complains when --emptytree
        package dependency graph reinstall is unsatisfied, even if the already
        installed packages successfully satisfy the dependency tree.

        See bug #651018 where emerge silently skips package
        reinstalls because of unsatisfied use flag requirements.
        """
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "dev-libs/B",
                "RDEPEND": "dev-libs/B",
                "EAPI": "2",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/C[foo]",
                "RDEPEND": "dev-libs/C[foo]",
                "EAPI": "2",
            },
            "dev-libs/C-1": {
                "IUSE": "foo",
                "EAPI": "2",
            },
            "dev-libs/X-1": {
                "DEPEND": "dev-libs/Y[-baz]",
                "RDEPEND": "dev-libs/Y[-baz]",
                "EAPI": "2",
            },
            "dev-libs/Y-1": {
                "IUSE": "baz",
                "EAPI": "2",
            },
            "dev-libs/Z-1": {
                "DEPEND": "dev-libs/W",
                "RDEPEND": "dev-libs/W",
                "EAPI": "2",
            },
            "dev-libs/W-1": {
                "EAPI": "2",
            },
        }

        installed = {
            "dev-libs/A-1": {
                "DEPEND": "dev-libs/B",
                "RDEPEND": "dev-libs/B",
                "EAPI": "2",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/C[foo]",
                "RDEPEND": "dev-libs/C[foo]",
                "EAPI": "2",
            },
            "dev-libs/C-1": {
                "IUSE": "foo",
                "USE": "foo",
                "EAPI": "2",
            },
            "dev-libs/X-1": {
                "DEPEND": "dev-libs/Y[-baz]",
                "RDEPEND": "dev-libs/Y[-baz]",
                "EAPI": "2",
            },
            "dev-libs/Y-1": {
                "IUSE": "baz",
                "USE": "-baz",
                "EAPI": "2",
            },
            "dev-libs/Z-1": {
                "DEPEND": "dev-libs/W",
                "RDEPEND": "dev-libs/W",
                "EAPI": "2",
            },
            "dev-libs/W-1": {
                "EAPI": "2",
            },
        }

        user_config = {
            "package.use": ("dev-libs/Y baz",),
            "package.mask": ("dev-libs/W",),
        }

        world = ["dev-libs/X"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--emptytree": True},
                success=False,
                mergelist=["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"],
                use_changes={"dev-libs/C-1": {"foo": True}},
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--emptytree": True, "--exclude": ["dev-libs/C"]},
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-1"],
            ),
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--emptytree": True},
                success=False,
                mergelist=["dev-libs/Y-1", "dev-libs/X-1"],
                use_changes={"dev-libs/Y-1": {"baz": False}},
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/Z"],
                options={"--emptytree": True},
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            user_config=user_config,
            world=world,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
