# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import pickle

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

from _emerge.Blocker import Blocker
from _emerge.BlockerDepPriority import BlockerDepPriority
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import backtrack_depgraph
from _emerge.DepPriority import DepPriority
from _emerge.Package import Package
from _emerge.UnmergeDepPriority import UnmergeDepPriority
from _emerge._depgraph_fork import (
    _decode_priority,
    _encode_priority,
    decode_scheduler_graph,
    encode_scheduler_graph,
)


def _is_arg(node):
    return not isinstance(node, (Blocker, Package))


class DepgraphForkTestCase(TestCase):
    def testPriorityRoundTrip(self):
        """
        The encoding walks __slots__, so a priority class which gains a
        field has to survive the trip without being taught about it.
        """
        priorities = (
            DepPriority(buildtime=True, satisfied=True),
            DepPriority(runtime=True, optional=True),
            UnmergeDepPriority(runtime_slot_op=True, ignored=True),
            BlockerDepPriority(runtime=True),
        )

        for priority in priorities:
            decoded = _decode_priority(_encode_priority(priority))
            self.assertEqual(type(decoded), type(priority))
            self.assertEqual(str(decoded), str(priority))
            self.assertEqual(int(decoded), int(priority))

    def testSolvedBlockerRoundTrip(self):
        """
        A blocker which the calculation solved is in the mergelist, for
        display, without being a node of the scheduler graph.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "RDEPEND": "!dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "RDEPEND": "!dev-libs/A"},
        }
        installed = {
            "dev-libs/B-1": {"EAPI": "8", "RDEPEND": "!dev-libs/A"},
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )
        try:
            settings = playground.settings
            trees = playground.trees
            myopts = {"--quiet": True, "--oneshot": True}
            myparams = create_depgraph_params(myopts, None)

            success, mydepgraph, _favorites = backtrack_depgraph(
                settings, trees, myopts, myparams, None, ["dev-libs/A"], None
            )
            self.assertTrue(success)

            graph_config = mydepgraph.schedulerGraph()
            blockers = [x for x in graph_config.mergelist if isinstance(x, Blocker)]
            self.assertTrue(blockers)
            self.assertTrue(
                any(x not in graph_config.graph.nodes for x in blockers),
                "expected a mergelist blocker which is not a graph node",
            )

            payload = pickle.loads(pickle.dumps(encode_scheduler_graph(graph_config)))
            decoded = decode_scheduler_graph(payload, trees, myopts)

            self.assertEqual(
                [str(x) for x in decoded.mergelist],
                [str(x) for x in graph_config.mergelist],
            )
            self.assertEqual(len(decoded.graph.nodes), len(graph_config.graph.nodes))
        finally:
            playground.cleanup()

    def testSchedulerGraphRoundTrip(self):
        ebuilds = {
            "dev-libs/A-2": {
                "EAPI": "8",
                "IUSE": "+flag",
                "DEPEND": "dev-libs/B",
                "RDEPEND": "dev-libs/C flag? ( dev-libs/D )",
                "LICENSE": "flag? ( GPL-2 ) BSD",
            },
            "dev-libs/B-1": {"EAPI": "8"},
            "dev-libs/C-1": {"EAPI": "8", "RDEPEND": "!<dev-libs/E-2"},
            "dev-libs/D-1": {"EAPI": "8"},
            "dev-libs/E-2": {"EAPI": "8"},
        }
        installed = {
            "dev-libs/A-1": {"EAPI": "8", "RDEPEND": "dev-libs/C"},
            "dev-libs/C-1": {"EAPI": "8"},
            "dev-libs/E-1": {"EAPI": "8"},
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, debug=False
        )
        try:
            settings = playground.settings
            trees = playground.trees
            myopts = {"--quiet": True, "--update": True, "--deep": True}
            myparams = create_depgraph_params(myopts, None)

            success, mydepgraph, _favorites = backtrack_depgraph(
                settings, trees, myopts, myparams, None, ["dev-libs/A"], None
            )
            self.assertTrue(success)

            graph_config = mydepgraph.schedulerGraph()
            payload = encode_scheduler_graph(graph_config)

            # The whole point of the child process is that the result
            # travels as plain data.
            payload = pickle.loads(pickle.dumps(payload))

            decoded = decode_scheduler_graph(payload, trees, myopts)

            self.assertEqual(
                [str(x) for x in decoded.mergelist],
                [str(x) for x in graph_config.mergelist],
            )
            # The DependencyArg nodes come back as placeholders, which only
            # preserve the shape of the graph, so compare the rest.
            self.assertEqual(
                sorted(str(x) for x in decoded.graph.nodes if not _is_arg(x)),
                sorted(str(x) for x in graph_config.graph.nodes if not _is_arg(x)),
            )
            self.assertEqual(len(decoded.graph.nodes), len(graph_config.graph.nodes))

            before = {
                pkg._hash_key: pkg
                for pkg in graph_config.pkg_cache.values()
                if isinstance(pkg, Package)
            }
            after = {
                pkg._hash_key: pkg
                for pkg in decoded.pkg_cache.values()
                if isinstance(pkg, Package)
            }
            self.assertEqual(sorted(after), sorted(before))

            for key, pkg in before.items():
                for metadata_key in Package._dep_keys + ("LICENSE", "SLOT"):
                    self.assertEqual(
                        after[key]._metadata[metadata_key],
                        pkg._metadata[metadata_key],
                        f"{key}: {metadata_key} differs",
                    )
        finally:
            playground.cleanup()
