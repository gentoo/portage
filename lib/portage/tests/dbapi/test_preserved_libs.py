# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dbapi.vartree import _find_unneeded_preserved_nodes
from portage.tests import TestCase
from portage.util.digraph import digraph


class FindUnneededPreservedNodesTestCase(TestCase):
    """
    Tests for the graph analysis which decides that a preserved library
    has no consumers left. In the graph, the parents of a node are its
    consumers.
    """

    def _build(self, edges, preserved):
        # Each edge is a (consumer, library) pair.
        graph = digraph()
        for node in preserved:
            graph.add(node, None)
        for consumer, lib in edges:
            graph.add(lib, consumer)
        return graph, set(preserved)

    def testNoConsumers(self):
        graph, preserved = self._build([], ["libfoo"])
        self.assertEqual(_find_unneeded_preserved_nodes(graph, preserved), {"libfoo"})

    def testInstalledConsumer(self):
        graph, preserved = self._build([("bar", "libfoo")], ["libfoo"])
        self.assertEqual(_find_unneeded_preserved_nodes(graph, preserved), set())

    def testChainOfPreservedLibs(self):
        # libbar is preserved and consumes libfoo, and nothing consumes
        # libbar, so both are unneeded.
        graph, preserved = self._build([("libbar", "libfoo")], ["libfoo", "libbar"])
        self.assertEqual(
            _find_unneeded_preserved_nodes(graph, preserved),
            {"libfoo", "libbar"},
        )

    def testChainWithInstalledConsumer(self):
        # An installed consumer at the head of the chain keeps everything
        # in the chain alive.
        graph, preserved = self._build(
            [("baz", "libbar"), ("libbar", "libfoo")], ["libfoo", "libbar"]
        )
        self.assertEqual(_find_unneeded_preserved_nodes(graph, preserved), set())
