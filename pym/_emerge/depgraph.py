# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import gc
import logging
import re
import sys
import textwrap
from itertools import chain

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_PACKAGE_ATOM
from portage.dbapi import dbapi
from portage.dep import Atom, extract_affecting_use, check_required_use, human_readable_required_use, _repo_separator
from portage.eapi import eapi_has_strong_blocks, eapi_has_required_use
from portage.exception import InvalidAtom
from portage.output import colorize, create_color_func, \
	darkgreen, green
bad = create_color_func("BAD")
from portage.package.ebuild.getmaskingstatus import \
	_getmaskingstatus, _MaskReason
from portage._sets import SETPREFIX
from portage._sets.base import InternalPackageSet
from portage.util import cmp_sort_key, writemsg, writemsg_stdout
from portage.util import writemsg_level
from portage.util.digraph import digraph

from _emerge.AtomArg import AtomArg
from _emerge.Blocker import Blocker
from _emerge.BlockerCache import BlockerCache
from _emerge.BlockerDepPriority import BlockerDepPriority
from _emerge.countdown import countdown
from _emerge.create_world_atom import create_world_atom
from _emerge.Dependency import Dependency
from _emerge.DependencyArg import DependencyArg
from _emerge.DepPriority import DepPriority
from _emerge.DepPriorityNormalRange import DepPriorityNormalRange
from _emerge.DepPrioritySatisfiedRange import DepPrioritySatisfiedRange
from _emerge.FakeVartree import FakeVartree
from _emerge._find_deep_system_runtime_deps import _find_deep_system_runtime_deps
from _emerge.is_valid_package_atom import is_valid_package_atom
from _emerge.Package import Package
from _emerge.PackageArg import PackageArg
from _emerge.PackageVirtualDbapi import PackageVirtualDbapi
from _emerge.RootConfig import RootConfig
from _emerge.search import search
from _emerge.SetArg import SetArg
from _emerge.show_invalid_depstring_notice import show_invalid_depstring_notice
from _emerge.UnmergeDepPriority import UnmergeDepPriority

from _emerge.resolver.backtracking import Backtracker, BacktrackParameter
from _emerge.resolver.slot_collision import slot_conflict_handler
from _emerge.resolver.circular_dependency import circular_dependency_handler
from _emerge.resolver.output import Display

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int

class _scheduler_graph_config(object):
	def __init__(self, trees, pkg_cache, graph, mergelist):
		self.trees = trees
		self.pkg_cache = pkg_cache
		self.graph = graph
		self.mergelist = mergelist

class _frozen_depgraph_config(object):

	def __init__(self, settings, trees, myopts, spinner):
		self.settings = settings
		self.target_root = settings["ROOT"]
		self.myopts = myopts
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.spinner = spinner
		self._running_root = trees["/"]["root_config"]
		self._opts_no_restart = frozenset(["--buildpkgonly",
			"--fetchonly", "--fetch-all-uri", "--pretend"])
		self.pkgsettings = {}
		self.trees = {}
		self._trees_orig = trees
		self.roots = {}
		# All Package instances
		self._pkg_cache = {}
		self._highest_license_masked = {}
		for myroot in trees:
			self.trees[myroot] = {}
			# Create a RootConfig instance that references
			# the FakeVartree instead of the real one.
			self.roots[myroot] = RootConfig(
				trees[myroot]["vartree"].settings,
				self.trees[myroot],
				trees[myroot]["root_config"].setconfig)
			for tree in ("porttree", "bintree"):
				self.trees[myroot][tree] = trees[myroot][tree]
			self.trees[myroot]["vartree"] = \
				FakeVartree(trees[myroot]["root_config"],
					pkg_cache=self._pkg_cache,
					pkg_root_config=self.roots[myroot])
			self.pkgsettings[myroot] = portage.config(
				clone=self.trees[myroot]["vartree"].settings)

		self._required_set_names = set(["world"])

		self.excluded_pkgs = InternalPackageSet(allow_wildcard=True)
		for x in ' '.join(myopts.get("--exclude", [])).split():
			try:
				x = Atom(x, allow_wildcard=True)
			except portage.exception.InvalidAtom:
				x = Atom("*/" + x, allow_wildcard=True)
			self.excluded_pkgs.add(x)

class _depgraph_sets(object):
	def __init__(self):
		# contains all sets added to the graph
		self.sets = {}
		# contains non-set atoms given as arguments
		self.sets['__non_set_args__'] = InternalPackageSet(allow_repo=True)
		# contains all atoms from all sets added to the graph, including
		# atoms given as arguments
		self.atoms = InternalPackageSet(allow_repo=True)
		self.atom_arg_map = {}

class _dynamic_depgraph_config(object):

	def __init__(self, depgraph, myparams, allow_backtracking, backtrack_parameters):
		self.myparams = myparams.copy()
		self._vdb_loaded = False
		self._allow_backtracking = allow_backtracking
		# Maps slot atom to package for each Package added to the graph.
		self._slot_pkg_map = {}
		# Maps nodes to the reasons they were selected for reinstallation.
		self._reinstall_nodes = {}
		self.mydbapi = {}
		# Contains a filtered view of preferred packages that are selected
		# from available repositories.
		self._filtered_trees = {}
		# Contains installed packages and new packages that have been added
		# to the graph.
		self._graph_trees = {}
		# Caches visible packages returned from _select_package, for use in
		# depgraph._iter_atoms_for_pkg() SLOT logic.
		self._visible_pkgs = {}
		#contains the args created by select_files
		self._initial_arg_list = []
		self.digraph = portage.digraph()
		# manages sets added to the graph
		self.sets = {}
		# contains all nodes pulled in by self.sets
		self._set_nodes = set()
		# Contains only Blocker -> Uninstall edges
		self._blocker_uninstalls = digraph()
		# Contains only Package -> Blocker edges
		self._blocker_parents = digraph()
		# Contains only irrelevant Package -> Blocker edges
		self._irrelevant_blockers = digraph()
		# Contains only unsolvable Package -> Blocker edges
		self._unsolvable_blockers = digraph()
		# Contains all Blocker -> Blocked Package edges
		self._blocked_pkgs = digraph()
		# Contains world packages that have been protected from
		# uninstallation but may not have been added to the graph
		# if the graph is not complete yet.
		self._blocked_world_pkgs = {}
		# Contains packages whose dependencies have been traversed.
		# This use used to check if we have accounted for blockers
		# relevant to a package.
		self._traversed_pkg_deps = set()
		self._slot_collision_info = {}
		# Slot collision nodes are not allowed to block other packages since
		# blocker validation is only able to account for one package per slot.
		self._slot_collision_nodes = set()
		self._parent_atoms = {}
		self._slot_conflict_parent_atoms = set()
		self._slot_conflict_handler = None
		self._circular_dependency_handler = None
		self._serialized_tasks_cache = None
		self._scheduler_graph = None
		self._displayed_list = None
		self._pprovided_args = []
		self._missing_args = []
		self._masked_installed = set()
		self._masked_license_updates = set()
		self._unsatisfied_deps_for_display = []
		self._unsatisfied_blockers_for_display = None
		self._circular_deps_for_display = None
		self._dep_stack = []
		self._dep_disjunctive_stack = []
		self._unsatisfied_deps = []
		self._initially_unsatisfied_deps = []
		self._ignored_deps = []
		self._highest_pkg_cache = {}

		self._needed_unstable_keywords = backtrack_parameters.needed_unstable_keywords
		self._needed_license_changes = backtrack_parameters.needed_license_changes
		self._needed_use_config_changes = backtrack_parameters.needed_use_config_changes
		self._runtime_pkg_mask = backtrack_parameters.runtime_pkg_mask
		self._need_restart = False
		self._backtrack_infos = {}

		self._autounmask = depgraph._frozen_config.myopts.get('--autounmask', 'n') == True
		self._success_without_autounmask = False

		for myroot in depgraph._frozen_config.trees:
			self.sets[myroot] = _depgraph_sets()
			self._slot_pkg_map[myroot] = {}
			vardb = depgraph._frozen_config.trees[myroot]["vartree"].dbapi
			# This dbapi instance will model the state that the vdb will
			# have after new packages have been installed.
			fakedb = PackageVirtualDbapi(vardb.settings)

			self.mydbapi[myroot] = fakedb
			def graph_tree():
				pass
			graph_tree.dbapi = fakedb
			self._graph_trees[myroot] = {}
			self._filtered_trees[myroot] = {}
			# Substitute the graph tree for the vartree in dep_check() since we
			# want atom selections to be consistent with package selections
			# have already been made.
			self._graph_trees[myroot]["porttree"]   = graph_tree
			self._graph_trees[myroot]["vartree"]    = graph_tree
			def filtered_tree():
				pass
			filtered_tree.dbapi = _dep_check_composite_db(depgraph, myroot)
			self._filtered_trees[myroot]["porttree"] = filtered_tree
			self._visible_pkgs[myroot] = PackageVirtualDbapi(vardb.settings)

			# Passing in graph_tree as the vartree here could lead to better
			# atom selections in some cases by causing atoms for packages that
			# have been added to the graph to be preferred over other choices.
			# However, it can trigger atom selections that result in
			# unresolvable direct circular dependencies. For example, this
			# happens with gwydion-dylan which depends on either itself or
			# gwydion-dylan-bin. In case gwydion-dylan is not yet installed,
			# gwydion-dylan-bin needs to be selected in order to avoid a
			# an unresolvable direct circular dependency.
			#
			# To solve the problem described above, pass in "graph_db" so that
			# packages that have been added to the graph are distinguishable
			# from other available packages and installed packages. Also, pass
			# the parent package into self._select_atoms() calls so that
			# unresolvable direct circular dependencies can be detected and
			# avoided when possible.
			self._filtered_trees[myroot]["graph_db"] = graph_tree.dbapi
			self._filtered_trees[myroot]["vartree"] = \
				depgraph._frozen_config.trees[myroot]["vartree"]

			dbs = []
			#               (db, pkg_type, built, installed, db_keys)
			if "remove" in self.myparams:
				# For removal operations, use _dep_check_composite_db
				# for availability and visibility checks. This provides
				# consistency with install operations, so we don't
				# get install/uninstall cycles like in bug #332719.
				self._graph_trees[myroot]["porttree"] = filtered_tree
			else:
				if "--usepkgonly" not in depgraph._frozen_config.myopts:
					portdb = depgraph._frozen_config.trees[myroot]["porttree"].dbapi
					db_keys = list(portdb._aux_cache_keys)
					dbs.append((portdb, "ebuild", False, False, db_keys))

				if "--usepkg" in depgraph._frozen_config.myopts:
					bindb  = depgraph._frozen_config.trees[myroot]["bintree"].dbapi
					db_keys = list(bindb._aux_cache_keys)
					dbs.append((bindb,  "binary", True, False, db_keys))

			vardb  = depgraph._frozen_config.trees[myroot]["vartree"].dbapi
			db_keys = list(depgraph._frozen_config._trees_orig[myroot
				]["vartree"].dbapi._aux_cache_keys)
			dbs.append((vardb, "installed", True, True, db_keys))
			self._filtered_trees[myroot]["dbs"] = dbs

