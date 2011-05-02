# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import copy

class BacktrackParameter(object):

	__slots__ = (
		"needed_unstable_keywords", "runtime_pkg_mask", "needed_use_config_changes", "needed_license_changes",
		"rebuild_list", "reinstall_list"
	)

	def __init__(self):
		self.needed_unstable_keywords = set()
		self.runtime_pkg_mask = {}
		self.needed_use_config_changes = {}
		self.needed_license_changes = {}
		self.rebuild_list = set()
		self.reinstall_list = set()

	def __deepcopy__(self, memo=None):
		if memo is None:
			memo = {}
		result = BacktrackParameter()
		memo[id(self)] = result

		#Shallow copies are enough here, as we only need to ensure that nobody adds stuff
		#to our sets and dicts. The existing content is immutable.
		result.needed_unstable_keywords = copy.copy(self.needed_unstable_keywords)
		result.runtime_pkg_mask = copy.copy(self.runtime_pkg_mask)
		result.needed_use_config_changes = copy.copy(self.needed_use_config_changes)
		result.needed_license_changes = copy.copy(self.needed_license_changes)
		result.rebuild_list = copy.copy(self.rebuild_list)
		result.reinstall_list = copy.copy(self.reinstall_list)

		return result

	def __eq__(self, other):
		return self.needed_unstable_keywords == other.needed_unstable_keywords and \
			self.runtime_pkg_mask == other.runtime_pkg_mask and \
			self.needed_use_config_changes == other.needed_use_config_changes and \
			self.needed_license_changes == other.needed_license_changes and \
			self.rebuild_list == other.rebuild_list and \
			self.reinstall_list == other.reinstall_list


class _BacktrackNode:

	__slots__ = (
		"parameter", "depth", "mask_steps", "terminal",
	)

	def __init__(self, parameter=BacktrackParameter(), depth=0, mask_steps=0, terminal=True):
		self.parameter = parameter
		self.depth = depth
		self.mask_steps = mask_steps
		self.terminal = terminal

	def __eq__(self, other):
		return self.parameter == other.parameter


class Backtracker(object):

	__slots__ = (
		"_max_depth", "_unexplored_nodes", "_current_node", "_nodes", "_root",
	)

	def __init__(self, max_depth):
		self._max_depth = max_depth
		self._unexplored_nodes = []
		self._current_node = None
		self._nodes = []

		self._root = _BacktrackNode()
		self._add(self._root)


	def _add(self, node, explore=True):
		"""
		Adds a newly computed backtrack parameter. Makes sure that it doesn't already exist and
		that we don't backtrack deeper than we are allowed by --backtrack.
		"""
		if node.mask_steps <= self._max_depth and node not in self._nodes:
			if explore:
				self._unexplored_nodes.append(node)
			self._nodes.append(node)


	def get(self):
		"""
		Returns a backtrack parameter. The backtrack graph is explored with depth first.
		"""
		if self._unexplored_nodes:
			node = self._unexplored_nodes.pop()
			self._current_node = node
			return copy.deepcopy(node.parameter)
		else:
			return None


	def __len__(self):
		return len(self._unexplored_nodes)


	def _feedback_slot_conflict(self, conflict_data):
		for pkg, parent_atoms in conflict_data:
			new_node = copy.deepcopy(self._current_node)
			new_node.depth += 1
			new_node.mask_steps += 1
			new_node.terminal = False
			new_node.parameter.runtime_pkg_mask.setdefault(
				pkg, {})["slot conflict"] = parent_atoms
			self._add(new_node)


	def _feedback_missing_dep(self, dep):
		new_node = copy.deepcopy(self._current_node)
		new_node.depth += 1
		new_node.mask_steps += 1
		new_node.terminal = False

		new_node.parameter.runtime_pkg_mask.setdefault(
			dep.parent, {})["missing dependency"] = \
				set([(dep.parent, dep.root, dep.atom)])

		self._add(new_node)


	def _feedback_config(self, changes, explore=True):
		"""
		Handle config changes. Don't count config changes for the maximum backtrack depth.
		"""
		new_node = copy.deepcopy(self._current_node)
		new_node.depth += 1
		para = new_node.parameter

		for change, data in changes.items():
			if change == "needed_unstable_keywords":
				para.needed_unstable_keywords.update(data)
			elif change == "needed_license_changes":
				for pkg, missing_licenses in data:
					para.needed_license_changes.setdefault(pkg, set()).update(missing_licenses)
			elif change == "needed_use_config_changes":
				for pkg, (new_use, new_changes) in data:
					para.needed_use_config_changes[pkg] = (new_use, new_changes)
			elif change == "rebuild_list":
				para.rebuild_list.update(data)
			elif change == "reinstall_list":
				para.reinstall_list.update(data)

		self._add(new_node, explore=explore)
		self._current_node = new_node


	def feedback(self, infos):
		"""
		Takes information from the depgraph and computes new backtrack parameters to try.
		"""
		assert self._current_node is not None, "call feedback() only after get() was called"

		#Not all config changes require a restart, that's why they can appear together
		#with other conflicts.
		if "config" in infos:
			self._feedback_config(infos["config"], explore=(len(infos)==1))

		#There is at most one of the following types of conflicts for a given restart.
		if "slot conflict" in infos:
			self._feedback_slot_conflict(infos["slot conflict"])
		elif "missing dependency" in infos:
			self._feedback_missing_dep(infos["missing dependency"])


	def backtracked(self):
		"""
		If we didn't backtrack, there is only the root.
		"""
		return len(self._nodes) > 1


	def get_best_run(self):
		"""
		Like, get() but returns the backtrack parameter that has as many config changes as possible,
		but has no masks. This makes --autounmask effective, but prevents confusing error messages
		with "masked by backtracking".
		"""
		best_node = self._root
		for node in self._nodes:
			if node.terminal and node.depth > best_node.depth:
				best_node = node

		return copy.deepcopy(best_node.parameter)
