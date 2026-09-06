# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class DepcleanCycleTestCase(TestCase):
    """
    --depclean with arguments only considers the given packages, so a
    package that is kept alive by a dependency cycle looks unremovable.
    Tell the user which packages to pass instead (bug 346351).
    """

    def testDepcleanCycleSuggestion(self):
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "RDEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "RDEPEND": "dev-libs/A"},
            "dev-libs/C-1": {"EAPI": "8"},
        }

        installed = ebuilds
        world = ["dev-libs/C"]

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world
        )
        try:
            # Passing a single member of the cycle removes nothing, but
            # the suggestion names every member.
            test_case = ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--depclean": True},
                success=True,
                cleanlist=[],
                cycle_suggestions={"dev-libs/A-1": ["dev-libs/A-1", "dev-libs/B-1"]},
            )
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            # Passing all of them removes the whole cycle.
            test_case = ResolverPlaygroundTestCase(
                ["dev-libs/A", "dev-libs/B"],
                options={"--depclean": True},
                success=True,
                ignore_cleanlist_order=True,
                cleanlist=["dev-libs/A-1", "dev-libs/B-1"],
            )
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