class depgraph(object):

	pkg_tree_map = RootConfig.pkg_tree_map

	_dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	
	def __init__(self, settings, trees, myopts, myparams, spinner,
		frozen_config=None, backtrack_parameters=BacktrackParameter(), allow_backtracking=False):
		if frozen_config is None:
			frozen_config = _frozen_depgraph_config(settings, trees,
			myopts, spinner)
		self._frozen_config = frozen_config
		self._dynamic_config = _dynamic_depgraph_config(self, myparams,
			allow_backtracking, backtrack_parameters)

		self._select_atoms = self._select_atoms_highest_available
		self._select_package = self._select_pkg_highest_available

	def _load_vdb(self):
		"""
		Load installed package metadata if appropriate. This used to be called
		from the constructor, but that wasn't very nice since this procedure
		is slow and it generates spinner output. So, now it's called on-demand
		by various methods when necessary.
		"""

		if self._dynamic_config._vdb_loaded:
			return

		for myroot in self._frozen_config.trees:

			preload_installed_pkgs = \
				"--nodeps" not in self._frozen_config.myopts

			fake_vartree = self._frozen_config.trees[myroot]["vartree"]
			if not fake_vartree.dbapi:
				# This needs to be called for the first depgraph, but not for
				# backtracking depgraphs that share the same frozen_config.
				fake_vartree.sync()

				# FakeVartree.sync() populates virtuals, and we want
				# self.pkgsettings to have them populated too.
				self._frozen_config.pkgsettings[myroot] = \
					portage.config(clone=fake_vartree.settings)

			if preload_installed_pkgs:
				vardb = fake_vartree.dbapi
				fakedb = self._dynamic_config._graph_trees[
					myroot]["vartree"].dbapi

				for pkg in vardb:
					self._spinner_update()
					# This triggers metadata updates via FakeVartree.
					vardb.aux_get(pkg.cpv, [])
					fakedb.cpv_inject(pkg)

				# Now that the vardb state is cached in our FakeVartree,
				# we won't be needing the real vartree cache for awhile.
				# To make some room on the heap, clear the vardbapi
				# caches.
				self._frozen_config._trees_orig[myroot
					]["vartree"].dbapi._clear_cache()
				gc.collect()

		self._dynamic_config._vdb_loaded = True

	def _spinner_update(self):
		if self._frozen_config.spinner:
			self._frozen_config.spinner.update()

	def _show_missed_update(self):

		if '--quiet' in self._frozen_config.myopts and \
			'--debug' not in self._frozen_config.myopts:
			return

		# In order to minimize noise, show only the highest
		# missed update from each SLOT.
		missed_updates = {}
		for pkg, mask_reasons in \
			self._dynamic_config._runtime_pkg_mask.items():
			if pkg.installed:
				# Exclude installed here since we only
				# want to show available updates.
				continue
			k = (pkg.root, pkg.slot_atom)
			if k in missed_updates:
				other_pkg, mask_type, parent_atoms = missed_updates[k]
				if other_pkg > pkg:
					continue
			for mask_type, parent_atoms in mask_reasons.items():
				if not parent_atoms:
					continue
				missed_updates[k] = (pkg, mask_type, parent_atoms)
				break

		if not missed_updates:
			return

		missed_update_types = {}
		for pkg, mask_type, parent_atoms in missed_updates.values():
			missed_update_types.setdefault(mask_type,
				[]).append((pkg, parent_atoms))

		self._show_missed_update_slot_conflicts(
			missed_update_types.get("slot conflict"))

		self._show_missed_update_unsatisfied_dep(
			missed_update_types.get("missing dependency"))

	def _show_missed_update_unsatisfied_dep(self, missed_updates):

		if not missed_updates:
			return

		backtrack_masked = []

		for pkg, parent_atoms in missed_updates:

			try:
				for parent, root, atom in parent_atoms:
					self._show_unsatisfied_dep(root, atom, myparent=parent,
						check_backtrack=True)
			except self._backtrack_mask:
				# This is displayed below in abbreviated form.
				backtrack_masked.append((pkg, parent_atoms))
				continue

			writemsg("\n!!! The following update has been skipped " + \
				"due to unsatisfied dependencies:\n\n", noiselevel=-1)

			writemsg(str(pkg.slot_atom), noiselevel=-1)
			if pkg.root != '/':
				writemsg(" for %s" % (pkg.root,), noiselevel=-1)
			writemsg("\n", noiselevel=-1)

			for parent, root, atom in parent_atoms:
				self._show_unsatisfied_dep(root, atom, myparent=parent)
				writemsg("\n", noiselevel=-1)

		if backtrack_masked:
			# These are shown in abbreviated form, in order to avoid terminal
			# flooding from mask messages as reported in bug #285832.
			writemsg("\n!!! The following update(s) have been skipped " + \
				"due to unsatisfied dependencies\n" + \
				"!!! triggered by backtracking:\n\n", noiselevel=-1)
			for pkg, parent_atoms in backtrack_masked:
				writemsg(str(pkg.slot_atom), noiselevel=-1)
				if pkg.root != '/':
					writemsg(" for %s" % (pkg.root,), noiselevel=-1)
				writemsg("\n", noiselevel=-1)

	def _show_missed_update_slot_conflicts(self, missed_updates):

		if not missed_updates:
			return

		msg = []
		msg.append("\n!!! One or more updates have been skipped due to " + \
			"a dependency conflict:\n\n")

		indent = "  "
		for pkg, parent_atoms in missed_updates:
			msg.append(str(pkg.slot_atom))
			if pkg.root != '/':
				msg.append(" for %s" % (pkg.root,))
			msg.append("\n\n")

			for parent, atom in parent_atoms:
				msg.append(indent)
				msg.append(str(pkg))

				msg.append(" conflicts with\n")
				msg.append(2*indent)
				if isinstance(parent,
					(PackageArg, AtomArg)):
					# For PackageArg and AtomArg types, it's
					# redundant to display the atom attribute.
					msg.append(str(parent))
				else:
					# Display the specific atom from SetArg or
					# Package types.
					msg.append("%s required by %s" % (atom, parent))
				msg.append("\n")
			msg.append("\n")

		writemsg("".join(msg), noiselevel=-1)

	def _show_slot_collision_notice(self):
		"""Show an informational message advising the user to mask one of the
		the packages. In some cases it may be possible to resolve this
		automatically, but support for backtracking (removal nodes that have
		already been selected) will be required in order to handle all possible
		cases.
		"""

		if not self._dynamic_config._slot_collision_info:
			return

		self._show_merge_list()

		self._dynamic_config._slot_conflict_handler = slot_conflict_handler(self)
		handler = self._dynamic_config._slot_conflict_handler

		conflict = handler.get_conflict()
		writemsg(conflict, noiselevel=-1)
		
		explanation = handler.get_explanation()
		if explanation:
			writemsg(explanation, noiselevel=-1)
			return

		if "--quiet" in self._frozen_config.myopts:
			return

		msg = []
		msg.append("It may be possible to solve this problem ")
		msg.append("by using package.mask to prevent one of ")
		msg.append("those packages from being selected. ")
		msg.append("However, it is also possible that conflicting ")
		msg.append("dependencies exist such that they are impossible to ")
		msg.append("satisfy simultaneously.  If such a conflict exists in ")
		msg.append("the dependencies of two different packages, then those ")
		msg.append("packages can not be installed simultaneously.")
		backtrack_opt = self._frozen_config.myopts.get('--backtrack')
		if not self._dynamic_config._allow_backtracking and \
			(backtrack_opt is None or \
			(backtrack_opt > 0 and backtrack_opt < 30)):
			msg.append(" You may want to try a larger value of the ")
			msg.append("--backtrack option, such as --backtrack=30, ")
			msg.append("in order to see if that will solve this conflict ")
			msg.append("automatically.")

		for line in textwrap.wrap(''.join(msg), 70):
			writemsg(line + '\n', noiselevel=-1)
		writemsg('\n', noiselevel=-1)

		msg = []
		msg.append("For more information, see MASKED PACKAGES ")
		msg.append("section in the emerge man page or refer ")
		msg.append("to the Gentoo Handbook.")
		for line in textwrap.wrap(''.join(msg), 70):
			writemsg(line + '\n', noiselevel=-1)
		writemsg('\n', noiselevel=-1)

	def _process_slot_conflicts(self):
		"""
		Process slot conflict data to identify specific atoms which
		lead to conflict. These atoms only match a subset of the
		packages that have been pulled into a given slot.
		"""
		for (slot_atom, root), slot_nodes \
			in self._dynamic_config._slot_collision_info.items():

			all_parent_atoms = set()
			for pkg in slot_nodes:
				parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
				if not parent_atoms:
					continue
				all_parent_atoms.update(parent_atoms)

			for pkg in slot_nodes:
				parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
				if parent_atoms is None:
					parent_atoms = set()
					self._dynamic_config._parent_atoms[pkg] = parent_atoms
				for parent_atom in all_parent_atoms:
					if parent_atom in parent_atoms:
						continue
					# Use package set for matching since it will match via
					# PROVIDE when necessary, while match_from_list does not.
					parent, atom = parent_atom
					atom_set = InternalPackageSet(
						initial_atoms=(atom,), allow_repo=True)
					if atom_set.findAtomForPackage(pkg, modified_use=self._pkg_use_enabled(pkg)):
						parent_atoms.add(parent_atom)
					else:
						self._dynamic_config._slot_conflict_parent_atoms.add(parent_atom)

	def _reinstall_for_flags(self, forced_flags,
		orig_use, orig_iuse, cur_use, cur_iuse):
		"""Return a set of flags that trigger reinstallation, or None if there
		are no such flags."""
		if "--newuse" in self._frozen_config.myopts or \
			"--binpkg-respect-use" in self._frozen_config.myopts:
			flags = set(orig_iuse.symmetric_difference(
				cur_iuse).difference(forced_flags))
			flags.update(orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use)))
			if flags:
				return flags
		elif "changed-use" == self._frozen_config.myopts.get("--reinstall"):
			flags = orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use))
			if flags:
				return flags
		return None

	def _create_graph(self, allow_unsatisfied=False):
		dep_stack = self._dynamic_config._dep_stack
		dep_disjunctive_stack = self._dynamic_config._dep_disjunctive_stack
		while dep_stack or dep_disjunctive_stack:
			self._spinner_update()
			while dep_stack:
				dep = dep_stack.pop()
				if isinstance(dep, Package):
					if not self._add_pkg_deps(dep,
						allow_unsatisfied=allow_unsatisfied):
						return 0
					continue
				if not self._add_dep(dep, allow_unsatisfied=allow_unsatisfied):
					return 0
			if dep_disjunctive_stack:
				if not self._pop_disjunction(allow_unsatisfied):
					return 0
		return 1

	def _expand_set_args(self, input_args, add_to_digraph=False):
		"""
		Iterate over a list of DependencyArg instances and yield all
		instances given in the input together with additional SetArg
		instances that are generated from nested sets.
		@param input_args: An iterable of DependencyArg instances
		@type input_args: Iterable
		@param add_to_digraph: If True then add SetArg instances
			to the digraph, in order to record parent -> child
			relationships from nested sets
		@type add_to_digraph: Boolean
		@rtype: Iterable
		@returns: All args given in the input together with additional
			SetArg instances that are generated from nested sets
		"""

		traversed_set_args = set()

		for arg in input_args:
			if not isinstance(arg, SetArg):
				yield arg
				continue

			root_config = arg.root_config
			depgraph_sets = self._dynamic_config.sets[root_config.root]
			arg_stack = [arg]
			while arg_stack:
				arg = arg_stack.pop()
				if arg in traversed_set_args:
					continue
				traversed_set_args.add(arg)
				yield arg

				# Traverse nested sets and add them to the stack
				# if they're not already in the graph. Also, graph
				# edges between parent and nested sets.
				for token in arg.pset.getNonAtoms():
					if not token.startswith(SETPREFIX):
						continue
					s = token[len(SETPREFIX):]
					nested_set = depgraph_sets.sets.get(s)
					if nested_set is None:
						nested_set = root_config.sets.get(s)
					if nested_set is not None:
						nested_arg = SetArg(arg=token, pset=nested_set,
							root_config=root_config)
						arg_stack.append(nested_arg)
						if add_to_digraph:
							self._dynamic_config.digraph.add(nested_arg, arg,
								priority=BlockerDepPriority.instance)
							depgraph_sets.sets[nested_arg.name] = nested_arg.pset

	def _add_dep(self, dep, allow_unsatisfied=False):
		debug = "--debug" in self._frozen_config.myopts
		buildpkgonly = "--buildpkgonly" in self._frozen_config.myopts
		nodeps = "--nodeps" in self._frozen_config.myopts
		empty = "empty" in self._dynamic_config.myparams
		deep = self._dynamic_config.myparams.get("deep", 0)
		recurse = empty or deep is True or dep.depth <= deep
		if dep.blocker:
			if not buildpkgonly and \
				not nodeps and \
				dep.parent not in self._dynamic_config._slot_collision_nodes:
				if dep.parent.onlydeps:
					# It's safe to ignore blockers if the
					# parent is an --onlydeps node.
					return 1
				# The blocker applies to the root where
				# the parent is or will be installed.
				blocker = Blocker(atom=dep.atom,
					eapi=dep.parent.metadata["EAPI"],
					priority=dep.priority, root=dep.parent.root)
				self._dynamic_config._blocker_parents.add(blocker, dep.parent)
			return 1

		if dep.child is None:
			dep_pkg, existing_node = self._select_package(dep.root, dep.atom,
				onlydeps=dep.onlydeps)
		else:
			# The caller has selected a specific package
			# via self._minimize_packages().
			dep_pkg = dep.child
			existing_node = self._dynamic_config._slot_pkg_map[
				dep.root].get(dep_pkg.slot_atom)
			if existing_node is not dep_pkg:
				existing_node = None 

		if not dep_pkg:
			if dep.priority.optional:
				# This could be an unnecessary build-time dep
				# pulled in by --with-bdeps=y.
				return 1
			if allow_unsatisfied:
				self._dynamic_config._unsatisfied_deps.append(dep)
				return 1
			self._dynamic_config._unsatisfied_deps_for_display.append(
				((dep.root, dep.atom), {"myparent":dep.parent}))

			# The parent node should not already be in
			# runtime_pkg_mask, since that would trigger an
			# infinite backtracking loop.
			if self._dynamic_config._allow_backtracking:
				if dep.parent in self._dynamic_config._runtime_pkg_mask:
					if "--debug" in self._frozen_config.myopts:
						writemsg(
							"!!! backtracking loop detected: %s %s\n" % \
							(dep.parent,
							self._dynamic_config._runtime_pkg_mask[
							dep.parent]), noiselevel=-1)
				elif not self.need_restart():
					# Do not backtrack if only USE have to be changed in
					# order to satisfy the dependency.
					dep_pkg, existing_node = \
						self._select_package(dep.root, dep.atom.without_use,
							onlydeps=dep.onlydeps)
					if dep_pkg is None:
						self._dynamic_config._backtrack_infos["missing dependency"] = dep
						self._dynamic_config._need_restart = True
						if "--debug" in self._frozen_config.myopts:
							msg = []
							msg.append("")
							msg.append("")
							msg.append("backtracking due to unsatisfied dep:")
							msg.append("    parent: %s" % dep.parent)
							msg.append("  priority: %s" % dep.priority)
							msg.append("      root: %s" % dep.root)
							msg.append("      atom: %s" % dep.atom)
							msg.append("")
							writemsg_level("".join("%s\n" % l for l in msg),
								noiselevel=-1, level=logging.DEBUG)

			return 0
		# In some cases, dep_check will return deps that shouldn't
		# be proccessed any further, so they are identified and
		# discarded here. Try to discard as few as possible since
		# discarded dependencies reduce the amount of information
		# available for optimization of merge order.
		if dep.priority.satisfied and \
			dep.priority.satisfied.visible and \
			not dep_pkg.installed and \
			not (existing_node or recurse):
			myarg = None
			if dep.root == self._frozen_config.target_root:
				try:
					myarg = next(self._iter_atoms_for_pkg(dep_pkg))
				except StopIteration:
					pass
				except portage.exception.InvalidDependString:
					if not dep_pkg.installed:
						# This shouldn't happen since the package
						# should have been masked.
						raise
			if not myarg:
				# Existing child selection may not be valid unless
				# it's added to the graph immediately, since "complete"
				# mode may select a different child later.
				dep.child = None
				self._dynamic_config._ignored_deps.append(dep)
				return 1

		if not self._add_pkg(dep_pkg, dep):
			return 0
		return 1

	def _check_slot_conflict(self, pkg, atom):
		existing_node = self._dynamic_config._slot_pkg_map[pkg.root].get(pkg.slot_atom)
		matches = None
		if existing_node:
			matches = pkg.cpv == existing_node.cpv
			if pkg != existing_node and \
				atom is not None:
				# Use package set for matching since it will match via
				# PROVIDE when necessary, while match_from_list does not.
				matches = bool(InternalPackageSet(initial_atoms=(atom,),
					allow_repo=True).findAtomForPackage(existing_node,
					modified_use=self._pkg_use_enabled(existing_node)))

		return (existing_node, matches)

	def _add_pkg(self, pkg, dep):
		myparent = None
		priority = None
		depth = 0
		if dep is None:
			dep = Dependency()
		else:
			myparent = dep.parent
			priority = dep.priority
			depth = dep.depth
		if priority is None:
			priority = DepPriority()
		"""
		Fills the digraph with nodes comprised of packages to merge.
		mybigkey is the package spec of the package to merge.
		myparent is the package depending on mybigkey ( or None )
		addme = Should we add this package to the digraph or are we just looking at it's deps?
			Think --onlydeps, we need to ignore packages in that case.
		#stuff to add:
		#SLOT-aware emerge
		#IUSE-aware emerge -> USE DEP aware depgraph
		#"no downgrade" emerge
		"""
		# Ensure that the dependencies of the same package
		# are never processed more than once.
		previously_added = pkg in self._dynamic_config.digraph

		# select the correct /var database that we'll be checking against
		vardbapi = self._frozen_config.trees[pkg.root]["vartree"].dbapi
		pkgsettings = self._frozen_config.pkgsettings[pkg.root]

		arg_atoms = None
		if True:
			try:
				arg_atoms = list(self._iter_atoms_for_pkg(pkg))
			except portage.exception.InvalidDependString as e:
				if not pkg.installed:
					# should have been masked before it was selected
					raise
				del e

		if not pkg.onlydeps:
			if not pkg.installed and \
				"empty" not in self._dynamic_config.myparams and \
				vardbapi.match(pkg.slot_atom):
				# Increase the priority of dependencies on packages that
				# are being rebuilt. This optimizes merge order so that
				# dependencies are rebuilt/updated as soon as possible,
				# which is needed especially when emerge is called by
				# revdep-rebuild since dependencies may be affected by ABI
				# breakage that has rendered them useless. Don't adjust
				# priority here when in "empty" mode since all packages
				# are being merged in that case.
				priority.rebuild = True

			existing_node, existing_node_matches = \
				self._check_slot_conflict(pkg, dep.atom)
			slot_collision = False
			if existing_node:
				if existing_node_matches:
					# The existing node can be reused.
					if arg_atoms:
						for parent_atom in arg_atoms:
							parent, atom = parent_atom
							self._dynamic_config.digraph.add(existing_node, parent,
								priority=priority)
							self._add_parent_atom(existing_node, parent_atom)
					# If a direct circular dependency is not an unsatisfied
					# buildtime dependency then drop it here since otherwise
					# it can skew the merge order calculation in an unwanted
					# way.
					if existing_node != myparent or \
						(priority.buildtime and not priority.satisfied):
						self._dynamic_config.digraph.addnode(existing_node, myparent,
							priority=priority)
						if dep.atom is not None and dep.parent is not None:
							self._add_parent_atom(existing_node,
								(dep.parent, dep.atom))
					return 1
				else:
					# A slot conflict has occurred. 
					# The existing node should not already be in
					# runtime_pkg_mask, since that would trigger an
					# infinite backtracking loop.
					if self._dynamic_config._allow_backtracking and \
						existing_node in \
						self._dynamic_config._runtime_pkg_mask:
						if "--debug" in self._frozen_config.myopts:
							writemsg(
								"!!! backtracking loop detected: %s %s\n" % \
								(existing_node,
								self._dynamic_config._runtime_pkg_mask[
								existing_node]), noiselevel=-1)
					elif self._dynamic_config._allow_backtracking and \
						not self._accept_blocker_conflicts() and \
						not self.need_restart():

						self._add_slot_conflict(pkg)
						if dep.atom is not None and dep.parent is not None:
							self._add_parent_atom(pkg, (dep.parent, dep.atom))

						if arg_atoms:
							for parent_atom in arg_atoms:
								parent, atom = parent_atom
								self._add_parent_atom(pkg, parent_atom)
						self._process_slot_conflicts()

						backtrack_data = []
						fallback_data = []
						all_parents = set()
						# The ordering of backtrack_data can make
						# a difference here, because both mask actions may lead
						# to valid, but different, solutions and the one with
						# 'existing_node' masked is usually the better one. Because
						# of that, we choose an order such that
						# the backtracker will first explore the choice with
						# existing_node masked. The backtracker reverses the
						# order, so the order it uses is the reverse of the
						# order shown here. See bug #339606.
						for to_be_selected, to_be_masked in (existing_node, pkg), (pkg, existing_node):
							# For missed update messages, find out which
							# atoms matched to_be_selected that did not
							# match to_be_masked.
							parent_atoms = \
								self._dynamic_config._parent_atoms.get(to_be_selected, set())
							if parent_atoms:
								conflict_atoms = self._dynamic_config._slot_conflict_parent_atoms.intersection(parent_atoms)
								if conflict_atoms:
									parent_atoms = conflict_atoms

							all_parents.update(parent_atoms)

							all_match = True
							for parent, atom in parent_atoms:
								i = InternalPackageSet(initial_atoms=(atom,),
									allow_repo=True)
								if not i.findAtomForPackage(to_be_masked):
									all_match = False
									break

							if to_be_selected >= to_be_masked:
								# We only care about the parent atoms
								# when they trigger a downgrade.
								parent_atoms = set()

							fallback_data.append((to_be_masked, parent_atoms))

							if all_match:
								# 'to_be_masked' does not violate any parent atom, which means
								# there is no point in masking it.
								pass
							else:
								backtrack_data.append((to_be_masked, parent_atoms))

						if not backtrack_data:
							# This shouldn't happen, but fall back to the old
							# behavior if this gets triggered somehow.
							backtrack_data = fallback_data

						if len(backtrack_data) > 1:
							# NOTE: Generally, we prefer to mask the higher
							# version since this solves common cases in which a
							# lower version is needed so that all dependencies
							# will be satisfied (bug #337178). However, if
							# existing_node happens to be installed then we
							# mask that since this is a common case that is
							# triggered when --update is not enabled.
							if existing_node.installed:
								pass
							elif pkg > existing_node:
								backtrack_data.reverse()

						to_be_masked = backtrack_data[-1][0]

						self._dynamic_config._backtrack_infos["slot conflict"] = backtrack_data
						self._dynamic_config._need_restart = True
						if "--debug" in self._frozen_config.myopts:
							msg = []
							msg.append("")
							msg.append("")
							msg.append("backtracking due to slot conflict:")
							if backtrack_data is fallback_data:
								msg.append("!!! backtrack_data fallback")
							msg.append("   first package:  %s" % existing_node)
							msg.append("   second package: %s" % pkg)
							msg.append("  package to mask: %s" % to_be_masked)
							msg.append("      slot: %s" % pkg.slot_atom)
							msg.append("   parents: %s" % ", ".join( \
								"(%s, '%s')" % (ppkg, atom) for ppkg, atom in all_parents))
							msg.append("")
							writemsg_level("".join("%s\n" % l for l in msg),
								noiselevel=-1, level=logging.DEBUG)
						return 0

					# A slot collision has occurred.  Sometimes this coincides
					# with unresolvable blockers, so the slot collision will be
					# shown later if there are no unresolvable blockers.
					self._add_slot_conflict(pkg)
					slot_collision = True

			if slot_collision:
				# Now add this node to the graph so that self.display()
				# can show use flags and --tree portage.output.  This node is
				# only being partially added to the graph.  It must not be
				# allowed to interfere with the other nodes that have been
				# added.  Do not overwrite data for existing nodes in
				# self._dynamic_config.mydbapi since that data will be used for blocker
				# validation.
				# Even though the graph is now invalid, continue to process
				# dependencies so that things like --fetchonly can still
				# function despite collisions.
				pass
			elif not previously_added:
				self._dynamic_config._slot_pkg_map[pkg.root][pkg.slot_atom] = pkg
				self._dynamic_config.mydbapi[pkg.root].cpv_inject(pkg)
				self._dynamic_config._filtered_trees[pkg.root]["porttree"].dbapi._clear_cache()
				self._dynamic_config._highest_pkg_cache.clear()
				self._check_masks(pkg)

			if not pkg.installed:
				# Allow this package to satisfy old-style virtuals in case it
				# doesn't already. Any pre-existing providers will be preferred
				# over this one.
				try:
					pkgsettings.setinst(pkg.cpv, pkg.metadata)
					# For consistency, also update the global virtuals.
					settings = self._frozen_config.roots[pkg.root].settings
					settings.unlock()
					settings.setinst(pkg.cpv, pkg.metadata)
					settings.lock()
				except portage.exception.InvalidDependString as e:
					if not pkg.installed:
						# should have been masked before it was selected
						raise

		if arg_atoms:
			self._dynamic_config._set_nodes.add(pkg)

		# Do this even when addme is False (--onlydeps) so that the
		# parent/child relationship is always known in case
		# self._show_slot_collision_notice() needs to be called later.
		self._dynamic_config.digraph.add(pkg, myparent, priority=priority)
		if dep.atom is not None and dep.parent is not None:
			self._add_parent_atom(pkg, (dep.parent, dep.atom))

		if arg_atoms:
			for parent_atom in arg_atoms:
				parent, atom = parent_atom
				self._dynamic_config.digraph.add(pkg, parent, priority=priority)
				self._add_parent_atom(pkg, parent_atom)

		""" This section determines whether we go deeper into dependencies or not.
			We want to go deeper on a few occasions:
			Installing package A, we need to make sure package A's deps are met.
			emerge --deep <pkgspec>; we need to recursively check dependencies of pkgspec
			If we are in --nodeps (no recursion) mode, we obviously only check 1 level of dependencies.
		"""
		if arg_atoms:
			depth = 0
		pkg.depth = depth
		deep = self._dynamic_config.myparams.get("deep", 0)
		empty = "empty" in self._dynamic_config.myparams
		recurse = empty or deep is True or depth + 1 <= deep
		dep_stack = self._dynamic_config._dep_stack
		if "recurse" not in self._dynamic_config.myparams:
			return 1
		elif pkg.installed and not recurse:
			dep_stack = self._dynamic_config._ignored_deps

		self._spinner_update()

		if not previously_added:
			dep_stack.append(pkg)
		return 1

	def _check_masks(self, pkg):

		slot_key = (pkg.root, pkg.slot_atom)

		# Check for upgrades in the same slot that are
		# masked due to a LICENSE change in a newer
		# version that is not masked for any other reason.
		other_pkg = self._frozen_config._highest_license_masked.get(slot_key)
		if other_pkg is not None and pkg < other_pkg:
			self._dynamic_config._masked_license_updates.add(other_pkg)

	def _add_parent_atom(self, pkg, parent_atom):
		parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
		if parent_atoms is None:
			parent_atoms = set()
			self._dynamic_config._parent_atoms[pkg] = parent_atoms
		parent_atoms.add(parent_atom)

	def _add_slot_conflict(self, pkg):
		self._dynamic_config._slot_collision_nodes.add(pkg)
		slot_key = (pkg.slot_atom, pkg.root)
		slot_nodes = self._dynamic_config._slot_collision_info.get(slot_key)
		if slot_nodes is None:
			slot_nodes = set()
			slot_nodes.add(self._dynamic_config._slot_pkg_map[pkg.root][pkg.slot_atom])
			self._dynamic_config._slot_collision_info[slot_key] = slot_nodes
		slot_nodes.add(pkg)

	def _add_pkg_deps(self, pkg, allow_unsatisfied=False):

		mytype = pkg.type_name
		myroot = pkg.root
		mykey = pkg.cpv
		metadata = pkg.metadata
		myuse = self._pkg_use_enabled(pkg)
		jbigkey = pkg
		depth = pkg.depth + 1
		removal_action = "remove" in self._dynamic_config.myparams

		edepend={}
		depkeys = ["DEPEND","RDEPEND","PDEPEND"]
		for k in depkeys:
			edepend[k] = metadata[k]

		if not pkg.built and \
			"--buildpkgonly" in self._frozen_config.myopts and \
			"deep" not in self._dynamic_config.myparams and \
			"empty" not in self._dynamic_config.myparams:
			edepend["RDEPEND"] = ""
			edepend["PDEPEND"] = ""

		if pkg.built and not removal_action:
			if self._frozen_config.myopts.get("--with-bdeps", "n") == "y":
				# Pull in build time deps as requested, but marked them as
				# "optional" since they are not strictly required. This allows
				# more freedom in the merge order calculation for solving
				# circular dependencies. Don't convert to PDEPEND since that
				# could make --with-bdeps=y less effective if it is used to
				# adjust merge order to prevent built_with_use() calls from
				# failing.
				pass
			else:
				# built packages do not have build time dependencies.
				edepend["DEPEND"] = ""

		if removal_action and self._frozen_config.myopts.get("--with-bdeps", "y") == "n":
			edepend["DEPEND"] = ""

		if removal_action:
			depend_root = myroot
		else:
			depend_root = "/"
			root_deps = self._frozen_config.myopts.get("--root-deps")
			if root_deps is not None:
				if root_deps is True:
					depend_root = myroot
				elif root_deps == "rdeps":
					edepend["DEPEND"] = ""

		deps = (
			(depend_root, edepend["DEPEND"],
				self._priority(buildtime=(not pkg.built),
				optional=pkg.built),
				pkg.built),
			(myroot, edepend["RDEPEND"],
				self._priority(runtime=True),
				False),
			(myroot, edepend["PDEPEND"],
				self._priority(runtime_post=True),
				False)
		)

		debug = "--debug" in self._frozen_config.myopts
		strict = mytype != "installed"
		try:
			for dep_root, dep_string, dep_priority, ignore_blockers in deps:
				if not dep_string:
					continue
				if debug:
					writemsg_level("\nParent:    %s\n" % (pkg,),
						noiselevel=-1, level=logging.DEBUG)
					writemsg_level("Depstring: %s\n" % (dep_string,),
						noiselevel=-1, level=logging.DEBUG)
					writemsg_level("Priority:  %s\n" % (dep_priority,),
						noiselevel=-1, level=logging.DEBUG)

				try:
					dep_string = portage.dep.use_reduce(dep_string,
						uselist=self._pkg_use_enabled(pkg), is_valid_flag=pkg.iuse.is_valid_flag)
				except portage.exception.InvalidDependString as e:
					if not pkg.installed:
						# should have been masked before it was selected
						raise
					del e

					# Try again, but omit the is_valid_flag argument, since
					# invalid USE conditionals are a common problem and it's
					# practical to ignore this issue for installed packages.
					try:
						dep_string = portage.dep.use_reduce(dep_string,
							uselist=self._pkg_use_enabled(pkg))
					except portage.exception.InvalidDependString as e:
						self._dynamic_config._masked_installed.add(pkg)
						del e
						continue

				try:
					dep_string = list(self._queue_disjunctive_deps(
						pkg, dep_root, dep_priority, dep_string))
				except portage.exception.InvalidDependString as e:
					if pkg.installed:
						self._dynamic_config._masked_installed.add(pkg)
						del e
						continue

					# should have been masked before it was selected
					raise

				if not dep_string:
					continue

				dep_string = portage.dep.paren_enclose(dep_string,
					unevaluated_atom=True)

				if not self._add_pkg_dep_string(
					pkg, dep_root, dep_priority, dep_string,
					allow_unsatisfied, ignore_blockers=ignore_blockers):
					return 0

		except portage.exception.AmbiguousPackageName as e:
			pkgs = e.args[0]
			portage.writemsg("\n\n!!! An atom in the dependencies " + \
				"is not fully-qualified. Multiple matches:\n\n", noiselevel=-1)
			for cpv in pkgs:
				portage.writemsg("    %s\n" % cpv, noiselevel=-1)
			portage.writemsg("\n", noiselevel=-1)
			if mytype == "binary":
				portage.writemsg(
					"!!! This binary package cannot be installed: '%s'\n" % \
					mykey, noiselevel=-1)
			elif mytype == "ebuild":
				portdb = self._frozen_config.roots[myroot].trees["porttree"].dbapi
				myebuild, mylocation = portdb.findname2(mykey, myrepo = pkg.repo)
				portage.writemsg("!!! This ebuild cannot be installed: " + \
					"'%s'\n" % myebuild, noiselevel=-1)
			portage.writemsg("!!! Please notify the package maintainer " + \
				"that atoms must be fully-qualified.\n", noiselevel=-1)
			return 0
		self._dynamic_config._traversed_pkg_deps.add(pkg)
		return 1

	def _add_pkg_dep_string(self, pkg, dep_root, dep_priority, dep_string,
		allow_unsatisfied, ignore_blockers=False):
		depth = pkg.depth + 1
		debug = "--debug" in self._frozen_config.myopts
		strict = pkg.type_name != "installed"

		if debug:
			writemsg_level("\nParent:    %s\n" % (pkg,),
				noiselevel=-1, level=logging.DEBUG)
			writemsg_level("Depstring: %s\n" % (dep_string,),
				noiselevel=-1, level=logging.DEBUG)
			writemsg_level("Priority:  %s\n" % (dep_priority,),
				noiselevel=-1, level=logging.DEBUG)

		try:
			selected_atoms = self._select_atoms(dep_root,
				dep_string, myuse=self._pkg_use_enabled(pkg), parent=pkg,
				strict=strict, priority=dep_priority)
		except portage.exception.InvalidDependString as e:
			if pkg.installed:
				self._dynamic_config._masked_installed.add(pkg)
				return 1

			# should have been masked before it was selected
			raise

		if debug:
			writemsg_level("Candidates: %s\n" % \
				([str(x) for x in selected_atoms[pkg]],),
				noiselevel=-1, level=logging.DEBUG)

		root_config = self._frozen_config.roots[dep_root]
		vardb = root_config.trees["vartree"].dbapi

		for atom, child in self._minimize_children(
			pkg, dep_priority, root_config, selected_atoms[pkg]):

			if ignore_blockers and atom.blocker:
				# For --with-bdeps, ignore build-time only blockers
				# that originate from built packages.
				continue

			mypriority = dep_priority.copy()
			if not atom.blocker:
				inst_pkgs = vardb.match_pkgs(atom)
				if inst_pkgs:
					for inst_pkg in inst_pkgs:
						if self._pkg_visibility_check(inst_pkg):
							# highest visible
							mypriority.satisfied = inst_pkg
							break
					if not mypriority.satisfied:
						# none visible, so use highest
						mypriority.satisfied = inst_pkgs[0]

			if not self._add_dep(Dependency(atom=atom,
				blocker=atom.blocker, child=child, depth=depth, parent=pkg,
				priority=mypriority, root=dep_root),
				allow_unsatisfied=allow_unsatisfied):
				return 0

		selected_atoms.pop(pkg)

		# Add selected indirect virtual deps to the graph. This
		# takes advantage of circular dependency avoidance that's done
		# by dep_zapdeps. We preserve actual parent/child relationships
		# here in order to avoid distorting the dependency graph like
		# <=portage-2.1.6.x did.
		for virt_pkg, atoms in selected_atoms.items():

			if debug:
				writemsg_level("Candidates: %s: %s\n" % \
					(virt_pkg.cpv, [str(x) for x in atoms]),
					noiselevel=-1, level=logging.DEBUG)

			# Just assume depth + 1 here for now, though it's not entirely
			# accurate since multilple levels of indirect virtual deps may
			# have been traversed. The _add_pkg call will reset the depth to
			# 0 if this package happens to match an argument.
			if not self._add_pkg(virt_pkg,
				Dependency(atom=Atom('=' + virt_pkg.cpv),
				depth=(depth + 1), parent=pkg, priority=dep_priority.copy(),
				root=dep_root)):
				return 0

			for atom, child in self._minimize_children(
				pkg, self._priority(runtime=True), root_config, atoms):
				# This is a GLEP 37 virtual, so its deps are all runtime.
				mypriority = self._priority(runtime=True)
				if not atom.blocker:
					inst_pkgs = vardb.match_pkgs(atom)
					if inst_pkgs:
						for inst_pkg in inst_pkgs:
							if self._pkg_visibility_check(inst_pkg):
								# highest visible
								mypriority.satisfied = inst_pkg
								break
						if not mypriority.satisfied:
							# none visible, so use highest
							mypriority.satisfied = inst_pkgs[0]

				if not self._add_dep(Dependency(atom=atom,
					blocker=atom.blocker, child=child, depth=virt_pkg.depth,
					parent=virt_pkg, priority=mypriority, root=dep_root),
					allow_unsatisfied=allow_unsatisfied):
					return 0

		if debug:
			writemsg_level("Exiting... %s\n" % (pkg,),
				noiselevel=-1, level=logging.DEBUG)

		return 1

	def _minimize_children(self, parent, priority, root_config, atoms):
		"""
		Selects packages to satisfy the given atoms, and minimizes the
		number of selected packages. This serves to identify and eliminate
		redundant package selections when multiple atoms happen to specify
		a version range.
		"""

		atom_pkg_map = {}

		for atom in atoms:
			if atom.blocker:
				yield (atom, None)
				continue
			dep_pkg, existing_node = self._select_package(
				root_config.root, atom)
			if dep_pkg is None:
				yield (atom, None)
				continue
			atom_pkg_map[atom] = dep_pkg

		if len(atom_pkg_map) < 2:
			for item in atom_pkg_map.items():
				yield item
			return

		cp_pkg_map = {}
		pkg_atom_map = {}
		for atom, pkg in atom_pkg_map.items():
			pkg_atom_map.setdefault(pkg, set()).add(atom)
			cp_pkg_map.setdefault(pkg.cp, set()).add(pkg)

		for cp, pkgs in cp_pkg_map.items():
			if len(pkgs) < 2:
				for pkg in pkgs:
					for atom in pkg_atom_map[pkg]:
						yield (atom, pkg)
				continue

			# Use a digraph to identify and eliminate any
			# redundant package selections.
			atom_pkg_graph = digraph()
			cp_atoms = set()
			for pkg1 in pkgs:
				for atom in pkg_atom_map[pkg1]:
					cp_atoms.add(atom)
					atom_pkg_graph.add(pkg1, atom)
					atom_set = InternalPackageSet(initial_atoms=(atom,),
						allow_repo=True)
					for pkg2 in pkgs:
						if pkg2 is pkg1:
							continue
						if atom_set.findAtomForPackage(pkg2, modified_use=self._pkg_use_enabled(pkg2)):
							atom_pkg_graph.add(pkg2, atom)

			for pkg in pkgs:
				eliminate_pkg = True
				for atom in atom_pkg_graph.parent_nodes(pkg):
					if len(atom_pkg_graph.child_nodes(atom)) < 2:
						eliminate_pkg = False
						break
				if eliminate_pkg:
					atom_pkg_graph.remove(pkg)

			# Yield ~, =*, < and <= atoms first, since those are more likely to
			# cause slot conflicts, and we want those atoms to be displayed
			# in the resulting slot conflict message (see bug #291142).
			conflict_atoms = []
			normal_atoms = []
			for atom in cp_atoms:
				conflict = False
				for child_pkg in atom_pkg_graph.child_nodes(atom):
					existing_node, matches = \
						self._check_slot_conflict(child_pkg, atom)
					if existing_node and not matches:
						conflict = True
						break
				if conflict:
					conflict_atoms.append(atom)
				else:
					normal_atoms.append(atom)

			for atom in chain(conflict_atoms, normal_atoms):
				child_pkgs = atom_pkg_graph.child_nodes(atom)
				# if more than one child, yield highest version
				if len(child_pkgs) > 1:
					child_pkgs.sort()
				yield (atom, child_pkgs[-1])

	def _queue_disjunctive_deps(self, pkg, dep_root, dep_priority, dep_struct):
		"""
		Queue disjunctive (virtual and ||) deps in self._dynamic_config._dep_disjunctive_stack.
		Yields non-disjunctive deps. Raises InvalidDependString when 
		necessary.
		"""
		i = 0
		while i < len(dep_struct):
			x = dep_struct[i]
			if isinstance(x, list):
				for y in self._queue_disjunctive_deps(
					pkg, dep_root, dep_priority, x):
					yield y
			elif x == "||":
				self._queue_disjunction(pkg, dep_root, dep_priority,
					[ x, dep_struct[ i + 1 ] ] )
				i += 1
			else:
				try:
					x = portage.dep.Atom(x)
				except portage.exception.InvalidAtom:
					if not pkg.installed:
						raise portage.exception.InvalidDependString(
							"invalid atom: '%s'" % x)
				else:
					# Note: Eventually this will check for PROPERTIES=virtual
					# or whatever other metadata gets implemented for this
					# purpose.
					if x.cp.startswith('virtual/'):
						self._queue_disjunction( pkg, dep_root,
							dep_priority, [ str(x) ] )
					else:
						yield str(x)
			i += 1

	def _queue_disjunction(self, pkg, dep_root, dep_priority, dep_struct):
		self._dynamic_config._dep_disjunctive_stack.append(
			(pkg, dep_root, dep_priority, dep_struct))

	def _pop_disjunction(self, allow_unsatisfied):
		"""
		Pop one disjunctive dep from self._dynamic_config._dep_disjunctive_stack, and use it to
		populate self._dynamic_config._dep_stack.
		"""
		pkg, dep_root, dep_priority, dep_struct = \
			self._dynamic_config._dep_disjunctive_stack.pop()
		dep_string = portage.dep.paren_enclose(dep_struct,
			unevaluated_atom=True)
		if not self._add_pkg_dep_string(
			pkg, dep_root, dep_priority, dep_string, allow_unsatisfied):
			return 0
		return 1

	def _priority(self, **kwargs):
		if "remove" in self._dynamic_config.myparams:
			priority_constructor = UnmergeDepPriority
		else:
			priority_constructor = DepPriority
		return priority_constructor(**kwargs)

	def _dep_expand(self, root_config, atom_without_category):
		"""
		@param root_config: a root config instance
		@type root_config: RootConfig
		@param atom_without_category: an atom without a category component
		@type atom_without_category: String
		@rtype: list
		@returns: a list of atoms containing categories (possibly empty)
		"""
		null_cp = portage.dep_getkey(insert_category_into_atom(
			atom_without_category, "null"))
		cat, atom_pn = portage.catsplit(null_cp)

		dbs = self._dynamic_config._filtered_trees[root_config.root]["dbs"]
		categories = set()
		for db, pkg_type, built, installed, db_keys in dbs:
			for cat in db.categories:
				if db.cp_list("%s/%s" % (cat, atom_pn)):
					categories.add(cat)

		deps = []
		for cat in categories:
			deps.append(Atom(insert_category_into_atom(
				atom_without_category, cat), allow_repo=True))
		return deps

	def _have_new_virt(self, root, atom_cp):
		ret = False
		for db, pkg_type, built, installed, db_keys in \
			self._dynamic_config._filtered_trees[root]["dbs"]:
			if db.cp_list(atom_cp):
				ret = True
				break
		return ret

	def _iter_atoms_for_pkg(self, pkg):
		depgraph_sets = self._dynamic_config.sets[pkg.root]
		atom_arg_map = depgraph_sets.atom_arg_map
		root_config = self._frozen_config.roots[pkg.root]
		for atom in depgraph_sets.atoms.iterAtomsForPackage(pkg):
			if atom.cp != pkg.cp and \
				self._have_new_virt(pkg.root, atom.cp):
				continue
			visible_pkgs = \
				self._dynamic_config._visible_pkgs[pkg.root].match_pkgs(atom)
			visible_pkgs.reverse() # descending order
			higher_slot = None
			for visible_pkg in visible_pkgs:
				if visible_pkg.cp != atom.cp:
					continue
				if pkg >= visible_pkg:
					# This is descending order, and we're not
					# interested in any versions <= pkg given.
					break
				if pkg.slot_atom != visible_pkg.slot_atom:
					higher_slot = visible_pkg
					break
			if higher_slot is not None:
				continue
			for arg in atom_arg_map[(atom, pkg.root)]:
				if isinstance(arg, PackageArg) and \
					arg.package != pkg:
					continue
				yield arg, atom

	def select_files(self, myfiles):
		"""Given a list of .tbz2s, .ebuilds sets, and deps, populate
		self._dynamic_config._initial_arg_list and call self._resolve to create the 
		appropriate depgraph and return a favorite list."""
		self._load_vdb()
		debug = "--debug" in self._frozen_config.myopts
		root_config = self._frozen_config.roots[self._frozen_config.target_root]
		sets = root_config.sets
		depgraph_sets = self._dynamic_config.sets[root_config.root]
		myfavorites=[]
		myroot = self._frozen_config.target_root
		dbs = self._dynamic_config._filtered_trees[myroot]["dbs"]
		vardb = self._frozen_config.trees[myroot]["vartree"].dbapi
		real_vardb = self._frozen_config._trees_orig[myroot]["vartree"].dbapi
		portdb = self._frozen_config.trees[myroot]["porttree"].dbapi
		bindb = self._frozen_config.trees[myroot]["bintree"].dbapi
		pkgsettings = self._frozen_config.pkgsettings[myroot]
		args = []
		onlydeps = "--onlydeps" in self._frozen_config.myopts
		lookup_owners = []
		for x in myfiles:
			ext = os.path.splitext(x)[1]
			if ext==".tbz2":
				if not os.path.exists(x):
					if os.path.exists(
						os.path.join(pkgsettings["PKGDIR"], "All", x)):
						x = os.path.join(pkgsettings["PKGDIR"], "All", x)
					elif os.path.exists(
						os.path.join(pkgsettings["PKGDIR"], x)):
						x = os.path.join(pkgsettings["PKGDIR"], x)
					else:
						writemsg("\n\n!!! Binary package '"+str(x)+"' does not exist.\n", noiselevel=-1)
						writemsg("!!! Please ensure the tbz2 exists as specified.\n\n", noiselevel=-1)
						return 0, myfavorites
				mytbz2=portage.xpak.tbz2(x)
				mykey=mytbz2.getelements("CATEGORY")[0]+"/"+os.path.splitext(os.path.basename(x))[0]
				if os.path.realpath(x) != \
					os.path.realpath(self._frozen_config.trees[myroot]["bintree"].getname(mykey)):
					writemsg(colorize("BAD", "\n*** You need to adjust PKGDIR to emerge this package.\n\n"), noiselevel=-1)
					return 0, myfavorites

				pkg = self._pkg(mykey, "binary", root_config,
					onlydeps=onlydeps)
				args.append(PackageArg(arg=x, package=pkg,
					root_config=root_config))
			elif ext==".ebuild":
				ebuild_path = portage.util.normalize_path(os.path.abspath(x))
				pkgdir = os.path.dirname(ebuild_path)
				tree_root = os.path.dirname(os.path.dirname(pkgdir))
				cp = pkgdir[len(tree_root)+1:]
				e = portage.exception.PackageNotFound(
					("%s is not in a valid portage tree " + \
					"hierarchy or does not exist") % x)
				if not portage.isvalidatom(cp):
					raise e
				cat = portage.catsplit(cp)[0]
				mykey = cat + "/" + os.path.basename(ebuild_path[:-7])
				if not portage.isvalidatom("="+mykey):
					raise e
				ebuild_path = portdb.findname(mykey)
				if ebuild_path:
					if ebuild_path != os.path.join(os.path.realpath(tree_root),
						cp, os.path.basename(ebuild_path)):
						writemsg(colorize("BAD", "\n*** You need to adjust PORTDIR or PORTDIR_OVERLAY to emerge this package.\n\n"), noiselevel=-1)
						return 0, myfavorites
					if mykey not in portdb.xmatch(
						"match-visible", portage.cpv_getkey(mykey)):
						writemsg(colorize("BAD", "\n*** You are emerging a masked package. It is MUCH better to use\n"), noiselevel=-1)
						writemsg(colorize("BAD", "*** /etc/portage/package.* to accomplish this. See portage(5) man\n"), noiselevel=-1)
						writemsg(colorize("BAD", "*** page for details.\n"), noiselevel=-1)
						countdown(int(self._frozen_config.settings["EMERGE_WARNING_DELAY"]),
							"Continuing...")
				else:
					raise portage.exception.PackageNotFound(
						"%s is not in a valid portage tree hierarchy or does not exist" % x)
				pkg = self._pkg(mykey, "ebuild", root_config,
					onlydeps=onlydeps, myrepo=portdb.getRepositoryName(
					os.path.dirname(os.path.dirname(os.path.dirname(ebuild_path)))))
				args.append(PackageArg(arg=x, package=pkg,
					root_config=root_config))
			elif x.startswith(os.path.sep):
				if not x.startswith(myroot):
					portage.writemsg(("\n\n!!! '%s' does not start with" + \
						" $ROOT.\n") % x, noiselevel=-1)
					return 0, []
				# Queue these up since it's most efficient to handle
				# multiple files in a single iter_owners() call.
				lookup_owners.append(x)
			else:
				if x in ("system", "world"):
					x = SETPREFIX + x
				if x.startswith(SETPREFIX):
					s = x[len(SETPREFIX):]
					if s not in sets:
						raise portage.exception.PackageSetNotFound(s)
					if s in depgraph_sets.sets:
						continue
					pset = sets[s]
					depgraph_sets.sets[s] = pset
					args.append(SetArg(arg=x, pset=pset,
						root_config=root_config))
					continue
				if not is_valid_package_atom(x, allow_repo=True):
					portage.writemsg("\n\n!!! '%s' is not a valid package atom.\n" % x,
						noiselevel=-1)
					portage.writemsg("!!! Please check ebuild(5) for full details.\n")
					portage.writemsg("!!! (Did you specify a version but forget to prefix with '='?)\n")
					return (0,[])
				# Don't expand categories or old-style virtuals here unless
				# necessary. Expansion of old-style virtuals here causes at
				# least the following problems:
				#   1) It's more difficult to determine which set(s) an atom
				#      came from, if any.
				#   2) It takes away freedom from the resolver to choose other
				#      possible expansions when necessary.
				if "/" in x:
					args.append(AtomArg(arg=x, atom=Atom(x, allow_repo=True),
						root_config=root_config))
					continue
				expanded_atoms = self._dep_expand(root_config, x)
				installed_cp_set = set()
				for atom in expanded_atoms:
					if vardb.cp_list(atom.cp):
						installed_cp_set.add(atom.cp)

				if len(installed_cp_set) > 1:
					non_virtual_cps = set()
					for atom_cp in installed_cp_set:
						if not atom_cp.startswith("virtual/"):
							non_virtual_cps.add(atom_cp)
					if len(non_virtual_cps) == 1:
						installed_cp_set = non_virtual_cps

				if len(expanded_atoms) > 1 and len(installed_cp_set) == 1:
					installed_cp = next(iter(installed_cp_set))
					for atom in expanded_atoms:
						if atom.cp == installed_cp:
							available = False
							for pkg in self._iter_match_pkgs_any(
								root_config, atom.without_use,
								onlydeps=onlydeps):
								if not pkg.installed:
									available = True
									break
							if available:
								expanded_atoms = [atom]
								break

				# If a non-virtual package and one or more virtual packages
				# are in expanded_atoms, use the non-virtual package.
				if len(expanded_atoms) > 1:
					number_of_virtuals = 0
					for expanded_atom in expanded_atoms:
						if expanded_atom.cp.startswith("virtual/"):
							number_of_virtuals += 1
						else:
							candidate = expanded_atom
					if len(expanded_atoms) - number_of_virtuals == 1:
						expanded_atoms = [ candidate ]

				if len(expanded_atoms) > 1:
					writemsg("\n\n", noiselevel=-1)
					ambiguous_package_name(x, expanded_atoms, root_config,
						self._frozen_config.spinner, self._frozen_config.myopts)
					return False, myfavorites
				if expanded_atoms:
					atom = expanded_atoms[0]
				else:
					null_atom = Atom(insert_category_into_atom(x, "null"),
						allow_repo=True)
					cat, atom_pn = portage.catsplit(null_atom.cp)
					virts_p = root_config.settings.get_virts_p().get(atom_pn)
					if virts_p:
						# Allow the depgraph to choose which virtual.
						atom = Atom(null_atom.replace('null/', 'virtual/', 1),
							allow_repo=True)
					else:
						atom = null_atom

				args.append(AtomArg(arg=x, atom=atom,
					root_config=root_config))

		if lookup_owners:
			relative_paths = []
			search_for_multiple = False
			if len(lookup_owners) > 1:
				search_for_multiple = True

			for x in lookup_owners:
				if not search_for_multiple and os.path.isdir(x):
					search_for_multiple = True
				relative_paths.append(x[len(myroot)-1:])

			owners = set()
			for pkg, relative_path in \
				real_vardb._owners.iter_owners(relative_paths):
				owners.add(pkg.mycpv)
				if not search_for_multiple:
					break

			if not owners:
				portage.writemsg(("\n\n!!! '%s' is not claimed " + \
					"by any package.\n") % lookup_owners[0], noiselevel=-1)
				return 0, []

			for cpv in owners:
				slot = vardb.aux_get(cpv, ["SLOT"])[0]
				if not slot:
					# portage now masks packages with missing slot, but it's
					# possible that one was installed by an older version
					atom = Atom(portage.cpv_getkey(cpv))
				else:
					atom = Atom("%s:%s" % (portage.cpv_getkey(cpv), slot))
				args.append(AtomArg(arg=atom, atom=atom,
					root_config=root_config))

		if "--update" in self._frozen_config.myopts:
			# In some cases, the greedy slots behavior can pull in a slot that
			# the user would want to uninstall due to it being blocked by a
			# newer version in a different slot. Therefore, it's necessary to
			# detect and discard any that should be uninstalled. Each time
			# that arguments are updated, package selections are repeated in
			# order to ensure consistency with the current arguments:
			#
			#  1) Initialize args
			#  2) Select packages and generate initial greedy atoms
			#  3) Update args with greedy atoms
			#  4) Select packages and generate greedy atoms again, while
			#     accounting for any blockers between selected packages
			#  5) Update args with revised greedy atoms

			self._set_args(args)
			greedy_args = []
			for arg in args:
				greedy_args.append(arg)
				if not isinstance(arg, AtomArg):
					continue
				for atom in self._greedy_slots(arg.root_config, arg.atom):
					greedy_args.append(
						AtomArg(arg=arg.arg, atom=atom,
							root_config=arg.root_config))

			self._set_args(greedy_args)
			del greedy_args

			# Revise greedy atoms, accounting for any blockers
			# between selected packages.
			revised_greedy_args = []
			for arg in args:
				revised_greedy_args.append(arg)
				if not isinstance(arg, AtomArg):
					continue
				for atom in self._greedy_slots(arg.root_config, arg.atom,
					blocker_lookahead=True):
					revised_greedy_args.append(
						AtomArg(arg=arg.arg, atom=atom,
							root_config=arg.root_config))
			args = revised_greedy_args
			del revised_greedy_args

		self._set_args(args)

		myfavorites = set(myfavorites)
		for arg in args:
			if isinstance(arg, (AtomArg, PackageArg)):
				myfavorites.add(arg.atom)
			elif isinstance(arg, SetArg):
				myfavorites.add(arg.arg)
		myfavorites = list(myfavorites)

		if debug:
			portage.writemsg("\n", noiselevel=-1)
		# Order needs to be preserved since a feature of --nodeps
		# is to allow the user to force a specific merge order.
		self._dynamic_config._initial_arg_list = args[:]
	
		return self._resolve(myfavorites)
	
	def _resolve(self, myfavorites):
		"""Given self._dynamic_config._initial_arg_list, pull in the root nodes, 
		call self._creategraph to process theier deps and return 
		a favorite list."""
		debug = "--debug" in self._frozen_config.myopts
		onlydeps = "--onlydeps" in self._frozen_config.myopts
		myroot = self._frozen_config.target_root
		pkgsettings = self._frozen_config.pkgsettings[myroot]
		pprovideddict = pkgsettings.pprovideddict
		virtuals = pkgsettings.getvirtuals()
		for arg in self._expand_set_args(
			self._dynamic_config._initial_arg_list,
			add_to_digraph=True):
			for atom in arg.pset.getAtoms():
				self._spinner_update()
				dep = Dependency(atom=atom, onlydeps=onlydeps,
					root=myroot, parent=arg)
				try:
					pprovided = pprovideddict.get(atom.cp)
					if pprovided and portage.match_from_list(atom, pprovided):
						# A provided package has been specified on the command line.
						self._dynamic_config._pprovided_args.append((arg, atom))
						continue
					if isinstance(arg, PackageArg):
						if not self._add_pkg(arg.package, dep) or \
							not self._create_graph():
							if not self._dynamic_config._need_restart:
								sys.stderr.write(("\n\n!!! Problem " + \
									"resolving dependencies for %s\n") % \
									arg.arg)
							return 0, myfavorites
						continue
					if debug:
						portage.writemsg("      Arg: %s\n     Atom: %s\n" % \
							(arg, atom), noiselevel=-1)
					pkg, existing_node = self._select_package(
						myroot, atom, onlydeps=onlydeps)
					if not pkg:
						pprovided_match = False
						for virt_choice in virtuals.get(atom.cp, []):
							expanded_atom = portage.dep.Atom(
								atom.replace(atom.cp, virt_choice.cp, 1))
							pprovided = pprovideddict.get(expanded_atom.cp)
							if pprovided and \
								portage.match_from_list(expanded_atom, pprovided):
								# A provided package has been
								# specified on the command line.
								self._dynamic_config._pprovided_args.append((arg, atom))
								pprovided_match = True
								break
						if pprovided_match:
							continue

						if not (isinstance(arg, SetArg) and \
							arg.name in ("selected", "system", "world")):
							self._dynamic_config._unsatisfied_deps_for_display.append(
								((myroot, atom), {"myparent" : arg}))
							return 0, myfavorites
						self._dynamic_config._missing_args.append((arg, atom))
						continue
					if atom.cp != pkg.cp:
						# For old-style virtuals, we need to repeat the
						# package.provided check against the selected package.
						expanded_atom = atom.replace(atom.cp, pkg.cp)
						pprovided = pprovideddict.get(pkg.cp)
						if pprovided and \
							portage.match_from_list(expanded_atom, pprovided):
							# A provided package has been
							# specified on the command line.
							self._dynamic_config._pprovided_args.append((arg, atom))
							continue
					if pkg.installed and "selective" not in self._dynamic_config.myparams:
						self._dynamic_config._unsatisfied_deps_for_display.append(
							((myroot, atom), {"myparent" : arg}))
						# Previous behavior was to bail out in this case, but
						# since the dep is satisfied by the installed package,
						# it's more friendly to continue building the graph
						# and just show a warning message. Therefore, only bail
						# out here if the atom is not from either the system or
						# world set.
						if not (isinstance(arg, SetArg) and \
							arg.name in ("selected", "system", "world")):
							return 0, myfavorites

					# Add the selected package to the graph as soon as possible
					# so that later dep_check() calls can use it as feedback
					# for making more consistent atom selections.
					if not self._add_pkg(pkg, dep):
						if self._dynamic_config._need_restart:
							pass
						elif isinstance(arg, SetArg):
							sys.stderr.write(("\n\n!!! Problem resolving " + \
								"dependencies for %s from %s\n") % \
								(atom, arg.arg))
						else:
							sys.stderr.write(("\n\n!!! Problem resolving " + \
								"dependencies for %s\n") % atom)
						return 0, myfavorites

				except portage.exception.MissingSignature as e:
					portage.writemsg("\n\n!!! A missing gpg signature is preventing portage from calculating the\n")
					portage.writemsg("!!! required dependencies. This is a security feature enabled by the admin\n")
					portage.writemsg("!!! to aid in the detection of malicious intent.\n\n")
					portage.writemsg("!!! THIS IS A POSSIBLE INDICATION OF TAMPERED FILES -- CHECK CAREFULLY.\n")
					portage.writemsg("!!! Affected file: %s\n" % (e), noiselevel=-1)
					return 0, myfavorites
				except portage.exception.InvalidSignature as e:
					portage.writemsg("\n\n!!! An invalid gpg signature is preventing portage from calculating the\n")
					portage.writemsg("!!! required dependencies. This is a security feature enabled by the admin\n")
					portage.writemsg("!!! to aid in the detection of malicious intent.\n\n")
					portage.writemsg("!!! THIS IS A POSSIBLE INDICATION OF TAMPERED FILES -- CHECK CAREFULLY.\n")
					portage.writemsg("!!! Affected file: %s\n" % (e), noiselevel=-1)
					return 0, myfavorites
				except SystemExit as e:
					raise # Needed else can't exit
				except Exception as e:
					writemsg("\n\n!!! Problem in '%s' dependencies.\n" % atom, noiselevel=-1)
					writemsg("!!! %s %s\n" % (str(e), str(getattr(e, "__module__", None))))
					raise

		# Now that the root packages have been added to the graph,
		# process the dependencies.
		if not self._create_graph():
			return 0, myfavorites

		try:
			self.altlist()
		except self._unknown_internal_error:
			return False, myfavorites

		if set(self._dynamic_config.digraph).intersection( \
			self._dynamic_config._needed_unstable_keywords) or \
			set(self._dynamic_config.digraph).intersection( \
			self._dynamic_config._needed_use_config_changes) or \
			set(self._dynamic_config.digraph).intersection( \
			self._dynamic_config._needed_license_changes) :
			#We failed if the user needs to change the configuration
			self._dynamic_config._success_without_autounmask = True
			return False, myfavorites

		# We're true here unless we are missing binaries.
		return (True, myfavorites)

	def _set_args(self, args):
		"""
		Create the "__non_set_args__" package set from atoms and packages given as
		arguments. This method can be called multiple times if necessary.
		The package selection cache is automatically invalidated, since
		arguments influence package selections.
		"""

		set_atoms = {}
		non_set_atoms = {}
		for root in self._dynamic_config.sets:
			depgraph_sets = self._dynamic_config.sets[root]
			depgraph_sets.sets.setdefault('__non_set_args__',
				InternalPackageSet(allow_repo=True)).clear()
			depgraph_sets.atoms.clear()
			depgraph_sets.atom_arg_map.clear()
			set_atoms[root] = []
			non_set_atoms[root] = []

		# We don't add set args to the digraph here since that
		# happens at a later stage and we don't want to make
		# any state changes here that aren't reversed by a
		# another call to this method.
		for arg in self._expand_set_args(args, add_to_digraph=False):
			atom_arg_map = self._dynamic_config.sets[
				arg.root_config.root].atom_arg_map
			if isinstance(arg, SetArg):
				atom_group = set_atoms[arg.root_config.root]
			else:
				atom_group = non_set_atoms[arg.root_config.root]

			for atom in arg.pset.getAtoms():
				atom_group.append(atom)
				atom_key = (atom, arg.root_config.root)
				refs = atom_arg_map.get(atom_key)
				if refs is None:
					refs = []
					atom_arg_map[atom_key] = refs
					if arg not in refs:
						refs.append(arg)

		for root in self._dynamic_config.sets:
			depgraph_sets = self._dynamic_config.sets[root]
			depgraph_sets.atoms.update(chain(set_atoms.get(root, []),
				non_set_atoms.get(root, [])))
			depgraph_sets.sets['__non_set_args__'].update(
				non_set_atoms.get(root, []))

		# Invalidate the package selection cache, since
		# arguments influence package selections.
		self._dynamic_config._highest_pkg_cache.clear()
		for trees in self._dynamic_config._filtered_trees.values():
			trees["porttree"].dbapi._clear_cache()

	def _greedy_slots(self, root_config, atom, blocker_lookahead=False):
		"""
		Return a list of slot atoms corresponding to installed slots that
		differ from the slot of the highest visible match. When
		blocker_lookahead is True, slot atoms that would trigger a blocker
		conflict are automatically discarded, potentially allowing automatic
		uninstallation of older slots when appropriate.
		"""
		highest_pkg, in_graph = self._select_package(root_config.root, atom)
		if highest_pkg is None:
			return []
		vardb = root_config.trees["vartree"].dbapi
		slots = set()
		for cpv in vardb.match(atom):
			# don't mix new virtuals with old virtuals
			if portage.cpv_getkey(cpv) == highest_pkg.cp:
				slots.add(vardb.aux_get(cpv, ["SLOT"])[0])

		slots.add(highest_pkg.metadata["SLOT"])
		if len(slots) == 1:
			return []
		greedy_pkgs = []
		slots.remove(highest_pkg.metadata["SLOT"])
		while slots:
			slot = slots.pop()
			slot_atom = portage.dep.Atom("%s:%s" % (highest_pkg.cp, slot))
			pkg, in_graph = self._select_package(root_config.root, slot_atom)
			if pkg is not None and \
				pkg.cp == highest_pkg.cp and pkg < highest_pkg:
				greedy_pkgs.append(pkg)
		if not greedy_pkgs:
			return []
		if not blocker_lookahead:
			return [pkg.slot_atom for pkg in greedy_pkgs]

		blockers = {}
		blocker_dep_keys = ["DEPEND", "PDEPEND", "RDEPEND"]
		for pkg in greedy_pkgs + [highest_pkg]:
			dep_str = " ".join(pkg.metadata[k] for k in blocker_dep_keys)
			try:
				selected_atoms = self._select_atoms(
					pkg.root, dep_str, self._pkg_use_enabled(pkg),
					parent=pkg, strict=True)
			except portage.exception.InvalidDependString:
				continue
			blocker_atoms = []
			for atoms in selected_atoms.values():
				blocker_atoms.extend(x for x in atoms if x.blocker)
			blockers[pkg] = InternalPackageSet(initial_atoms=blocker_atoms)

		if highest_pkg not in blockers:
			return []

		# filter packages with invalid deps
		greedy_pkgs = [pkg for pkg in greedy_pkgs if pkg in blockers]

		# filter packages that conflict with highest_pkg
		greedy_pkgs = [pkg for pkg in greedy_pkgs if not \
			(blockers[highest_pkg].findAtomForPackage(pkg, modified_use=self._pkg_use_enabled(pkg)) or \
			blockers[pkg].findAtomForPackage(highest_pkg, modified_use=self._pkg_use_enabled(highest_pkg)))]

		if not greedy_pkgs:
			return []

		# If two packages conflict, discard the lower version.
		discard_pkgs = set()
		greedy_pkgs.sort(reverse=True)
		for i in range(len(greedy_pkgs) - 1):
			pkg1 = greedy_pkgs[i]
			if pkg1 in discard_pkgs:
				continue
			for j in range(i + 1, len(greedy_pkgs)):
				pkg2 = greedy_pkgs[j]
				if pkg2 in discard_pkgs:
					continue
				if blockers[pkg1].findAtomForPackage(pkg2, modified_use=self._pkg_use_enabled(pkg2)) or \
					blockers[pkg2].findAtomForPackage(pkg1, modified_use=self._pkg_use_enabled(pkg1)):
					# pkg1 > pkg2
					discard_pkgs.add(pkg2)

		return [pkg.slot_atom for pkg in greedy_pkgs \
			if pkg not in discard_pkgs]

	def _select_atoms_from_graph(self, *pargs, **kwargs):
		"""
		Prefer atoms matching packages that have already been
		added to the graph or those that are installed and have
		not been scheduled for replacement.
		"""
		kwargs["trees"] = self._dynamic_config._graph_trees
		return self._select_atoms_highest_available(*pargs, **kwargs)

	def _select_atoms_highest_available(self, root, depstring,
		myuse=None, parent=None, strict=True, trees=None, priority=None):
		"""This will raise InvalidDependString if necessary. If trees is
		None then self._dynamic_config._filtered_trees is used."""

		pkgsettings = self._frozen_config.pkgsettings[root]
		if trees is None:
			trees = self._dynamic_config._filtered_trees
		mytrees = trees[root]
		atom_graph = digraph()
		if True:
			# Temporarily disable autounmask so that || preferences
			# account for masking and USE settings.
			_autounmask_backup = self._dynamic_config._autounmask
			self._dynamic_config._autounmask = False
			mytrees["pkg_use_enabled"] = self._pkg_use_enabled
			try:
				if parent is not None:
					trees[root]["parent"] = parent
					trees[root]["atom_graph"] = atom_graph
				if priority is not None:
					trees[root]["priority"] = priority
				mycheck = portage.dep_check(depstring, None,
					pkgsettings, myuse=myuse,
					myroot=root, trees=trees)
			finally:
				self._dynamic_config._autounmask = _autounmask_backup
				del mytrees["pkg_use_enabled"]
				if parent is not None:
					trees[root].pop("parent")
					trees[root].pop("atom_graph")
				if priority is not None:
					trees[root].pop("priority")
			if not mycheck[0]:
				raise portage.exception.InvalidDependString(mycheck[1])
		if parent is None:
			selected_atoms = mycheck[1]
		else:
			chosen_atoms = frozenset(mycheck[1])
			selected_atoms = {parent : []}
			for node in atom_graph:
				if isinstance(node, Atom):
					continue
				if node is parent:
					pkg = parent
				else:
					pkg, virt_atom = node
					if virt_atom not in chosen_atoms:
						continue
					if not portage.match_from_list(virt_atom, [pkg]):
						# Typically this means that the atom
						# specifies USE deps that are unsatisfied
						# by the selected package. The caller will
						# record this as an unsatisfied dependency
						# when necessary.
						continue

				selected_atoms[pkg] = [atom for atom in \
					atom_graph.child_nodes(node) if atom in chosen_atoms]

		return selected_atoms

	def _show_unsatisfied_dep(self, root, atom, myparent=None, arg=None,
		check_backtrack=False):
		"""
		When check_backtrack=True, no output is produced and
		the method either returns or raises _backtrack_mask if
		a matching package has been masked by backtracking.
		"""
		backtrack_mask = False
		atom_set = InternalPackageSet(initial_atoms=(atom.without_use,),
			allow_repo=True)
		xinfo = '"%s"' % atom.unevaluated_atom
		if arg:
			xinfo='"%s"' % arg
		if isinstance(myparent, AtomArg):
			xinfo = _unicode_decode('"%s"') % (myparent,)
		# Discard null/ from failed cpv_expand category expansion.
		xinfo = xinfo.replace("null/", "")
		if root != "/":
			xinfo = "%s for %s" % (xinfo, root)
		masked_packages = []
		missing_use = []
		masked_pkg_instances = set()
		missing_licenses = []
		have_eapi_mask = False
		pkgsettings = self._frozen_config.pkgsettings[root]
		root_config = self._frozen_config.roots[root]
		portdb = self._frozen_config.roots[root].trees["porttree"].dbapi
		dbs = self._dynamic_config._filtered_trees[root]["dbs"]
		for db, pkg_type, built, installed, db_keys in dbs:
			if installed:
				continue
			match = db.match
			if hasattr(db, "xmatch"):
				cpv_list = db.xmatch("match-all-cpv-only", atom.without_use)
			else:
				cpv_list = db.match(atom.without_use)

			if atom.repo is None and hasattr(db, "getRepositories"):
				repo_list = db.getRepositories()
			else:
				repo_list = [atom.repo]

			# descending order
			cpv_list.reverse()
			for cpv in cpv_list:
				for repo in repo_list:
					if not db.cpv_exists(cpv, myrepo=repo):
						continue

					metadata, mreasons  = get_mask_info(root_config, cpv, pkgsettings, db, pkg_type, \
						built, installed, db_keys, myrepo=repo, _pkg_use_enabled=self._pkg_use_enabled)

					if metadata is not None:
						if not repo:
							repo = metadata.get('repository')
						pkg = self._pkg(cpv, pkg_type, root_config,
							installed=installed, myrepo=repo)
						if not atom_set.findAtomForPackage(pkg,
							modified_use=self._pkg_use_enabled(pkg)):
							continue
						# pkg.metadata contains calculated USE for ebuilds,
						# required later for getMissingLicenses.
						metadata = pkg.metadata
						if pkg in self._dynamic_config._runtime_pkg_mask:
							backtrack_reasons = \
								self._dynamic_config._runtime_pkg_mask[pkg]
							mreasons.append('backtracking: %s' % \
								', '.join(sorted(backtrack_reasons)))
							backtrack_mask = True
						if not mreasons and self._frozen_config.excluded_pkgs.findAtomForPackage(pkg, \
							modified_use=self._pkg_use_enabled(pkg)):
							mreasons = ["exclude option"]
						if mreasons:
							masked_pkg_instances.add(pkg)
						if atom.unevaluated_atom.use:
							try:
								if not pkg.iuse.is_valid_flag(atom.unevaluated_atom.use.required) \
									or atom.violated_conditionals(self._pkg_use_enabled(pkg), pkg.iuse.is_valid_flag).use:
									missing_use.append(pkg)
									if not mreasons:
										continue
							except InvalidAtom:
								writemsg("violated_conditionals raised " + \
									"InvalidAtom: '%s' parent: %s" % \
									(atom, myparent), noiselevel=-1)
								raise
						if pkg.built and not mreasons:
							mreasons = ["use flag configuration mismatch"]
					masked_packages.append(
						(root_config, pkgsettings, cpv, repo, metadata, mreasons))

		if check_backtrack:
			if backtrack_mask:
				raise self._backtrack_mask()
			else:
				return

		missing_use_reasons = []
		missing_iuse_reasons = []
		for pkg in missing_use:
			use = self._pkg_use_enabled(pkg)
			missing_iuse = []
			#Use the unevaluated atom here, because some flags might have gone
			#lost during evaluation.
			required_flags = atom.unevaluated_atom.use.required
			missing_iuse = pkg.iuse.get_missing_iuse(required_flags)

			mreasons = []
			if missing_iuse:
				mreasons.append("Missing IUSE: %s" % " ".join(missing_iuse))
				missing_iuse_reasons.append((pkg, mreasons))
			else:
				need_enable = sorted(atom.use.enabled.difference(use).intersection(pkg.iuse.all))
				need_disable = sorted(atom.use.disabled.intersection(use).intersection(pkg.iuse.all))

				untouchable_flags = \
					frozenset(chain(pkg.use.mask, pkg.use.force))
				if untouchable_flags.intersection(
					chain(need_enable, need_disable)):
					continue

				required_use = pkg.metadata["REQUIRED_USE"]
				required_use_warning = ""
				if required_use:
					old_use = self._pkg_use_enabled(pkg)
					new_use = set(self._pkg_use_enabled(pkg))
					for flag in need_enable:
						new_use.add(flag)
					for flag in need_disable:
						new_use.discard(flag)
					if check_required_use(required_use, old_use, pkg.iuse.is_valid_flag) and \
						not check_required_use(required_use, new_use, pkg.iuse.is_valid_flag):
							required_use_warning = ", this change violates use flag constraints " + \
								"defined by %s: '%s'" % (pkg.cpv, human_readable_required_use(required_use))

				if need_enable or need_disable:
					changes = []
					changes.extend(colorize("red", "+" + x) \
						for x in need_enable)
					changes.extend(colorize("blue", "-" + x) \
						for x in need_disable)
					mreasons.append("Change USE: %s" % " ".join(changes) + required_use_warning)
					missing_use_reasons.append((pkg, mreasons))

			if not missing_iuse and myparent and atom.unevaluated_atom.use.conditional:
				# Lets see if the violated use deps are conditional.
				# If so, suggest to change them on the parent.

				# If the child package is masked then a change to
				# parent USE is not a valid solution (a normal mask
				# message should be displayed instead).
				if pkg in masked_pkg_instances:
					continue

				mreasons = []
				violated_atom = atom.unevaluated_atom.violated_conditionals(self._pkg_use_enabled(pkg), \
					pkg.iuse.is_valid_flag, self._pkg_use_enabled(myparent))
				if not (violated_atom.use.enabled or violated_atom.use.disabled):
					#all violated use deps are conditional
					changes = []
					conditional = violated_atom.use.conditional
					involved_flags = set(chain(conditional.equal, conditional.not_equal, \
						conditional.enabled, conditional.disabled))

					untouchable_flags = \
						frozenset(chain(myparent.use.mask, myparent.use.force))
					if untouchable_flags.intersection(involved_flags):
						continue

					required_use = myparent.metadata["REQUIRED_USE"]
					required_use_warning = ""
					if required_use:
						old_use = self._pkg_use_enabled(myparent)
						new_use = set(self._pkg_use_enabled(myparent))
						for flag in involved_flags:
							if flag in old_use:
								new_use.discard(flag)
							else:
								new_use.add(flag)
						if check_required_use(required_use, old_use, myparent.iuse.is_valid_flag) and \
							not check_required_use(required_use, new_use, myparent.iuse.is_valid_flag):
								required_use_warning = ", this change violates use flag constraints " + \
									"defined by %s: '%s'" % (myparent.cpv, \
									human_readable_required_use(required_use))

					for flag in involved_flags:
						if flag in self._pkg_use_enabled(myparent):
							changes.append(colorize("blue", "-" + flag))
						else:
							changes.append(colorize("red", "+" + flag))
					mreasons.append("Change USE: %s" % " ".join(changes) + required_use_warning)
					if (myparent, mreasons) not in missing_use_reasons:
						missing_use_reasons.append((myparent, mreasons))

		unmasked_use_reasons = [(pkg, mreasons) for (pkg, mreasons) \
			in missing_use_reasons if pkg not in masked_pkg_instances]

		unmasked_iuse_reasons = [(pkg, mreasons) for (pkg, mreasons) \
			in missing_iuse_reasons if pkg not in masked_pkg_instances]

		show_missing_use = False
		if unmasked_use_reasons:
			# Only show the latest version.
			show_missing_use = []
			pkg_reason = None
			parent_reason = None
			for pkg, mreasons in unmasked_use_reasons:
				if pkg is myparent:
					if parent_reason is None:
						#This happens if a use change on the parent
						#leads to a satisfied conditional use dep.
						parent_reason = (pkg, mreasons)
				elif pkg_reason is None:
					#Don't rely on the first pkg in unmasked_use_reasons,
					#being the highest version of the dependency.
					pkg_reason = (pkg, mreasons)
			if pkg_reason:
				show_missing_use.append(pkg_reason)
			if parent_reason:
				show_missing_use.append(parent_reason)

		elif unmasked_iuse_reasons:
			masked_with_iuse = False
			for pkg in masked_pkg_instances:
				#Use atom.unevaluated here, because some flags might have gone
				#lost during evaluation.
				if not pkg.iuse.get_missing_iuse(atom.unevaluated_atom.use.required):
					# Package(s) with required IUSE are masked,
					# so display a normal masking message.
					masked_with_iuse = True
					break
			if not masked_with_iuse:
				show_missing_use = unmasked_iuse_reasons

		mask_docs = False

		if show_missing_use:
			writemsg_stdout("\nemerge: there are no ebuilds built with USE flags to satisfy "+green(xinfo)+".\n", noiselevel=-1)
			writemsg_stdout("!!! One of the following packages is required to complete your request:\n", noiselevel=-1)
			for pkg, mreasons in show_missing_use:
				writemsg_stdout("- "+pkg.cpv+" ("+", ".join(mreasons)+")\n", noiselevel=-1)

		elif masked_packages:
			writemsg_stdout("\n!!! " + \
				colorize("BAD", "All ebuilds that could satisfy ") + \
				colorize("INFORM", xinfo) + \
				colorize("BAD", " have been masked.") + "\n", noiselevel=-1)
			writemsg_stdout("!!! One of the following masked packages is required to complete your request:\n", noiselevel=-1)
			have_eapi_mask = show_masked_packages(masked_packages)
			if have_eapi_mask:
				writemsg_stdout("\n", noiselevel=-1)
				msg = ("The current version of portage supports " + \
					"EAPI '%s'. You must upgrade to a newer version" + \
					" of portage before EAPI masked packages can" + \
					" be installed.") % portage.const.EAPI
				writemsg_stdout("\n".join(textwrap.wrap(msg, 75)), noiselevel=-1)
			writemsg_stdout("\n", noiselevel=-1)
			mask_docs = True
		else:
			writemsg_stdout("\nemerge: there are no ebuilds to satisfy "+green(xinfo)+".\n", noiselevel=-1)

		# Show parent nodes and the argument that pulled them in.
		traversed_nodes = set()
		node = myparent
		if isinstance(myparent, AtomArg):
			# It's redundant to show parent for AtomArg since
			# it's the same as 'xinfo' displayed above.
			node = None
		else:
			node = myparent
		msg = []
		while node is not None:
			traversed_nodes.add(node)
			if isinstance(node, DependencyArg):
				msg.append('(dependency required by "%s")' % \
					colorize('INFORM', _unicode_decode("%s") % (node,)))
			else:
				msg.append('(dependency required by "%s" [%s])' % \
					(colorize('INFORM', _unicode_decode("%s") % \
					(node.cpv,)), node.type_name))

			if node not in self._dynamic_config.digraph:
				# The parent is not in the graph due to backtracking.
				break

			# When traversing to parents, prefer arguments over packages
			# since arguments are root nodes. Never traverse the same
			# package twice, in order to prevent an infinite loop.
			selected_parent = None
			for parent in self._dynamic_config.digraph.parent_nodes(node):
				if parent in traversed_nodes:
					continue
				if isinstance(parent, DependencyArg):
					if self._dynamic_config.digraph.parent_nodes(parent):
						selected_parent = parent
					else:
						msg.append('(dependency required by "%s" [argument])' % \
							colorize('INFORM', _unicode_decode("%s") % (parent,)))
						selected_parent = None
					break
				else:
					selected_parent = parent
			node = selected_parent
		if msg:
			writemsg_stdout("\n".join(msg), noiselevel=-1)
			writemsg_stdout("\n", noiselevel=-1)

		if mask_docs:
			show_mask_docs()
			writemsg_stdout("\n", noiselevel=-1)

	def _iter_match_pkgs_any(self, root_config, atom, onlydeps=False):
		for db, pkg_type, built, installed, db_keys in \
			self._dynamic_config._filtered_trees[root_config.root]["dbs"]:
			for pkg in self._iter_match_pkgs(root_config,
				pkg_type, atom, onlydeps=onlydeps):
				yield pkg

	def _iter_match_pkgs(self, root_config, pkg_type, atom, onlydeps=False):
		"""
		Iterate over Package instances of pkg_type matching the given atom.
		This does not check visibility and it also does not match USE for
		unbuilt ebuilds since USE are lazily calculated after visibility
		checks (to avoid the expense when possible).
		"""

		db = root_config.trees[self.pkg_tree_map[pkg_type]].dbapi

		if hasattr(db, "xmatch"):
			# For portdbapi we match only against the cpv, in order
			# to bypass unnecessary cache access for things like IUSE
			# and SLOT. Later, we cache the metadata in a Package
			# instance, and use that for further matching. This
			# optimization is especially relevant since
			# pordbapi.aux_get() does not cache calls that have
			# myrepo or mytree arguments.
			cpv_list = db.xmatch("match-all-cpv-only", atom)
		else:
			cpv_list = db.match(atom)

		# USE=multislot can make an installed package appear as if
		# it doesn't satisfy a slot dependency. Rebuilding the ebuild
		# won't do any good as long as USE=multislot is enabled since
		# the newly built package still won't have the expected slot.
		# Therefore, assume that such SLOT dependencies are already
		# satisfied rather than forcing a rebuild.
		installed = pkg_type == 'installed'
		if installed and not cpv_list and atom.slot:
			for cpv in db.match(atom.cp):
				slot_available = False
				for other_db, other_type, other_built, \
					other_installed, other_keys in \
					self._dynamic_config._filtered_trees[root_config.root]["dbs"]:
					try:
						if atom.slot == \
							other_db.aux_get(cpv, ["SLOT"])[0]:
							slot_available = True
							break
					except KeyError:
						pass
				if not slot_available:
					continue
				inst_pkg = self._pkg(cpv, "installed",
					root_config, installed=installed, myrepo = atom.repo)
				# Remove the slot from the atom and verify that
				# the package matches the resulting atom.
				if portage.match_from_list(
					atom.without_slot, [inst_pkg]):
					yield inst_pkg
					return

		if cpv_list:
			atom_set = InternalPackageSet(initial_atoms=(atom,),
				allow_repo=True)
			if atom.repo is None and hasattr(db, "getRepositories"):
				repo_list = db.getRepositories()
			else:
				repo_list = [atom.repo]

			# descending order
			cpv_list.reverse()
			for cpv in cpv_list:
				for repo in repo_list:

					try:
						pkg = self._pkg(cpv, pkg_type, root_config,
							installed=installed, onlydeps=onlydeps, myrepo=repo)
					except portage.exception.PackageNotFound:
						pass
					else:
						# A cpv can be returned from dbapi.match() as an
						# old-style virtual match even in cases when the
						# package does not actually PROVIDE the virtual.
						# Filter out any such false matches here.

						# Make sure that cpv from the current repo satisfies the atom.
						# This might not be the case if there are several repos with
						# the same cpv, but different metadata keys, like SLOT.
						# Also, for portdbapi, parts of the match that require
						# metadata access are deferred until we have cached the
						# metadata in a Package instance.
						if not atom_set.findAtomForPackage(pkg,
							modified_use=self._pkg_use_enabled(pkg)):
							continue
						yield pkg

	def _select_pkg_highest_available(self, root, atom, onlydeps=False):
		cache_key = (root, atom, onlydeps)
		ret = self._dynamic_config._highest_pkg_cache.get(cache_key)
		if ret is not None:
			pkg, existing = ret
			if pkg and not existing:
				existing = self._dynamic_config._slot_pkg_map[root].get(pkg.slot_atom)
				if existing and existing == pkg:
					# Update the cache to reflect that the
					# package has been added to the graph.
					ret = pkg, pkg
					self._dynamic_config._highest_pkg_cache[cache_key] = ret
			return ret
		ret = self._select_pkg_highest_available_imp(root, atom, onlydeps=onlydeps)
		self._dynamic_config._highest_pkg_cache[cache_key] = ret
		pkg, existing = ret
		if pkg is not None:
			settings = pkg.root_config.settings
			if self._pkg_visibility_check(pkg) and not (pkg.installed and \
				settings._getMissingKeywords(pkg.cpv, pkg.metadata)):
				self._dynamic_config._visible_pkgs[pkg.root].cpv_inject(pkg)
		return ret

	def _want_installed_pkg(self, pkg):
		"""
		Given an installed package returned from select_pkg, return
		True if the user has not explicitly requested for this package
		to be replaced (typically via an atom on the command line).
		"""
		if "selective" not in self._dynamic_config.myparams and \
			pkg.root == self._frozen_config.target_root:
			try:
				next(self._iter_atoms_for_pkg(pkg))
			except StopIteration:
				pass
			except portage.exception.InvalidDependString:
				pass
			else:
				return False
		return True

	def _select_pkg_highest_available_imp(self, root, atom, onlydeps=False):
		pkg, existing = self._wrapped_select_pkg_highest_available_imp(root, atom, onlydeps=onlydeps)

		default_selection = (pkg, existing)

		if self._dynamic_config._autounmask is True:
			if pkg is not None and \
				pkg.installed and \
				not self._want_installed_pkg(pkg):
				pkg = None

			for only_use_changes in True, False:
				if pkg is not None:
					break

				pkg, existing = \
					self._wrapped_select_pkg_highest_available_imp(
						root, atom, onlydeps=onlydeps,
						allow_use_changes=True,
						allow_unstable_keywords=(not only_use_changes),
						allow_license_changes=(not only_use_changes))

				if pkg is not None and \
					pkg.installed and \
					not self._want_installed_pkg(pkg):
					pkg = None
			
			if self._dynamic_config._need_restart:
				return None, None

		if pkg is None:
			# This ensures that we can fall back to an installed package
			# that may have been rejected in the autounmask path above.
			return default_selection

		return pkg, existing

	def _pkg_visibility_check(self, pkg, allow_unstable_keywords=False, allow_license_changes=False):

		if pkg.visible:
			return True

		if self._frozen_config.myopts.get('--autounmask', 'n') is not True:
			return False

		pkgsettings = self._frozen_config.pkgsettings[pkg.root]
		root_config = self._frozen_config.roots[pkg.root]
		mreasons = _get_masking_status(pkg, pkgsettings, root_config, use=self._pkg_use_enabled(pkg))

		masked_by_unstable_keywords = False
		missing_licenses = None
		masked_by_something_else = False

		for reason in mreasons:
			hint = reason.unmask_hint

			if hint is None:
				masked_by_something_else = True
			elif hint.key == "unstable keyword":
				masked_by_unstable_keywords = True
			elif hint.key == "license":
				missing_licenses = hint.value
			else:
				masked_by_something_else = True

		if masked_by_something_else:
			return False

		if pkg in self._dynamic_config._needed_unstable_keywords:
			#If the package is already keyworded, remove the mask.
			masked_by_unstable_keywords = False

		if missing_licenses:
			#If the needed licenses are already unmasked, remove the mask.
			missing_licenses.difference_update(self._dynamic_config._needed_license_changes.get(pkg, set()))

		if not (masked_by_unstable_keywords or missing_licenses):
			#Package has already been unmasked.
			return True

		if (masked_by_unstable_keywords and not allow_unstable_keywords) or \
			(missing_licenses and not allow_license_changes):
			#We are not allowed to do the needed changes.
			return False

		if masked_by_unstable_keywords:
			self._dynamic_config._needed_unstable_keywords.add(pkg)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_unstable_keywords", set())
			backtrack_infos["config"]["needed_unstable_keywords"].add(pkg)
			

		if missing_licenses:
			self._dynamic_config._needed_license_changes.setdefault(pkg, set()).update(missing_licenses)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_license_changes", set())
			backtrack_infos["config"]["needed_license_changes"].add((pkg, frozenset(missing_licenses)))

		return True

	def _pkg_use_enabled(self, pkg, target_use=None):
		"""
		If target_use is None, returns pkg.use.enabled + changes in _needed_use_config_changes.
		If target_use is given, the need changes are computed to make the package useable.
		Example: target_use = { "foo": True, "bar": False }
		The flags target_use must be in the pkg's IUSE.
		"""
		needed_use_config_change = self._dynamic_config._needed_use_config_changes.get(pkg)

		if target_use is None:
			if needed_use_config_change is None:
				return pkg.use.enabled
			else:
				return needed_use_config_change[0]

		if needed_use_config_change is not None:
			old_use = needed_use_config_change[0]
			new_use = set()
			old_changes = needed_use_config_change[1]
			new_changes = old_changes.copy()
		else:
			old_use = pkg.use.enabled
			new_use = set()
			old_changes = {}
			new_changes = {}

		for flag, state in target_use.items():
			if state:
				if flag not in old_use:
					if new_changes.get(flag) == False:
						return old_use
					new_changes[flag] = True
				new_use.add(flag)
			else:
				if flag in old_use:
					if new_changes.get(flag) == True:
						return old_use
					new_changes[flag] = False
		new_use.update(old_use.difference(target_use))

		def want_restart_for_use_change(pkg, new_use):
			if pkg not in self._dynamic_config.digraph.nodes:
				return False

			for key in "DEPEND", "RDEPEND", "PDEPEND", "LICENSE":
				dep = pkg.metadata[key]
				old_val = set(portage.dep.use_reduce(dep, pkg.use.enabled, is_valid_flag=pkg.iuse.is_valid_flag, flat=True))
				new_val = set(portage.dep.use_reduce(dep, new_use, is_valid_flag=pkg.iuse.is_valid_flag, flat=True))

				if old_val != new_val:
					return True

			parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
			if not parent_atoms:
				return False

			new_use, changes = self._dynamic_config._needed_use_config_changes.get(pkg)
			for ppkg, atom in parent_atoms:
				if not atom.use or \
					not atom.use.required.intersection(changes):
					continue
				else:
					return True

			return False

		if new_changes != old_changes:
			#Don't do the change if it violates REQUIRED_USE.
			required_use = pkg.metadata["REQUIRED_USE"]
			if required_use and check_required_use(required_use, old_use, pkg.iuse.is_valid_flag) and \
				not check_required_use(required_use, new_use, pkg.iuse.is_valid_flag):
				return old_use

			self._dynamic_config._needed_use_config_changes[pkg] = (new_use, new_changes)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_use_config_changes", [])
			backtrack_infos["config"]["needed_use_config_changes"].append((pkg, (new_use, new_changes)))
			if want_restart_for_use_change(pkg, new_use):
				self._dynamic_config._need_restart = True
		return new_use

	def _wrapped_select_pkg_highest_available_imp(self, root, atom, onlydeps=False, \
		allow_use_changes=False, allow_unstable_keywords=False, allow_license_changes=False):
		root_config = self._frozen_config.roots[root]
		pkgsettings = self._frozen_config.pkgsettings[root]
		dbs = self._dynamic_config._filtered_trees[root]["dbs"]
		vardb = self._frozen_config.roots[root].trees["vartree"].dbapi
		portdb = self._frozen_config.roots[root].trees["porttree"].dbapi
		# List of acceptable packages, ordered by type preference.
		matched_packages = []
		matched_pkgs_ignore_use = []
		highest_version = None
		if not isinstance(atom, portage.dep.Atom):
			atom = portage.dep.Atom(atom)
		atom_cp = atom.cp
		atom_set = InternalPackageSet(initial_atoms=(atom,), allow_repo=True)
		existing_node = None
		myeb = None
		rebuilt_binaries = 'rebuilt_binaries' in self._dynamic_config.myparams
		usepkgonly = "--usepkgonly" in self._frozen_config.myopts
		empty = "empty" in self._dynamic_config.myparams
		selective = "selective" in self._dynamic_config.myparams
		reinstall = False
		noreplace = "--noreplace" in self._frozen_config.myopts
		avoid_update = "--update" not in self._frozen_config.myopts
		dont_miss_updates = "--update" in self._frozen_config.myopts
		use_ebuild_visibility = self._frozen_config.myopts.get(
			'--use-ebuild-visibility', 'n') != 'n'
		# Behavior of the "selective" parameter depends on
		# whether or not a package matches an argument atom.
		# If an installed package provides an old-style
		# virtual that is no longer provided by an available
		# package, the installed package may match an argument
		# atom even though none of the available packages do.
		# Therefore, "selective" logic does not consider
		# whether or not an installed package matches an
		# argument atom. It only considers whether or not
		# available packages match argument atoms, which is
		# represented by the found_available_arg flag.
		found_available_arg = False
		packages_with_invalid_use_config = []
		for find_existing_node in True, False:
			if existing_node:
				break
			for db, pkg_type, built, installed, db_keys in dbs:
				if existing_node:
					break
				if installed and not find_existing_node:
					want_reinstall = reinstall or empty or \
						(found_available_arg and not selective)
					if want_reinstall and matched_packages:
						continue

				# Ignore USE deps for the initial match since we want to
				# ensure that updates aren't missed solely due to the user's
				# USE configuration.
				for pkg in self._iter_match_pkgs(root_config, pkg_type, atom.without_use, 
					onlydeps=onlydeps):
					if pkg in self._dynamic_config._runtime_pkg_mask:
						# The package has been masked by the backtracking logic
						continue

					if not pkg.installed and \
						self._frozen_config.excluded_pkgs.findAtomForPackage(pkg, \
							modified_use=self._pkg_use_enabled(pkg)):
						continue

					if dont_miss_updates:
						# Check if a higher version was rejected due to user
						# USE configuration. The packages_with_invalid_use_config
						# list only contains unbuilt ebuilds since USE can't
						# be changed for built packages.
						higher_version_rejected = False
						for rejected in packages_with_invalid_use_config:
							if rejected.cp != pkg.cp:
								continue
							if rejected > pkg:
								higher_version_rejected = True
								break
						if higher_version_rejected:
							continue

					cpv = pkg.cpv
					# Make --noreplace take precedence over --newuse.
					if not pkg.installed and noreplace and \
						cpv in vardb.match(atom):
						inst_pkg = self._pkg(pkg.cpv, "installed",
							root_config, installed=True)
						if inst_pkg.visible:
							# If the installed version is masked, it may
							# be necessary to look at lower versions,
							# in case there is a visible downgrade.
							continue
					reinstall_for_flags = None

					if not pkg.installed or \
						(matched_packages and not avoid_update):
						# Only enforce visibility on installed packages
						# if there is at least one other visible package
						# available. By filtering installed masked packages
						# here, packages that have been masked since they
						# were installed can be automatically downgraded
						# to an unmasked version.

						if not self._pkg_visibility_check(pkg, \
							allow_unstable_keywords=allow_unstable_keywords,
							allow_license_changes=allow_license_changes):
							continue

						# Enable upgrade or downgrade to a version
						# with visible KEYWORDS when the installed
						# version is masked by KEYWORDS, but never
						# reinstall the same exact version only due
						# to a KEYWORDS mask. See bug #252167.
						if matched_packages:

							different_version = None
							for avail_pkg in matched_packages:
								if not portage.dep.cpvequal(
									pkg.cpv, avail_pkg.cpv):
									different_version = avail_pkg
									break
							if different_version is not None:
								# If the ebuild no longer exists or it's
								# keywords have been dropped, reject built
								# instances (installed or binary).
								# If --usepkgonly is enabled, assume that
								# the ebuild status should be ignored.
								if not use_ebuild_visibility and usepkgonly:
									if installed and \
										pkgsettings._getMissingKeywords(
										pkg.cpv, pkg.metadata):
										continue
								else:
									try:
										pkg_eb = self._pkg(
											pkg.cpv, "ebuild", root_config, myrepo=pkg.repo)
									except portage.exception.PackageNotFound:
										continue
									else:
										if not self._pkg_visibility_check(pkg_eb, \
											allow_unstable_keywords=allow_unstable_keywords,
											allow_license_changes=allow_license_changes):
											continue

					# Calculation of USE for unbuilt ebuilds is relatively
					# expensive, so it is only performed lazily, after the
					# above visibility checks are complete.

					myarg = None
					if root == self._frozen_config.target_root:
						try:
							myarg = next(self._iter_atoms_for_pkg(pkg))
						except StopIteration:
							pass
						except portage.exception.InvalidDependString:
							if not installed:
								# masked by corruption
								continue
					if not installed and myarg:
						found_available_arg = True

					if atom.unevaluated_atom.use:
						#Make sure we don't miss a 'missing IUSE'.
						if pkg.iuse.get_missing_iuse(atom.unevaluated_atom.use.required):
							# Don't add this to packages_with_invalid_use_config
							# since IUSE cannot be adjusted by the user.
							continue

					if atom.use:

						matched_pkgs_ignore_use.append(pkg)
						if allow_use_changes:
							target_use = {}
							for flag in atom.use.enabled:
								target_use[flag] = True
							for flag in atom.use.disabled:
								target_use[flag] = False
							use = self._pkg_use_enabled(pkg, target_use)
						else:
							use = self._pkg_use_enabled(pkg)

						use_match = True
						can_adjust_use = not pkg.built
						missing_enabled = atom.use.missing_enabled.difference(pkg.iuse.all)
						missing_disabled = atom.use.missing_disabled.difference(pkg.iuse.all)

						if atom.use.enabled:
							if atom.use.enabled.intersection(missing_disabled):
								use_match = False
								can_adjust_use = False
							need_enabled = atom.use.enabled.difference(use)
							if need_enabled:
								need_enabled = need_enabled.difference(missing_enabled)
								if need_enabled:
									use_match = False
									if can_adjust_use:
										if pkg.use.mask.intersection(need_enabled):
											can_adjust_use = False

						if atom.use.disabled:
							if atom.use.disabled.intersection(missing_enabled):
								use_match = False
								can_adjust_use = False
							need_disabled = atom.use.disabled.intersection(use)
							if need_disabled:
								need_disabled = need_disabled.difference(missing_disabled)
								if need_disabled:
									use_match = False
									if can_adjust_use:
										if pkg.use.force.difference(
											pkg.use.mask).intersection(need_disabled):
											can_adjust_use = False

						if not use_match:
							if can_adjust_use:
								# Above we must ensure that this package has
								# absolutely no use.force, use.mask, or IUSE
								# issues that the user typically can't make
								# adjustments to solve (see bug #345979).
								# FIXME: Conditional USE deps complicate
								# issues. This code currently excludes cases
								# in which the user can adjust the parent
								# package's USE in order to satisfy the dep.
								packages_with_invalid_use_config.append(pkg)
							continue

					#check REQUIRED_USE constraints
					if not pkg.built and pkg.metadata["REQUIRED_USE"] and \
						eapi_has_required_use(pkg.metadata["EAPI"]):
						required_use = pkg.metadata["REQUIRED_USE"]
						use = self._pkg_use_enabled(pkg)
						try:
							required_use_is_sat = check_required_use(
								pkg.metadata["REQUIRED_USE"], use, pkg.iuse.is_valid_flag)
						except portage.exception.InvalidDependString as e:
							portage.writemsg("!!! Invalid REQUIRED_USE specified by " + \
								"'%s': %s\n" % (pkg.cpv, str(e)), noiselevel=-1)
							del e
							continue
						if not required_use_is_sat:
							continue

					if pkg.cp == atom_cp:
						if highest_version is None:
							highest_version = pkg
						elif pkg > highest_version:
							highest_version = pkg
					# At this point, we've found the highest visible
					# match from the current repo. Any lower versions
					# from this repo are ignored, so this so the loop
					# will always end with a break statement below
					# this point.
					if find_existing_node:
						e_pkg = self._dynamic_config._slot_pkg_map[root].get(pkg.slot_atom)
						if not e_pkg:
							break
						# Use PackageSet.findAtomForPackage()
						# for PROVIDE support.
						if atom_set.findAtomForPackage(e_pkg, modified_use=self._pkg_use_enabled(e_pkg)):
							if highest_version and \
								e_pkg.cp == atom_cp and \
								e_pkg < highest_version and \
								e_pkg.slot_atom != highest_version.slot_atom:
								# There is a higher version available in a
								# different slot, so this existing node is
								# irrelevant.
								pass
							else:
								matched_packages.append(e_pkg)
								existing_node = e_pkg
						break
					# Compare built package to current config and
					# reject the built package if necessary.
					if built and (not installed or matched_pkgs_ignore_use) and \
						("--newuse" in self._frozen_config.myopts or \
						"--reinstall" in self._frozen_config.myopts or \
						"--binpkg-respect-use" in self._frozen_config.myopts):
						iuses = pkg.iuse.all
						old_use = self._pkg_use_enabled(pkg)
						if myeb:
							pkgsettings.setcpv(myeb)
						else:
							pkgsettings.setcpv(pkg)
						now_use = pkgsettings["PORTAGE_USE"].split()
						forced_flags = set()
						forced_flags.update(pkgsettings.useforce)
						forced_flags.update(pkgsettings.usemask)
						cur_iuse = iuses
						if myeb and not usepkgonly:
							cur_iuse = myeb.iuse.all
						if self._reinstall_for_flags(forced_flags,
							old_use, iuses,
							now_use, cur_iuse):
							break
					# Compare current config to installed package
					# and do not reinstall if possible.
					if not installed and \
						("--newuse" in self._frozen_config.myopts or \
						"--reinstall" in self._frozen_config.myopts) and \
						cpv in vardb.match(atom):
						forced_flags = set()
						forced_flags.update(pkg.use.force)
						forced_flags.update(pkg.use.mask)
						inst_pkg = vardb.match_pkgs('=' + pkg.cpv)[0]
						old_use = inst_pkg.use.enabled
						old_iuse = inst_pkg.iuse.all
						cur_use = self._pkg_use_enabled(pkg)
						cur_iuse = pkg.iuse.all
						reinstall_for_flags = \
							self._reinstall_for_flags(
							forced_flags, old_use, old_iuse,
							cur_use, cur_iuse)
						if reinstall_for_flags:
							reinstall = True
					if not built:
						myeb = pkg
					matched_packages.append(pkg)
					if reinstall_for_flags:
						self._dynamic_config._reinstall_nodes[pkg] = \
							reinstall_for_flags
					break

		if not matched_packages:
			return None, None

		if "--debug" in self._frozen_config.myopts:
			for pkg in matched_packages:
				portage.writemsg("%s %s\n" % \
					((pkg.type_name + ":").rjust(10), pkg.cpv), noiselevel=-1)

		# Filter out any old-style virtual matches if they are
		# mixed with new-style virtual matches.
		cp = atom.cp
		if len(matched_packages) > 1 and \
			"virtual" == portage.catsplit(cp)[0]:
			for pkg in matched_packages:
				if pkg.cp != cp:
					continue
				# Got a new-style virtual, so filter
				# out any old-style virtuals.
				matched_packages = [pkg for pkg in matched_packages \
					if pkg.cp == cp]
				break

		if existing_node is not None and \
			existing_node in matched_packages:
			return existing_node, existing_node

		if len(matched_packages) > 1:
			if rebuilt_binaries:
				inst_pkg = None
				built_pkg = None
				for pkg in matched_packages:
					if pkg.installed:
						inst_pkg = pkg
					elif pkg.built:
						built_pkg = pkg
				if built_pkg is not None and inst_pkg is not None:
					# Only reinstall if binary package BUILD_TIME is
					# non-empty, in order to avoid cases like to
					# bug #306659 where BUILD_TIME fields are missing
					# in local and/or remote Packages file.
					try:
						built_timestamp = int(built_pkg.metadata['BUILD_TIME'])
					except (KeyError, ValueError):
						built_timestamp = 0

					try:
						installed_timestamp = int(inst_pkg.metadata['BUILD_TIME'])
					except (KeyError, ValueError):
						installed_timestamp = 0

					if "--rebuilt-binaries-timestamp" in self._frozen_config.myopts:
						minimal_timestamp = self._frozen_config.myopts["--rebuilt-binaries-timestamp"]
						if built_timestamp and \
							built_timestamp > installed_timestamp and \
							built_timestamp >= minimal_timestamp:
							return built_pkg, existing_node
					else:
						#Don't care if the binary has an older BUILD_TIME than the installed
						#package. This is for closely tracking a binhost.
						#Use --rebuilt-binaries-timestamp 0 if you want only newer binaries
						#pulled in here.
						if built_timestamp and \
							built_timestamp != installed_timestamp:
							return built_pkg, existing_node

			for pkg in matched_packages:
				if pkg.installed and pkg.invalid:
					matched_packages = [x for x in \
						matched_packages if x is not pkg]

			if avoid_update:
				for pkg in matched_packages:
					if pkg.installed and self._pkg_visibility_check(pkg, \
						allow_unstable_keywords=allow_unstable_keywords,
						allow_license_changes=allow_license_changes):
						return pkg, existing_node

			bestmatch = portage.best(
				[pkg.cpv for pkg in matched_packages \
					if self._pkg_visibility_check(pkg, allow_unstable_keywords=allow_unstable_keywords,
						allow_license_changes=allow_license_changes)])
			if not bestmatch:
				# all are masked, so ignore visibility
				bestmatch = portage.best(
					[pkg.cpv for pkg in matched_packages])
			matched_packages = [pkg for pkg in matched_packages \
				if portage.dep.cpvequal(pkg.cpv, bestmatch)]

		# ordered by type preference ("ebuild" type is the last resort)
		return  matched_packages[-1], existing_node

	def _select_pkg_from_graph(self, root, atom, onlydeps=False):
		"""
		Select packages that have already been added to the graph or
		those that are installed and have not been scheduled for
		replacement.
		"""
		graph_db = self._dynamic_config._graph_trees[root]["porttree"].dbapi
		matches = graph_db.match_pkgs(atom)
		if not matches:
			return None, None
		pkg = matches[-1] # highest match
		in_graph = self._dynamic_config._slot_pkg_map[root].get(pkg.slot_atom)
		return pkg, in_graph

	def _select_pkg_from_installed(self, root, atom, onlydeps=False):
		"""
		Select packages that are installed.
		"""
		vardb = self._dynamic_config._graph_trees[root]["vartree"].dbapi
		matches = vardb.match_pkgs(atom)
		if not matches:
			return None, None
		if len(matches) > 1:
			unmasked = [pkg for pkg in matches if \
				self._pkg_visibility_check(pkg)]
			if unmasked:
				if len(unmasked) == 1:
					matches = unmasked
				else:
					# Account for packages with masks (like KEYWORDS masks)
					# that are usually ignored in visibility checks for
					# installed packages, in order to handle cases like
					# bug #350285.
					unmasked = [pkg for pkg in matches if not pkg.masks]
					if unmasked:
						matches = unmasked
		pkg = matches[-1] # highest match
		in_graph = self._dynamic_config._slot_pkg_map[root].get(pkg.slot_atom)
		return pkg, in_graph

	def _complete_graph(self, required_sets=None):
		"""
		Add any deep dependencies of required sets (args, system, world) that
		have not been pulled into the graph yet. This ensures that the graph
		is consistent such that initially satisfied deep dependencies are not
		broken in the new graph. Initially unsatisfied dependencies are
		irrelevant since we only want to avoid breaking dependencies that are
		initially satisfied.

		Since this method can consume enough time to disturb users, it is
		currently only enabled by the --complete-graph option.

		@param required_sets: contains required sets (currently only used
			for depclean and prune removal operations)
		@type required_sets: dict
		"""
		if "--buildpkgonly" in self._frozen_config.myopts or \
			"recurse" not in self._dynamic_config.myparams:
			return 1

		if "complete" not in self._dynamic_config.myparams:
			# Skip this to avoid consuming enough time to disturb users.
			return 1

		self._load_vdb()

		# Put the depgraph into a mode that causes it to only
		# select packages that have already been added to the
		# graph or those that are installed and have not been
		# scheduled for replacement. Also, toggle the "deep"
		# parameter so that all dependencies are traversed and
		# accounted for.
		self._select_atoms = self._select_atoms_from_graph
		if "remove" in self._dynamic_config.myparams:
			self._select_package = self._select_pkg_from_installed
		else:
			self._select_package = self._select_pkg_from_graph
		already_deep = self._dynamic_config.myparams.get("deep") is True
		if not already_deep:
			self._dynamic_config.myparams["deep"] = True

		# Invalidate the package selection cache, since
		# _select_package has just changed implementations.
		for trees in self._dynamic_config._filtered_trees.values():
			trees["porttree"].dbapi._clear_cache()

		args = self._dynamic_config._initial_arg_list[:]
		for root in self._frozen_config.roots:
			if root != self._frozen_config.target_root and \
				"remove" in self._dynamic_config.myparams:
				# Only pull in deps for the relevant root.
				continue
			depgraph_sets = self._dynamic_config.sets[root]
			required_set_names = self._frozen_config._required_set_names.copy()
			remaining_args = required_set_names.copy()
			if required_sets is None or root not in required_sets:
				pass
			else:
				# Removal actions may override sets with temporary
				# replacements that have had atoms removed in order
				# to implement --deselect behavior.
				required_set_names = set(required_sets[root])
				depgraph_sets.sets.clear()
				depgraph_sets.sets.update(required_sets[root])
			if "remove" not in self._dynamic_config.myparams and \
				root == self._frozen_config.target_root and \
				(already_deep or "empty" in self._dynamic_config.myparams):
				remaining_args.difference_update(depgraph_sets.sets)
			if not remaining_args and \
				not self._dynamic_config._ignored_deps and \
				not self._dynamic_config._dep_stack:
				continue
			root_config = self._frozen_config.roots[root]
			for s in required_set_names:
				pset = depgraph_sets.sets.get(s)
				if pset is None:
					pset = root_config.sets[s]
				atom = SETPREFIX + s
				args.append(SetArg(arg=atom, pset=pset,
					root_config=root_config))

		self._set_args(args)
		for arg in self._expand_set_args(args, add_to_digraph=True):
			for atom in arg.pset.getAtoms():
				self._dynamic_config._dep_stack.append(
					Dependency(atom=atom, root=arg.root_config.root,
						parent=arg))

		if True:
			if self._dynamic_config._ignored_deps:
				self._dynamic_config._dep_stack.extend(self._dynamic_config._ignored_deps)
				self._dynamic_config._ignored_deps = []
			if not self._create_graph(allow_unsatisfied=True):
				return 0
			# Check the unsatisfied deps to see if any initially satisfied deps
			# will become unsatisfied due to an upgrade. Initially unsatisfied
			# deps are irrelevant since we only want to avoid breaking deps
			# that are initially satisfied.
			while self._dynamic_config._unsatisfied_deps:
				dep = self._dynamic_config._unsatisfied_deps.pop()
				vardb = self._frozen_config.roots[
					dep.root].trees["vartree"].dbapi
				matches = vardb.match_pkgs(dep.atom)
				if not matches:
					self._dynamic_config._initially_unsatisfied_deps.append(dep)
					continue
				# An scheduled installation broke a deep dependency.
				# Add the installed package to the graph so that it
				# will be appropriately reported as a slot collision
				# (possibly solvable via backtracking).
				pkg = matches[-1] # highest match
				if not self._add_pkg(pkg, dep):
					return 0
				if not self._create_graph(allow_unsatisfied=True):
					return 0
		return 1

	def _pkg(self, cpv, type_name, root_config, installed=False, 
		onlydeps=False, myrepo = None):
		"""
		Get a package instance from the cache, or create a new
		one if necessary. Raises PackageNotFound from aux_get if it
		failures for some reason (package does not exist or is
		corrupt).
		"""
		if type_name != "ebuild":
			# For installed (and binary) packages we don't care for the repo
			# when it comes to hashing, because there can only be one cpv.
			# So overwrite the repo_key with type_name.
			repo_key = type_name
			myrepo = None
		elif myrepo is None:
			raise AssertionError(
				"depgraph._pkg() called without 'myrepo' argument")
		else:
			repo_key = myrepo

		operation = "merge"
		if installed or onlydeps:
			operation = "nomerge"
		# Ensure that we use the specially optimized RootConfig instance
		# that refers to FakeVartree instead of the real vartree.
		root_config = self._frozen_config.roots[root_config.root]
		pkg = self._frozen_config._pkg_cache.get(
			(type_name, root_config.root, cpv, operation, repo_key))
		if pkg is None and onlydeps and not installed:
			# Maybe it already got pulled in as a "merge" node.
			pkg = self._dynamic_config.mydbapi[root_config.root].get(
				(type_name, root_config.root, cpv, 'merge', repo_key))

		if pkg is None:
			tree_type = self.pkg_tree_map[type_name]
			db = root_config.trees[tree_type].dbapi
			db_keys = list(self._frozen_config._trees_orig[root_config.root][
				tree_type].dbapi._aux_cache_keys)

			try:
				metadata = zip(db_keys, db.aux_get(cpv, db_keys, myrepo=myrepo))
			except KeyError:
				raise portage.exception.PackageNotFound(cpv)

			pkg = Package(built=(type_name != "ebuild"), cpv=cpv,
				installed=installed, metadata=metadata, onlydeps=onlydeps,
				root_config=root_config, type_name=type_name)

			self._frozen_config._pkg_cache[pkg] = pkg

			if not self._pkg_visibility_check(pkg) and \
				'LICENSE' in pkg.masks and len(pkg.masks) == 1:
				slot_key = (pkg.root, pkg.slot_atom)
				other_pkg = self._frozen_config._highest_license_masked.get(slot_key)
				if other_pkg is None or pkg > other_pkg:
					self._frozen_config._highest_license_masked[slot_key] = pkg

		return pkg

	def _validate_blockers(self):
		"""Remove any blockers from the digraph that do not match any of the
		packages within the graph.  If necessary, create hard deps to ensure
		correct merge order such that mutually blocking packages are never
		installed simultaneously."""

		if "--buildpkgonly" in self._frozen_config.myopts or \
			"--nodeps" in self._frozen_config.myopts:
			return True

		complete = "complete" in self._dynamic_config.myparams
		deep = "deep" in self._dynamic_config.myparams

		if True:
			# Pull in blockers from all installed packages that haven't already
			# been pulled into the depgraph.  This is not enabled by default
			# due to the performance penalty that is incurred by all the
			# additional dep_check calls that are required.

			# For installed packages, always ignore blockers from DEPEND since
			# only runtime dependencies should be relevant for packages that
			# are already built.
			dep_keys = ["RDEPEND", "PDEPEND"]
			for myroot in self._frozen_config.trees:
				vardb = self._frozen_config.trees[myroot]["vartree"].dbapi
				portdb = self._frozen_config.trees[myroot]["porttree"].dbapi
				pkgsettings = self._frozen_config.pkgsettings[myroot]
				root_config = self._frozen_config.roots[myroot]
				dbs = self._dynamic_config._filtered_trees[myroot]["dbs"]
				final_db = self._dynamic_config.mydbapi[myroot]

				blocker_cache = BlockerCache(myroot, vardb)
				stale_cache = set(blocker_cache)
				for pkg in vardb:
					cpv = pkg.cpv
					stale_cache.discard(cpv)
					pkg_in_graph = self._dynamic_config.digraph.contains(pkg)
					pkg_deps_added = \
						pkg in self._dynamic_config._traversed_pkg_deps

					# Check for masked installed packages. Only warn about
					# packages that are in the graph in order to avoid warning
					# about those that will be automatically uninstalled during
					# the merge process or by --depclean. Always warn about
					# packages masked by license, since the user likely wants
					# to adjust ACCEPT_LICENSE.
					if pkg in final_db:
						if not self._pkg_visibility_check(pkg) and \
							(pkg_in_graph or 'LICENSE' in pkg.masks):
							self._dynamic_config._masked_installed.add(pkg)
						else:
							self._check_masks(pkg)

					blocker_atoms = None
					blockers = None
					if pkg_deps_added:
						blockers = []
						try:
							blockers.extend(
								self._dynamic_config._blocker_parents.child_nodes(pkg))
						except KeyError:
							pass
						try:
							blockers.extend(
								self._dynamic_config._irrelevant_blockers.child_nodes(pkg))
						except KeyError:
							pass
						if blockers:
							# Select just the runtime blockers.
							blockers = [blocker for blocker in blockers \
								if blocker.priority.runtime or \
								blocker.priority.runtime_post]
					if blockers is not None:
						blockers = set(blocker.atom for blocker in blockers)

					# If this node has any blockers, create a "nomerge"
					# node for it so that they can be enforced.
					self._spinner_update()
					blocker_data = blocker_cache.get(cpv)
					if blocker_data is not None and \
						blocker_data.counter != long(pkg.metadata["COUNTER"]):
						blocker_data = None

					# If blocker data from the graph is available, use
					# it to validate the cache and update the cache if
					# it seems invalid.
					if blocker_data is not None and \
						blockers is not None:
						if not blockers.symmetric_difference(
							blocker_data.atoms):
							continue
						blocker_data = None

					if blocker_data is None and \
						blockers is not None:
						# Re-use the blockers from the graph.
						blocker_atoms = sorted(blockers)
						counter = long(pkg.metadata["COUNTER"])
						blocker_data = \
							blocker_cache.BlockerData(counter, blocker_atoms)
						blocker_cache[pkg.cpv] = blocker_data
						continue

					if blocker_data:
						blocker_atoms = [Atom(atom) for atom in blocker_data.atoms]
					else:
						# Use aux_get() to trigger FakeVartree global
						# updates on *DEPEND when appropriate.
						depstr = " ".join(vardb.aux_get(pkg.cpv, dep_keys))
						# It is crucial to pass in final_db here in order to
						# optimize dep_check calls by eliminating atoms via
						# dep_wordreduce and dep_eval calls.
						try:
							success, atoms = portage.dep_check(depstr,
								final_db, pkgsettings, myuse=self._pkg_use_enabled(pkg),
								trees=self._dynamic_config._graph_trees, myroot=myroot)
						except SystemExit:
							raise
						except Exception as e:
							# This is helpful, for example, if a ValueError
							# is thrown from cpv_expand due to multiple
							# matches (this can happen if an atom lacks a
							# category).
							show_invalid_depstring_notice(
								pkg, depstr, str(e))
							del e
							raise
						if not success:
							replacement_pkg = final_db.match_pkgs(pkg.slot_atom)
							if replacement_pkg and \
								replacement_pkg[0].operation == "merge":
								# This package is being replaced anyway, so
								# ignore invalid dependencies so as not to
								# annoy the user too much (otherwise they'd be
								# forced to manually unmerge it first).
								continue
							show_invalid_depstring_notice(pkg, depstr, atoms)
							return False
						blocker_atoms = [myatom for myatom in atoms \
							if myatom.blocker]
						blocker_atoms.sort()
						counter = long(pkg.metadata["COUNTER"])
						blocker_cache[cpv] = \
							blocker_cache.BlockerData(counter, blocker_atoms)
					if blocker_atoms:
						try:
							for atom in blocker_atoms:
								blocker = Blocker(atom=atom,
									eapi=pkg.metadata["EAPI"],
									priority=self._priority(runtime=True),
									root=myroot)
								self._dynamic_config._blocker_parents.add(blocker, pkg)
						except portage.exception.InvalidAtom as e:
							depstr = " ".join(vardb.aux_get(pkg.cpv, dep_keys))
							show_invalid_depstring_notice(
								pkg, depstr, "Invalid Atom: %s" % (e,))
							return False
				for cpv in stale_cache:
					del blocker_cache[cpv]
				blocker_cache.flush()
				del blocker_cache

		# Discard any "uninstall" tasks scheduled by previous calls
		# to this method, since those tasks may not make sense given
		# the current graph state.
		previous_uninstall_tasks = self._dynamic_config._blocker_uninstalls.leaf_nodes()
		if previous_uninstall_tasks:
			self._dynamic_config._blocker_uninstalls = digraph()
			self._dynamic_config.digraph.difference_update(previous_uninstall_tasks)

		for blocker in self._dynamic_config._blocker_parents.leaf_nodes():
			self._spinner_update()
			root_config = self._frozen_config.roots[blocker.root]
			virtuals = root_config.settings.getvirtuals()
			myroot = blocker.root
			initial_db = self._frozen_config.trees[myroot]["vartree"].dbapi
			final_db = self._dynamic_config.mydbapi[myroot]
			
			provider_virtual = False
			if blocker.cp in virtuals and \
				not self._have_new_virt(blocker.root, blocker.cp):
				provider_virtual = True

			# Use this to check PROVIDE for each matched package
			# when necessary.
			atom_set = InternalPackageSet(
				initial_atoms=[blocker.atom])

			if provider_virtual:
				atoms = []
				for provider_entry in virtuals[blocker.cp]:
					atoms.append(Atom(blocker.atom.replace(
						blocker.cp, provider_entry.cp, 1)))
			else:
				atoms = [blocker.atom]

			blocked_initial = set()
			for atom in atoms:
				for pkg in initial_db.match_pkgs(atom):
					if atom_set.findAtomForPackage(pkg, modified_use=self._pkg_use_enabled(pkg)):
						blocked_initial.add(pkg)

			blocked_final = set()
			for atom in atoms:
				for pkg in final_db.match_pkgs(atom):
					if atom_set.findAtomForPackage(pkg, modified_use=self._pkg_use_enabled(pkg)):
						blocked_final.add(pkg)

			if not blocked_initial and not blocked_final:
				parent_pkgs = self._dynamic_config._blocker_parents.parent_nodes(blocker)
				self._dynamic_config._blocker_parents.remove(blocker)
				# Discard any parents that don't have any more blockers.
				for pkg in parent_pkgs:
					self._dynamic_config._irrelevant_blockers.add(blocker, pkg)
					if not self._dynamic_config._blocker_parents.child_nodes(pkg):
						self._dynamic_config._blocker_parents.remove(pkg)
				continue
			for parent in self._dynamic_config._blocker_parents.parent_nodes(blocker):
				unresolved_blocks = False
				depends_on_order = set()
				for pkg in blocked_initial:
					if pkg.slot_atom == parent.slot_atom and \
						not blocker.atom.blocker.overlap.forbid:
						# New !!atom blockers do not allow temporary
						# simulaneous installation, so unlike !atom
						# blockers, !!atom blockers aren't ignored
						# when they match other packages occupying
						# the same slot.
						continue
					if parent.installed:
						# Two currently installed packages conflict with
						# eachother. Ignore this case since the damage
						# is already done and this would be likely to
						# confuse users if displayed like a normal blocker.
						continue

					self._dynamic_config._blocked_pkgs.add(pkg, blocker)

					if parent.operation == "merge":
						# Maybe the blocked package can be replaced or simply
						# unmerged to resolve this block.
						depends_on_order.add((pkg, parent))
						continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True
				for pkg in blocked_final:
					if pkg.slot_atom == parent.slot_atom and \
						not blocker.atom.blocker.overlap.forbid:
						# New !!atom blockers do not allow temporary
						# simulaneous installation, so unlike !atom
						# blockers, !!atom blockers aren't ignored
						# when they match other packages occupying
						# the same slot.
						continue
					if parent.operation == "nomerge" and \
						pkg.operation == "nomerge":
						# This blocker will be handled the next time that a
						# merge of either package is triggered.
						continue

					self._dynamic_config._blocked_pkgs.add(pkg, blocker)

					# Maybe the blocking package can be
					# unmerged to resolve this block.
					if parent.operation == "merge" and pkg.installed:
						depends_on_order.add((pkg, parent))
						continue
					elif parent.operation == "nomerge":
						depends_on_order.add((parent, pkg))
						continue
					# None of the above blocker resolutions techniques apply,
					# so apparently this one is unresolvable.
					unresolved_blocks = True

				# Make sure we don't unmerge any package that have been pulled
				# into the graph.
				if not unresolved_blocks and depends_on_order:
					for inst_pkg, inst_task in depends_on_order:
						if self._dynamic_config.digraph.contains(inst_pkg) and \
							self._dynamic_config.digraph.parent_nodes(inst_pkg):
							unresolved_blocks = True
							break

				if not unresolved_blocks and depends_on_order:
					for inst_pkg, inst_task in depends_on_order:
						uninst_task = Package(built=inst_pkg.built,
							cpv=inst_pkg.cpv, installed=inst_pkg.installed,
							metadata=inst_pkg.metadata,
							operation="uninstall",
							root_config=inst_pkg.root_config,
							type_name=inst_pkg.type_name)
						# Enforce correct merge order with a hard dep.
						self._dynamic_config.digraph.addnode(uninst_task, inst_task,
							priority=BlockerDepPriority.instance)
						# Count references to this blocker so that it can be
						# invalidated after nodes referencing it have been
						# merged.
						self._dynamic_config._blocker_uninstalls.addnode(uninst_task, blocker)
				if not unresolved_blocks and not depends_on_order:
					self._dynamic_config._irrelevant_blockers.add(blocker, parent)
					self._dynamic_config._blocker_parents.remove_edge(blocker, parent)
					if not self._dynamic_config._blocker_parents.parent_nodes(blocker):
						self._dynamic_config._blocker_parents.remove(blocker)
					if not self._dynamic_config._blocker_parents.child_nodes(parent):
						self._dynamic_config._blocker_parents.remove(parent)
				if unresolved_blocks:
					self._dynamic_config._unsolvable_blockers.add(blocker, parent)

		return True

	def _accept_blocker_conflicts(self):
		acceptable = False
		for x in ("--buildpkgonly", "--fetchonly",
			"--fetch-all-uri", "--nodeps"):
			if x in self._frozen_config.myopts:
				acceptable = True
				break
		return acceptable

	def _merge_order_bias(self, mygraph):
		"""
		For optimal leaf node selection, promote deep system runtime deps and
		order nodes from highest to lowest overall reference count.
		"""

		node_info = {}
		for node in mygraph.order:
			node_info[node] = len(mygraph.parent_nodes(node))
		deep_system_deps = _find_deep_system_runtime_deps(mygraph)

		def cmp_merge_preference(node1, node2):

			if node1.operation == 'uninstall':
				if node2.operation == 'uninstall':
					return 0
				return 1

			if node2.operation == 'uninstall':
				if node1.operation == 'uninstall':
					return 0
				return -1

			node1_sys = node1 in deep_system_deps
			node2_sys = node2 in deep_system_deps
			if node1_sys != node2_sys:
				if node1_sys:
					return -1
				return 1

			return node_info[node2] - node_info[node1]

		mygraph.order.sort(key=cmp_sort_key(cmp_merge_preference))

	def altlist(self, reversed=False):

		while self._dynamic_config._serialized_tasks_cache is None:
			self._resolve_conflicts()
			try:
				self._dynamic_config._serialized_tasks_cache, self._dynamic_config._scheduler_graph = \
					self._serialize_tasks()
			except self._serialize_tasks_retry:
				pass

		retlist = self._dynamic_config._serialized_tasks_cache[:]
		if reversed:
			retlist.reverse()
		return retlist

	def schedulerGraph(self):
		"""
		The scheduler graph is identical to the normal one except that
		uninstall edges are reversed in specific cases that require
		conflicting packages to be temporarily installed simultaneously.
		This is intended for use by the Scheduler in it's parallelization
		logic. It ensures that temporary simultaneous installation of
		conflicting packages is avoided when appropriate (especially for
		!!atom blockers), but allowed in specific cases that require it.

		Note that this method calls break_refs() which alters the state of
		internal Package instances such that this depgraph instance should
		not be used to perform any more calculations.
		"""

		# NOTE: altlist initializes self._dynamic_config._scheduler_graph
		mergelist = self.altlist()
		self.break_refs(mergelist)
		self.break_refs(self._dynamic_config._scheduler_graph.order)

		# Break DepPriority.satisfied attributes which reference
		# installed Package instances.
		for parents, children, node in \
			self._dynamic_config._scheduler_graph.nodes.values():
			for priorities in chain(parents.values(), children.values()):
				for priority in priorities:
					if priority.satisfied:
						priority.satisfied = True

		pkg_cache = self._frozen_config._pkg_cache
		graph = self._dynamic_config._scheduler_graph
		trees = self._frozen_config.trees
		pruned_pkg_cache = {}
		for key, pkg in pkg_cache.items():
			if pkg in graph or \
				(pkg.installed and pkg in trees[pkg.root]['vartree'].dbapi):
				pruned_pkg_cache[key] = pkg

		for root in trees:
			trees[root]['vartree']._pkg_cache = pruned_pkg_cache
			self.break_refs(trees[root]['vartree'].dbapi)

		self.break_refs(pruned_pkg_cache.values())
		sched_config = \
			_scheduler_graph_config(trees, pruned_pkg_cache, graph, mergelist)

		return sched_config

	def break_refs(self, nodes):
		"""
		Take a mergelist like that returned from self.altlist() and
		break any references that lead back to the depgraph. This is
		useful if you want to hold references to packages without
		also holding the depgraph on the heap.
		"""
		for node in nodes:
			if hasattr(node, "root_config"):
				# The FakeVartree references the _package_cache which
				# references the depgraph. So that Package instances don't
				# hold the depgraph and FakeVartree on the heap, replace
				# the RootConfig that references the FakeVartree with the
				# original RootConfig instance which references the actual
				# vartree.
				node.root_config = \
					self._frozen_config._trees_orig[node.root_config.root]["root_config"]

	def _resolve_conflicts(self):
		if not self._complete_graph():
			raise self._unknown_internal_error()

		if not self._validate_blockers():
			raise self._unknown_internal_error()

		if self._dynamic_config._slot_collision_info:
			self._process_slot_conflicts()

	def _serialize_tasks(self):

		if "--debug" in self._frozen_config.myopts:
			writemsg("\ndigraph:\n\n", noiselevel=-1)
			self._dynamic_config.digraph.debug_print()
			writemsg("\n", noiselevel=-1)

		scheduler_graph = self._dynamic_config.digraph.copy()

		if '--nodeps' in self._frozen_config.myopts:
			# Preserve the package order given on the command line.
			return ([node for node in scheduler_graph \
				if isinstance(node, Package) \
				and node.operation == 'merge'], scheduler_graph)

		mygraph=self._dynamic_config.digraph.copy()

		removed_nodes = set()

		# Prune off all DependencyArg instances since they aren't
		# needed, and because of nested sets this is faster than doing
		# it with multiple digraph.root_nodes() calls below. This also
		# takes care of nested sets that have circular references,
		# which wouldn't be matched by digraph.root_nodes().
		for node in mygraph:
			if isinstance(node, DependencyArg):
				removed_nodes.add(node)
		if removed_nodes:
			mygraph.difference_update(removed_nodes)
			removed_nodes.clear()

		# Prune "nomerge" root nodes if nothing depends on them, since
		# otherwise they slow down merge order calculation. Don't remove
		# non-root nodes since they help optimize merge order in some cases
		# such as revdep-rebuild.

		while True:
			for node in mygraph.root_nodes():
				if not isinstance(node, Package) or \
					node.installed or node.onlydeps:
					removed_nodes.add(node)
			if removed_nodes:
				self._spinner_update()
				mygraph.difference_update(removed_nodes)
			if not removed_nodes:
				break
			removed_nodes.clear()
		self._merge_order_bias(mygraph)
		def cmp_circular_bias(n1, n2):
			"""
			RDEPEND is stronger than PDEPEND and this function
			measures such a strength bias within a circular
			dependency relationship.
			"""
			n1_n2_medium = n2 in mygraph.child_nodes(n1,
				ignore_priority=priority_range.ignore_medium_soft)
			n2_n1_medium = n1 in mygraph.child_nodes(n2,
				ignore_priority=priority_range.ignore_medium_soft)
			if n1_n2_medium == n2_n1_medium:
				return 0
			elif n1_n2_medium:
				return 1
			return -1
		myblocker_uninstalls = self._dynamic_config._blocker_uninstalls.copy()
		retlist=[]
		# Contains uninstall tasks that have been scheduled to
		# occur after overlapping blockers have been installed.
		scheduled_uninstalls = set()
		# Contains any Uninstall tasks that have been ignored
		# in order to avoid the circular deps code path. These
		# correspond to blocker conflicts that could not be
		# resolved.
		ignored_uninstall_tasks = set()
		have_uninstall_task = False
		complete = "complete" in self._dynamic_config.myparams
		asap_nodes = []

		def get_nodes(**kwargs):
			"""
			Returns leaf nodes excluding Uninstall instances
			since those should be executed as late as possible.
			"""
			return [node for node in mygraph.leaf_nodes(**kwargs) \
				if isinstance(node, Package) and \
					(node.operation != "uninstall" or \
					node in scheduled_uninstalls)]

		# sys-apps/portage needs special treatment if ROOT="/"
		running_root = self._frozen_config._running_root.root
		runtime_deps = InternalPackageSet(
			initial_atoms=[PORTAGE_PACKAGE_ATOM])
		running_portage = self._frozen_config.trees[running_root]["vartree"].dbapi.match_pkgs(
			PORTAGE_PACKAGE_ATOM)
		replacement_portage = self._dynamic_config.mydbapi[running_root].match_pkgs(
			PORTAGE_PACKAGE_ATOM)

		if running_portage:
			running_portage = running_portage[0]
		else:
			running_portage = None

		if replacement_portage:
			replacement_portage = replacement_portage[0]
		else:
			replacement_portage = None

		if replacement_portage == running_portage:
			replacement_portage = None

		if replacement_portage is not None and \
			(running_portage is None or \
			running_portage.cpv != replacement_portage.cpv or \
			'9999' in replacement_portage.cpv or \
			'git' in replacement_portage.inherited):
			# update from running_portage to replacement_portage asap
			asap_nodes.append(replacement_portage)

		if running_portage is not None:
			try:
				portage_rdepend = self._select_atoms_highest_available(
					running_root, running_portage.metadata["RDEPEND"],
					myuse=self._pkg_use_enabled(running_portage),
					parent=running_portage, strict=False)
			except portage.exception.InvalidDependString as e:
				portage.writemsg("!!! Invalid RDEPEND in " + \
					"'%svar/db/pkg/%s/RDEPEND': %s\n" % \
					(running_root, running_portage.cpv, e), noiselevel=-1)
				del e
				portage_rdepend = {running_portage : []}
			for atoms in portage_rdepend.values():
				runtime_deps.update(atom for atom in atoms \
					if not atom.blocker)

		# Merge libc asap, in order to account for implicit
		# dependencies. See bug #303567.
		for root in (running_root,):
			libc_pkg = self._dynamic_config.mydbapi[root].match_pkgs(
				portage.const.LIBC_PACKAGE_ATOM)
			if libc_pkg:
				libc_pkg = libc_pkg[0]
				if libc_pkg.operation == 'merge':
					# Only add a dep when the version changes.
					if not libc_pkg.root_config.trees[
						'vartree'].dbapi.cpv_exists(libc_pkg.cpv):

						# If there's also an os-headers upgrade, we need to
						# pull that in first. See bug #328317.
						os_headers_pkg = self._dynamic_config.mydbapi[root].match_pkgs(
							portage.const.OS_HEADERS_PACKAGE_ATOM)
						if os_headers_pkg:
							os_headers_pkg = os_headers_pkg[0]
							if os_headers_pkg.operation == 'merge':
								# Only add a dep when the version changes.
								if not os_headers_pkg.root_config.trees[
									'vartree'].dbapi.cpv_exists(os_headers_pkg.cpv):
									asap_nodes.append(os_headers_pkg)

						asap_nodes.append(libc_pkg)

		def gather_deps(ignore_priority, mergeable_nodes,
			selected_nodes, node):
			"""
			Recursively gather a group of nodes that RDEPEND on
			eachother. This ensures that they are merged as a group
			and get their RDEPENDs satisfied as soon as possible.
			"""
			if node in selected_nodes:
				return True
			if node not in mergeable_nodes:
				return False
			if node == replacement_portage and \
				mygraph.child_nodes(node,
				ignore_priority=priority_range.ignore_medium_soft):
				# Make sure that portage always has all of it's
				# RDEPENDs installed first.
				return False
			selected_nodes.add(node)
			for child in mygraph.child_nodes(node,
				ignore_priority=ignore_priority):
				if not gather_deps(ignore_priority,
					mergeable_nodes, selected_nodes, child):
					return False
			return True

		def ignore_uninst_or_med(priority):
			if priority is BlockerDepPriority.instance:
				return True
			return priority_range.ignore_medium(priority)

		def ignore_uninst_or_med_soft(priority):
			if priority is BlockerDepPriority.instance:
				return True
			return priority_range.ignore_medium_soft(priority)

		tree_mode = "--tree" in self._frozen_config.myopts
		# Tracks whether or not the current iteration should prefer asap_nodes
		# if available.  This is set to False when the previous iteration
		# failed to select any nodes.  It is reset whenever nodes are
		# successfully selected.
		prefer_asap = True

		# Controls whether or not the current iteration should drop edges that
		# are "satisfied" by installed packages, in order to solve circular
		# dependencies. The deep runtime dependencies of installed packages are
		# not checked in this case (bug #199856), so it must be avoided
		# whenever possible.
		drop_satisfied = False

		# State of variables for successive iterations that loosen the
		# criteria for node selection.
		#
		# iteration   prefer_asap   drop_satisfied
		# 1           True          False
		# 2           False         False
		# 3           False         True
		#
		# If no nodes are selected on the last iteration, it is due to
		# unresolved blockers or circular dependencies.

		while not mygraph.empty():
			self._spinner_update()
			selected_nodes = None
			ignore_priority = None
			if drop_satisfied or (prefer_asap and asap_nodes):
				priority_range = DepPrioritySatisfiedRange
			else:
				priority_range = DepPriorityNormalRange
			if prefer_asap and asap_nodes:
				# ASAP nodes are merged before their soft deps. Go ahead and
				# select root nodes here if necessary, since it's typical for
				# the parent to have been removed from the graph already.
				asap_nodes = [node for node in asap_nodes \
					if mygraph.contains(node)]
				for node in asap_nodes:
					if not mygraph.child_nodes(node,
						ignore_priority=priority_range.ignore_soft):
						selected_nodes = [node]
						asap_nodes.remove(node)
						break
			if not selected_nodes and \
				not (prefer_asap and asap_nodes):
				for i in range(priority_range.NONE,
					priority_range.MEDIUM_SOFT + 1):
					ignore_priority = priority_range.ignore_priority[i]
					nodes = get_nodes(ignore_priority=ignore_priority)
					if nodes:
						# If there is a mixture of merges and uninstalls,
						# do the uninstalls first.
						if len(nodes) > 1:
							good_uninstalls = []
							for node in nodes:
								if node.operation == "uninstall":
									good_uninstalls.append(node)

							if good_uninstalls:
								nodes = good_uninstalls
							else:
								nodes = nodes

						if ignore_priority is None and not tree_mode:
							# Greedily pop all of these nodes since no
							# relationship has been ignored. This optimization
							# destroys --tree output, so it's disabled in tree
							# mode.
							selected_nodes = nodes
						else:
							# For optimal merge order:
							#  * Only pop one node.
							#  * Removing a root node (node without a parent)
							#    will not produce a leaf node, so avoid it.
							#  * It's normal for a selected uninstall to be a
							#    root node, so don't check them for parents.
							for node in nodes:
								if node.operation == "uninstall" or \
									mygraph.parent_nodes(node):
									selected_nodes = [node]
									break

						if selected_nodes:
							break

			if not selected_nodes:
				nodes = get_nodes(ignore_priority=priority_range.ignore_medium)
				if nodes:
					mergeable_nodes = set(nodes)
					if prefer_asap and asap_nodes:
						nodes = asap_nodes
					for i in range(priority_range.SOFT,
						priority_range.MEDIUM_SOFT + 1):
						ignore_priority = priority_range.ignore_priority[i]
						for node in nodes:
							if not mygraph.parent_nodes(node):
								continue
							selected_nodes = set()
							if gather_deps(ignore_priority,
								mergeable_nodes, selected_nodes, node):
								break
							else:
								selected_nodes = None
						if selected_nodes:
							break

					if prefer_asap and asap_nodes and not selected_nodes:
						# We failed to find any asap nodes to merge, so ignore
						# them for the next iteration.
						prefer_asap = False
						continue

			if selected_nodes and ignore_priority is not None:
				# Try to merge ignored medium_soft deps as soon as possible
				# if they're not satisfied by installed packages.
				for node in selected_nodes:
					children = set(mygraph.child_nodes(node))
					soft = children.difference(
						mygraph.child_nodes(node,
						ignore_priority=DepPrioritySatisfiedRange.ignore_soft))
					medium_soft = children.difference(
						mygraph.child_nodes(node,
							ignore_priority = \
							DepPrioritySatisfiedRange.ignore_medium_soft))
					medium_soft.difference_update(soft)
					for child in medium_soft:
						if child in selected_nodes:
							continue
						if child in asap_nodes:
							continue
						asap_nodes.append(child)

			if selected_nodes and len(selected_nodes) > 1:
				if not isinstance(selected_nodes, list):
					selected_nodes = list(selected_nodes)
				selected_nodes.sort(key=cmp_sort_key(cmp_circular_bias))

			if not selected_nodes and not myblocker_uninstalls.is_empty():
				# An Uninstall task needs to be executed in order to
				# avoid conflict if possible.

				if drop_satisfied:
					priority_range = DepPrioritySatisfiedRange
				else:
					priority_range = DepPriorityNormalRange

				mergeable_nodes = get_nodes(
					ignore_priority=ignore_uninst_or_med)

				min_parent_deps = None
				uninst_task = None

				for task in myblocker_uninstalls.leaf_nodes():
					# Do some sanity checks so that system or world packages
					# don't get uninstalled inappropriately here (only really
					# necessary when --complete-graph has not been enabled).

					if task in ignored_uninstall_tasks:
						continue

					if task in scheduled_uninstalls:
						# It's been scheduled but it hasn't
						# been executed yet due to dependence
						# on installation of blocking packages.
						continue

					root_config = self._frozen_config.roots[task.root]
					inst_pkg = self._pkg(task.cpv, "installed", root_config,
						installed=True)

					if self._dynamic_config.digraph.contains(inst_pkg):
						continue

					forbid_overlap = False
					heuristic_overlap = False
					for blocker in myblocker_uninstalls.parent_nodes(task):
						if not eapi_has_strong_blocks(blocker.eapi):
							heuristic_overlap = True
						elif blocker.atom.blocker.overlap.forbid:
							forbid_overlap = True
							break
					if forbid_overlap and running_root == task.root:
						continue

					if heuristic_overlap and running_root == task.root:
						# Never uninstall sys-apps/portage or it's essential
						# dependencies, except through replacement.
						try:
							runtime_dep_atoms = \
								list(runtime_deps.iterAtomsForPackage(task))
						except portage.exception.InvalidDependString as e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							continue

						# Don't uninstall a runtime dep if it appears
						# to be the only suitable one installed.
						skip = False
						vardb = root_config.trees["vartree"].dbapi
						for atom in runtime_dep_atoms:
							other_version = None
							for pkg in vardb.match_pkgs(atom):
								if pkg.cpv == task.cpv and \
									pkg.metadata["COUNTER"] == \
									task.metadata["COUNTER"]:
									continue
								other_version = pkg
								break
							if other_version is None:
								skip = True
								break
						if skip:
							continue

						# For packages in the system set, don't take
						# any chances. If the conflict can't be resolved
						# by a normal replacement operation then abort.
						skip = False
						try:
							for atom in root_config.sets[
								"system"].iterAtomsForPackage(task):
								skip = True
								break
						except portage.exception.InvalidDependString as e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							skip = True
						if skip:
							continue

					# Note that the world check isn't always
					# necessary since self._complete_graph() will
					# add all packages from the system and world sets to the
					# graph. This just allows unresolved conflicts to be
					# detected as early as possible, which makes it possible
					# to avoid calling self._complete_graph() when it is
					# unnecessary due to blockers triggering an abortion.
					if not complete:
						# For packages in the world set, go ahead an uninstall
						# when necessary, as long as the atom will be satisfied
						# in the final state.
						graph_db = self._dynamic_config.mydbapi[task.root]
						skip = False
						try:
							for atom in root_config.sets[
								"selected"].iterAtomsForPackage(task):
								satisfied = False
								for pkg in graph_db.match_pkgs(atom):
									if pkg == inst_pkg:
										continue
									satisfied = True
									break
								if not satisfied:
									skip = True
									self._dynamic_config._blocked_world_pkgs[inst_pkg] = atom
									break
						except portage.exception.InvalidDependString as e:
							portage.writemsg("!!! Invalid PROVIDE in " + \
								"'%svar/db/pkg/%s/PROVIDE': %s\n" % \
								(task.root, task.cpv, e), noiselevel=-1)
							del e
							skip = True
						if skip:
							continue

					# Check the deps of parent nodes to ensure that
					# the chosen task produces a leaf node. Maybe
					# this can be optimized some more to make the
					# best possible choice, but the current algorithm
					# is simple and should be near optimal for most
					# common cases.
					self._spinner_update()
					mergeable_parent = False
					parent_deps = set()
					parent_deps.add(task)
					for parent in mygraph.parent_nodes(task):
						parent_deps.update(mygraph.child_nodes(parent,
							ignore_priority=priority_range.ignore_medium_soft))
						if min_parent_deps is not None and \
							len(parent_deps) >= min_parent_deps:
							# This task is no better than a previously selected
							# task, so abort search now in order to avoid wasting
							# any more cpu time on this task. This increases
							# performance dramatically in cases when there are
							# hundreds of blockers to solve, like when
							# upgrading to a new slot of kde-meta.
							mergeable_parent = None
							break
						if parent in mergeable_nodes and \
							gather_deps(ignore_uninst_or_med_soft,
							mergeable_nodes, set(), parent):
							mergeable_parent = True

					if not mergeable_parent:
						continue

					if min_parent_deps is None or \
						len(parent_deps) < min_parent_deps:
						min_parent_deps = len(parent_deps)
						uninst_task = task

					if uninst_task is not None and min_parent_deps == 1:
						# This is the best possible result, so so abort search
						# now in order to avoid wasting any more cpu time.
						break

				if uninst_task is not None:
					# The uninstall is performed only after blocking
					# packages have been merged on top of it. File
					# collisions between blocking packages are detected
					# and removed from the list of files to be uninstalled.
					scheduled_uninstalls.add(uninst_task)
					parent_nodes = mygraph.parent_nodes(uninst_task)

					# Reverse the parent -> uninstall edges since we want
					# to do the uninstall after blocking packages have
					# been merged on top of it.
					mygraph.remove(uninst_task)
					for blocked_pkg in parent_nodes:
						mygraph.add(blocked_pkg, uninst_task,
							priority=BlockerDepPriority.instance)
						scheduler_graph.remove_edge(uninst_task, blocked_pkg)
						scheduler_graph.add(blocked_pkg, uninst_task,
							priority=BlockerDepPriority.instance)

					# Sometimes a merge node will render an uninstall
					# node unnecessary (due to occupying the same SLOT),
					# and we want to avoid executing a separate uninstall
					# task in that case.
					slot_node = self._dynamic_config.mydbapi[uninst_task.root
						].match_pkgs(uninst_task.slot_atom)
					if slot_node and \
						slot_node[0].operation == "merge":
						mygraph.add(slot_node[0], uninst_task,
							priority=BlockerDepPriority.instance)

					# Reset the state variables for leaf node selection and
					# continue trying to select leaf nodes.
					prefer_asap = True
					drop_satisfied = False
					continue

			if not selected_nodes:
				# Only select root nodes as a last resort. This case should
				# only trigger when the graph is nearly empty and the only
				# remaining nodes are isolated (no parents or children). Since
				# the nodes must be isolated, ignore_priority is not needed.
				selected_nodes = get_nodes()

			if not selected_nodes and not drop_satisfied:
				drop_satisfied = True
				continue

			if not selected_nodes and not myblocker_uninstalls.is_empty():
				# If possible, drop an uninstall task here in order to avoid
				# the circular deps code path. The corresponding blocker will
				# still be counted as an unresolved conflict.
				uninst_task = None
				for node in myblocker_uninstalls.leaf_nodes():
					try:
						mygraph.remove(node)
					except KeyError:
						pass
					else:
						uninst_task = node
						ignored_uninstall_tasks.add(node)
						break

				if uninst_task is not None:
					# Reset the state variables for leaf node selection and
					# continue trying to select leaf nodes.
					prefer_asap = True
					drop_satisfied = False
					continue

			if not selected_nodes:
				self._dynamic_config._circular_deps_for_display = mygraph
				raise self._unknown_internal_error()

			# At this point, we've succeeded in selecting one or more nodes, so
			# reset state variables for leaf node selection.
			prefer_asap = True
			drop_satisfied = False

			mygraph.difference_update(selected_nodes)

			for node in selected_nodes:
				if isinstance(node, Package) and \
					node.operation == "nomerge":
					continue

				# Handle interactions between blockers
				# and uninstallation tasks.
				solved_blockers = set()
				uninst_task = None
				if isinstance(node, Package) and \
					"uninstall" == node.operation:
					have_uninstall_task = True
					uninst_task = node
				else:
					vardb = self._frozen_config.trees[node.root]["vartree"].dbapi
					inst_pkg = vardb.match_pkgs(node.slot_atom)
					if inst_pkg:
						# The package will be replaced by this one, so remove
						# the corresponding Uninstall task if necessary.
						inst_pkg = inst_pkg[0]
						uninst_task = Package(built=inst_pkg.built,
							cpv=inst_pkg.cpv, installed=inst_pkg.installed,
							metadata=inst_pkg.metadata,
							operation="uninstall",
							root_config=inst_pkg.root_config,
							type_name=inst_pkg.type_name)
						try:
							mygraph.remove(uninst_task)
						except KeyError:
							pass

				if uninst_task is not None and \
					uninst_task not in ignored_uninstall_tasks and \
					myblocker_uninstalls.contains(uninst_task):
					blocker_nodes = myblocker_uninstalls.parent_nodes(uninst_task)
					myblocker_uninstalls.remove(uninst_task)
					# Discard any blockers that this Uninstall solves.
					for blocker in blocker_nodes:
						if not myblocker_uninstalls.child_nodes(blocker):
							myblocker_uninstalls.remove(blocker)
							if blocker not in \
								self._dynamic_config._unsolvable_blockers:
								solved_blockers.add(blocker)

				retlist.append(node)

				if (isinstance(node, Package) and \
					"uninstall" == node.operation) or \
					(uninst_task is not None and \
					uninst_task in scheduled_uninstalls):
					# Include satisfied blockers in the merge list
					# since the user might be interested and also
					# it serves as an indicator that blocking packages
					# will be temporarily installed simultaneously.
					for blocker in solved_blockers:
						retlist.append(blocker)

		unsolvable_blockers = set(self._dynamic_config._unsolvable_blockers.leaf_nodes())
		for node in myblocker_uninstalls.root_nodes():
			unsolvable_blockers.add(node)

		# If any Uninstall tasks need to be executed in order
		# to avoid a conflict, complete the graph with any
		# dependencies that may have been initially
		# neglected (to ensure that unsafe Uninstall tasks
		# are properly identified and blocked from execution).
		if have_uninstall_task and \
			not complete and \
			not unsolvable_blockers:
			self._dynamic_config.myparams["complete"] = True
			if '--debug' in self._frozen_config.myopts:
				msg = []
				msg.append("enabling 'complete' depgraph mode " + \
					"due to uninstall task(s):")
				msg.append("")
				for node in retlist:
					if isinstance(node, Package) and \
						node.operation == 'uninstall':
						msg.append("\t%s" % (node,))
				writemsg_level("\n%s\n" % \
					"".join("%s\n" % line for line in msg),
					level=logging.DEBUG, noiselevel=-1)
			raise self._serialize_tasks_retry("")

		# Set satisfied state on blockers, but not before the
		# above retry path, since we don't want to modify the
		# state in that case.
		for node in retlist:
			if isinstance(node, Blocker):
				node.satisfied = True

		for blocker in unsolvable_blockers:
			retlist.append(blocker)

		if unsolvable_blockers and \
			not self._accept_blocker_conflicts():
			self._dynamic_config._unsatisfied_blockers_for_display = unsolvable_blockers
			self._dynamic_config._serialized_tasks_cache = retlist[:]
			self._dynamic_config._scheduler_graph = scheduler_graph
			raise self._unknown_internal_error()

		if self._dynamic_config._slot_collision_info and \
			not self._accept_blocker_conflicts():
			self._dynamic_config._serialized_tasks_cache = retlist[:]
			self._dynamic_config._scheduler_graph = scheduler_graph
			raise self._unknown_internal_error()

		return retlist, scheduler_graph

	def _show_circular_deps(self, mygraph):
		self._dynamic_config._circular_dependency_handler = \
			circular_dependency_handler(self, mygraph)
		handler = self._dynamic_config._circular_dependency_handler

		self._frozen_config.myopts.pop("--quiet", None)
		self._frozen_config.myopts["--verbose"] = True
		self._frozen_config.myopts["--tree"] = True
		portage.writemsg("\n\n", noiselevel=-1)
		self.display(handler.merge_list)
		prefix = colorize("BAD", " * ")
		portage.writemsg("\n", noiselevel=-1)
		portage.writemsg(prefix + "Error: circular dependencies:\n",
			noiselevel=-1)
		portage.writemsg("\n", noiselevel=-1)

		if handler.circular_dep_message is None or \
			"--debug" in self._frozen_config.myopts:
			handler.debug_print()
			portage.writemsg("\n", noiselevel=-1)

		if handler.circular_dep_message is not None:
			portage.writemsg(handler.circular_dep_message, noiselevel=-1)

		suggestions = handler.suggestions
		if suggestions:
			writemsg("\n\nIt might be possible to break this cycle\n", noiselevel=-1)
			if len(suggestions) == 1:
				writemsg("by applying the following change:\n", noiselevel=-1)
			else:
				writemsg("by applying " + colorize("bold", "any of") + \
					" the following changes:\n", noiselevel=-1)
			writemsg("".join(suggestions), noiselevel=-1)
			writemsg("\nNote that this change can be reverted, once the package has" + \
				" been installed.\n", noiselevel=-1)
			if handler.large_cycle_count:
				writemsg("\nNote that the dependency graph contains a lot of cycles.\n" + \
					"Several changes might be required to resolve all cycles.\n" + \
					"Temporarily changing some use flag for all packages might be the better option.\n", noiselevel=-1)
		else:
			writemsg("\n\n", noiselevel=-1)
			writemsg(prefix + "Note that circular dependencies " + \
				"can often be avoided by temporarily\n", noiselevel=-1)
			writemsg(prefix + "disabling USE flags that trigger " + \
				"optional dependencies.\n", noiselevel=-1)

	def _show_merge_list(self):
		if self._dynamic_config._serialized_tasks_cache is not None and \
			not (self._dynamic_config._displayed_list and \
			(self._dynamic_config._displayed_list == self._dynamic_config._serialized_tasks_cache or \
			self._dynamic_config._displayed_list == \
				list(reversed(self._dynamic_config._serialized_tasks_cache)))):
			display_list = self._dynamic_config._serialized_tasks_cache[:]
			if "--tree" in self._frozen_config.myopts:
				display_list.reverse()
			self.display(display_list)

	def _show_unsatisfied_blockers(self, blockers):
		self._show_merge_list()
		msg = "Error: The above package list contains " + \
			"packages which cannot be installed " + \
			"at the same time on the same system."
		prefix = colorize("BAD", " * ")
		portage.writemsg("\n", noiselevel=-1)
		for line in textwrap.wrap(msg, 70):
			portage.writemsg(prefix + line + "\n", noiselevel=-1)

		# Display the conflicting packages along with the packages
		# that pulled them in. This is helpful for troubleshooting
		# cases in which blockers don't solve automatically and
		# the reasons are not apparent from the normal merge list
		# display.

		conflict_pkgs = {}
		for blocker in blockers:
			for pkg in chain(self._dynamic_config._blocked_pkgs.child_nodes(blocker), \
				self._dynamic_config._blocker_parents.parent_nodes(blocker)):
				parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
				if not parent_atoms:
					atom = self._dynamic_config._blocked_world_pkgs.get(pkg)
					if atom is not None:
						parent_atoms = set([("@selected", atom)])
				if parent_atoms:
					conflict_pkgs[pkg] = parent_atoms

		if conflict_pkgs:
			# Reduce noise by pruning packages that are only
			# pulled in by other conflict packages.
			pruned_pkgs = set()
			for pkg, parent_atoms in conflict_pkgs.items():
				relevant_parent = False
				for parent, atom in parent_atoms:
					if parent not in conflict_pkgs:
						relevant_parent = True
						break
				if not relevant_parent:
					pruned_pkgs.add(pkg)
			for pkg in pruned_pkgs:
				del conflict_pkgs[pkg]

		if conflict_pkgs:
			msg = []
			msg.append("\n")
			indent = "  "
			# Max number of parents shown, to avoid flooding the display.
			max_parents = 3
			for pkg, parent_atoms in conflict_pkgs.items():

				pruned_list = set()

				# Prefer packages that are not directly involved in a conflict.
				for parent_atom in parent_atoms:
					if len(pruned_list) >= max_parents:
						break
					parent, atom = parent_atom
					if parent not in conflict_pkgs:
						pruned_list.add(parent_atom)

				for parent_atom in parent_atoms:
					if len(pruned_list) >= max_parents:
						break
					pruned_list.add(parent_atom)

				omitted_parents = len(parent_atoms) - len(pruned_list)
				msg.append(indent + "%s pulled in by\n" % pkg)

				for parent_atom in pruned_list:
					parent, atom = parent_atom
					msg.append(2*indent)
					if isinstance(parent,
						(PackageArg, AtomArg)):
						# For PackageArg and AtomArg types, it's
						# redundant to display the atom attribute.
						msg.append(str(parent))
					else:
						# Display the specific atom from SetArg or
						# Package types.
						msg.append("%s required by %s" % (atom, parent))
					msg.append("\n")

				if omitted_parents:
					msg.append(2*indent)
					msg.append("(and %d more)\n" % omitted_parents)

				msg.append("\n")

			sys.stderr.write("".join(msg))
			sys.stderr.flush()

		if "--quiet" not in self._frozen_config.myopts:
			show_blocker_docs_link()

	def display(self, mylist, favorites=[], verbosity=None):

		# This is used to prevent display_problems() from
		# redundantly displaying this exact same merge list
		# again via _show_merge_list().
		self._dynamic_config._displayed_list = mylist
		display = Display()

		return display(self, mylist, favorites, verbosity)

	def display_problems(self):
		"""
		Display problems with the dependency graph such as slot collisions.
		This is called internally by display() to show the problems _after_
		the merge list where it is most likely to be seen, but if display()
		is not going to be called then this method should be called explicitly
		to ensure that the user is notified of problems with the graph.

		All output goes to stderr, except for unsatisfied dependencies which
		go to stdout for parsing by programs such as autounmask.
		"""

		# Note that show_masked_packages() sends it's output to
		# stdout, and some programs such as autounmask parse the
		# output in cases when emerge bails out. However, when
		# show_masked_packages() is called for installed packages
		# here, the message is a warning that is more appropriate
		# to send to stderr, so temporarily redirect stdout to
		# stderr. TODO: Fix output code so there's a cleaner way
		# to redirect everything to stderr.
		sys.stdout.flush()
		sys.stderr.flush()
		stdout = sys.stdout
		try:
			sys.stdout = sys.stderr
			self._display_problems()
		finally:
			sys.stdout = stdout
			sys.stdout.flush()
			sys.stderr.flush()

		# This goes to stdout for parsing by programs like autounmask.
		for pargs, kwargs in self._dynamic_config._unsatisfied_deps_for_display:
			self._show_unsatisfied_dep(*pargs, **kwargs)

	def _display_problems(self):
		if self._dynamic_config._circular_deps_for_display is not None:
			self._show_circular_deps(
				self._dynamic_config._circular_deps_for_display)

		# The user is only notified of a slot conflict if
		# there are no unresolvable blocker conflicts.
		if self._dynamic_config._unsatisfied_blockers_for_display is not None:
			self._show_unsatisfied_blockers(
				self._dynamic_config._unsatisfied_blockers_for_display)
		elif self._dynamic_config._slot_collision_info:
			self._show_slot_collision_notice()
		else:
			self._show_missed_update()

		def get_dep_chain(pkg):
			traversed_nodes = set()
			msg = "#"
			node = pkg
			first = True
			child = None
			all_parents = self._dynamic_config._parent_atoms
			while node is not None:
				traversed_nodes.add(node)
				if isinstance(node, DependencyArg):
					if first:
						first = False
					else:
						msg += ", "
					msg += _unicode_decode('required by %s') % (node,)
				elif node is not pkg:
					for ppkg, patom in all_parents[child]:
						if ppkg == node:
							atom = patom.unevaluated_atom
							break

					dep_strings = set()
					for priority in self._dynamic_config.digraph.nodes[node][0][child]:
						if priority.buildtime:
							dep_strings.add(node.metadata["DEPEND"])
						if priority.runtime:
							dep_strings.add(node.metadata["RDEPEND"])
						if priority.runtime_post:
							dep_strings.add(node.metadata["PDEPEND"])
					
					affecting_use = set()
					for dep_str in dep_strings:
						affecting_use.update(extract_affecting_use(dep_str, atom))
					
					#Don't show flags as 'affecting' if the user can't change them,
					affecting_use.difference_update(node.use.mask, \
						node.use.force)

					pkg_name = node.cpv
					if affecting_use:
						usedep = []
						for flag in affecting_use:
							if flag in self._pkg_use_enabled(node):
								usedep.append(flag)
							else:
								usedep.append("-"+flag)
						pkg_name += "[%s]" % ",".join(usedep)

					if first:
						first = False
					else:
						msg += ", "
					msg += 'required by =%s' % pkg_name
	
				if node not in self._dynamic_config.digraph:
					# The parent is not in the graph due to backtracking.
					break
	
				# When traversing to parents, prefer arguments over packages
				# since arguments are root nodes. Never traverse the same
				# package twice, in order to prevent an infinite loop.
				selected_parent = None
				for parent in self._dynamic_config.digraph.parent_nodes(node):
					if parent in traversed_nodes:
						continue
					if isinstance(parent, DependencyArg):
						if self._dynamic_config.digraph.parent_nodes(parent):
							selected_parent = parent
							child = node
						else:
							if first:
								first = False
							else:
								msg += ", "
							msg += _unicode_decode(
								'required by %s (argument)') % (parent,)
							selected_parent = None
						break
					else:
						selected_parent = parent
						child = node
				node = selected_parent
			msg += "\n"
			return msg

		unstable_keyword_msg = []
		for pkg in self._dynamic_config._needed_unstable_keywords:
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				pkgsettings = self._frozen_config.pkgsettings[pkg.root]
				mreasons = _get_masking_status(pkg, pkgsettings, pkg.root_config,
					use=self._pkg_use_enabled(pkg))
				for reason in mreasons:
					if reason.unmask_hint and \
						reason.unmask_hint.key == 'unstable keyword':
						keyword = reason.unmask_hint.value

						unstable_keyword_msg.append(get_dep_chain(pkg))
						unstable_keyword_msg.append("=%s %s\n" % (pkg.cpv, keyword))

		use_changes_msg = []
		for pkg, needed_use_config_change in self._dynamic_config._needed_use_config_changes.items():
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				changes = needed_use_config_change[1]
				adjustments = []
				for flag, state in changes.items():
					if state:
						adjustments.append(flag)
					else:
						adjustments.append("-" + flag)
				use_changes_msg.append(get_dep_chain(pkg))
				use_changes_msg.append("=%s %s\n" % (pkg.cpv, " ".join(adjustments)))

		license_msg = []
		for pkg, missing_licenses in self._dynamic_config._needed_license_changes.items():
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				license_msg.append(get_dep_chain(pkg))
				license_msg.append("=%s %s\n" % (pkg.cpv, " ".join(sorted(missing_licenses))))

		if unstable_keyword_msg:
			writemsg_stdout("\nThe following " + colorize("BAD", "keyword changes") + \
				" are necessary to proceed:\n", noiselevel=-1)
			writemsg_stdout("".join(unstable_keyword_msg), noiselevel=-1)

		if use_changes_msg:
			writemsg_stdout("\nThe following " + colorize("BAD", "USE changes") + \
				" are necessary to proceed:\n", noiselevel=-1)
			writemsg_stdout("".join(use_changes_msg), noiselevel=-1)

		if license_msg:
			writemsg_stdout("\nThe following " + colorize("BAD", "license changes") + \
				" are necessary to proceed:\n", noiselevel=-1)
			writemsg_stdout("".join(license_msg), noiselevel=-1)

		# TODO: Add generic support for "set problem" handlers so that
		# the below warnings aren't special cases for world only.

		if self._dynamic_config._missing_args:
			world_problems = False
			if "world" in self._dynamic_config.sets[
				self._frozen_config.target_root].sets:
				# Filter out indirect members of world (from nested sets)
				# since only direct members of world are desired here.
				world_set = self._frozen_config.roots[self._frozen_config.target_root].sets["selected"]
				for arg, atom in self._dynamic_config._missing_args:
					if arg.name in ("selected", "world") and atom in world_set:
						world_problems = True
						break

			if world_problems:
				sys.stderr.write("\n!!! Problems have been " + \
					"detected with your world file\n")
				sys.stderr.write("!!! Please run " + \
					green("emaint --check world")+"\n\n")

		if self._dynamic_config._missing_args:
			sys.stderr.write("\n" + colorize("BAD", "!!!") + \
				" Ebuilds for the following packages are either all\n")
			sys.stderr.write(colorize("BAD", "!!!") + \
				" masked or don't exist:\n")
			sys.stderr.write(" ".join(str(atom) for arg, atom in \
				self._dynamic_config._missing_args) + "\n")

		if self._dynamic_config._pprovided_args:
			arg_refs = {}
			for arg, atom in self._dynamic_config._pprovided_args:
				if isinstance(arg, SetArg):
					parent = arg.name
					arg_atom = (atom, atom)
				else:
					parent = "args"
					arg_atom = (arg.arg, atom)
				refs = arg_refs.setdefault(arg_atom, [])
				if parent not in refs:
					refs.append(parent)
			msg = []
			msg.append(bad("\nWARNING: "))
			if len(self._dynamic_config._pprovided_args) > 1:
				msg.append("Requested packages will not be " + \
					"merged because they are listed in\n")
			else:
				msg.append("A requested package will not be " + \
					"merged because it is listed in\n")
			msg.append("package.provided:\n\n")
			problems_sets = set()
			for (arg, atom), refs in arg_refs.items():
				ref_string = ""
				if refs:
					problems_sets.update(refs)
					refs.sort()
					ref_string = ", ".join(["'%s'" % name for name in refs])
					ref_string = " pulled in by " + ref_string
				msg.append("  %s%s\n" % (colorize("INFORM", str(arg)), ref_string))
			msg.append("\n")
			if "selected" in problems_sets or "world" in problems_sets:
				msg.append("This problem can be solved in one of the following ways:\n\n")
				msg.append("  A) Use emaint to clean offending packages from world (if not installed).\n")
				msg.append("  B) Uninstall offending packages (cleans them from world).\n")
				msg.append("  C) Remove offending entries from package.provided.\n\n")
				msg.append("The best course of action depends on the reason that an offending\n")
				msg.append("package.provided entry exists.\n\n")
			sys.stderr.write("".join(msg))

		masked_packages = []
		for pkg in self._dynamic_config._masked_license_updates:
			root_config = pkg.root_config
			pkgsettings = self._frozen_config.pkgsettings[pkg.root]
			mreasons = get_masking_status(pkg, pkgsettings, root_config, use=self._pkg_use_enabled(pkg))
			masked_packages.append((root_config, pkgsettings,
				pkg.cpv, pkg.repo, pkg.metadata, mreasons))
		if masked_packages:
			writemsg("\n" + colorize("BAD", "!!!") + \
				" The following updates are masked by LICENSE changes:\n",
				noiselevel=-1)
			show_masked_packages(masked_packages)
			show_mask_docs()
			writemsg("\n", noiselevel=-1)

		masked_packages = []
		for pkg in self._dynamic_config._masked_installed:
			root_config = pkg.root_config
			pkgsettings = self._frozen_config.pkgsettings[pkg.root]
			mreasons = get_masking_status(pkg, pkgsettings, root_config, use=self._pkg_use_enabled)
			masked_packages.append((root_config, pkgsettings,
				pkg.cpv, pkg.repo, pkg.metadata, mreasons))
		if masked_packages:
			writemsg("\n" + colorize("BAD", "!!!") + \
				" The following installed packages are masked:\n",
				noiselevel=-1)
			show_masked_packages(masked_packages)
			show_mask_docs()
			writemsg("\n", noiselevel=-1)

	def saveNomergeFavorites(self):
		"""Find atoms in favorites that are not in the mergelist and add them
		to the world file if necessary."""
		for x in ("--buildpkgonly", "--fetchonly", "--fetch-all-uri",
			"--oneshot", "--onlydeps", "--pretend"):
			if x in self._frozen_config.myopts:
				return
		root_config = self._frozen_config.roots[self._frozen_config.target_root]
		world_set = root_config.sets["selected"]

		world_locked = False
		if hasattr(world_set, "lock"):
			world_set.lock()
			world_locked = True

		if hasattr(world_set, "load"):
			world_set.load() # maybe it's changed on disk

		args_set = self._dynamic_config.sets[
			self._frozen_config.target_root].sets['__non_set_args__']
		portdb = self._frozen_config.trees[self._frozen_config.target_root]["porttree"].dbapi
		added_favorites = set()
		for x in self._dynamic_config._set_nodes:
			if x.operation != "nomerge":
				continue

			if x.root != root_config.root:
				continue

			try:
				myfavkey = create_world_atom(x, args_set, root_config)
				if myfavkey:
					if myfavkey in added_favorites:
						continue
					added_favorites.add(myfavkey)
			except portage.exception.InvalidDependString as e:
				writemsg("\n\n!!! '%s' has invalid PROVIDE: %s\n" % \
					(x.cpv, e), noiselevel=-1)
				writemsg("!!! see '%s'\n\n" % os.path.join(
					x.root, portage.VDB_PATH, x.cpv, "PROVIDE"), noiselevel=-1)
				del e
		all_added = []
		for arg in self._dynamic_config._initial_arg_list:
			if not isinstance(arg, SetArg):
				continue
			if arg.root_config.root != root_config.root:
				continue
			k = arg.name
			if k in ("selected", "world") or \
				not root_config.sets[k].world_candidate:
				continue
			s = SETPREFIX + k
			if s in world_set:
				continue
			all_added.append(SETPREFIX + k)
		all_added.extend(added_favorites)
		all_added.sort()
		for a in all_added:
			writemsg(">>> Recording %s in \"world\" favorites file...\n" % \
				colorize("INFORM", str(a)), noiselevel=-1)
		if all_added:
			world_set.update(all_added)

		if world_locked:
			world_set.unlock()

	def _loadResumeCommand(self, resume_data, skip_masked=True,
		skip_missing=True):
		"""
		Add a resume command to the graph and validate it in the process.  This
		will raise a PackageNotFound exception if a package is not available.
		"""

		self._load_vdb()

		if not isinstance(resume_data, dict):
			return False

		mergelist = resume_data.get("mergelist")
		if not isinstance(mergelist, list):
			mergelist = []

		favorites = resume_data.get("favorites")
		args_set = self._dynamic_config.sets[
			self._frozen_config.target_root].sets['__non_set_args__']
		if isinstance(favorites, list):
			args = self._load_favorites(favorites)
		else:
			args = []

		fakedb = self._dynamic_config.mydbapi
		trees = self._frozen_config.trees
		serialized_tasks = []
		masked_tasks = []
		for x in mergelist:
			if not (isinstance(x, list) and len(x) == 4):
				continue
			pkg_type, myroot, pkg_key, action = x
			if pkg_type not in self.pkg_tree_map:
				continue
			if action != "merge":
				continue
			root_config = self._frozen_config.roots[myroot]

			# Use the resume "favorites" list to see if a repo was specified
			# for this package.
			depgraph_sets = self._dynamic_config.sets[root_config.root]
			repo = None
			for atom in depgraph_sets.atoms.getAtoms():
				if atom.repo and portage.dep.match_from_list(atom, [pkg_key]):
					repo = atom.repo
					break

			atom = "=" + pkg_key
			if repo:
				atom = atom + _repo_separator + repo

			try:
				atom = Atom(atom, allow_repo=True)
			except InvalidAtom:
				continue

			pkg = None
			for pkg in self._iter_match_pkgs(root_config, pkg_type, atom):
				if not self._pkg_visibility_check(pkg) or \
					self._frozen_config.excluded_pkgs.findAtomForPackage(pkg,
						modified_use=self._pkg_use_enabled(pkg)):
					continue
				break

			if pkg is None:
				# It does no exist or it is corrupt.
				if skip_missing:
					# TODO: log these somewhere
					continue
				raise portage.exception.PackageNotFound(pkg_key)

			if "merge" == pkg.operation and \
				self._frozen_config.excluded_pkgs.findAtomForPackage(pkg, \
					modified_use=self._pkg_use_enabled(pkg)):
				continue

			if "merge" == pkg.operation and not self._pkg_visibility_check(pkg):
				if skip_masked:
					masked_tasks.append(Dependency(root=pkg.root, parent=pkg))
				else:
					self._dynamic_config._unsatisfied_deps_for_display.append(
						((pkg.root, "="+pkg.cpv), {"myparent":None}))

			fakedb[myroot].cpv_inject(pkg)
			serialized_tasks.append(pkg)
			self._spinner_update()

		if self._dynamic_config._unsatisfied_deps_for_display:
			return False

		if not serialized_tasks or "--nodeps" in self._frozen_config.myopts:
			self._dynamic_config._serialized_tasks_cache = serialized_tasks
			self._dynamic_config._scheduler_graph = self._dynamic_config.digraph
		else:
			self._select_package = self._select_pkg_from_graph
			self._dynamic_config.myparams["selective"] = True
			# Always traverse deep dependencies in order to account for
			# potentially unsatisfied dependencies of installed packages.
			# This is necessary for correct --keep-going or --resume operation
			# in case a package from a group of circularly dependent packages
			# fails. In this case, a package which has recently been installed
			# may have an unsatisfied circular dependency (pulled in by
			# PDEPEND, for example). So, even though a package is already
			# installed, it may not have all of it's dependencies satisfied, so
			# it may not be usable. If such a package is in the subgraph of
			# deep depenedencies of a scheduled build, that build needs to
			# be cancelled. In order for this type of situation to be
			# recognized, deep traversal of dependencies is required.
			self._dynamic_config.myparams["deep"] = True

			for task in serialized_tasks:
				if isinstance(task, Package) and \
					task.operation == "merge":
					if not self._add_pkg(task, None):
						return False

			# Packages for argument atoms need to be explicitly
			# added via _add_pkg() so that they are included in the
			# digraph (needed at least for --tree display).
			for arg in self._expand_set_args(args, add_to_digraph=True):
				for atom in arg.pset.getAtoms():
					pkg, existing_node = self._select_package(
						arg.root_config.root, atom)
					if existing_node is None and \
						pkg is not None:
						if not self._add_pkg(pkg, Dependency(atom=atom,
							root=pkg.root, parent=arg)):
							return False

			# Allow unsatisfied deps here to avoid showing a masking
			# message for an unsatisfied dep that isn't necessarily
			# masked.
			if not self._create_graph(allow_unsatisfied=True):
				return False

			unsatisfied_deps = []
			for dep in self._dynamic_config._unsatisfied_deps:
				if not isinstance(dep.parent, Package):
					continue
				if dep.parent.operation == "merge":
					unsatisfied_deps.append(dep)
					continue

				# For unsatisfied deps of installed packages, only account for
				# them if they are in the subgraph of dependencies of a package
				# which is scheduled to be installed.
				unsatisfied_install = False
				traversed = set()
				dep_stack = self._dynamic_config.digraph.parent_nodes(dep.parent)
				while dep_stack:
					node = dep_stack.pop()
					if not isinstance(node, Package):
						continue
					if node.operation == "merge":
						unsatisfied_install = True
						break
					if node in traversed:
						continue
					traversed.add(node)
					dep_stack.extend(self._dynamic_config.digraph.parent_nodes(node))

				if unsatisfied_install:
					unsatisfied_deps.append(dep)

			if masked_tasks or unsatisfied_deps:
				# This probably means that a required package
				# was dropped via --skipfirst. It makes the
				# resume list invalid, so convert it to a
				# UnsatisfiedResumeDep exception.
				raise self.UnsatisfiedResumeDep(self,
					masked_tasks + unsatisfied_deps)
			self._dynamic_config._serialized_tasks_cache = None
			try:
				self.altlist()
			except self._unknown_internal_error:
				return False

		return True

	def _load_favorites(self, favorites):
		"""
		Use a list of favorites to resume state from a
		previous select_files() call. This creates similar
		DependencyArg instances to those that would have
		been created by the original select_files() call.
		This allows Package instances to be matched with
		DependencyArg instances during graph creation.
		"""
		root_config = self._frozen_config.roots[self._frozen_config.target_root]
		sets = root_config.sets
		depgraph_sets = self._dynamic_config.sets[root_config.root]
		args = []
		for x in favorites:
			if not isinstance(x, basestring):
				continue
			if x in ("system", "world"):
				x = SETPREFIX + x
			if x.startswith(SETPREFIX):
				s = x[len(SETPREFIX):]
				if s not in sets:
					continue
				if s in depgraph_sets.sets:
					continue
				pset = sets[s]
				depgraph_sets.sets[s] = pset
				args.append(SetArg(arg=x, pset=pset,
					root_config=root_config))
			else:
				try:
					x = Atom(x, allow_repo=True)
				except portage.exception.InvalidAtom:
					continue
				args.append(AtomArg(arg=x, atom=x,
					root_config=root_config))

		self._set_args(args)
		return args

	class UnsatisfiedResumeDep(portage.exception.PortageException):
		"""
		A dependency of a resume list is not installed. This
		can occur when a required package is dropped from the
		merge list via --skipfirst.
		"""
		def __init__(self, depgraph, value):
			portage.exception.PortageException.__init__(self, value)
			self.depgraph = depgraph

	class _internal_exception(portage.exception.PortageException):
		def __init__(self, value=""):
			portage.exception.PortageException.__init__(self, value)

	class _unknown_internal_error(_internal_exception):
		"""
		Used by the depgraph internally to terminate graph creation.
		The specific reason for the failure should have been dumped
		to stderr, unfortunately, the exact reason for the failure
		may not be known.
		"""

	class _serialize_tasks_retry(_internal_exception):
		"""
		This is raised by the _serialize_tasks() method when it needs to
		be called again for some reason. The only case that it's currently
		used for is when neglected dependencies need to be added to the
		graph in order to avoid making a potentially unsafe decision.
		"""

	class _backtrack_mask(_internal_exception):
		"""
		This is raised by _show_unsatisfied_dep() when it's called with
		check_backtrack=True and a matching package has been masked by
		backtracking.
		"""

	def need_restart(self):
		return self._dynamic_config._need_restart
	
	def success_without_autounmask(self):
		return self._dynamic_config._success_without_autounmask

	def get_backtrack_infos(self):
		return self._dynamic_config._backtrack_infos
			

