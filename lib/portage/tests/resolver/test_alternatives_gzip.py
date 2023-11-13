# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class AlternativesGzipTestCase(TestCase):
    def testAlternativesGzip(self):
        """
        Test bug 917259, where app-alternatives/gzip was upgraded before
        its pigz RDEPEND was installed.
        """
        ebuilds = {
            "app-alternatives/gzip-1": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( >=app-arch/pigz-2.8[-symlink(-)] )",
                "IUSE": "reference pigz",
                "REQUIRED_USE": "^^ ( reference pigz )",
            },
            "app-alternatives/gzip-0": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( app-arch/pigz[-symlink(-)] )",
                "IUSE": "reference pigz",
                "REQUIRED_USE": "^^ ( reference pigz )",
            },
            "app-arch/gzip-1.13": {
                "EAPI": "8",
                "PDEPEND": "app-alternatives/gzip",
            },
            "app-arch/pigz-2.8": {
                "EAPI": "8",
                "PDEPEND": "app-alternatives/gzip",
            },
        }

        installed = {
            "app-alternatives/gzip-0": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( app-arch/pigz[-symlink(-)] )",
                "IUSE": "reference pigz",
                "USE": "reference",
            },
            "app-arch/gzip-1.13": {
                "EAPI": "8",
                "PDEPEND": "app-alternatives/gzip",
            },
        }

        world = ["app-alternatives/gzip", "app-arch/gzip"]

        user_config = {
            "package.use": ("app-alternatives/gzip -reference pigz",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--deep": True, "--update": True, "--verbose": True},
                success=True,
                mergelist=[
                    "app-arch/pigz-2.8",
                    "app-alternatives/gzip-1",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            world=world,
            user_config=user_config,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
