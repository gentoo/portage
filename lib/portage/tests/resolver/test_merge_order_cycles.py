# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class MergeOrderCyclesTestCase(TestCase):
    def testRebuildTriggerMergeOrder(self):
        """
        A rebuild triggered by an upgrade must be merged after the upgrade
        that triggered it, even when the upgrade is itself part of a cycle
        (bug 463976).
        """
        ebuilds = {
            "sys-apps/util-linux-2.22.2": {"EAPI": "8", "DEPEND": "virtual/udev"},
            "sys-fs/udev-200": {
                "EAPI": "8",
                "DEPEND": "sys-apps/util-linux",
                "PDEPEND": "virtual/udev",
            },
            "virtual/udev-197-r2": {"EAPI": "8", "RDEPEND": "sys-fs/udev"},
            "x11-base/xorg-server-1.13.1": {"EAPI": "8", "DEPEND": "virtual/udev"},
        }

        installed = {
            "sys-apps/util-linux-2.22.2": {"EAPI": "8", "DEPEND": "virtual/udev"},
            "sys-fs/udev-197-r8": {"EAPI": "8", "PDEPEND": "virtual/udev"},
            "virtual/udev-197-r2": {"EAPI": "8", "RDEPEND": "sys-fs/udev"},
            "x11-base/xorg-server-1.13.1": {"EAPI": "8", "DEPEND": "virtual/udev"},
        }

        world = ["sys-apps/util-linux", "x11-base/xorg-server"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--update": True,
                    "--deep": True,
                    "--newuse": True,
                    "--complete-graph": "y",
                    "--with-bdeps": "y",
                    "--rebuild-if-new-rev": "y",
                },
                success=True,
                ambiguous_merge_order=True,
                merge_order_assertions=(
                    ("sys-fs/udev-200", "x11-base/xorg-server-1.13.1"),
                ),
                mergelist=[
                    "sys-apps/util-linux-2.22.2",
                    "sys-fs/udev-200",
                    "x11-base/xorg-server-1.13.1",
                ],
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

    def testEmptyTreeSlotOperatorMergeOrder(self):
        """
        A package must be merged after the slot operator dependency it
        links against, even with --emptytree, where every package is in
        the merge list and cycles are more likely (bug 468052).
        """
        ebuilds = {
            "dev-libs/icu-51": {"EAPI": "8", "SLOT": "0/51"},
            "dev-libs/libxml2-2.9": {
                "EAPI": "8",
                "DEPEND": "dev-libs/icu:=",
                "RDEPEND": "dev-libs/icu:=",
            },
            "dev-libs/libxslt-1.1": {
                "EAPI": "8",
                "DEPEND": "dev-libs/libxml2",
                "RDEPEND": "dev-libs/libxml2",
            },
        }

        installed = {
            "dev-libs/icu-49": {"EAPI": "8", "SLOT": "0/49"},
            "dev-libs/libxml2-2.9": {
                "EAPI": "8",
                "DEPEND": "dev-libs/icu:0/49=",
                "RDEPEND": "dev-libs/icu:0/49=",
            },
            "dev-libs/libxslt-1.1": {
                "EAPI": "8",
                "DEPEND": "dev-libs/libxml2",
                "RDEPEND": "dev-libs/libxml2",
            },
        }

        world = ["dev-libs/libxslt"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--emptytree": True},
                success=True,
                mergelist=[
                    "dev-libs/icu-51",
                    "dev-libs/libxml2-2.9",
                    "dev-libs/libxslt-1.1",
                ],
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