class _dep_check_composite_db(dbapi):
	"""
	A dbapi-like interface that is optimized for use in dep_check() calls.
	This is built on top of the existing depgraph package selection logic.
	Some packages that have been added to the graph may be masked from this
	view in order to influence the atom preference selection that occurs
	via dep_check().
	"""
	def __init__(self, depgraph, root):
		dbapi.__init__(self)
		self._depgraph = depgraph
		self._root = root
		self._match_cache = {}
		self._cpv_pkg_map = {}

	def _clear_cache(self):
		self._match_cache.clear()
		self._cpv_pkg_map.clear()

	def match(self, atom):
		ret = self._match_cache.get(atom)
		if ret is not None:
			return ret[:]
		orig_atom = atom
		if "/" not in atom:
			atom = self._dep_expand(atom)
		pkg, existing = self._depgraph._select_package(self._root, atom)
		if not pkg:
			ret = []
		else:
			# Return the highest available from select_package() as well as
			# any matching slots in the graph db.
			slots = set()
			slots.add(pkg.metadata["SLOT"])
			if pkg.cp.startswith("virtual/"):
				# For new-style virtual lookahead that occurs inside
				# dep_check(), examine all slots. This is needed
				# so that newer slots will not unnecessarily be pulled in
				# when a satisfying lower slot is already installed. For
				# example, if virtual/jdk-1.4 is satisfied via kaffe then
				# there's no need to pull in a newer slot to satisfy a
				# virtual/jdk dependency.
				for db, pkg_type, built, installed, db_keys in \
					self._depgraph._dynamic_config._filtered_trees[self._root]["dbs"]:
					for cpv in db.match(atom):
						if portage.cpv_getkey(cpv) != pkg.cp:
							continue
						slots.add(db.aux_get(cpv, ["SLOT"])[0])
			ret = []
			if self._visible(pkg):
				self._cpv_pkg_map[pkg.cpv] = pkg
				ret.append(pkg.cpv)
			slots.remove(pkg.metadata["SLOT"])
			while slots:
				slot_atom = Atom("%s:%s" % (atom.cp, slots.pop()))
				pkg, existing = self._depgraph._select_package(
					self._root, slot_atom)
				if not pkg:
					continue
				if not self._visible(pkg):
					continue
				self._cpv_pkg_map[pkg.cpv] = pkg
				ret.append(pkg.cpv)
			if ret:
				self._cpv_sort_ascending(ret)
		self._match_cache[orig_atom] = ret
		return ret[:]

	def _visible(self, pkg):
		if pkg.installed and "selective" not in self._depgraph._dynamic_config.myparams:
			try:
				arg = next(self._depgraph._iter_atoms_for_pkg(pkg))
			except (StopIteration, portage.exception.InvalidDependString):
				arg = None
			if arg:
				return False
		if pkg.installed and not self._depgraph._pkg_visibility_check(pkg):
			return False
		in_graph = self._depgraph._dynamic_config._slot_pkg_map[
			self._root].get(pkg.slot_atom)
		if in_graph is None:
			# Mask choices for packages which are not the highest visible
			# version within their slot (since they usually trigger slot
			# conflicts).
			highest_visible, in_graph = self._depgraph._select_package(
				self._root, pkg.slot_atom)
			# Note: highest_visible is not necessarily the real highest
			# visible, especially when --update is not enabled, so use
			# < operator instead of !=.
			if pkg < highest_visible:
				return False
		elif in_graph != pkg:
			# Mask choices for packages that would trigger a slot
			# conflict with a previously selected package.
			return False
		return True

	def _dep_expand(self, atom):
		"""
		This is only needed for old installed packages that may
		contain atoms that are not fully qualified with a specific
		category. Emulate the cpv_expand() function that's used by
		dbapi.match() in cases like this. If there are multiple
		matches, it's often due to a new-style virtual that has
		been added, so try to filter those out to avoid raising
		a ValueError.
		"""
		root_config = self._depgraph.roots[self._root]
		orig_atom = atom
		expanded_atoms = self._depgraph._dep_expand(root_config, atom)
		if len(expanded_atoms) > 1:
			non_virtual_atoms = []
			for x in expanded_atoms:
				if not x.cp.startswith("virtual/"):
					non_virtual_atoms.append(x)
			if len(non_virtual_atoms) == 1:
				expanded_atoms = non_virtual_atoms
		if len(expanded_atoms) > 1:
			# compatible with portage.cpv_expand()
			raise portage.exception.AmbiguousPackageName(
				[x.cp for x in expanded_atoms])
		if expanded_atoms:
			atom = expanded_atoms[0]
		else:
			null_atom = Atom(insert_category_into_atom(atom, "null"),
				allow_repo=True)
			cat, atom_pn = portage.catsplit(null_atom.cp)
			virts_p = root_config.settings.get_virts_p().get(atom_pn)
			if virts_p:
				# Allow the resolver to choose which virtual.
				atom = Atom(null_atom.replace('null/', 'virtual/', 1),
					allow_repo=True)
			else:
				atom = null_atom
		return atom

	def aux_get(self, cpv, wants):
		metadata = self._cpv_pkg_map[cpv].metadata
		return [metadata.get(x, "") for x in wants]

	def match_pkgs(self, atom):
		return [self._cpv_pkg_map[cpv] for cpv in self.match(atom)]

