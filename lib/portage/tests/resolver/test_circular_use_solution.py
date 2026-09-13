# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class CircularUseSolutionTestCase(TestCase):
    """
    A cycle that can be broken by disabling a USE flag is solved with an
    autounmask USE change instead of an error (bug 175808).
    """

    def testCircularUseSolution(self):
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        test_cases = (
            # The cycle is reported as a needed USE change, like any
            # other autounmask change.
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                success=False,
                use_changes={"media-libs/freetype-1": {"harfbuzz": False}},
            ),
            # With --autounmask-backtrack=y the resolver continues and
            # produces a merge list for the changed configuration.
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--autounmask-backtrack": "y"},
                success=False,
                use_changes={"media-libs/freetype-1": {"harfbuzz": False}},
                mergelist=["media-libs/freetype-1", "media-libs/harfbuzz-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
