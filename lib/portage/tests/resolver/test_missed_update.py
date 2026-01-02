# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class MissedQtUpdateTestCase(TestCase):
    def testMissedQtUpdate(self):
        """
        Testcase where Portage was unable to upgrade from
        Qt 6.9.3 -> Qt 6.10.1 without an explicit redundant
        argument on the command line (bug #968228).

        This was fixed by the "earlier slot operator backtracking"
        patch related to bug #964705.
        """
        ebuilds = {
            "dev-qt/qtbase-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "IUSE": "+nls",
                "RDEPEND": """
                    !<dev-qt/qtconnectivity-6.9.3:6
                    !<dev-qt/qtsvg-6.9.3:6
                    !<dev-qt/qttools-6.9.3:6
                """,
                "PDEPEND": "nls? ( ~dev-qt/qttranslations-6.9.3:6 )",
            },
            "dev-qt/qtbase-6.10.1": {
                "EAPI": "8",
                "SLOT": "6",
                "IUSE": "+nls",
                "RDEPEND": """
                    !<dev-qt/qtconnectivity-6.10.1:6
                    !<dev-qt/qtsvg-6.10.1:6
                    !<dev-qt/qttools-6.10.1:6
                """,
                "PDEPEND": "nls? ( ~dev-qt/qttranslations-6.10.1:6 )",
            },
            "dev-qt/qtconnectivity-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
            },
            "dev-qt/qtconnectivity-6.10.1": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.10.1:6",
            },
            "dev-qt/qttranslations-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "BDEPEND": "~dev-qt/qttools-6.9.3:6",
            },
            "dev-qt/qttranslations-6.10.1": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.10.1:6",
                "BDEPEND": "~dev-qt/qttools-6.10.1:6",
            },
            "dev-qt/qtsvg-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "RDEPEND": """
                    ~dev-qt/qtbase-6.9.3:6
                """,
            },
            "dev-qt/qtsvg-6.10.1": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.10.1:6",
                "RDEPEND": """
                    ~dev-qt/qtbase-6.10.1:6
                """,
            },
            "dev-qt/qttools-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "RDEPEND": "~dev-qt/qtbase-6.9.3:6",
            },
            "dev-qt/qttools-6.10.1": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.10.1:6",
                "RDEPEND": """
                    ~dev-qt/qtbase-6.10.1:6
                """,
            },
            "dev-python/pyside-6.9.3": {
                "EAPI": "8",
                "SLOT": "6/6.9.3",
                "DEPEND": """
                    =dev-qt/qtbase-6.9.3*:6
                    =dev-qt/qttools-6.9.3*:6
                    =dev-qt/qtconnectivity-6.9.3*:6
                """,
                "RDEPEND": """
                    =dev-qt/qtbase-6.9.3*:6
                    =dev-qt/qttools-6.9.3*:6
                    =dev-qt/qtconnectivity-6.9.3*:6
                """,
            },
            "dev-python/pyside-6.10.1": {
                "EAPI": "8",
                "SLOT": "6/6.10.1",
                "DEPEND": """
                    =dev-qt/qtbase-6.10.1*:6
                    =dev-qt/qtconnectivity-6.10.1*:6
                """,
                "RDEPEND": """
                    =dev-qt/qtbase-6.10.1*:6
                    =dev-qt/qtconnectivity-6.10.1*:6
                """,
            },
            "media-gfx/freecad-1.0.1-r2": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": """
                    dev-qt/qtbase:6
                    dev-qt/qtsvg:6
                    dev-python/pyside:6=
                """,
                "RDEPEND": """
                    dev-qt/qtbase:6
                    dev-qt/qtsvg:6
                    dev-python/pyside:6=
                """,
            },
        }
        installed = {
            "dev-qt/qtbase-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "IUSE": "+nls",
                "USE": "nls",
                "PDEPEND": "nls? ( ~dev-qt/qttranslations-6.9.3:6 )",
            },
            "dev-qt/qtconnectivity-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
            },
            "dev-qt/qttranslations-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "BDEPEND": "~dev-qt/qttools-6.9.3:6",
            },
            "dev-qt/qtsvg-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "RDEPEND": "~dev-qt/qtbase-6.9.3:6",
            },
            "dev-qt/qttools-6.9.3": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": "~dev-qt/qtbase-6.9.3:6",
                "RDEPEND": "~dev-qt/qtbase-6.9.3:6",
            },
            "dev-python/pyside-6.9.3": {
                "EAPI": "8",
                "SLOT": "6/6.9.3",
                "DEPEND": """
                    =dev-qt/qtbase-6.9.3*:6
                    =dev-qt/qtconnectivity-6.9.3*:6
                """,
                "RDEPEND": """
                    =dev-qt/qtbase-6.9.3*:6
                    =dev-qt/qtconnectivity-6.9.3*:6
                """,
            },
            "media-gfx/freecad-1.0.1-r2": {
                "EAPI": "8",
                "SLOT": "6",
                "DEPEND": """
                    dev-qt/qtbase:6
                    dev-qt/qtsvg:6
                    dev-python/pyside:6/6.9.3=
                """,
                "RDEPEND": """
                    dev-qt/qtbase:6
                    dev-qt/qtsvg:6
                    dev-python/pyside:6/6.9.3=
                """,
            },
        }

        world = ("media-gfx/freecad",)

        test_cases = (
            # The extra pyside atom is sufficient to nudge Portage
            # towards a solution but shouldn't be necessary.
            # ResolverPlaygroundTestCase(
            #     ["@world", "=dev-python/pyside-6.10.1"],
            #     success=True,
            #     options={"--update": True, "--deep": True},
            #     mergelist=[
            #         "dev-qt/qtbase-6.10.1",
            #         "dev-qt/qttools-6.10.1",
            #         "!<dev-qt/qttools-6.10.1:6",
            #         "dev-qt/qttranslations-6.10.1",
            #         "dev-qt/qtconnectivity-6.10.1",
            #         "!<dev-qt/qtconnectivity-6.10.1:6",
            #         "dev-qt/qtsvg-6.10.1",
            #         "!<dev-qt/qtsvg-6.10.1:6",
            #         "dev-python/pyside-6.10.1",
            #         "media-gfx/freecad-1.0.1-r2",
            #     ],
            # ),
            # It should resolve identically (or at least with a solution)
            # without explicit dev-python/pyside, as it's a dependency of
            # media-gfx/freecad.
            ResolverPlaygroundTestCase(
                ["@world"],
                success=True,
                options={"--update": True, "--deep": True},
                mergelist=[
                    "dev-qt/qtbase-6.10.1",
                    "dev-qt/qttools-6.10.1",
                    "!<dev-qt/qttools-6.10.1:6",
                    "dev-qt/qttranslations-6.10.1",
                    "dev-qt/qtconnectivity-6.10.1",
                    "!<dev-qt/qtconnectivity-6.10.1:6",
                    "dev-qt/qtsvg-6.10.1",
                    "!<dev-qt/qtsvg-6.10.1:6",
                    "dev-python/pyside-6.10.1",
                    "media-gfx/freecad-1.0.1-r2",
                ],
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