def ambiguous_package_name(arg, atoms, root_config, spinner, myopts):

	if "--quiet" in myopts:
		writemsg("!!! The short ebuild name \"%s\" is ambiguous. Please specify\n" % arg, noiselevel=-1)
		writemsg("!!! one of the following fully-qualified ebuild names instead:\n\n", noiselevel=-1)
		for cp in sorted(set(portage.dep_getkey(atom) for atom in atoms)):
			writemsg("    " + colorize("INFORM", cp) + "\n", noiselevel=-1)
		return

	s = search(root_config, spinner, "--searchdesc" in myopts,
		"--quiet" not in myopts, "--usepkg" in myopts,
		"--usepkgonly" in myopts)
	null_cp = portage.dep_getkey(insert_category_into_atom(
		arg, "null"))
	cat, atom_pn = portage.catsplit(null_cp)
	s.searchkey = atom_pn
	for cp in sorted(set(portage.dep_getkey(atom) for atom in atoms)):
		s.addCP(cp)
	s.output()
	writemsg("!!! The short ebuild name \"%s\" is ambiguous. Please specify\n" % arg, noiselevel=-1)
	writemsg("!!! one of the above fully-qualified ebuild names instead.\n\n", noiselevel=-1)

def insert_category_into_atom(atom, category):
	alphanum = re.search(r'\w', atom)
	if alphanum:
		ret = atom[:alphanum.start()] + "%s/" % category + \
			atom[alphanum.start():]
	else:
		ret = None
	return ret

