# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BinpackageDowngradesSlotDepTestCase(TestCase):
    def testBinpackageDowngradesSlotDep(self):
        python_use = "python_targets_python3_12 +python_targets_python3_13"
        python_usedep = "python_targets_python3_12(-)?,python_targets_python3_13(-)?"
        common_metadata = {
            "EAPI": "8",
            "REQUIRED_USE": """
                python? (
                    || (
                        python_targets_python3_12
                        python_targets_python3_13
                    )
                )
            """,
        }

        ebuilds = {
            "dev-libs/libxml2-2.13.9": {
                "IUSE": f"+python {python_use}",
                "SLOT": "2",
                **common_metadata,
            },
            "dev-libs/libxml2-2.14.6": {
                "IUSE": f"+python {python_use}",
                "SLOT": "2/16",
                **common_metadata,
            },
            "dev-libs/libxslt-1.1.43-r1": {
                "IUSE": f"python {python_use}",
                "RDEPEND": f"""
                    >=dev-libs/libxml2-2.13:2=
                    python? (
                        >=dev-libs/libxml2-2.13:2=[python,{python_usedep}]
                    )
                """,
                **common_metadata,
            },
        }

        binpkgs = {
            "dev-libs/libxslt-1.1.43-r1": {
                "IUSE": f"python {python_use}",
                "RDEPEND": f"""
                    >=dev-libs/libxml2-2.13:2/2=
                    python? (
                        >=dev-libs/libxml2-2.13:2/2=[python,{python_usedep}]
                    )
                """,
                **common_metadata,
            },
        }

        installed = {
            "dev-libs/libxml2-2.14.6": {
                "IUSE": f"+python {python_use}",
                "USE": f"python python_targets_python3_13",
                "SLOT": "2/16",
                **common_metadata,
            },
            "dev-libs/libxslt-1.1.43-r1": {
                "IUSE": f"python {python_use}",
                "USE": "python_targets_python3_13",
                "RDEPEND": f"""
                    >=dev-libs/libxml2-2.13:2/16=
                    python? (
                        >=dev-libs/libxml2-2.13:2/16=[python,{python_usedep}]
                    )
                """,
                **common_metadata,
            },
        }

        world = []
        user_config = {"package.use": ["*/* -python_targets_python3_13"]}

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=binpkgs,
            world=world,
            user_config=user_config,
            debug=False,
        )

        settings = playground.settings
        profile_path = settings.profile_path

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/libxslt"],
                success=True,
                options={"--usepkg": True},
                mergelist=["dev-libs/libxslt-1.1.43-r1"],
            ),
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
