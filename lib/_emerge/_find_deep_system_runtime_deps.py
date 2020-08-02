# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
from _emerge.Package import Package

def _find_deep_system_runtime_deps(graph):
	deep_system_deps = set()
	node_stack = []
	for node in graph:
		if not isinstance(node, Package) or \
			node.operation == 'uninstall':
			continue
		if node.root_config.sets['system'].findAtomForPackage(node):
			node_stack.append(node)

	def ignore_priority(priority):
		"""
		Ignore non-runtime priorities.
		"""
		if isinstance(priority, DepPriority) and \
			(priority.runtime or priority.runtime_post):
			return False
		return True

	while node_stack:
		node = node_stack.pop()
		if node in deep_system_deps:
			continue
		deep_system_deps.add(node)
		for child in graph.child_nodes(node, ignore_priority=ignore_priority):
			if not isinstance(child, Package) or \
				child.operation == 'uninstall':
				continue
			node_stack.append(child)

	return deep_system_deps