def _spinner_start(spinner, myopts):
	if spinner is None:
		return
	if "--quiet" not in myopts and \
		("--pretend" in myopts or "--ask" in myopts or \
		"--tree" in myopts or "--verbose" in myopts):
		action = ""
		if "--fetchonly" in myopts or "--fetch-all-uri" in myopts:
			action = "fetched"
		elif "--buildpkgonly" in myopts:
			action = "built"
		else:
			action = "merged"
		if "--tree" in myopts and action != "fetched": # Tree doesn't work with fetching
			if "--unordered-display" in myopts:
				portage.writemsg_stdout("\n" + \
					darkgreen("These are the packages that " + \
					"would be %s:" % action) + "\n\n")
			else:
				portage.writemsg_stdout("\n" + \
					darkgreen("These are the packages that " + \
					"would be %s, in reverse order:" % action) + "\n\n")
		else:
			portage.writemsg_stdout("\n" + \
				darkgreen("These are the packages that " + \
				"would be %s, in order:" % action) + "\n\n")

	show_spinner = "--quiet" not in myopts and "--nodeps" not in myopts
	if not show_spinner:
		spinner.update = spinner.update_quiet

	if show_spinner:
		portage.writemsg_stdout("Calculating dependencies  ")

def _spinner_stop(spinner):
	if spinner is None or \
		spinner.update is spinner.update_quiet:
		return

	portage.writemsg_stdout("\b\b... done!\n")

