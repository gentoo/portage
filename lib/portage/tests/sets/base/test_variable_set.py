# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class VariableSetTestCase(TestCase):
    def testVariableSetEmerge(self):
        ebuilds = {
            "dev-go/go-pkg-1": {"BDEPEND": "dev-lang/go"},
            "www-client/firefox-1": {
                "BDEPEND": "|| ( virtual/rust:0/a virtual/rust:0/b )"
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
        )

        try:
            for test_case in test_cases:
                # Create an artificial VariableSet to test against
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
