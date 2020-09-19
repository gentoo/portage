# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import copy

class BacktrackParameter:

	__slots__ = (
		"circular_dependency",
		"needed_unstable_keywords", "runtime_pkg_mask", "needed_use_config_changes", "needed_license_changes",
		"prune_rebuilds", "rebuild_list", "reinstall_list", "needed_p_mask_changes",
		"slot_operator_mask_built", "slot_operator_replace_installed"
	)

	def __init__(self):
		self.circular_dependency = {}
		self.needed_unstable_keywords = set()
		self.needed_p_mask_changes = set()
		self.runtime_pkg_mask = {}
		self.needed_use_config_changes = {}
		self.needed_license_changes = {}
		self.rebuild_list = set()
		self.reinstall_list = set()
		self.slot_operator_replace_installed = set()
		self.slot_operator_mask_built = set()
		self.prune_rebuilds = False

	def __deepcopy__(self, memo=None):
		if memo is None:
			memo = {}
		result = BacktrackParameter()
		memo[id(self)] = result

		#Shallow copies are enough here, as we only need to ensure that nobody adds stuff
		#to our sets and dicts. The existing content is immutable.
		result.circular_dependency = copy.copy(self.circular_dependency)
		result.needed_unstable_keywords = copy.copy(self.needed_unstable_keywords)
		result.needed_p_mask_changes = copy.copy(self.needed_p_mask_changes)
		result.needed_use_config_changes = copy.copy(self.needed_use_config_changes)
		result.needed_license_changes = copy.copy(self.needed_license_changes)
		result.rebuild_list = copy.copy(self.rebuild_list)
		result.reinstall_list = copy.copy(self.reinstall_list)
		result.slot_operator_replace_installed = copy.copy(self.slot_operator_replace_installed)
		result.slot_operator_mask_built = self.slot_operator_mask_built.copy()
		result.prune_rebuilds = self.prune_rebuilds

		# runtime_pkg_mask contains nested dicts that must also be copied
		result.runtime_pkg_mask = {}
		for k, v in self.runtime_pkg_mask.items():
			result.runtime_pkg_mask[k] = copy.copy(v)

		return result

	def __eq__(self, other):
		return self.circular_dependency == other.circular_dependency and \
			self.needed_unstable_keywords == other.needed_unstable_keywords and \
			self.needed_p_mask_changes == other.needed_p_mask_changes and \
			self.runtime_pkg_mask == other.runtime_pkg_mask and \
			self.needed_use_config_changes == other.needed_use_config_changes and \
			self.needed_license_changes == other.needed_license_changes and \
			self.rebuild_list == other.rebuild_list and \
			self.reinstall_list == other.reinstall_list and \
			self.slot_operator_replace_installed == other.slot_operator_replace_installed and \
			self.slot_operator_mask_built == other.slot_operator_mask_built and \
			self.prune_rebuilds == other.prune_rebuilds


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


class Backtracker:

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
		if not self._check_runtime_pkg_mask(node.parameter.runtime_pkg_mask):
			return

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
		return None


	def __len__(self):
		return len(self._unexplored_nodes)

	def _check_runtime_pkg_mask(self, runtime_pkg_mask):
		"""
		If a package gets masked that caused other packages to be masked
		before, we revert the mask for other packages (bug 375573).
		"""

		for pkg, mask_info in runtime_pkg_mask.items():

			if "missing dependency" in mask_info or \
				"slot_operator_mask_built" in mask_info:
				continue

			entry_is_valid = False
			any_conflict_parents = False

			for ppkg, patom in runtime_pkg_mask[pkg].get("slot conflict", set()):
				any_conflict_parents = True
				if ppkg not in runtime_pkg_mask:
					entry_is_valid = True
					break
			else:
				if not any_conflict_parents:
					# Even though pkg was involved in a slot conflict
					# where it was matched by all involved parent atoms,
					# consider masking it in order to avoid a missed
					# update as in bug 692746.
					entry_is_valid = True

			if not entry_is_valid:
				return False

		return True

	def _feedback_slot_conflicts(self, conflicts_data):
		# Only create BacktrackNode instances for the first
		# conflict which occurred, since the conflicts that
		# occurred later may have been caused by the first
		# conflict.
		self._feedback_slot_conflict(conflicts_data[0])

	def _feedback_slot_conflict(self, conflict_data):
		for similar_pkgs in conflict_data:
			new_node = copy.deepcopy(self._current_node)
			new_node.depth += 1
			new_node.mask_steps += 1
			new_node.terminal = False
			for pkg, parent_atoms in similar_pkgs:
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
			if change == "circular_dependency":
				for pkg, circular_children in data.items():
					para.circular_dependency.setdefault(pkg, set()).update(circular_children)
			elif change == "needed_unstable_keywords":
				para.needed_unstable_keywords.update(data)
			elif change == "needed_p_mask_changes":
				para.needed_p_mask_changes.update(data)
			elif change == "needed_license_changes":
				for pkg, missing_licenses in data:
					para.needed_license_changes.setdefault(pkg, set()).update(missing_licenses)
			elif change == "needed_use_config_changes":
				for pkg, (new_use, new_changes) in data:
					para.needed_use_config_changes[pkg] = (new_use, new_changes)
			elif change == "slot_conflict_abi":
				new_node.terminal = False
			elif change == "slot_operator_mask_built":
				para.slot_operator_mask_built.update(data)
				for pkg, mask_reasons in data.items():
					para.runtime_pkg_mask.setdefault(pkg,
						{}).update(mask_reasons)
			elif change == "slot_operator_replace_installed":
				para.slot_operator_replace_installed.update(data)
			elif change == "rebuild_list":
				para.rebuild_list.update(data)
			elif change == "reinstall_list":
				para.reinstall_list.update(data)
			elif change == "prune_rebuilds":
				para.prune_rebuilds = True
				para.slot_operator_replace_installed.clear()
				for pkg in para.slot_operator_mask_built:
					runtime_masks = para.runtime_pkg_mask.get(pkg)
					if runtime_masks is None:
						continue
					runtime_masks.pop("slot_operator_mask_built", None)
					if not runtime_masks:
						para.runtime_pkg_mask.pop(pkg)
				para.slot_operator_mask_built.clear()

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
			self._feedback_slot_conflicts(infos["slot conflict"])
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
