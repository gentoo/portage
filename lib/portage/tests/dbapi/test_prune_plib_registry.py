# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage import config
from portage.dbapi.vartree import dblink
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class PrunePlibRegistryTestCase(TestCase):
    """
    dblink._prune_plib_registry() rebuilds the linkmap only when it is
    going to use it.
    """

    def setUp(self):
        self.playground = ResolverPlayground(
            installed={
                "dev-libs/A-1": {"EAPI": "8"},
                "dev-libs/B-1": {"EAPI": "8"},
            }
        )
        settings = self.playground.settings
        vartree = self.playground.trees[settings["EROOT"]]["vartree"]
        self.vardb = vartree.dbapi
        with open(self.vardb.getpath("dev-libs/A-1", filename="CONTENTS"), "w") as f:
            f.write("obj /usr/lib/libA.so.1 d41d8cd98f00b204e9800998ecf8427e 0\n")

        settings = config(clone=settings)
        settings["SLOT"] = "0"
        self.dblink = dblink(
            "dev-libs", "A-1", settings=settings, vartree=vartree, treetype="vartree"
        )
        self.rebuilds = 0

        def count_rebuild(**kwargs):
            self.rebuilds += 1

        self.dblink._linkmap_rebuild = count_rebuild
        # It would query the linkmap, which is never built here.
        self.dblink._find_unused_preserved_libs = lambda unmerge_no_replacement: {}

    def tearDown(self):
        self.playground.cleanup()

    def register_plib(self):
        # The registry drops entries whose files do not exist.
        lib = os.path.join(self.playground.settings["EROOT"], "usr/lib/libB.so.1")
        os.makedirs(os.path.dirname(lib), exist_ok=True)
        open(lib, "w").close()
        registry = self.vardb._plib_registry
        registry.lock()
        try:
            registry.load()
            registry.register("dev-libs/B-1", "0", "1", [lib])
            registry.store()
        finally:
            registry.unlock()

    def prune(self, **kwargs):
        self.rebuilds = 0
        self.dblink._prune_plib_registry(**kwargs)
        return self.rebuilds

    def testEmptyRegistry(self):
        self.assertEqual(self.prune(), 0)
        self.assertEqual(self.prune(unmerge=True, preserve_paths=set()), 0)

    def testUnmergeWithoutReplacement(self):
        self.assertEqual(self.prune(unmerge=True), 1)

    def testRegistryEntries(self):
        self.register_plib()
        self.assertEqual(self.prune(), 1)
        self.assertEqual(self.prune(unmerge=True, preserve_paths=set()), 1)
