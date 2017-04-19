# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util.digraph import digraph
#~ from portage.util import noiselimit
import portage.util

class DigraphTest(TestCase):

	def _assertBFSEqual(self, result, expected):
		result_stack = list(result)
		result_stack.reverse()
		expected_stack = list(reversed(expected))
		result_compared = []
		expected_compared = []
		while result_stack:
			if not expected_stack:
				result_compared.append(result_stack.pop())
				self.assertEqual(result_compared, expected_compared)
			expected_set = expected_stack.pop()
			if not isinstance(expected_set, list):
				expected_set = [expected_set]
			expected_set = set(expected_set)
			while expected_set:
				if not result_stack:
					expected_compared.extend(expected_set)
					self.assertEqual(result_compared, expected_compared)
				obj = result_stack.pop()
				try:
					expected_set.remove(obj)
				except KeyError:
					expected_compared.extend(expected_set)
					result_compared.append(obj)
					self.assertEqual(result_compared, expected_compared)
				else:
					expected_compared.append(obj)
					result_compared.append(obj)
		if expected_stack:
			expected_set = expected_stack.pop()
			if not isinstance(expected_set, list):
				expected_set = [expected_set]
			expected_compared.extend(expected_set)
			self.assertEqual(result_compared, expected_compared)

	def testBackwardCompatibility(self):
		g = digraph()
		f = g.copy()
		g.addnode("A", None)
		self.assertEqual("A" in g, True)
		self.assertEqual(bool(g), True)
		self.assertEqual(g.allnodes(), ["A"])
		self.assertEqual(g.allzeros(), ["A"])
		self.assertEqual(g.hasnode("A"), True)

	def testDigraphEmptyGraph(self):
		g = digraph()
		f = g.clone()
		for x in g, f:
			self.assertEqual(bool(x), False)
			self.assertEqual(x.contains("A"), False)
			self.assertEqual(x.firstzero(), None)
			self.assertRaises(KeyError, x.remove, "A")
			x.delnode("A")
			self.assertEqual(list(x), [])
			self.assertEqual(x.get("A"), None)
			self.assertEqual(x.get("A", "default"), "default")
			self.assertEqual(x.all_nodes(), [])
			self.assertEqual(x.leaf_nodes(), [])
			self.assertEqual(x.root_nodes(), [])
			self.assertRaises(KeyError, x.child_nodes, "A")
			self.assertRaises(KeyError, x.parent_nodes, "A")
			self.assertEqual(x.hasallzeros(), True)
			self.assertRaises(KeyError, list, x.bfs("A"))
			self.assertRaises(KeyError, x.shortest_path, "A", "B")
			self.assertRaises(KeyError, x.remove_edge, "A", "B")
			self.assertEqual(x.get_cycles(), [])
			x.difference_update("A")
			portage.util.noiselimit = -2
			x.debug_print()
			portage.util.noiselimit = 0

	def testDigraphCircle(self):
		g = digraph()
		g.add("A", "B", -1)
		g.add("B", "C", 0)
		g.add("C", "D", 1)
		g.add("D", "A", 2)

		f = g.clone()
		h = digraph()
		h.update(f)
		for x in g, f, h:
			self.assertEqual(bool(x), True)
			self.assertEqual(x.contains("A"), True)
			self.assertEqual(x.firstzero(), None)
			self.assertRaises(KeyError, x.remove, "Z")
			x.delnode("Z")
			self.assertEqual(list(x), ["A", "B", "C", "D"])
			self.assertEqual(x.get("A"), "A")
			self.assertEqual(x.get("A", "default"), "A")
			self.assertEqual(x.all_nodes(), ["A", "B", "C", "D"])
			self.assertEqual(x.leaf_nodes(), [])
			self.assertEqual(x.root_nodes(), [])
			self.assertEqual(x.child_nodes("A"), ["D"])
			self.assertEqual(x.child_nodes("A", ignore_priority=2), [])
			self.assertEqual(x.parent_nodes("A"), ["B"])
			self.assertEqual(x.parent_nodes("A", ignore_priority=-2), ["B"])
			self.assertEqual(x.parent_nodes("A", ignore_priority=-1), [])
			self.assertEqual(x.hasallzeros(), False)
			self._assertBFSEqual(x.bfs("A"), [(None, "A"), ("A", "D"), ("D", "C"), ("C", "B")])
			self.assertEqual(x.shortest_path("A", "D"), ["A", "D"])
			self.assertEqual(x.shortest_path("D", "A"), ["D", "C", "B", "A"])
			self.assertEqual(x.shortest_path("A", "D", ignore_priority=2), None)
			self.assertEqual(x.shortest_path("D", "A", ignore_priority=-2), ["D", "C", "B", "A"])
			cycles = set(tuple(y) for y in x.get_cycles())
			self.assertEqual(cycles, set([("D", "C", "B", "A"), ("C", "B", "A", "D"), ("B", "A", "D", "C"), \
				("A", "D", "C", "B")]))
			x.remove_edge("A", "B")
			self.assertEqual(x.get_cycles(), [])
			x.difference_update(["D"])
			self.assertEqual(x.all_nodes(), ["A", "B", "C"])
			portage.util.noiselimit = -2
			x.debug_print()
			portage.util.noiselimit = 0

	def testDigraphTree(self):
		g = digraph()
		g.add("B", "A", -1)
		g.add("C", "A", 0)
		g.add("D", "C", 1)
		g.add("E", "C", 2)

		f = g.clone()
		for x in g, f:
			self.assertEqual(bool(x), True)
			self.assertEqual(x.contains("A"), True)
			self.assertEqual(x.has_edge("B", "A"), True)
			self.assertEqual(x.has_edge("A", "B"), False)
			self.assertEqual(x.firstzero(), "B")
			self.assertRaises(KeyError, x.remove, "Z")
			x.delnode("Z")
			self.assertEqual(set(x), set(["A", "B", "C", "D", "E"]))
			self.assertEqual(x.get("A"), "A")
			self.assertEqual(x.get("A", "default"), "A")
			self.assertEqual(set(x.all_nodes()), set(["A", "B", "C", "D", "E"]))
			self.assertEqual(set(x.leaf_nodes()), set(["B", "D", "E"]))
			self.assertEqual(set(x.leaf_nodes(ignore_priority=0)), set(["A", "B", "D", "E"]))
			self.assertEqual(x.root_nodes(), ["A"])
			self.assertEqual(set(x.root_nodes(ignore_priority=0)), set(["A", "B", "C"]))
			self.assertEqual(set(x.child_nodes("A")), set(["B", "C"]))
			self.assertEqual(x.child_nodes("A", ignore_priority=2), [])
			self.assertEqual(x.parent_nodes("B"), ["A"])
			self.assertEqual(x.parent_nodes("B", ignore_priority=-2), ["A"])
			self.assertEqual(x.parent_nodes("B", ignore_priority=-1), [])
			self.assertEqual(x.hasallzeros(), False)
			self._assertBFSEqual(x.bfs("A"), [(None, "A"), [("A", "C"), ("A", "B")], [("C", "E"), ("C", "D")]])
			self.assertEqual(x.shortest_path("A", "D"), ["A", "C", "D"])
			self.assertEqual(x.shortest_path("D", "A"), None)
			self.assertEqual(x.shortest_path("A", "D", ignore_priority=2), None)
			cycles = set(tuple(y) for y in x.get_cycles())
			self.assertEqual(cycles, set())
			x.remove("D")
			self.assertEqual(set(x.all_nodes()), set(["A", "B", "C", "E"]))
			x.remove("C")
			self.assertEqual(set(x.all_nodes()), set(["A", "B", "E"]))
			portage.util.noiselimit = -2
			x.debug_print()
			portage.util.noiselimit = 0
			self.assertRaises(KeyError, x.remove_edge, "A", "E")

	def testDigraphCompleteGraph(self):
		g = digraph()
		g.add("A", "B", -1)
		g.add("B", "A", 1)
		g.add("A", "C", 1)
		g.add("C", "A", -1)
		g.add("C", "B", 1)
		g.add("B", "C", 1)

		f = g.clone()
		for x in g, f:
			self.assertEqual(bool(x), True)
			self.assertEqual(x.contains("A"), True)
			self.assertEqual(x.firstzero(), None)
			self.assertRaises(KeyError, x.remove, "Z")
			x.delnode("Z")
			self.assertEqual(list(x), ["A", "B", "C"])
			self.assertEqual(x.get("A"), "A")
			self.assertEqual(x.get("A", "default"), "A")
			self.assertEqual(x.all_nodes(), ["A", "B", "C"])
			self.assertEqual(x.leaf_nodes(), [])
			self.assertEqual(x.root_nodes(), [])
			self.assertEqual(set(x.child_nodes("A")), set(["B", "C"]))
			self.assertEqual(x.child_nodes("A", ignore_priority=0), ["B"])
			self.assertEqual(set(x.parent_nodes("A")), set(["B", "C"]))
			self.assertEqual(x.parent_nodes("A", ignore_priority=0), ["C"])
			self.assertEqual(x.parent_nodes("A", ignore_priority=1), [])
			self.assertEqual(x.hasallzeros(), False)
			self._assertBFSEqual(x.bfs("A"), [(None, "A"), [("A", "C"), ("A", "B")]])
			self.assertEqual(x.shortest_path("A", "C"), ["A", "C"])
			self.assertEqual(x.shortest_path("C", "A"), ["C", "A"])
			self.assertEqual(x.shortest_path("A", "C", ignore_priority=0), ["A", "B", "C"])
			self.assertEqual(x.shortest_path("C", "A", ignore_priority=0), ["C", "A"])
			cycles = set(frozenset(y) for y in x.get_cycles())
			self.assertEqual(cycles, set([frozenset(["A", "B"]), frozenset(["A", "C"]), frozenset(["B", "C"])]))
			x.remove_edge("A", "B")
			cycles = set(frozenset(y) for y in x.get_cycles())
			self.assertEqual(cycles, set([frozenset(["A", "C"]), frozenset(["C", "B"])]))
			x.difference_update(["C"])
			self.assertEqual(x.all_nodes(), ["A", "B"])
			portage.util.noiselimit = -2
			x.debug_print()
			portage.util.noiselimit = 0

	def testDigraphIgnorePriority(self):

		def always_true(dummy):
			return True

		def always_false(dummy):
			return False

		g = digraph()
		g.add("A", "B")

		self.assertEqual(g.parent_nodes("A"), ["B"])
		self.assertEqual(g.parent_nodes("A", ignore_priority=always_false), ["B"])
		self.assertEqual(g.parent_nodes("A", ignore_priority=always_true), [])

		self.assertEqual(g.child_nodes("B"), ["A"])
		self.assertEqual(g.child_nodes("B", ignore_priority=always_false), ["A"])
		self.assertEqual(g.child_nodes("B", ignore_priority=always_true), [])

		self.assertEqual(g.leaf_nodes(), ["A"])
		self.assertEqual(g.leaf_nodes(ignore_priority=always_false), ["A"])
		self.assertEqual(g.leaf_nodes(ignore_priority=always_true), ["A", "B"])

		self.assertEqual(g.root_nodes(), ["B"])
		self.assertEqual(g.root_nodes(ignore_priority=always_false), ["B"])
		self.assertEqual(g.root_nodes(ignore_priority=always_true), ["A", "B"])
