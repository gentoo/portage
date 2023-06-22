# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class SlotConflictBlockedPruneTestCase(TestCase):
    def testSlotConflictBlockedPrune(self):
        """
        Bug 622270
        Downgrading package (as openssl here) due to un-accepting unstable.
        Dependent package (as rustup here) cannot be rebuilt due to missing
        keyword, so dependee downgrade is cancelled, but other dependents
        (such as xwayland here) are rebuilt nevertheless. This should not
        happen and the rebuilds should be pruned.
        """
        ebuilds = {
            "x11-base/xwayland-23.1.1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/openssl:=",
            },
            "dev-util/rustup-1.25.2": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/openssl:0=",
                "KEYWORDS": "~x86",
            },
            "dev-libs/openssl-1.1.1u": {
                "EAPI": "5",
                "SLOT": "0/1.1",
            },
            "dev-libs/openssl-3.1.1": {
                "EAPI": "5",
                "SLOT": "0/3",
                "KEYWORDS": "~x86",
            },
        }

        installed = {
            "x11-base/xwayland-23.1.1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/openssl:0/3=",
            },
            "dev-util/rustup-1.25.2": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/openssl:0/3=",
                "KEYWORDS": "~x86",
            },
            "dev-libs/openssl-3.1.1": {
                "EAPI": "5",
                "SLOT": "0/3",
                "KEYWORDS": "~x86",
            },
        }

        world = ["x11-base/xwayland", "dev-util/rustup"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--deep": True, "--update": True, "--verbose": True},
                success=True,
                mergelist=["x11-base/xwayland-23.1.1"],
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
