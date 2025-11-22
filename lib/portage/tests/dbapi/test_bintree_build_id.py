# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase

from portage.dbapi.bintree import binarytree


class BinarytreeBuildIdTestCase(TestCase):
    def testBinarytreeBuildId(self):
        cases = {
            "sec-keys/openpgp-keys-bzip2-20220406.gpkg.tar": -1,
            "sec-keys/openpgp-keys-bzip2/openpgp-keys-bzip2-20220406-1.gpkg.tar": 1,
            "sec-keys/openpgp-keys-bzip2-20220406.xpak": -1,
            "sec-keys/openpgp-keys-bzip2/openpgp-keys-bzip2-20220406-1.xpak": 1,
        }
        for filename, expected_build_id in cases.items():
            build_id = binarytree._parse_build_id(filename)
            self.assertEqual(
                build_id,
                expected_build_id,
                msg=f"Failed to parse build ID from '{filename}'",
            )