def backtrack_depgraph(settings, trees, myopts, myparams, 
	myaction, myfiles, spinner):
	"""
	Raises PackageSetNotFound if myfiles contains a missing package set.
	"""
	_spinner_start(spinner, myopts)
	try:
		return _backtrack_depgraph(settings, trees, myopts, myparams, 
			myaction, myfiles, spinner)
	finally:
		_spinner_stop(spinner)


def _backtrack_depgraph(settings, trees, myopts, myparams, myaction, myfiles, spinner):

	max_retries = myopts.get('--backtrack', 10)
	max_depth = max(1, (max_retries + 1) / 2)
	allow_backtracking = max_retries > 0
	backtracker = Backtracker(max_depth)
	backtracked = 0

	frozen_config = _frozen_depgraph_config(settings, trees,
		myopts, spinner)

	while backtracker:
		backtrack_parameters = backtracker.get()

		mydepgraph = depgraph(settings, trees, myopts, myparams, spinner,
			frozen_config=frozen_config,
			allow_backtracking=allow_backtracking,
			backtrack_parameters=backtrack_parameters)
		success, favorites = mydepgraph.select_files(myfiles)

		if success or mydepgraph.success_without_autounmask():
			break
		elif not allow_backtracking:
			break
		elif backtracked >= max_retries:
			break
		elif mydepgraph.need_restart():
			backtracked += 1
			backtracker.feedback(mydepgraph.get_backtrack_infos())
		else:
			break

	if not (success or mydepgraph.success_without_autounmask()) and backtracked:

		if "--debug" in myopts:
			writemsg_level(
				"\n\nbacktracking aborted after %s tries\n\n" % \
				backtracked, noiselevel=-1, level=logging.DEBUG)

		mydepgraph = depgraph(settings, trees, myopts, myparams, spinner,
			frozen_config=frozen_config,
			allow_backtracking=False)
		success, favorites = mydepgraph.select_files(myfiles)

	return (success, mydepgraph, favorites)


