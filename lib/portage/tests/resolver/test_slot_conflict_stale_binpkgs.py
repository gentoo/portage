# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class SlotConflictStaleBinpkgsTestCase(TestCase):
    def testSlotConflictStaleBinpkgs(self):
        ebuilds = {
            "dev-libs/tree-sitter-0.25.10": {"EAPI": "8", "SLOT": "0/0.25.10"},
            "dev-libs/tree-sitter-0.26.12": {"EAPI": "8", "SLOT": "0/0.26.12"},
            "app-editors/neovim-1": {
                "EAPI": "8",
                "RDEPEND": "=dev-libs/tree-sitter-0.25*:=",
            },
            "dev-python/tree-sitter-0.25": {
                "EAPI": "8",
                "RDEPEND": ">=dev-libs/tree-sitter-0.25:=",
            },
            # The second atom makes more parent atoms reject 0.25.10 than
            # 0.26.12, so that the backtracker masks 0.25.10 first.
            "dev-python/tree-sitter-0.26": {
                "EAPI": "8",
                "DEPEND": ">=dev-libs/tree-sitter-0.26.1:=",
                "RDEPEND": ">=dev-libs/tree-sitter-0.26:=",
            },
            "dev-util/pkgcheck-1": {
                "EAPI": "8",
                "RDEPEND": ">=dev-python/tree-sitter-0.25",
            },
            "dev-util/pkgcheck-2": {
                "EAPI": "8",
                "RDEPEND": ">=dev-python/tree-sitter-0.26",
            },
        }

        installed = {
            "dev-libs/tree-sitter-0.25.10": {"EAPI": "8", "SLOT": "0/0.25.10"},
            "app-editors/neovim-1": {
                "EAPI": "8",
                "RDEPEND": "=dev-libs/tree-sitter-0.25*:0/0.25.10=",
            },
            "dev-python/tree-sitter-0.25": {
                "EAPI": "8",
                "RDEPEND": ">=dev-libs/tree-sitter-0.25:0/0.25.10=",
            },
            "dev-util/pkgcheck-1": {
                "EAPI": "8",
                "RDEPEND": ">=dev-python/tree-sitter-0.25",
            },
        }

        # Old versions with no ebuild.
        binpkgs = {
            f"dev-libs/tree-sitter-0.25.{i}": {"EAPI": "8", "SLOT": f"0/0.25.{i}"}
            for i in range(1, 5)
        }

        world = ["app-editors/neovim", "dev-util/pkgcheck"]

        test_cases = (
            # The pkgcheck update has to be skipped. When the backtracker
            # masks tree-sitter-0.25.10, it should mask the old binary
            # packages in the same step.
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--update": True,
                    "--deep": True,
                    "--usepkg": True,
                    "--backtrack": 6,
                },
                success=True,
                mergelist=[],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=binpkgs,
            world=world,
            debug=False,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
