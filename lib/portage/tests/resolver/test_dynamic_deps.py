# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

from _emerge.BlockerDB import BlockerDB
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import backtrack_depgraph
from _emerge.FakeVartree import FakeVartree, fake_vartree_options


class DynamicDepsMergeTestCase(TestCase):
    def testBlockerQueryFromRunningLoop(self):
        """
        The Scheduler queries installed blockers from inside its own event
        loop, where the lazy dynamic-deps pull cannot run. See bug 982753.
        """
        ebuilds = {
            "dev-libs/A-2": {"EAPI": "8", "RDEPEND": "dev-libs/C"},
            "dev-libs/C-1": {"EAPI": "8"},
            # The live dependencies block the package being merged, the
            # recorded ones do not, so the two answers can be told apart.
            "dev-libs/D-1": {"EAPI": "8", "RDEPEND": "!dev-libs/A"},
        }
        installed = {
            "dev-libs/A-1": {"EAPI": "8", "RDEPEND": "dev-libs/C"},
            "dev-libs/C-1": {"EAPI": "8"},
            "dev-libs/D-1": {"EAPI": "8"},
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )
        try:
            settings = playground.settings
            trees = playground.trees
            eroot = settings["EROOT"]
            myopts = {"--quiet": True, "--oneshot": True}
            myparams = create_depgraph_params(myopts, None)
            self.assertTrue("dynamic_deps" in myparams)

            success, mydepgraph, _favorites = backtrack_depgraph(
                settings, trees, myopts, myparams, None, ["dev-libs/A"], None
            )
            self.assertTrue(success)
            new_pkg = next(
                pkg
                for pkg in mydepgraph.schedulerGraph().mergelist
                if pkg.operation == "merge"
            )

            # A tree of the kind the Scheduler builds for --resume, where the
            # dynamic-deps apply has not run for any instance.
            fake_vartree = FakeVartree(
                trees[eroot]["root_config"], **fake_vartree_options(myopts)
            )
            fake_vartree.sync()
            blocker_db = BlockerDB(fake_vartree)

            async def find_blockers():
                return list(blocker_db.findInstalledBlockers(new_pkg))

            loop = asyncio.new_event_loop()
            try:
                self.assertEqual(loop.run_until_complete(find_blockers()), [])
            finally:
                loop.close()

            # The recorded dependencies answered the query, and the instance
            # stays pinned to them.
            self.assertEqual(
                fake_vartree.dbapi.aux_get("dev-libs/D-1", ["RDEPEND"]), [""]
            )
            self.assertEqual(
                trees[eroot]["porttree"].dbapi.aux_get("dev-libs/D-1", ["RDEPEND"]),
                ["!dev-libs/A"],
            )
        finally:
            playground.cleanup()