def resume_depgraph(settings, trees, mtimedb, myopts, myparams, spinner):
	"""
	Raises PackageSetNotFound if myfiles contains a missing package set.
	"""
	_spinner_start(spinner, myopts)
	try:
		return _resume_depgraph(settings, trees, mtimedb, myopts,
			myparams, spinner)
	finally:
		_spinner_stop(spinner)

def _resume_depgraph(settings, trees, mtimedb, myopts, myparams, spinner):
	"""
	Construct a depgraph for the given resume list. This will raise
	PackageNotFound or depgraph.UnsatisfiedResumeDep when necessary.
	TODO: Return reasons for dropped_tasks, for display/logging.
	@rtype: tuple
	@returns: (success, depgraph, dropped_tasks)
	"""
	skip_masked = True
	skip_unsatisfied = True
	mergelist = mtimedb["resume"]["mergelist"]
	dropped_tasks = set()
	frozen_config = _frozen_depgraph_config(settings, trees,
		myopts, spinner)
	while True:
		mydepgraph = depgraph(settings, trees,
			myopts, myparams, spinner, frozen_config=frozen_config)
		try:
			success = mydepgraph._loadResumeCommand(mtimedb["resume"],
				skip_masked=skip_masked)
		except depgraph.UnsatisfiedResumeDep as e:
			if not skip_unsatisfied:
				raise

			graph = mydepgraph._dynamic_config.digraph
			unsatisfied_parents = dict((dep.parent, dep.parent) \
				for dep in e.value)
			traversed_nodes = set()
			unsatisfied_stack = list(unsatisfied_parents)
			while unsatisfied_stack:
				pkg = unsatisfied_stack.pop()
				if pkg in traversed_nodes:
					continue
				traversed_nodes.add(pkg)

				# If this package was pulled in by a parent
				# package scheduled for merge, removing this
				# package may cause the the parent package's
				# dependency to become unsatisfied.
				for parent_node in graph.parent_nodes(pkg):
					if not isinstance(parent_node, Package) \
						or parent_node.operation not in ("merge", "nomerge"):
						continue
					unsatisfied = \
						graph.child_nodes(parent_node,
						ignore_priority=DepPrioritySatisfiedRange.ignore_soft)
					if pkg in unsatisfied:
						unsatisfied_parents[parent_node] = parent_node
						unsatisfied_stack.append(parent_node)

			pruned_mergelist = []
			for x in mergelist:
				if isinstance(x, list) and \
					tuple(x) not in unsatisfied_parents:
					pruned_mergelist.append(x)

			# If the mergelist doesn't shrink then this loop is infinite.
			if len(pruned_mergelist) == len(mergelist):
				# This happens if a package can't be dropped because
				# it's already installed, but it has unsatisfied PDEPEND.
				raise
			mergelist[:] = pruned_mergelist

			# Exclude installed packages that have been removed from the graph due
			# to failure to build/install runtime dependencies after the dependent
			# package has already been installed.
			dropped_tasks.update(pkg for pkg in \
				unsatisfied_parents if pkg.operation != "nomerge")
			mydepgraph.break_refs(unsatisfied_parents)

			del e, graph, traversed_nodes, \
				unsatisfied_parents, unsatisfied_stack
			continue
		else:
			break
	return (success, mydepgraph, dropped_tasks)

