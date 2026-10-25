# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class MaskedUseTestCase(TestCase):
    def testMaskedUseMetadata(self):
        """
        MASKED_USE is ebuild metadata for EAPIs that support it. Like IUSE
        and REQUIRED_USE, values set by eclasses accumulate.
        """
        ebuilds = {
            "dev-vcs/git-1": {
                "EAPI": "9-masked-use",
                "IUSE": "perforce python_single_target_python3_13",
                "MASKED_USE": "!perforce? ( python_single_target_python3_13 )",
                "MISC_CONTENT": "inherit foo",
            },
            "dev-vcs/git-2": {
                "EAPI": "9",
                "IUSE": "perforce python_single_target_python3_13",
                "MASKED_USE": "!perforce? ( python_single_target_python3_13 )",
            },
        }
        eclasses = {
            "foo": (
                'IUSE="foo bar"',
                'MASKED_USE="!foo? ( bar )"',
            ),
        }

        playground = ResolverPlayground(ebuilds=ebuilds, eclasses=eclasses)
        try:
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            self.assertEqual(
                portdb.aux_get("dev-vcs/git-1", ["MASKED_USE"]),
                ["!perforce? ( python_single_target_python3_13 ) !foo? ( bar )"],
            )
            # Not supported by this EAPI, so it is not metadata.
            self.assertEqual(portdb.aux_get("dev-vcs/git-2", ["MASKED_USE"]), [""])
        finally:
            playground.cleanup()

    def testMaskedUseInvalid(self):
        """
        An ebuild with invalid MASKED_USE is masked.
        """
        ebuilds = {
            "dev-libs/valid-1": {
                "EAPI": "9-masked-use",
                "IUSE": "a b",
                "MASKED_USE": "!a? ( b )",
            },
            # The operators of REQUIRED_USE are not allowed.
            "dev-libs/invalid-1": {
                "EAPI": "9-masked-use",
                "IUSE": "a b",
                "MASKED_USE": "|| ( a b )",
            },
            # Flags must be in IUSE, both the masked ones
            "dev-libs/invalid-2": {
                "EAPI": "9-masked-use",
                "IUSE": "a",
                "MASKED_USE": "!a? ( b )",
            },
            # and the ones in conditionals.
            "dev-libs/invalid-3": {
                "EAPI": "9-masked-use",
                "IUSE": "b",
                "MASKED_USE": "!a? ( b )",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/valid"],
                success=True,
                mergelist=["dev-libs/valid-1"],
            ),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-1"], success=False),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-2"], success=False),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-3"], success=False),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
