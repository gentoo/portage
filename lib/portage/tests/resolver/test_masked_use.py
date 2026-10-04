# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


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
