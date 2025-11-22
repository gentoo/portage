# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class VirtualCycleTestCase(TestCase):
    def testVirtualCycle(self):
        ebuilds = {
            "app-misc/foo-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/A",
            },
            "virtual/A-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/B",
            },
            "virtual/B-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/C",
            },
            "virtual/C-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/A",
            },
            "app-misc/bar-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/gzip",
            },
            "virtual/gzip-1": {
                "EAPI": "8",
                "RDEPEND": "virtual/gzip",
            },
        }

        test_cases = (
            # Test direct virtual cycle for bug 965570.
            ResolverPlaygroundTestCase(
                ["app-misc/bar"],
                success=False,
                virtual_cycle={"virtual/gzip-1"},
            ),
            # Test indirect virtual cycle for bug 965570.
            ResolverPlaygroundTestCase(
                ["app-misc/foo"],
                success=False,
                virtual_cycle={"virtual/A-1", "virtual/B-1", "virtual/C-1"},
            ),
        )

        playground = ResolverPlayground(debug=False, ebuilds=ebuilds)

        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
