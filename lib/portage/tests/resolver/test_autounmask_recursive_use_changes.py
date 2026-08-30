# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class AutounmaskRecursiveUseChangesTestCase(TestCase):
    def testAutounmaskRecursiveUseChanges(self):
        """
        Attempt to trigger bug 925625 (unsuccessfully), where
        --autounmask did not create all of the necessary abi_x86_32
        USE changes, and then --autounmask-continue proceeded with
        an invalid calculation.
        """
        binpkgs = {
            "sys-libs/zlib-1.3-r4": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "USE": "abi_x86_64",
            },
            "x11-libs/libpciaccess-0.17-r1": {
                "EAPI": "8",
                "IUSE": "x86_32 x86_64 zlib",
                "DEPEND": "zlib? ( >=sys-libs/zlib-1.2.8-r1:=[abi_x86_32?,abi_x86_64?] )",
                "RDEPEND": "zlib? ( >=sys-libs/zlib-1.2.8-r1:=[abi_x86_32?,abi_x86_64?] )",
                "USE": "abi_x86_64 zlib",
            },
            "x11-libs/libdrm-2.4.120": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": ">=x11-libs/libpciaccess-0.13.1-r1:=[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": ">=x11-libs/libpciaccess-0.13.1-r1:=[abi_x86_32?,abi_x86_64?]",
                "USE": "abi_x86_64",
            },
            "media-libs/gst-plugins-base-1.20.6": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": ">=x11-libs/libdrm-2.4.55[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": ">=x11-libs/libdrm-2.4.55[abi_x86_32?,abi_x86_64?]",
                "USE": "abi_x86_64",
            },
            "app-emulation/wine-vanilla-9.0": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": "media-libs/gst-plugins-base[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": "media-libs/gst-plugins-base[abi_x86_32?,abi_x86_64?]",
                "USE": "abi_x86_64",
            },
        }

        ebuilds = {
            "sys-libs/zlib-1.3-r4": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
            },
            "x11-libs/libpciaccess-0.17-r1": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64 zlib",
                "DEPEND": "zlib? ( >=sys-libs/zlib-1.2.8-r1:=[abi_x86_32?,abi_x86_64?] )",
                "RDEPEND": "zlib? ( >=sys-libs/zlib-1.2.8-r1:=[abi_x86_32?,abi_x86_64?] )",
            },
            "x11-libs/libdrm-2.4.120": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": ">=x11-libs/libpciaccess-0.13.1-r1:=[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": ">=x11-libs/libpciaccess-0.13.1-r1:=[abi_x86_32?,abi_x86_64?]",
            },
            "media-libs/gst-plugins-base-1.20.6": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": ">=x11-libs/libdrm-2.4.55[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": ">=x11-libs/libdrm-2.4.55[abi_x86_32?,abi_x86_64?]",
            },
            "app-emulation/wine-vanilla-9.0": {
                "EAPI": "8",
                "IUSE": "abi_x86_32 abi_x86_64",
                "DEPEND": "media-libs/gst-plugins-base[abi_x86_32?,abi_x86_64?]",
                "RDEPEND": "media-libs/gst-plugins-base[abi_x86_32?,abi_x86_64?]",
            },
        }

        user_config = {
            "make.conf": ('USE="abi_x86_64 zlib"',),
            "package.use": ("app-emulation/wine-vanilla abi_x86_32",),
        }

        world = ["app-emulation/wine-vanilla"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--usepkg": "y",
                },
                use_changes={
                    "media-libs/gst-plugins-base-1.20.6": {"abi_x86_32": True},
                    "x11-libs/libdrm-2.4.120": {"abi_x86_32": True},
                    "x11-libs/libpciaccess-0.17-r1": {"abi_x86_32": True},
                    "sys-libs/zlib-1.3-r4": {"abi_x86_32": True},
                },
                mergelist=[
                    "sys-libs/zlib-1.3-r4",
                    "x11-libs/libpciaccess-0.17-r1",
                    "x11-libs/libdrm-2.4.120",
                    "media-libs/gst-plugins-base-1.20.6",
                    "app-emulation/wine-vanilla-9.0",
                ],
                success=False,
            ),
        )

        playground = ResolverPlayground(
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            world=world,
            user_config=user_config,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