def get_mask_info(root_config, cpv, pkgsettings,
	db, pkg_type, built, installed, db_keys, myrepo = None, _pkg_use_enabled=None):
	eapi_masked = False
	try:
		metadata = dict(zip(db_keys,
			db.aux_get(cpv, db_keys, myrepo=myrepo)))
	except KeyError:
		metadata = None

	if metadata is None:
		mreasons = ["corruption"]
	else:
		eapi = metadata['EAPI']
		if eapi[:1] == '-':
			eapi = eapi[1:]
		if not portage.eapi_is_supported(eapi):
			mreasons = ['EAPI %s' % eapi]
		else:
			pkg = Package(type_name=pkg_type, root_config=root_config,
				cpv=cpv, built=built, installed=installed, metadata=metadata)

			modified_use = None
			if _pkg_use_enabled is not None:
				modified_use = _pkg_use_enabled(pkg)

			mreasons = get_masking_status(pkg, pkgsettings, root_config, myrepo=myrepo, use=modified_use)

	return metadata, mreasons

def show_masked_packages(masked_packages):
	shown_licenses = set()
	shown_comments = set()
	# Maybe there is both an ebuild and a binary. Only
	# show one of them to avoid redundant appearance.
	shown_cpvs = set()
	have_eapi_mask = False
	for (root_config, pkgsettings, cpv, repo,
		metadata, mreasons) in masked_packages:
		output_cpv = cpv
		if repo:
			output_cpv += _repo_separator + repo
		if output_cpv in shown_cpvs:
			continue
		shown_cpvs.add(output_cpv)
		comment, filename = None, None
		if "package.mask" in mreasons:
			comment, filename = \
				portage.getmaskingreason(
				cpv, metadata=metadata,
				settings=pkgsettings,
				portdb=root_config.trees["porttree"].dbapi,
				return_location=True)
		missing_licenses = []
		if metadata:
			if not portage.eapi_is_supported(metadata["EAPI"]):
				have_eapi_mask = True
			try:
				missing_licenses = \
					pkgsettings._getMissingLicenses(
						cpv, metadata)
			except portage.exception.InvalidDependString:
				# This will have already been reported
				# above via mreasons.
				pass

		writemsg_stdout("- "+output_cpv+" (masked by: "+", ".join(mreasons)+")\n", noiselevel=-1)

		if comment and comment not in shown_comments:
			writemsg_stdout(filename + ":\n" + comment + "\n",
				noiselevel=-1)
			shown_comments.add(comment)
		portdb = root_config.trees["porttree"].dbapi
		for l in missing_licenses:
			l_path = portdb.findLicensePath(l)
			if l in shown_licenses:
				continue
			msg = ("A copy of the '%s' license" + \
			" is located at '%s'.\n\n") % (l, l_path)
			writemsg_stdout(msg, noiselevel=-1)
			shown_licenses.add(l)
	return have_eapi_mask

def show_mask_docs():
	writemsg_stdout("For more information, see the MASKED PACKAGES section in the emerge\n", noiselevel=-1)
	writemsg_stdout("man page or refer to the Gentoo Handbook.\n", noiselevel=-1)

def show_blocker_docs_link():
	writemsg("\nFor more information about " + bad("Blocked Packages") + ", please refer to the following\n", noiselevel=-1)
	writemsg("section of the Gentoo Linux x86 Handbook (architecture is irrelevant):\n\n", noiselevel=-1)
	writemsg("http://www.gentoo.org/doc/en/handbook/handbook-x86.xml?full=1#blocked\n\n", noiselevel=-1)

def get_masking_status(pkg, pkgsettings, root_config, myrepo=None, use=None):
	return [mreason.message for \
		mreason in _get_masking_status(pkg, pkgsettings, root_config, myrepo=myrepo, use=use)]

def _get_masking_status(pkg, pkgsettings, root_config, myrepo=None, use=None):
	mreasons = _getmaskingstatus(
		pkg, settings=pkgsettings,
		portdb=root_config.trees["porttree"].dbapi, myrepo=myrepo)

	if not pkg.installed:
		if not pkgsettings._accept_chost(pkg.cpv, pkg.metadata):
			mreasons.append(_MaskReason("CHOST", "CHOST: %s" % \
				pkg.metadata["CHOST"]))

		if pkg.metadata["REQUIRED_USE"] and \
			eapi_has_required_use(pkg.metadata["EAPI"]):
			required_use = pkg.metadata["REQUIRED_USE"]
			if use is None:
				use = pkg.use.enabled
			try:
				required_use_is_sat = check_required_use(
					required_use, use, pkg.iuse.is_valid_flag)
			except portage.exception.InvalidDependString:
				mreasons.append(_MaskReason("invalid", "invalid: REQUIRED_USE"))
			else:
				if not required_use_is_sat:
					msg = "violated use flag constraints: '%s'" % required_use
					mreasons.append(_MaskReason("REQUIRED_USE", "REQUIRED_USE violated"))

	if pkg.invalid:
		for msg_type, msgs in pkg.invalid.items():
			for msg in msgs:
				mreasons.append(
					_MaskReason("invalid", "invalid: %s" % (msg,)))

	if not pkg.metadata["SLOT"]:
		mreasons.append(
			_MaskReason("invalid", "SLOT: undefined"))

	return mreasons
