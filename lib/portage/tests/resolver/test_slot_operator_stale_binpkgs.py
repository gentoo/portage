# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class SlotOperatorStaleBinpkgsTestCase(TestCase):
    def testSlotOperatorStaleBinpkgs(self):
        ebuilds = {
            "dev-lang/foo-1.0": {"EAPI": "8", "SLOT": "0/1.0"},
            "dev-lang/foo-2.0": {"EAPI": "8", "SLOT": "0/2.0"},
            "dev-foo/barlib-1.0": {"EAPI": "8", "RDEPEND": ">=dev-lang/foo-1.0:="},
            "dev-foo/barlib-2.0": {"EAPI": "8", "RDEPEND": ">=dev-lang/foo-2.0:="},
            "dev-foo/otherlib-1.0": {"EAPI": "8", "RDEPEND": ">=dev-lang/foo-1.0:="},
        }

        old_foo = {"EAPI": "8", "RDEPEND": ">=dev-lang/foo-1.0:0/1.0="}
        new_foo = {"EAPI": "8", "RDEPEND": ">=dev-lang/foo-1.0:0/2.0="}

        installed = {
            "dev-lang/foo-1.0": {"EAPI": "8", "SLOT": "0/1.0"},
            "dev-foo/barlib-1.0": old_foo,
            "dev-foo/otherlib-1.0": old_foo,
        }

        # Several builds of otherlib, all built against the old foo.
        stale_binpkgs = [
            (
                "dev-foo/otherlib-1.0",
                dict(old_foo, BUILD_ID=str(i), BUILD_TIME=str(i)),
            )
            for i in range(1, 6)
        ]

        world = ["dev-foo/barlib", "dev-foo/otherlib"]

        options = {"--usepkg": True, "--backtrack": 2}

        # barlib-2.0 needs foo-2.0, so otherlib has to be rebuilt. Each
        # of the otherlib binary packages has the same built slot-operator
        # dependency on the old foo, so they should all be masked in the
        # same backtracking step (bug 960617).
        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-foo/barlib"],
                options=options,
                success=True,
                mergelist=[
                    "dev-lang/foo-2.0",
                    "dev-foo/barlib-2.0",
                    "dev-foo/otherlib-1.0",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=stale_binpkgs,
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

        # A binary package that was built against the new foo has a
        # different dependency, so it should not be masked.
        binpkgs = stale_binpkgs + [
            ("dev-foo/otherlib-1.0", dict(new_foo, BUILD_ID="6", BUILD_TIME="6")),
        ]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-foo/barlib"],
                options=options,
                success=True,
                mergelist=[
                    "dev-lang/foo-2.0",
                    "dev-foo/barlib-2.0",
                    "[binary]dev-foo/otherlib-1.0-6",
                ],
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
