# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import random

from portage.tests import TestCase
from portage.util.digraph import digraph

from _emerge.depgraph import _gather_deps_closures


def _build(edges, extra_nodes=()):
    """Build a digraph from (child, parent) edges; add() links child->parent."""
    g = digraph()
    for node in extra_nodes:
        g.add(node, None)
    for child, parent in edges:
        g.add(child, parent)
    return g


def _reference(graph, valid_nodes, ignore_priority, blocked_nodes, node, selected):
    """Recursive gather_deps reference, mirroring depgraph._serialize_tasks."""
    if node in selected:
        return True
    if node not in valid_nodes:
        return False
    if node in blocked_nodes:
        return False
    selected.add(node)
    for child in graph.child_nodes(node, ignore_priority=ignore_priority):
        if not _reference(
            graph, valid_nodes, ignore_priority, blocked_nodes, child, selected
        ):
            return False
    return True


class GatherDepsClosuresTestCase(TestCase):
    def _assert_matches_reference(
        self, graph, valid_nodes, blocked_nodes=frozenset(), ignore_priority=None
    ):
        ok_nodes, closure_size, closure_members = _gather_deps_closures(
            graph, valid_nodes, ignore_priority, blocked_nodes
        )
        for node in valid_nodes:
            selected = set()
            ok = _reference(
                graph, valid_nodes, ignore_priority, blocked_nodes, node, selected
            )
            if ok:
                self.assertIn(node, ok_nodes)
                self.assertEqual(closure_size[node], len(selected))
                self.assertEqual(closure_members[node], frozenset(selected))
            else:
                self.assertNotIn(node, ok_nodes)
                self.assertNotIn(node, closure_size)
                self.assertNotIn(node, closure_members)
        # ok_nodes must not contain anything outside valid_nodes.
        self.assertTrue(ok_nodes.issubset(valid_nodes))
        return ok_nodes, closure_size, closure_members

    def testSimpleCycle(self):
        g = _build([("A", "B"), ("B", "A")])
        valid = {"A", "B"}
        ok, size, members = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, {"A", "B"})
        self.assertEqual(size["A"], 2)
        self.assertEqual(size["B"], 2)
        # Cycle members share one frozenset object.
        self.assertIs(members["A"], members["B"])

    def testDagClosure(self):
        g = _build([("B", "A"), ("C", "B")])
        valid = {"A", "B", "C"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, valid)
        self.assertEqual(size["A"], 3)
        self.assertEqual(size["B"], 2)
        self.assertEqual(size["C"], 1)

    def testNestedCycles(self):
        # {C,D} depends on {A,B}, so {A,B} must have the smaller closure.
        g = _build([("A", "B"), ("B", "A"), ("C", "D"), ("D", "C"), ("A", "C")])
        valid = {"A", "B", "C", "D"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, valid)
        self.assertEqual(size["A"], 2)
        self.assertEqual(size["B"], 2)
        self.assertEqual(size["C"], 4)
        self.assertEqual(size["D"], 4)

    def testEscapingCycle(self):
        # A escapes to X, and B reaches A, so both must fail.
        g = _build([("A", "B"), ("B", "A"), ("X", "A")])
        valid = {"A", "B"}
        ok, size, members = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, set())
        self.assertEqual(size, {})
        self.assertEqual(members, {})

    def testEscapePartial(self):
        g = _build([("A", "B"), ("B", "A"), ("X", "A"), ("C", "D"), ("D", "C")])
        valid = {"A", "B", "C", "D"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, {"C", "D"})
        self.assertEqual(size["C"], 2)

    def testBlockedNode(self):
        # P stands in for replacement_portage. A reaches P and fails with it,
        # but the independent B is unaffected.
        g = _build([("P", "A"), ("B", None)], extra_nodes=("P",))
        valid = {"A", "B", "P"}
        ok, size, _ = self._assert_matches_reference(
            g, valid, blocked_nodes=frozenset({"P"})
        )
        self.assertEqual(ok, {"B"})
        self.assertEqual(size["B"], 1)

    def testTieSizeIndependentCycles(self):
        # Equal-size cycles report equal sizes, leaving the tiebreak to the
        # caller's sorted node order.
        g = _build([("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")])
        valid = {"A", "B", "C", "D"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, valid)
        self.assertEqual(size["A"], size["C"])
        self.assertEqual(size["A"], 2)

    def testValidSubsetOfGraph(self):
        # B escapes to the excluded C, and A reaches B, so both fail.
        g = _build([("B", "A"), ("C", "B"), ("D", "C")])
        valid = {"A", "B"}
        ok, _, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, set())

    def testSelfLoop(self):
        g = _build([("A", "A")])
        valid = {"A"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, {"A"})
        self.assertEqual(size["A"], 1)

    def testEmpty(self):
        g = digraph()
        ok, size, members = _gather_deps_closures(g, set(), None, frozenset())
        self.assertEqual(ok, set())
        self.assertEqual(size, {})
        self.assertEqual(members, {})

    def testRandomFuzz(self):
        rng = random.Random(0)
        for _ in range(300):
            n = rng.randint(1, 9)
            all_nodes = [f"n{i}" for i in range(n)]
            g = digraph()
            for node in all_nodes:
                g.add(node, None)
            for parent in all_nodes:
                for child in all_nodes:
                    if rng.random() < 0.25:
                        g.add(child, parent)
            valid = {node for node in all_nodes if rng.random() < 0.8}
            blocked = frozenset(node for node in valid if rng.random() < 0.15)
            self._assert_matches_reference(g, valid, blocked_nodes=blocked)

    def testChainOfCycles(self):
        # A chain of three cycles, so closures accumulate across several
        # levels of the condensation.
        g = _build(
            [
                ("A", "B"),
                ("B", "A"),
                ("C", "D"),
                ("D", "C"),
                ("E", "F"),
                ("F", "E"),
                ("C", "A"),  # cycle1 depends on cycle2
                ("E", "C"),  # cycle2 depends on cycle3
            ]
        )
        valid = {"A", "B", "C", "D", "E", "F"}
        ok, size, _ = self._assert_matches_reference(g, valid)
        self.assertEqual(ok, valid)
        self.assertEqual(size["A"], 6)
        self.assertEqual(size["C"], 4)
        self.assertEqual(size["E"], 2)
