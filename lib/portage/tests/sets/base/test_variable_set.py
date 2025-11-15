# Copyright 2022-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class VariableSetTestCase(TestCase):
    def testVariableSetEmerge(self):
        rust_with_rustc_rebuild = "{class=portage.sets.dbapi.VariableSet,variable=BDEPEND,includes=dev-lang/rust dev-lang/rust-bin}"

        ebuilds = {
            "dev-lang/go-1": {},
            "dev-go/go-pkg-1": {"EAPI": "7", "BDEPEND": "dev-lang/go"},
            "www-client/firefox-1": {
                "EAPI": "7",
                "BDEPEND": "|| ( dev-lang/rust dev-lang/rust-bin )",
            },
            "dev-lang/rust-1": {
                "EAPI": "7",
                "BDEPEND": "|| ( dev-lang/rust dev-lang/rust-bin )",
            },
            "dev-lang/rust-bin-1": {
                "EAPI": "7",
                "BDEPEND": "|| ( dev-lang/rust-bin dev-lang/rust )",
            },
        }
        installed = ebuilds
        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@golang-rebuild"],
                mergelist=["dev-go/go-pkg-1"],
                success=True,
            ),
            ResolverPlaygroundTestCase(
                ["@rust-rebuild"],
                mergelist=["www-client/firefox-1"],
                success=True,
            ),
            ResolverPlaygroundTestCase(
                [f"@rust-with-rustc-rebuild{rust_with_rustc_rebuild}"],
                mergelist=[
                    "www-client/firefox-1",
                    "dev-lang/rust-1",
                    "dev-lang/rust-bin-1",
                ],
                ignore_mergelist_order=True,
                success=True,
            ),
        )

        try:
            for test_case in test_cases:
                # Create an artificial VariableSet to test against
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
