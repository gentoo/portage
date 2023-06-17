# Copyright 2022-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class UpdateIfInstalledTestCase(TestCase):
    def testUpdateIfInstalledEmerge(self):
        installed = {
            "dev-lang/ghc-4": {},
            "dev-libs/larryware-3": {},
            "dev-libs/larryware-ng-3": {},
            "virtual/libc-1": {},
        }

        ebuilds = installed.copy()
        ebuilds.update(
            {
                "app-misc/cowsay-10": {},
                "dev-lang/ghc-5": {},
                "dev-libs/larryware-4": {},
                "dev-libs/larryware-ng-4": {"RDEPEND": ">=net-libs/moo-1"},
                "net-libs/moo-1": {},
            }
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )

        test_cases = (
            # We should only try to update ghc when passed ghc and
            # --update-if-installed. We don't want larryware to appear here,
            # despite it being eligible for an upgrade otherwise with --update.
            ResolverPlaygroundTestCase(
                ["dev-lang/ghc"],
                mergelist=["dev-lang/ghc-5"],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
            # Only try to upgrade ghc even if passed another candidate,
            # as there's no upgrade due for it. We don't want to
            # reinstall virtual/libc for the sake of it.
            ResolverPlaygroundTestCase(
                ["dev-lang/ghc", "virtual/libc"],
                mergelist=["dev-lang/ghc-5"],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
            # Try to upgrade a package with no new versions available.
            # This is just checking we still have --update semantics.
            ResolverPlaygroundTestCase(
                ["virtual/libc"],
                mergelist=[],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
            # If a new package is given, we want to do nothing.
            ResolverPlaygroundTestCase(
                ["app-misc/cowsay"],
                mergelist=[],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
            # If a new package (app-misc/cowsay) is given combined with
            # a package eligible for an upgrade (dev-libs/larryware),
            # upgrade just the latter.
            ResolverPlaygroundTestCase(
                ["app-misc/cowsay", "dev-libs/larryware"],
                mergelist=["dev-libs/larryware-4"],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
            # Make sure that we can still pull in upgrades as
            # dependencies (net-libs/moo) of the package we requested
            # (dev-libs/larryware-ng).
            ResolverPlaygroundTestCase(
                ["dev-libs/larryware-ng"],
                mergelist=["net-libs/moo-1", "dev-libs/larryware-ng-4"],
                options={
                    "--update-if-installed": True,
                },
                success=True,
            ),
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
