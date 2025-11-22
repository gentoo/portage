# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class ProfileUseStableTestCase(TestCase):
    def testProfileUseStable(self):
        profile = {
            "eapi": ("9-pre1",),
            "package.use": ("app-misc/A -a d",),
            "package.use.stable": ("app-misc/A a -b -c f",),
            "use.stable": ("a", "b", "c", "e"),
        }

        user_config = {
            "package.accept_keywords": ("=app-misc/A-2 ~x86",),
        }

        ebuilds = {
            "app-misc/A-1": {"EAPI": "8", "KEYWORDS": "x86", "IUSE": "a b c d e f"},
            "app-misc/A-2": {"EAPI": "8", "KEYWORDS": "~x86", "IUSE": "a b c d e f"},
            "app-misc/B-1": {
                "EAPI": "8",
                # package.use.stable > package.use > use.stable
                "RDEPEND": "=app-misc/A-1[a,-b,-c,d,e,f]",
            },
            "app-misc/C-1": {
                "EAPI": "8",
                # package.use.stable and use.stable do not apply due to unstable keyword
                "RDEPEND": "=app-misc/A-2[-a,-b,-c,d,-e,-f]",
            },
        }

        test_cases = (
            # Test stable package
            ResolverPlaygroundTestCase(
                ["app-misc/B"],
                success=True,
                mergelist=[
                    "app-misc/A-1",
                    "app-misc/B-1",
                ],
            ),
            # Test unstable package
            ResolverPlaygroundTestCase(
                ["app-misc/C"],
                success=True,
                mergelist=[
                    "app-misc/A-2",
                    "app-misc/C-1",
                ],
            ),
        )

        playground = ResolverPlayground(
            debug=False,
            ebuilds=ebuilds,
            profile=profile,
            user_config=user_config,
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            # Disable debug so that cleanup works.
            playground.debug = False
            playground.cleanup()
