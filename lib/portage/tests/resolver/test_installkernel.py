# Copyright 2022 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class InstallKernelTestCase(TestCase):
    def testInstallKernel(self):
        ebuilds = {
            "sys-kernel/installkernel-systemd-boot-1": {
                "EAPI": "8",
                "RDEPEND": "!sys-kernel/installkernel-gentoo",
            },
            "sys-kernel/installkernel-gentoo-3": {
                "EAPI": "8",
                "RDEPEND": "!sys-kernel/installkernel-systemd-boot",
            },
            "sys-kernel/gentoo-kernel-5.15.23": {
                "EAPI": "8",
                "PDEPEND": ">=virtual/dist-kernel-5.15.23",
                "RDEPEND": "|| ( sys-kernel/installkernel-gentoo sys-kernel/installkernel-systemd-boot )",
            },
            "sys-kernel/gentoo-kernel-bin-5.15.23": {
                "EAPI": "8",
                "PDEPEND": ">=virtual/dist-kernel-5.15.23",
                "RDEPEND": "|| ( sys-kernel/installkernel-gentoo sys-kernel/installkernel-systemd-boot )",
            },
            "virtual/dist-kernel-5.15.23": {
                "EAPI": "8",
                "PDEPEND": "|| ( ~sys-kernel/gentoo-kernel-5.15.23 ~sys-kernel/gentoo-kernel-bin-5.15.23 )",
            },
        }

        installed = {
            "sys-kernel/installkernel-gentoo-3": {
                "EAPI": "8",
                "RDEPEND": "!sys-kernel/installkernel-systemd-boot",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                [
                    "sys-kernel/installkernel-systemd-boot",
                ],
                ambiguous_merge_order=True,
                success=True,
                mergelist=[
                    "sys-kernel/installkernel-systemd-boot-1",
                    "[uninstall]sys-kernel/installkernel-gentoo-3",
                    (
                        "!sys-kernel/installkernel-gentoo",
                        "!sys-kernel/installkernel-systemd-boot",
                    ),
                ],
            ),
            # Test bug 833014, where the calculation failed unless
            # --update and --deep are specified.
            ResolverPlaygroundTestCase(
                [
                    "sys-kernel/installkernel-systemd-boot",
                    "sys-kernel/gentoo-kernel-bin",
                ],
                ambiguous_merge_order=True,
                success=True,
                mergelist=[
                    "virtual/dist-kernel-5.15.23",
                    "sys-kernel/installkernel-systemd-boot-1",
                    "sys-kernel/gentoo-kernel-bin-5.15.23",
                    "[uninstall]sys-kernel/installkernel-gentoo-3",
                    (
                        "!sys-kernel/installkernel-systemd-boot",
                        "!sys-kernel/installkernel-gentoo",
                    ),
                ],
            ),
        )

        playground = ResolverPlayground(
            debug=False, ebuilds=ebuilds, installed=installed
        )

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
