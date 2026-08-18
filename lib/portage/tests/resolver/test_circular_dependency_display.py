# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util.digraph import digraph

from _emerge.DepPriority import DepPriority
from _emerge.resolver.circular_dependency import circular_dependency_handler


class CircularDependencyDisplayTestCase(TestCase):
    """
    Verify that the circular dependency handler is always able to
    describe the cycle it was created for, even when the cycle consists
    entirely of dependencies that are ignored by the default
    ignore_priority (bug 929010).
    """

    def _handler(self, graph):
        # The message preparation code does not need a depgraph, so
        # avoid the cost of constructing one here.
        handler = circular_dependency_handler.__new__(circular_dependency_handler)
        handler.graph = graph
        handler.cycles, handler.shortest_cycle = handler._find_cycles()
        return handler

    def testRuntimePostCycle(self):
        # PDEPEND edges are ignored by ignore_medium_soft.
        graph = digraph()
        priority = DepPriority(runtime_post=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertNotEqual(handler.shortest_cycle, None)
        self.assertEqual(set(handler.shortest_cycle), {"A", "B"})

        message = handler._prepare_circular_dep_message()
        self.assertNotEqual(message, None)
        self.assertTrue("A" in message)
        self.assertTrue("B" in message)

    def testOptionalCycle(self):
        # Optional edges are ignored by every ignore_priority.
        graph = digraph()
        priority = DepPriority(optional=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertNotEqual(handler.shortest_cycle, None)
        self.assertNotEqual(handler._prepare_circular_dep_message(), None)

    def testBuildtimeCycle(self):
        # The common case still uses the default ignore_priority.
        graph = digraph()
        priority = DepPriority(buildtime=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertEqual(set(handler.shortest_cycle), {"A", "B"})
