# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BacktrackMaskSimilarTestCase(TestCase):
    def testBacktrackMaskSimilar(self):
        ebuilds = {
            "app-misc/A-1": {"EAPI": "8", "RDEPEND": "=dev-libs/L-1"},
            "app-misc/C-1": {"EAPI": "8"},
            "app-misc/C-2": {"EAPI": "8", "RDEPEND": "=dev-libs/L-2"},
            "app-misc/C-3": {"EAPI": "8", "RDEPEND": ">=dev-libs/L-2"},
            "app-misc/C-4": {"EAPI": "8", "RDEPEND": ">=dev-libs/L-2"},
            "dev-libs/L-1": {"EAPI": "8", "IUSE": "+foo"},
            "dev-libs/L-2": {"EAPI": "8", "IUSE": "+foo"},
        }

        installed = {
            "app-misc/A-1": {"EAPI": "8", "RDEPEND": "=dev-libs/L-1"},
            "app-misc/C-1": {"EAPI": "8"},
            "dev-libs/L-1": {"EAPI": "8", "IUSE": "foo", "USE": ""},
        }

        world = ["app-misc/A", "app-misc/C"]

        test_cases = (
            # The C updates have to be skipped, since A needs L-1. L-1 is
            # rebuilt due to --newuse, so the slot conflict involves the
            # L-1 ebuild. When the backtracker masks it, the installed
            # L-1 should be masked in the same step.
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--update": True,
                    "--deep": True,
                    "--newuse": True,
                    "--backtrack": 7,
                },
                success=True,
                mergelist=["dev-libs/L-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world, debug=False
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
