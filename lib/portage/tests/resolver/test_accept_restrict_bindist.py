# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class AcceptRestrictBindistTestCase(TestCase):
    def testAcceptRestrictBindist(self):
        """
        Test that packages with RESTRICT=bindist are properly masked
        when ACCEPT_RESTRICT contains -bindist.

        This test focuses on make.conf-based configuration of ACCEPT_RESTRICT,
        assuming that command-line options are appropriately tested elsewhere.
        """
        ebuilds = {
            # Package without RESTRICT
            "dev-libs/unrestricted-1": {
                "EAPI": "7",
            },
            # Package with RESTRICT=bindist
            "dev-libs/bindist-restricted-1": {
                "EAPI": "7",
                "RESTRICT": "bindist",
            },
            # Package with multiple RESTRICT tokens including bindist
            "dev-libs/multi-restricted-1": {
                "EAPI": "7",
                "RESTRICT": "test bindist strip",
            },
            # Package that depends on bindist-restricted package
            "dev-libs/depends-on-bindist-1": {
                "EAPI": "7",
                "RDEPEND": "dev-libs/bindist-restricted",
            },
        }

        # Test default behavior (ACCEPT_RESTRICT="*" - should accept all)
        test_cases_default = (
            ResolverPlaygroundTestCase(
                ["dev-libs/unrestricted"],
                success=True,
                mergelist=["dev-libs/unrestricted-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=True,
                mergelist=["dev-libs/bindist-restricted-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/multi-restricted"],
                success=True,
                mergelist=["dev-libs/multi-restricted-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, debug=False)
        try:
            for test_case in test_cases_default:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Test ACCEPT_RESTRICT="* -bindist" - should mask bindist packages
        user_config_minus_bindist = {"make.conf": ('ACCEPT_RESTRICT="* -bindist"',)}
        test_cases_minus_bindist = (
            ResolverPlaygroundTestCase(
                ["dev-libs/unrestricted"],
                success=True,
                mergelist=["dev-libs/unrestricted-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/multi-restricted"],
                success=False,
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/depends-on-bindist"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_minus_bindist, debug=False
        )
        try:
            for test_case in test_cases_minus_bindist:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Test ACCEPT_RESTRICT="-bindist" alone - should mask bindist packages
        user_config_only_minus = {"make.conf": ('ACCEPT_RESTRICT="-bindist"',)}
        test_cases_only_minus = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_only_minus, debug=False
        )
        try:
            for test_case in test_cases_only_minus:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Test ACCEPT_RESTRICT="bindist" - should explicitly allow only bindist
        user_config_only_bindist = {"make.conf": ('ACCEPT_RESTRICT="bindist"',)}
        test_cases_only_bindist = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=True,
                mergelist=["dev-libs/bindist-restricted-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_only_bindist, debug=False
        )
        try:
            for test_case in test_cases_only_bindist:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Test ACCEPT_RESTRICT="" - behaves same as "*" (accepts all restrictions)
        user_config_empty = {"make.conf": ('ACCEPT_RESTRICT=""',)}
        test_cases_empty = (
            ResolverPlaygroundTestCase(
                ["dev-libs/unrestricted"],
                success=True,
                mergelist=["dev-libs/unrestricted-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=True,
                mergelist=["dev-libs/bindist-restricted-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_empty, debug=False
        )
        try:
            for test_case in test_cases_empty:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Test that FEATURES settings don't interfere with ACCEPT_RESTRICT behavior
        user_config_with_features = {
            "make.conf": (
                'ACCEPT_RESTRICT="* -bindist"',
                'FEATURES="buildpkg splitdebug"',
            )
        }
        test_cases_with_features = (
            ResolverPlaygroundTestCase(
                ["dev-libs/unrestricted"],
                success=True,
                mergelist=["dev-libs/unrestricted-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_with_features, debug=False
        )
        try:
            for test_case in test_cases_with_features:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testAcceptRestrictBindistWithFeatures(self):
        """
        Test that ACCEPT_RESTRICT behavior is independent of FEATURES.
        This verifies that packages with RESTRICT=bindist are masked
        regardless of what FEATURES are set.
        """
        ebuilds = {
            "dev-libs/bindist-restricted-1": {
                "EAPI": "7",
                "RESTRICT": "bindist",
            },
        }

        # Test with various FEATURES settings - should all behave the same
        user_config_with_sandbox = {
            "make.conf": (
                'ACCEPT_RESTRICT="* -bindist"',
                'FEATURES="sandbox"',
            )
        }
        test_cases_sandbox = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_with_sandbox, debug=False
        )
        try:
            for test_case in test_cases_sandbox:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        user_config_with_multiple_features = {
            "make.conf": (
                'ACCEPT_RESTRICT="* -bindist"',
                'FEATURES="sandbox userpriv usersandbox"',
            )
        }
        test_cases_multi_features = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_with_multiple_features, debug=False
        )
        try:
            for test_case in test_cases_multi_features:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        user_config_no_features = {
            "make.conf": (
                'ACCEPT_RESTRICT="* -bindist"',
                'FEATURES=""',
            )
        }
        test_cases_no_features = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_no_features, debug=False
        )
        try:
            for test_case in test_cases_no_features:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # Verify that with ACCEPT_RESTRICT="*", FEATURES don't matter
        user_config_accept_all = {
            "make.conf": (
                'ACCEPT_RESTRICT="*"',
                'FEATURES="sandbox userpriv"',
            )
        }
        test_cases_accept_all = (
            ResolverPlaygroundTestCase(
                ["dev-libs/bindist-restricted"],
                success=True,
                mergelist=["dev-libs/bindist-restricted-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config_accept_all, debug=False
        )
        try:
            for test_case in test_cases_accept_all:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
