# Copyright 2010-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class UseDepDefaultsTestCase(TestCase):
    def testUseDepDefaultse(self):
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "dev-libs/B[foo]",
                "RDEPEND": "dev-libs/B[foo]",
                "EAPI": "2",
            },
            "dev-libs/A-2": {
                "DEPEND": "dev-libs/B[foo(+)]",
                "RDEPEND": "dev-libs/B[foo(+)]",
                "EAPI": "4",
            },
            "dev-libs/A-3": {
                "DEPEND": "dev-libs/B[foo(-)]",
                "RDEPEND": "dev-libs/B[foo(-)]",
                "EAPI": "4",
            },
            "dev-libs/B-1": {"IUSE": "+foo", "EAPI": "1"},
            "dev-libs/B-2": {},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["=dev-libs/A-1"],
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-1"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/A-2"],
                success=True,
                mergelist=["dev-libs/B-2", "dev-libs/A-2"],
            ),
            ResolverPlaygroundTestCase(
                ["=dev-libs/A-3"],
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-3"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testUseDepDefaultsDowngrade(self):
        """
        Test for bug #917145 where we wrongly prefer a downgrade of sys-apps/systemd
        instead of either:
        1) suggesting +kernel-install in a "One of the following packages is required to complete your request" message, or
        2) autounmask suggesting +kernel-install
        """
        installed = {
            "sys-boot/gnu-efi-3.0.15": {},
            "sys-apps/systemd-253.11": {
                "EAPI": 8,
                "IUSE": "gnuefi",
                "RDEPEND": "gnuefi? ( sys-boot/gnu-efi )",
            },
            "sys-kernel/installkernel-gentoo-7": {
                "EAPI": 8,
                "RDEPEND": "!sys-kernel/installkernel-systemd",
            },
        }
        ebuilds = {
            "sys-boot/gnu-efi-3.0.15": {},
            "sys-apps/systemd-253.11": {
                "EAPI": 8,
                "IUSE": "gnuefi",
                "RDEPEND": "gnuefi? ( sys-boot/gnu-efi )",
            },
            "sys-apps/systemd-254.5": {
                "EAPI": 8,
                "IUSE": "kernel-install",
            },
            "sys-kernel/installkernel-gentoo-7": {
                "EAPI": 8,
                "RDEPEND": "!sys-kernel/installkernel-systemd",
            },
            "sys-kernel/installkernel-systemd-2-r4": {
                "EAPI": 8,
                "RDEPEND": """
                    !sys-kernel/installkernel-gentoo
                    || (
                        sys-apps/systemd[gnuefi(-)]
                        sys-apps/systemd[kernel-install(-)]
                    )
                """,
            },
        }

        test_cases = (
            # The following USE changes are necessary to proceed:
            # (see "package.use" in the portage(5) man page for more details)
            # # required by sys-kernel/installkernel-systemd-2-r4::test_repo
            # # required by sys-kernel/installkernel-systemd (argument)
            # =sys-apps/systemd-253.11 gnuefi
            ResolverPlaygroundTestCase(
                ["sys-kernel/installkernel-systemd"],
                success=False,
                ambiguous_merge_order=True,
                options={
                    "--autounmask": "y",
                },
                mergelist=[
                    "sys-apps/systemd-254.5",
                    "sys-kernel/installkernel-systemd-2-r4",
                    "[uninstall]sys-kernel/installkernel-gentoo-7",
                    (
                        "!sys-kernel/installkernel-gentoo",
                        "!sys-kernel/installkernel-systemd",
                    ),
                ],
                use_changes={"sys-apps/systemd": {"boot": True}},
            ),
            # emerge: there are no ebuilds built with USE flags to satisfy "sys-apps/systemd[gnuefi(-)]".
            # !!! One of the following packages is required to complete your request:
            # - sys-apps/systemd-253.11::test_repo (Change USE: +gnuefi)
            # (dependency required by "sys-kernel/installkernel-systemd-2-r4::test_repo" [ebuild])
            # (dependency required by "sys-kernel/installkernel-systemd" [argument])
            ResolverPlaygroundTestCase(
                ["sys-kernel/installkernel-systemd"],
                success=False,
                ambiguous_merge_order=True,
                options={
                    "--autounmask": "n",
                },
                mergelist=[
                    "sys-apps/systemd-254.5",
                    "sys-kernel/installkernel-systemd-2-r4",
                    "[uninstall]sys-kernel/installkernel-gentoo-7",
                    (
                        "!sys-kernel/installkernel-gentoo",
                        "!sys-kernel/installkernel-systemd",
                    ),
                ],
            ),
        )

        playground = ResolverPlayground(installed=installed, ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, False, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testUseDepDefaultsUpgradePreference(self):
        """
        Complement to test for bug #917145 where we wrongly prefer a downgrade of sys-apps/systemd
        instead of either:
        1) suggesting +kernel-install in a "One of the following packages is required to complete your request" message, or
        2) autounmask suggesting +kernel-install

        For this test, we make sure we have the right preference for upgrades
        if the USE settings align already (either by defaults or from the user).
        """
        installed = {
            "sys-boot/gnu-efi-3.0.15": {},
            "sys-apps/systemd-253.11": {
                "EAPI": 8,
                "IUSE": "gnuefi",
                "RDEPEND": "gnuefi? ( sys-boot/gnu-efi )",
            },
            "sys-kernel/installkernel-gentoo-7": {
                "EAPI": 8,
                "RDEPEND": "!sys-kernel/installkernel-systemd",
            },
        }
        ebuilds = {
            "sys-boot/gnu-efi-3.0.15": {},
            "sys-apps/systemd-253.11": {
                "EAPI": 8,
                "IUSE": "gnuefi",
                "RDEPEND": "gnuefi? ( sys-boot/gnu-efi )",
            },
            "sys-apps/systemd-254.5": {
                "EAPI": 8,
                "IUSE": "kernel-install",
            },
            "sys-kernel/installkernel-gentoo-7": {
                "EAPI": 8,
                "RDEPEND": "!sys-kernel/installkernel-systemd",
            },
            "sys-kernel/installkernel-systemd-2-r4": {
                "EAPI": 8,
                "RDEPEND": """
                    !sys-kernel/installkernel-gentoo
                    || (
                        sys-apps/systemd[gnuefi(-)]
                        sys-apps/systemd[kernel-install(-)]
                    )
                """,
            },
        }

        test_cases = (
            # emerge: there are no ebuilds built with USE flags to satisfy "sys-apps/systemd[gnuefi(-)]".
            # !!! One of the following packages is required to complete your request:
            # - sys-apps/systemd-253.11::test_repo (Change USE: +gnuefi)
            # (dependency required by "sys-kernel/installkernel-systemd-2-r4::test_repo" [ebuild])
            # (dependency required by "sys-kernel/installkernel-systemd" [argument])
            ResolverPlaygroundTestCase(
                ["sys-kernel/installkernel-systemd"],
                success=True,
                ambiguous_merge_order=True,
                options={
                    "--autounmask": "n",
                },
                mergelist=[
                    "sys-apps/systemd-254.5",
                    "sys-kernel/installkernel-systemd-2-r4",
                    "[uninstall]sys-kernel/installkernel-gentoo-7",
                    (
                        "!sys-kernel/installkernel-gentoo",
                        "!sys-kernel/installkernel-systemd",
                    ),
                ],
            ),
        )

        # Run with package.use settings that allow the cases from bug #917145 to succeed
        # to check that we have the right upgrade preference behavior there.
        playground = ResolverPlayground(
            installed=installed,
            ebuilds=ebuilds,
            user_config={
                "make.conf": (f'USE="gnuefi kernel-install"',),
            },
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
