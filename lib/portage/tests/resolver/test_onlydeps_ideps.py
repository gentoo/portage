# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class OnlydepsIdepsTestCase(TestCase):
    def testOnlydepsIdepsEAPI7(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "7",
                "DEPEND": "dev-libs/B",
                "RDEPEND": "dev-libs/C",
                "PDEPEND": "dev-libs/D",
                "IDEPEND": "dev-libs/E",
            },
            "dev-libs/B-1": {},
            "dev-libs/C-1": {},
            "dev-libs/D-1": {},
            "dev-libs/E-1": {},
        }
        ebuilds["dev-libs/F-1"] = ebuilds["dev-libs/A-1"]
        installed = {}

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                all_permutations=True,
                success=True,
                options={"--onlydeps": True, "--onlydeps-with-rdeps": "y"},
                ambiguous_merge_order=True,
                mergelist=[("dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1")],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                all_permutations=True,
                success=True,
                options={"--onlydeps": True, "--onlydeps-with-rdeps": "n"},
                mergelist=["dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": "y",
                },
                ambiguous_merge_order=True,
                mergelist=[("dev-libs/B-1")],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": True,
                },
                ambiguous_merge_order=True,
                mergelist=[("dev-libs/B-1")],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": "n",
                },
                mergelist=["dev-libs/B-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testOnlydepsIdepsEAPI8(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "8",
                "DEPEND": "dev-libs/B",
                "RDEPEND": "dev-libs/C",
                "PDEPEND": "dev-libs/D",
                "IDEPEND": "dev-libs/E",
            },
            "dev-libs/B-1": {},
            "dev-libs/C-1": {},
            "dev-libs/D-1": {},
            "dev-libs/E-1": {},
        }
        ebuilds["dev-libs/F-1"] = ebuilds["dev-libs/A-1"]
        installed = {}

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                all_permutations=True,
                success=True,
                options={"--onlydeps": True, "--onlydeps-with-rdeps": "y"},
                ambiguous_merge_order=True,
                mergelist=[
                    ("dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1", "dev-libs/E-1")
                ],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                all_permutations=True,
                success=True,
                options={"--onlydeps": True, "--onlydeps-with-rdeps": "n"},
                mergelist=["dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": "y",
                },
                ambiguous_merge_order=True,
                mergelist=[("dev-libs/B-1", "dev-libs/E-1")],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": True,
                },
                ambiguous_merge_order=True,
                mergelist=[("dev-libs/B-1", "dev-libs/E-1")],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                all_permutations=True,
                success=True,
                options={
                    "--onlydeps": True,
                    "--onlydeps-with-rdeps": "n",
                    "--onlydeps-with-ideps": "n",
                },
                mergelist=["dev-libs/B-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
