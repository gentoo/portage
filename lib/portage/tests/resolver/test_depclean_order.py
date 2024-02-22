# Copyright 2013-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class SimpleDepcleanTestCase(TestCase):
    def testSimpleDepclean(self):
        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/B:=",
            },
            "dev-libs/B-1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/A",
            },
            "dev-libs/C-1": {},
        }

        installed = {
            "dev-libs/A-1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/B:0/0=",
            },
            "dev-libs/B-1": {
                "EAPI": "5",
                "RDEPEND": "dev-libs/A",
            },
            "dev-libs/C-1": {},
        }

        world = ("dev-libs/C",)

        test_cases = (
            # Remove dev-libs/A-1 first because of dev-libs/B:0/0= (built
            # slot-operator dep).
            ResolverPlaygroundTestCase(
                [],
                options={"--depclean": True},
                success=True,
                ordered=True,
                cleanlist=["dev-libs/A-1", "dev-libs/B-1"],
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

    def testIDEPENDDepclean(self):
        """
        Test for bug 916135, where a direct circular dependency caused
        the unmerge order to fail to account for IDEPEND.
        """

        ebuilds = {
            "dev-util/A-1": {},
            "dev-libs/B-1": {
                "EAPI": "8",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:=",
            },
            "dev-libs/C-1": {},
        }

        installed = {
            "dev-util/A-1": {},
            "dev-libs/B-1": {
                "EAPI": "8",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:0/0=",
            },
            "dev-libs/C-1": {},
        }

        world = ("dev-libs/C",)

        test_cases = (
            # Remove dev-libs/B first because it IDEPENDs on dev-util/A
            ResolverPlaygroundTestCase(
                [],
                options={"--depclean": True},
                success=True,
                ordered=True,
                cleanlist=[
                    "dev-libs/B-1",
                    "dev-util/A-1",
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

    def testCircularDepclean(self):
        """
        Test for bug 916135, where an indirect circular dependency caused
        the unmerge order to fail to account for IDEPEND.
        """

        ebuilds = {
            "dev-util/A-1": {},
            "dev-libs/B-1": {
                "EAPI": "8",
                "SLOT": "1",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:=",
            },
            "dev-libs/B-2": {
                "EAPI": "8",
                "SLOT": "2",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:=",
            },
            "dev-libs/C-1": {},
        }

        installed = {
            "dev-util/A-1": {},
            "dev-libs/B-1": {
                "EAPI": "8",
                "SLOT": "1",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:2/2=",
            },
            "dev-libs/B-2": {
                "EAPI": "8",
                "SLOT": "2",
                "IDEPEND": "dev-util/A",
                "RDEPEND": "dev-libs/B:1/1=",
            },
            "dev-libs/C-1": {},
        }

        world = ("dev-libs/C",)

        test_cases = (
            # Remove dev-libs/B first because it IDEPENDs on dev-util/A
            ResolverPlaygroundTestCase(
                [],
                options={"--depclean": True},
                success=True,
                ordered=True,
                cleanlist=["dev-libs/B-2", "dev-libs/B-1", "dev-util/A-1"],
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
