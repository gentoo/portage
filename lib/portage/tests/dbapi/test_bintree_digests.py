# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
from unittest.mock import patch

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class BinarytreeDigestsTestCase(TestCase):
    """
    binarytree._get_digests() reads digests from the local Packages index,
    and parses it again only when the file has changed.
    """

    def setUp(self):
        self.playground = ResolverPlayground(
            binpkgs={"dev-libs/A-1": {"EAPI": "8"}, "dev-libs/B-1": {"EAPI": "8"}}
        )
        self.bintree = self.playground.trees[self.playground.eroot]["bintree"]
        self.bintree.populate()

    def tearDown(self):
        self.playground.cleanup()

    def _cpv(self, atom):
        (cpv,) = self.bintree.dbapi.match(atom)
        return cpv

    def test_digests(self):
        for atom in ("dev-libs/A", "dev-libs/B"):
            cpv = self._cpv(atom)
            self.assertEqual(
                self.bintree._get_digests(cpv)["size"],
                os.stat(self.bintree.getname(cpv)).st_size,
            )

    def test_index_parsed_once(self):
        with patch.object(
            self.bintree, "_load_pkgindex", wraps=self.bintree._load_pkgindex
        ) as load:
            self.bintree._get_digests(self._cpv("dev-libs/A"))
            self.bintree._get_digests(self._cpv("dev-libs/B"))
            self.assertEqual(load.call_count, 1)

    def test_index_changed(self):
        cpv = self._cpv("dev-libs/A")
        self.assertNotIn("SHA1", self.bintree._get_digests(cpv))
        pkgindex = self.bintree._load_pkgindex()
        for d in pkgindex.packages:
            if d["CPV"] == cpv:
                d["SHA1"] = "0" * 40
        # This also resets the mtime to the TIMESTAMP header.
        self.bintree._pkgindex_write(pkgindex)
        self.assertEqual(self.bintree._get_digests(cpv)["SHA1"], "0" * 40)
