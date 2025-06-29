# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class RebuildGhostscriptTestCase(TestCase):
    def testRebuildGhostscript(self):
        """
        Test bug 703676, where app-text/libspectre was rebuilt before
        its app-text/ghostscript-gpl DEPEND.
        """
        ebuilds = {
            "app-text/ghostscript-gpl-10.01.1": {
                "EAPI": "8",
                "DEPEND": "gtk? ( x11-libs/gtk+:3 )",
                "RDEPEND": "gtk? ( x11-libs/gtk+:3 )",
                "IUSE": "gtk",
            },
            "app-text/ghostscript-gpl-10.01.2": {
                "EAPI": "8",
                "SLOT": "0/10.01",
                "DEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "RDEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "IUSE": "dbus gtk",
            },
            "app-text/libspectre-0.2.11": {
                "EAPI": "8",
                "DEPEND": ">=app-text/ghostscript-gpl-9.53.0:=",
                "RDEPEND": ">=app-text/ghostscript-gpl-9.53.0:=",
            },
            "app-text/libspectre-0.2.12": {
                "EAPI": "8",
                "DEPEND": ">=app-text/ghostscript-gpl-9.53.0:=",
                "RDEPEND": ">=app-text/ghostscript-gpl-9.53.0:=",
            },
            "net-dns/avahi-0.8-r7": {
                "EAPI": "8",
                "DEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "RDEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "IUSE": "dbus gtk",
            },
            "net-print/cups-2.4.6": {
                "EAPI": "8",
                "DEPEND": "zeroconf? ( >=net-dns/avahi-0.6.31-r2[dbus] )",
                "RDEPEND": "zeroconf? ( >=net-dns/avahi-0.6.31-r2[dbus] )",
                "IUSE": "zeroconf",
            },
            "sys-apps/dbus-1.15.6": {
                "EAPI": "8",
            },
            "x11-libs/gtk+-3.24.38": {
                "EAPI": "8",
                "SLOT": "3",
                "DEPEND": "cups? ( >=net-print/cups-2.0 )",
                "RDEPEND": "cups? ( >=net-print/cups-2.0 )",
                "IUSE": "cups",
            },
            "x11-libs/goffice-0.10.55": {
                "EAPI": "8",
                "DEPEND": ">=app-text/libspectre-0.2.6:=",
                "RDEPEND": ">=app-text/libspectre-0.2.6:=",
            },
        }

        installed = {
            "app-text/ghostscript-gpl-10.01.1": {
                "EAPI": "8",
                "DEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "RDEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "IUSE": "dbus gtk",
                "USE": "dbus gtk",
            },
            "app-text/libspectre-0.2.11": {
                "EAPI": "8",
                "DEPEND": ">=app-text/ghostscript-gpl-9.53.0:0/10.01=",
                "RDEPEND": ">=app-text/ghostscript-gpl-9.53.0:0/10.01=",
            },
            "net-dns/avahi-0.8-r7": {
                "EAPI": "8",
                "DEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "RDEPEND": "dbus? ( sys-apps/dbus ) gtk? ( x11-libs/gtk+:3 )",
                "IUSE": "dbus gtk",
                "USE": "dbus gtk",
            },
            "net-print/cups-2.4.6": {
                "EAPI": "8",
                "DEPEND": "zeroconf? ( >=net-dns/avahi-0.6.31-r2[dbus] )",
                "RDEPEND": "zeroconf? ( >=net-dns/avahi-0.6.31-r2[dbus] )",
                "IUSE": "zeroconf",
                "USE": "zeroconf",
            },
            "sys-apps/dbus-1.15.6": {
                "EAPI": "8",
            },
            "x11-libs/gtk+-3.24.38": {
                "EAPI": "8",
                "SLOT": "3",
                "DEPEND": "cups? ( >=net-print/cups-2.0 )",
                "RDEPEND": "cups? ( >=net-print/cups-2.0 )",
                "IUSE": "cups",
                "USE": "cups",
            },
            "x11-libs/goffice-0.10.55": {
                "EAPI": "8",
                "DEPEND": ">=app-text/libspectre-0.2.6:0=",
                "RDEPEND": ">=app-text/libspectre-0.2.6:0=",
            },
        }

        world = [
            "x11-libs/goffice",
        ]

        user_config = {
            "make.conf": ('USE="cups dbus gtk zeroconf"',),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--deep": True, "--update": True},
                success=True,
                mergelist=[
                    "app-text/ghostscript-gpl-10.01.2",
                    "app-text/libspectre-0.2.12",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--emptytree": True},
                success=True,
                mergelist=[
                    "sys-apps/dbus-1.15.6",
                    "x11-libs/gtk+-3.24.38",
                    "net-dns/avahi-0.8-r7",
                    "net-print/cups-2.4.6",
                    "app-text/ghostscript-gpl-10.01.2",
                    "app-text/libspectre-0.2.12",
                    "x11-libs/goffice-0.10.55",
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
