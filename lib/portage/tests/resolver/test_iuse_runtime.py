# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class IuseRuntimeTestCase(TestCase):
    """
    Runtime-switchable USE flags (IUSE_RUNTIME, GLEP 62).
    """

    foo = {
        "EAPI": "8",
        "IUSE": "bar baz regular",
        "IUSE_RUNTIME": "bar baz",
        "RDEPEND": "bar? ( dev-libs/bar ) baz? ( dev-libs/baz )",
    }

    def _built_foo(self, use):
        # Built packages keep the conditionals of runtime-switchable flags.
        return dict(self.foo, USE=use)

    def testBinpkg(self):
        """
        Binary packages are used regardless of the values that their
        runtime-switchable flags were built with, and their dependencies
        follow the current configuration.
        """
        ebuilds = {
            "app-misc/foo-1": self.foo,
            "dev-libs/bar-1": {"EAPI": "8"},
            "dev-libs/baz-1": {"EAPI": "8"},
        }
        binpkgs = {
            "app-misc/foo-1": self._built_foo("baz"),
            "dev-libs/bar-1": {"EAPI": "8"},
            "dev-libs/baz-1": {"EAPI": "8"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                options={"--usepkg": True},
                success=True,
                mergelist=["[binary]dev-libs/bar-1", "[binary]app-misc/foo-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            binpkgs=binpkgs,
            user_config={"package.use": ("app-misc/foo bar",)},
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

        # A difference in a regular flag still rejects the binary package.
        test_cases = (
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                options={"--usepkg": True},
                success=True,
                mergelist=["[binary]dev-libs/bar-1", "app-misc/foo-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            binpkgs=binpkgs,
            user_config={"package.use": ("app-misc/foo bar regular",)},
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testRequiredUse(self):
        """
        Runtime-switchable flags are not changed on a built package if
        the configured values violate its REQUIRED_USE.
        """
        foo = dict(self.foo, REQUIRED_USE="?? ( bar baz )")
        ebuilds = {
            "app-misc/foo-1": foo,
            "dev-libs/bar-1": {"EAPI": "8"},
            "dev-libs/baz-1": {"EAPI": "8"},
        }
        binpkgs = {
            "app-misc/foo-1": dict(foo, USE="baz"),
            "dev-libs/bar-1": {"EAPI": "8"},
            "dev-libs/baz-1": {"EAPI": "8"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                options={"--usepkgonly": True},
                success=True,
                mergelist=["[binary]dev-libs/baz-1", "[binary]app-misc/foo-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            binpkgs=binpkgs,
            user_config={"package.use": ("app-misc/foo bar baz",)},
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
