# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class WorldWarningTestCase(TestCase):
    def testWorldWarningEmerge(self):
        """
        Test that we warn about a package in @world with no ebuild.
        """
        installed = {
            "app-misc/i-do-not-exist-1": {},
        }
        ebuilds = {}

        playground = ResolverPlayground(
            world=["app-misc/i-do-not-exist"],
            ebuilds=ebuilds,
            installed=installed,
        )

        test_case = ResolverPlaygroundTestCase(
            ["@world"],
            mergelist=[],
            options={
                "--update": True,
                "--deep": True,
            },
            success=True,
        )

        try:
            # Just to make sure we don't freak out on the general case
            # without worrying about the specific output first.
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            # We need access to the depgraph object to check for missing_args
            # so we run again manually.
            depgraph = playground.run(
                ["@world"], test_case.options, test_case.action
            ).depgraph

            self.assertIsNotNone(depgraph._dynamic_config._missing_args)
            self.assertTrue(
                len(depgraph._dynamic_config._missing_args) > 0,
                "Ebuild-less packages did not raise an error",
            )
        finally:
            playground.cleanup()

    def testAbsentWorldWarningEmerge(self):
        """
        Test that we do not warn about a package in @world with an ebuild
        available.
        """

        installed = {
            "app-misc/i-do-exist-1": {},
        }
        ebuilds = {
            # Package has a newer ebuild available but not
            # for the installed version.
            "app-misc/i-do-exist-2": {}
        }

        playground = ResolverPlayground(
            world=["app-misc/i-do-exist"],
            ebuilds=ebuilds,
            installed=installed,
        )

        test_case = ResolverPlaygroundTestCase(
            ["@world"],
            mergelist=["app-misc/i-do-exist-2"],
            options={
                "--update": True,
                "--deep": True,
            },
            success=True,
        )

        try:
            # Just to make sure we don't freak out on the general case
            # without worrying about the specific output first.
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            # We need access to the depgraph object to check for missing_args
            # so we run again manually.
            depgraph = playground.run(
                ["@world"], test_case.options, test_case.action
            ).depgraph

            self.assertIsNotNone(depgraph._dynamic_config._missing_args)
            self.assertTrue(
                len(depgraph._dynamic_config._missing_args) == 0,
                "Package with an ebuild was incorrectly flagged",
            )
        finally:
            playground.cleanup()

    def testAbsentNotInWorldWarningEmerge(self):
        """
        Test that we do not warn about an installed package with no
        ebuild available if the package is not in @world.
        """

        installed = {
            "app-misc/i-do-not-exist-1": {},
        }
        ebuilds = {}

        playground = ResolverPlayground(
            world=[],
            ebuilds=ebuilds,
            installed=installed,
        )

        test_case = ResolverPlaygroundTestCase(
            ["@world"],
            mergelist=[],
            options={
                "--update": True,
                "--deep": True,
            },
            success=True,
        )

        try:
            # Just to make sure we don't freak out on the general case
            # without worrying about the specific output first.
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            # We need access to the depgraph object to check for missing_args
            # so we run again manually.
            depgraph = playground.run(
                ["@world"], test_case.options, test_case.action
            ).depgraph

            self.assertIsNotNone(depgraph._dynamic_config._missing_args)
            self.assertTrue(
                len(depgraph._dynamic_config._missing_args) == 0,
                "Package without an ebuild but not in world was incorrectly flagged",
            )
        finally:
            playground.cleanup()

    def testAbsentNodeNotInWorldWarningEmerge(self):
        """
        Test that we do not warn about an installed package with an ebuild available
        if the package is not in @world but is depended on by something in @world.
        """

        installed = {
            "app-misc/foo-1": {"RDEPEND": "dev-libs/bar"},
            "dev-libs/bar-1": {},
        }
        ebuilds = {
            "app-misc/foo-1": {"RDEPEND": "dev-libs/bar"},
        }

        playground = ResolverPlayground(
            world=["app-misc/foo"],
            ebuilds=ebuilds,
            installed=installed,
        )

        test_case = ResolverPlaygroundTestCase(
            ["@world"],
            mergelist=[],
            options={
                "--update": True,
                "--deep": True,
            },
            success=True,
        )

        try:
            # Just to make sure we don't freak out on the general case
            # without worrying about the specific output first.
            playground.run_TestCase(test_case)
            self.assertEqual(test_case.test_success, True, test_case.fail_msg)

            # We need access to the depgraph object to check for missing_args
            # so we run again manually.
            depgraph = playground.run(
                ["@world"], test_case.options, test_case.action
            ).depgraph

            self.assertIsNotNone(depgraph._dynamic_config._missing_args)
            self.assertTrue(
                len(depgraph._dynamic_config._missing_args) == 0,
                "Package with an ebuild that was reachable from world was incorrectly flagged",
            )
        finally:
            playground.cleanup()
