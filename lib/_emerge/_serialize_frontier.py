# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Incrementally-maintained leaf frontier for depgraph._serialize_tasks.

_serialize_tasks repeatedly asks digraph.leaf_nodes() which nodes are leaves
under an ignore_priority filter. Each query is an O(V) scan, and the selection
loop issues many of them.

The frontier keeps, per node and per level, a count of how many children have an
edge surviving that level's filter; the node is a leaf under level L iff its
count for L is zero. Removing a node decrements its parents' counts; adding an
edge increments the parent's counts.

Each level owns a min-heap of the order-indices of its current leaves, so leaves
can be enumerated in mygraph.order without an O(V) walk. Heaps use lazy deletion:
an entry is valid iff the node is still in the graph, still leaf under the level,
and the entry's index is the node's current order-index.

order-index is a node's position in mygraph.order; a node introduced later
(uninstall reversal / blocker edges) gets an appended index, as in digraph.add().

PORTAGE_SERIALIZE_FRONTIER_DISABLE makes _serialize_tasks fall back to the
digraph.leaf_nodes() path (frontier not built).
"""

from heapq import heappop, heappush

from _emerge.DepPriorityNormalRange import DepPriorityNormalRange
from _emerge.DepPrioritySatisfiedRange import DepPrioritySatisfiedRange
from portage.util.digraph import digraph


def _build_levels():
    """Return (filters, level_of) for the union of ignore_priority filters used
    by the DepPriorityNormalRange and DepPrioritySatisfiedRange leaf scans.

    Level 0 is the None filter (leaf iff no children). Filters are deduplicated
    by object identity; the ignore_priority entries are stable singletons.
    """
    filters = [None]
    seen = {id(None)}
    for rng in (DepPriorityNormalRange, DepPrioritySatisfiedRange):
        for f in rng.ignore_priority:
            if id(f) not in seen:
                seen.add(id(f))
                filters.append(f)
    level_of = {id(f): i for i, f in enumerate(filters)}
    return tuple(filters), level_of


class _SerializeFrontier:
    """Per-node, per-level surviving-child counts and per-level ready heaps.

    A node is a leaf under level L iff surv[node][L] == 0. Counts and heaps are
    maintained incrementally as the graph is mutated (see remove/add_edge).
    """

    def __init__(self, graph):
        self._graph = graph
        self._filters, self._level_of = _build_levels()
        self._nlevels = nlevels = len(self._filters)
        # node -> list[int]: surviving-child count per level
        self._surv = {}
        # (parent, child) -> survival bitmask over levels
        self._edge_mask = {}
        # node -> current order-index; index -> node
        self._index = {}
        self._by_index = {}
        # per-level min-heap of order-indices for nodes currently leaf under it
        self._ready = [[] for _ in range(nlevels)]

        for i, node in enumerate(graph.order):
            self._index[node] = i
            self._by_index[i] = node
        self._next_index = len(graph.order)

        for node in graph.order:
            counts = [0] * nlevels
            for child, priorities in graph.nodes[node][0].items():
                mask = self._compute_mask(priorities)
                self._edge_mask[(node, child)] = mask
                m = mask
                while m:
                    lb = m & -m
                    counts[lb.bit_length() - 1] += 1
                    m ^= lb
            self._surv[node] = counts

        # Seed each level's ready heap with its initial leaves. Appending in
        # order-index order yields a valid min-heap without heapify.
        for node in graph.order:
            counts = self._surv[node]
            idx = self._index[node]
            for L in range(nlevels):
                if counts[L] == 0:
                    self._ready[L].append(idx)

    def _compute_mask(self, priorities):
        """Bitmask of the levels whose filter this edge survives.

        Level 0 (None) is always set: an edge always has at least one priority.
        For level L>0 with filter f, the edge survives iff some priority p has
        ``not f(p)``, as in digraph.leaf_nodes().
        """
        mask = 1
        filters = self._filters
        for L in range(1, self._nlevels):
            f = filters[L]
            for p in priorities:
                if not f(p):
                    mask |= 1 << L
                    break
        return mask

    def level_of(self, ignore_priority):
        """Level index for an ignore_priority filter, or None if untracked."""
        return self._level_of.get(id(ignore_priority))

    def is_leaf(self, node, level):
        counts = self._surv.get(node)
        return counts is not None and counts[level] == 0

    def ready_nodes(self, level):
        """Return the nodes that are leaves under `level`, in mygraph.order.

        Drains the level's heap, discarding stale/duplicate entries, and rebuilds
        it from the survivors. Entries pop in ascending order-index order, so the
        result is in mygraph.order and the rebuilt heap needs no heapify.
        """
        heap = self._ready[level]
        surv = self._surv
        index = self._index
        by_index = self._by_index
        result = []
        seen_idx = set()
        while heap:
            idx = heappop(heap)
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
            node = by_index.get(idx)
            if node is None:
                continue
            counts = surv.get(node)
            # Valid iff still in graph, still leaf here, and this is the node's
            # current index.
            if counts is None or counts[level] != 0 or index.get(node) != idx:
                continue
            result.append(node)
        self._ready[level] = [index[node] for node in result]
        return result

    def remove(self, node):
        """Account for `node` leaving the graph. Must be called while the graph
        still contains `node` and its edges, i.e. before the digraph mutation.
        """
        node_data = self._graph.nodes.get(node)
        if node_data is None:
            return
        children, parents, _ = node_data
        edge_mask = self._edge_mask
        surv = self._surv
        index = self._index
        ready = self._ready
        for parent in parents:
            mask = edge_mask.pop((parent, node), None)
            if mask is None:
                continue
            pcounts = surv.get(parent)
            if pcounts is None:
                continue
            pidx = index.get(parent)
            m = mask
            while m:
                lb = m & -m
                L = lb.bit_length() - 1
                pcounts[L] -= 1
                if pcounts[L] == 0 and pidx is not None:
                    heappush(ready[L], pidx)
                m ^= lb
        for child in children:
            edge_mask.pop((node, child), None)
        surv.pop(node, None)
        # Leave index/by_index in place; ready_nodes filters the stale entries.
        # Re-adding the node assigns it a fresh index.

    def difference_update(self, nodes):
        for node in nodes:
            self.remove(node)

    def _assign_index(self, node):
        """Ensure `node` has an order-index; assign a fresh appended one if it is
        new or being reintroduced after removal."""
        if node not in self._surv:
            idx = self._next_index
            self._next_index += 1
            self._index[node] = idx
            self._by_index[idx] = node
            self._surv[node] = [0] * self._nlevels
            # A reintroduced node starts isolated, so it is a leaf everywhere.
            for L in range(self._nlevels):
                heappush(self._ready[L], idx)

    def add_edge(self, node, parent, priority):
        """Account for digraph.add(node, parent, priority), an edge from graph
        parent `parent` to graph child `node`. Must be called after the digraph
        mutation, so the parent's priorities list is already updated.

        Adding a priority only makes an edge survive more levels, so the parent's
        counts only increase. A parent may leave a level's ready set; that is
        handled lazily on pop.
        """
        self._assign_index(node)
        if not parent:
            return
        self._assign_index(parent)
        priorities = self._graph.nodes[parent][0].get(node)
        if priorities is None:
            return
        new_mask = self._compute_mask(priorities)
        old_mask = self._edge_mask.get((parent, node), 0)
        if new_mask == old_mask:
            return
        self._edge_mask[(parent, node)] = new_mask
        delta = new_mask & ~old_mask
        pcounts = self._surv[parent]
        m = delta
        while m:
            lb = m & -m
            pcounts[lb.bit_length() - 1] += 1
            m ^= lb


class _FrontierDigraph(digraph):
    """digraph that keeps an attached _SerializeFrontier in sync on every
    mutation."""

    frontier = None

    def remove(self, node):
        if self.frontier is not None:
            self.frontier.remove(node)
        super().remove(node)

    def difference_update(self, t):
        if self.frontier is not None:
            if isinstance(t, (list, tuple)) or not hasattr(t, "__contains__"):
                t = frozenset(t)
            self.frontier.difference_update(t)
        super().difference_update(t)

    def add(self, node, parent, priority=0):
        super().add(node, parent, priority=priority)
        if self.frontier is not None:
            self.frontier.add_edge(node, parent, priority)
