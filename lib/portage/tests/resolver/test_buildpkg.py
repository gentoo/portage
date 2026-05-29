# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BuildPkgTestCase(TestCase):
    def testBuildPkgProactive(self):
        ebuilds = {
            "dev-libs/A-1": {},
            "dev-libs/B-1": {},
            "dev-libs/C-1": {},
            "dev-libs/D-1": {"KEYWORDS": "amd64"},
            "dev-libs/E-1": {"IUSE": "static"},
            "dev-libs/F-1": {"IUSE": "static"},
            "dev-libs/G-1": {"IUSE": "static"},
            "dev-libs/H-1": {"IUSE": "doc"},
        }

        installed = {
            "dev-libs/B-1": {},
            "dev-libs/C-1": {},
            "dev-libs/D-1": {},
            "dev-libs/E-1": {"IUSE": "static"},
            "dev-libs/F-1": {"IUSE": "static"},
            "dev-libs/G-1": {"IUSE": "static", "USE": "static"},
            "dev-libs/H-1": {"IUSE": "static", "USE": "static"},
        }

        binpkgs = {
            "dev-libs/C-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
            },
            "dev-libs/D-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "KEYWORDS": "~amd64",
            },
            "dev-libs/E-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "IUSE": "static",
            },
            "dev-libs/F-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "IUSE": "static",
                "USE": "static",
            },
            "dev-libs/G-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "IUSE": "static",
            },
            "dev-libs/H-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "IUSE": "static",
                "USE": "static",
            },
            "dev-libs/X-1": {
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
            },
        }

        user_config = {
            "make.conf": ('FEATURES="buildpkg buildpkg-proactive"', 'USE="static"'),
            "package.accept_keywords": ("dev-libs/D amd64",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                success=True,
                options={"--update": True},
                mergelist=["dev-libs/A-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=True,
                options={"--update": True},
                mergelist=["dev-libs/B-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/C"],
                success=True,
                options={"--update": True},
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/D"],
                success=True,
                options={"--update": True},
                mergelist=["dev-libs/D-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/E"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "y"},
                mergelist=["dev-libs/E-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/E"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "n"},
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "y"},
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/F"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "n"},
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/G"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "y"},
                mergelist=["dev-libs/G-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/G"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "n"},
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/H"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "y"},
                mergelist=["dev-libs/H-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/H"],
                success=True,
                options={"--update": True, "--binpkg-respect-use": "n"},
                mergelist=[],
            ),
        )

        playground = ResolverPlayground(
            debug=False,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            installed=installed,
            user_config=user_config,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
