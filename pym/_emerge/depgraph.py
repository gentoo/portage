# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import difflib
import errno
import io
import logging
import stat
import sys
import textwrap
from collections import deque
from itertools import chain

import portage
from portage import os, OrderedDict
from portage import _unicode_decode, _unicode_encode, _encodings
from portage.const import PORTAGE_PACKAGE_ATOM, USER_CONFIG_PATH
from portage.dbapi import dbapi
from portage.dbapi.dep_expand import dep_expand
from portage.dep import Atom, best_match_to_list, extract_affecting_use, \
	check_required_use, human_readable_required_use, match_from_list, \
	_repo_separator
from portage.dep._slot_operator import ignore_built_slot_operator_deps
from portage.eapi import eapi_has_strong_blocks, eapi_has_required_use, \
	_get_eapi_attrs
from portage.exception import (InvalidAtom, InvalidData, InvalidDependString,
	PackageNotFound, PortageException)
from portage.output import colorize, create_color_func, \
	darkgreen, green
bad = create_color_func("BAD")
from portage.package.ebuild.config import _get_feature_flags
from portage.package.ebuild.getmaskingstatus import \
	_getmaskingstatus, _MaskReason
from portage._sets import SETPREFIX
from portage._sets.base import InternalPackageSet
from portage.util import ConfigProtect, shlex_split, new_protect_filename
from portage.util import cmp_sort_key, writemsg, writemsg_stdout
from portage.util import ensure_dirs
from portage.util import writemsg_level, write_atomic
from portage.util.digraph import digraph
from portage.util.listdir import _ignorecvs_dirs
from portage.versions import catpkgsplit

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
from _emerge.is_valid_package_atom import insert_category_into_atom, \
	is_valid_package_atom
from _emerge.Package import Package
from _emerge.PackageArg import PackageArg
from _emerge.PackageVirtualDbapi import PackageVirtualDbapi
from _emerge.RootConfig import RootConfig
from _emerge.search import search
from _emerge.SetArg import SetArg
from _emerge.show_invalid_depstring_notice import show_invalid_depstring_notice
from _emerge.UnmergeDepPriority import UnmergeDepPriority
from _emerge.UseFlagDisplay import pkg_use_display
from _emerge.userquery import userquery

from _emerge.resolver.backtracking import Backtracker, BacktrackParameter
from _emerge.resolver.slot_collision import slot_conflict_handler
from _emerge.resolver.circular_dependency import circular_dependency_handler
from _emerge.resolver.output import Display

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int
	_unicode = str
else:
	_unicode = unicode

class _scheduler_graph_config(object):
	def __init__(self, trees, pkg_cache, graph, mergelist):
		self.trees = trees
		self.pkg_cache = pkg_cache
		self.graph = graph
		self.mergelist = mergelist

def _wildcard_set(atoms):
	pkgs = InternalPackageSet(allow_wildcard=True)
	for x in atoms:
		try:
			x = Atom(x, allow_wildcard=True, allow_repo=False)
		except portage.exception.InvalidAtom:
			x = Atom("*/" + x, allow_wildcard=True, allow_repo=False)
		pkgs.add(x)
	return pkgs

class _frozen_depgraph_config(object):

	def __init__(self, settings, trees, myopts, spinner):
		self.settings = settings
		self.target_root = settings["EROOT"]
		self.myopts = myopts
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.spinner = spinner
		self._running_root = trees[trees._running_eroot]["root_config"]
		self.pkgsettings = {}
		self.trees = {}
		self._trees_orig = trees
		self.roots = {}
		# All Package instances
		self._pkg_cache = {}
		self._highest_license_masked = {}
		dynamic_deps = myopts.get("--dynamic-deps", "y") != "n"
		ignore_built_slot_operator_deps = myopts.get(
			"--ignore-built-slot-operator-deps", "n") == "y"
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
					pkg_root_config=self.roots[myroot],
					dynamic_deps=dynamic_deps,
					ignore_built_slot_operator_deps=ignore_built_slot_operator_deps)
			self.pkgsettings[myroot] = portage.config(
				clone=self.trees[myroot]["vartree"].settings)

		self._required_set_names = set(["world"])

		atoms = ' '.join(myopts.get("--exclude", [])).split()
		self.excluded_pkgs = _wildcard_set(atoms)
		atoms = ' '.join(myopts.get("--reinstall-atoms", [])).split()
		self.reinstall_atoms = _wildcard_set(atoms)
		atoms = ' '.join(myopts.get("--usepkg-exclude", [])).split()
		self.usepkg_exclude = _wildcard_set(atoms)
		atoms = ' '.join(myopts.get("--useoldpkg-atoms", [])).split()
		self.useoldpkg_atoms = _wildcard_set(atoms)
		atoms = ' '.join(myopts.get("--rebuild-exclude", [])).split()
		self.rebuild_exclude = _wildcard_set(atoms)
		atoms = ' '.join(myopts.get("--rebuild-ignore", [])).split()
		self.rebuild_ignore = _wildcard_set(atoms)

		self.rebuild_if_new_rev = "--rebuild-if-new-rev" in myopts
		self.rebuild_if_new_ver = "--rebuild-if-new-ver" in myopts
		self.rebuild_if_unbuilt = "--rebuild-if-unbuilt" in myopts

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

class _rebuild_config(object):
	def __init__(self, frozen_config, backtrack_parameters):
		self._graph = digraph()
		self._frozen_config = frozen_config
		self.rebuild_list = backtrack_parameters.rebuild_list.copy()
		self.orig_rebuild_list = self.rebuild_list.copy()
		self.reinstall_list = backtrack_parameters.reinstall_list.copy()
		self.rebuild_if_new_rev = frozen_config.rebuild_if_new_rev
		self.rebuild_if_new_ver = frozen_config.rebuild_if_new_ver
		self.rebuild_if_unbuilt = frozen_config.rebuild_if_unbuilt
		self.rebuild = (self.rebuild_if_new_rev or self.rebuild_if_new_ver or
			self.rebuild_if_unbuilt)

	def add(self, dep_pkg, dep):
		parent = dep.collapsed_parent
		priority = dep.collapsed_priority
		rebuild_exclude = self._frozen_config.rebuild_exclude
		rebuild_ignore = self._frozen_config.rebuild_ignore
		if (self.rebuild and isinstance(parent, Package) and
			parent.built and priority.buildtime and
			isinstance(dep_pkg, Package) and
			not rebuild_exclude.findAtomForPackage(parent) and
			not rebuild_ignore.findAtomForPackage(dep_pkg)):
			self._graph.add(dep_pkg, parent, priority)

	def _needs_rebuild(self, dep_pkg):
		"""Check whether packages that depend on dep_pkg need to be rebuilt."""
		dep_root_slot = (dep_pkg.root, dep_pkg.slot_atom)
		if dep_pkg.built or dep_root_slot in self.orig_rebuild_list:
			return False

		if self.rebuild_if_unbuilt:
			# dep_pkg is being installed from source, so binary
			# packages for parents are invalid. Force rebuild
			return True

		trees = self._frozen_config.trees
		vardb = trees[dep_pkg.root]["vartree"].dbapi
		if self.rebuild_if_new_rev:
			# Parent packages are valid if a package with the same
			# cpv is already installed.
			return dep_pkg.cpv not in vardb.match(dep_pkg.slot_atom)

		# Otherwise, parent packages are valid if a package with the same
		# version (excluding revision) is already installed.
		assert self.rebuild_if_new_ver
		cpv_norev = catpkgsplit(dep_pkg.cpv)[:-1]
		for inst_cpv in vardb.match(dep_pkg.slot_atom):
			inst_cpv_norev = catpkgsplit(inst_cpv)[:-1]
			if inst_cpv_norev == cpv_norev:
				return False

		return True

	def _trigger_rebuild(self, parent, build_deps):
		root_slot = (parent.root, parent.slot_atom)
		if root_slot in self.rebuild_list:
			return False
		trees = self._frozen_config.trees
		reinstall = False
		for slot_atom, dep_pkg in build_deps.items():
			dep_root_slot = (dep_pkg.root, slot_atom)
			if self._needs_rebuild(dep_pkg):
				self.rebuild_list.add(root_slot)
				return True
			elif ("--usepkg" in self._frozen_config.myopts and
				(dep_root_slot in self.reinstall_list or
				dep_root_slot in self.rebuild_list or
				not dep_pkg.installed)):

				# A direct rebuild dependency is being installed. We
				# should update the parent as well to the latest binary,
				# if that binary is valid.
				#
				# To validate the binary, we check whether all of the
				# rebuild dependencies are present on the same binhost.
				#
				# 1) If parent is present on the binhost, but one of its
				#    rebuild dependencies is not, then the parent should
				#    be rebuilt from source.
				# 2) Otherwise, the parent binary is assumed to be valid,
				#    because all of its rebuild dependencies are
				#    consistent.
				bintree = trees[parent.root]["bintree"]
				uri = bintree.get_pkgindex_uri(parent.cpv)
				dep_uri = bintree.get_pkgindex_uri(dep_pkg.cpv)
				bindb = bintree.dbapi
				if self.rebuild_if_new_ver and uri and uri != dep_uri:
					cpv_norev = catpkgsplit(dep_pkg.cpv)[:-1]
					for cpv in bindb.match(dep_pkg.slot_atom):
						if cpv_norev == catpkgsplit(cpv)[:-1]:
							dep_uri = bintree.get_pkgindex_uri(cpv)
							if uri == dep_uri:
								break
				if uri and uri != dep_uri:
					# 1) Remote binary package is invalid because it was
					#    built without dep_pkg. Force rebuild.
					self.rebuild_list.add(root_slot)
					return True
				elif (parent.installed and
					root_slot not in self.reinstall_list):
					inst_build_time = parent.metadata.get("BUILD_TIME")
					try:
						bin_build_time, = bindb.aux_get(parent.cpv,
							["BUILD_TIME"])
					except KeyError:
						continue
					if bin_build_time != inst_build_time:
						# 2) Remote binary package is valid, and local package
						#    is not up to date. Force reinstall.
						reinstall = True
		if reinstall:
			self.reinstall_list.add(root_slot)
		return reinstall

	def trigger_rebuilds(self):
		"""
		Trigger rebuilds where necessary. If pkgA has been updated, and pkgB
		depends on pkgA at both build-time and run-time, pkgB needs to be
		rebuilt.
		"""
		need_restart = False
		graph = self._graph
		build_deps = {}

		leaf_nodes = deque(graph.leaf_nodes())

		# Trigger rebuilds bottom-up (starting with the leaves) so that parents
		# will always know which children are being rebuilt.
		while graph:
			if not leaf_nodes:
				# We'll have to drop an edge. This should be quite rare.
				leaf_nodes.append(graph.order[-1])

			node = leaf_nodes.popleft()
			if node not in graph:
				# This can be triggered by circular dependencies.
				continue
			slot_atom = node.slot_atom

			# Remove our leaf node from the graph, keeping track of deps.
			parents = graph.parent_nodes(node)
			graph.remove(node)
			node_build_deps = build_deps.get(node, {})
			for parent in parents:
				if parent == node:
					# Ignore a direct cycle.
					continue
				parent_bdeps = build_deps.setdefault(parent, {})
				parent_bdeps[slot_atom] = node
				if not graph.child_nodes(parent):
					leaf_nodes.append(parent)

			# Trigger rebuilds for our leaf node. Because all of our children
			# have been processed, the build_deps will be completely filled in,
			# and self.rebuild_list / self.reinstall_list will tell us whether
			# any of our children need to be rebuilt or reinstalled.
			if self._trigger_rebuild(node, node_build_deps):
				need_restart = True

		return need_restart


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
		# This should be ordered such that the backtracker will
		# attempt to solve conflicts which occurred earlier first,
		# since an earlier conflict can be the cause of a conflict
		# which occurs later.
		self._slot_collision_info = OrderedDict()
		# Slot collision nodes are not allowed to block other packages since
		# blocker validation is only able to account for one package per slot.
		self._slot_collision_nodes = set()
		self._parent_atoms = {}
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

		# Binary packages that have been rejected because their USE
		# didn't match the user's config. It maps packages to a set
		# of flags causing the rejection.
		self.ignored_binaries = {}

		self._needed_unstable_keywords = backtrack_parameters.needed_unstable_keywords
		self._needed_p_mask_changes = backtrack_parameters.needed_p_mask_changes
		self._needed_license_changes = backtrack_parameters.needed_license_changes
		self._needed_use_config_changes = backtrack_parameters.needed_use_config_changes
		self._runtime_pkg_mask = backtrack_parameters.runtime_pkg_mask
		self._slot_operator_replace_installed = backtrack_parameters.slot_operator_replace_installed
		self._prune_rebuilds = backtrack_parameters.prune_rebuilds
		self._need_restart = False
		# For conditions that always require user intervention, such as
		# unsatisfied REQUIRED_USE (currently has no autounmask support).
		self._skip_restart = False
		self._backtrack_infos = {}

		self._autounmask = depgraph._frozen_config.myopts.get('--autounmask') != 'n'
		self._success_without_autounmask = False
		self._traverse_ignored_deps = False
		self._complete_mode = False
		self._slot_operator_deps = {}

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
			self._graph_trees[myroot]["graph_db"]   = graph_tree.dbapi
			self._graph_trees[myroot]["graph"]      = self.digraph
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
			self._filtered_trees[myroot]["graph"]    = self.digraph
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
	
	def __init__(self, settings, trees, myopts, myparams, spinner,
		frozen_config=None, backtrack_parameters=BacktrackParameter(), allow_backtracking=False):
		if frozen_config is None:
			frozen_config = _frozen_depgraph_config(settings, trees,
			myopts, spinner)
		self._frozen_config = frozen_config
		self._dynamic_config = _dynamic_depgraph_config(self, myparams,
			allow_backtracking, backtrack_parameters)
		self._rebuild = _rebuild_config(frozen_config, backtrack_parameters)

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

			dynamic_deps = self._dynamic_config.myparams.get(
				"dynamic_deps", "y") != "n"
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
					if dynamic_deps:
						# This causes FakeVartree to update the
						# Package instance dependencies via
						# PackageVirtualDbapi.aux_update()
						vardb.aux_get(pkg.cpv, [])
					fakedb.cpv_inject(pkg)

		self._dynamic_config._vdb_loaded = True

	def _spinner_update(self):
		if self._frozen_config.spinner:
			self._frozen_config.spinner.update()

	def _show_ignored_binaries(self):
		"""
		Show binaries that have been ignored because their USE didn't
		match the user's config.
		"""
		if not self._dynamic_config.ignored_binaries \
			or '--quiet' in self._frozen_config.myopts \
			or self._dynamic_config.myparams.get(
			"binpkg_respect_use") in ("y", "n"):
			return

		for pkg in list(self._dynamic_config.ignored_binaries):

			selected_pkg = self._dynamic_config.mydbapi[pkg.root
				].match_pkgs(pkg.slot_atom)

			if not selected_pkg:
				continue

			selected_pkg = selected_pkg[-1]
			if selected_pkg > pkg:
				self._dynamic_config.ignored_binaries.pop(pkg)
				continue

			if selected_pkg.installed and \
				selected_pkg.cpv == pkg.cpv and \
				selected_pkg.metadata.get('BUILD_TIME') == \
				pkg.metadata.get('BUILD_TIME'):
				# We don't care about ignored binaries when an
				# identical installed instance is selected to
				# fill the slot.
				self._dynamic_config.ignored_binaries.pop(pkg)
				continue

		if not self._dynamic_config.ignored_binaries:
			return

		self._show_merge_list()

		writemsg("\n!!! The following binary packages have been ignored " + \
				"due to non matching USE:\n\n", noiselevel=-1)

		for pkg, flags in self._dynamic_config.ignored_binaries.items():
			flag_display = []
			for flag in sorted(flags):
				if flag not in pkg.use.enabled:
					flag = "-" + flag
				flag_display.append(flag)
			flag_display = " ".join(flag_display)
			# The user can paste this line into package.use
			writemsg("    =%s %s" % (pkg.cpv, flag_display), noiselevel=-1)
			if pkg.root_config.settings["ROOT"] != "/":
				writemsg(" # for %s" % (pkg.root,), noiselevel=-1)
			writemsg("\n", noiselevel=-1)

		msg = [
			"",
			"NOTE: The --binpkg-respect-use=n option will prevent emerge",
			"      from ignoring these binary packages if possible.",
			"      Using --binpkg-respect-use=y will silence this warning."
		]

		for line in msg:
			if line:
				line = colorize("INFORM", line)
			writemsg(line + "\n", noiselevel=-1)

	def _get_missed_updates(self):

		# In order to minimize noise, show only the highest
		# missed update from each SLOT.
		missed_updates = {}
		for pkg, mask_reasons in \
			self._dynamic_config._runtime_pkg_mask.items():
			if pkg.installed:
				# Exclude installed here since we only
				# want to show available updates.
				continue
			chosen_pkg = self._dynamic_config.mydbapi[pkg.root
				].match_pkgs(pkg.slot_atom)
			if not chosen_pkg or chosen_pkg[-1] >= pkg:
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

		return missed_updates

	def _show_missed_update(self):

		missed_updates = self._get_missed_updates()

		if not missed_updates:
			return

		missed_update_types = {}
		for pkg, mask_type, parent_atoms in missed_updates.values():
			missed_update_types.setdefault(mask_type,
				[]).append((pkg, parent_atoms))

		if '--quiet' in self._frozen_config.myopts and \
			'--debug' not in self._frozen_config.myopts:
			missed_update_types.pop("slot conflict", None)
			missed_update_types.pop("missing dependency", None)

		self._show_missed_update_slot_conflicts(
			missed_update_types.get("slot conflict"))

		self._show_missed_update_unsatisfied_dep(
			missed_update_types.get("missing dependency"))

	def _show_missed_update_unsatisfied_dep(self, missed_updates):

		if not missed_updates:
			return

		self._show_merge_list()
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
			if pkg.root_config.settings["ROOT"] != "/":
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
				if pkg.root_config.settings["ROOT"] != "/":
					writemsg(" for %s" % (pkg.root,), noiselevel=-1)
				writemsg("\n", noiselevel=-1)

	def _show_missed_update_slot_conflicts(self, missed_updates):

		if not missed_updates:
			return

		self._show_merge_list()
		msg = []
		msg.append("\nWARNING: One or more updates have been " + \
			"skipped due to a dependency conflict:\n\n")

		indent = "  "
		for pkg, parent_atoms in missed_updates:
			msg.append(str(pkg.slot_atom))
			if pkg.root_config.settings["ROOT"] != "/":
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
		If there are any slot conflicts and backtracking is enabled,
		_complete_graph should complete the graph before this method
		is called, so that all relevant reverse dependencies are
		available for use in backtracking decisions.
		"""
		for (slot_atom, root), slot_nodes in \
			self._dynamic_config._slot_collision_info.items():
			self._process_slot_conflict(root, slot_atom, slot_nodes)

	def _process_slot_conflict(self, root, slot_atom, slot_nodes):
		"""
		Process slot conflict data to identify specific atoms which
		lead to conflict. These atoms only match a subset of the
		packages that have been pulled into a given slot.
		"""

		debug = "--debug" in self._frozen_config.myopts

		slot_parent_atoms = set()
		for pkg in slot_nodes:
			parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
			if not parent_atoms:
				continue
			slot_parent_atoms.update(parent_atoms)

		conflict_pkgs = []
		conflict_atoms = {}
		for pkg in slot_nodes:

			if self._dynamic_config._allow_backtracking and \
				pkg in self._dynamic_config._runtime_pkg_mask:
				if debug:
					writemsg_level(
						"!!! backtracking loop detected: %s %s\n" % \
						(pkg,
						self._dynamic_config._runtime_pkg_mask[pkg]),
						level=logging.DEBUG, noiselevel=-1)

			parent_atoms = self._dynamic_config._parent_atoms.get(pkg)
			if parent_atoms is None:
				parent_atoms = set()
				self._dynamic_config._parent_atoms[pkg] = parent_atoms

			all_match = True
			for parent_atom in slot_parent_atoms:
				if parent_atom in parent_atoms:
					continue
				# Use package set for matching since it will match via
				# PROVIDE when necessary, while match_from_list does not.
				parent, atom = parent_atom
				atom_set = InternalPackageSet(
					initial_atoms=(atom,), allow_repo=True)
				if atom_set.findAtomForPackage(pkg,
					modified_use=self._pkg_use_enabled(pkg)):
					parent_atoms.add(parent_atom)
				else:
					all_match = False
					conflict_atoms.setdefault(parent_atom, set()).add(pkg)

			if not all_match:
				conflict_pkgs.append(pkg)

		if conflict_pkgs and \
			self._dynamic_config._allow_backtracking and \
			not self._accept_blocker_conflicts():
			remaining = []
			for pkg in conflict_pkgs:
				if self._slot_conflict_backtrack_abi(pkg,
					slot_nodes, conflict_atoms):
					backtrack_infos = self._dynamic_config._backtrack_infos
					config = backtrack_infos.setdefault("config", {})
					config.setdefault("slot_conflict_abi", set()).add(pkg)
				else:
					remaining.append(pkg)
			if remaining:
				self._slot_confict_backtrack(root, slot_atom,
					slot_parent_atoms, remaining)

	def _slot_confict_backtrack(self, root, slot_atom,
		all_parents, conflict_pkgs):

		debug = "--debug" in self._frozen_config.myopts
		existing_node = self._dynamic_config._slot_pkg_map[root][slot_atom]
		backtrack_data = []
		# The ordering of backtrack_data can make
		# a difference here, because both mask actions may lead
		# to valid, but different, solutions and the one with
		# 'existing_node' masked is usually the better one. Because
		# of that, we choose an order such that
		# the backtracker will first explore the choice with
		# existing_node masked. The backtracker reverses the
		# order, so the order it uses is the reverse of the
		# order shown here. See bug #339606.
		if existing_node in conflict_pkgs and \
			existing_node is not conflict_pkgs[-1]:
			conflict_pkgs.remove(existing_node)
			conflict_pkgs.append(existing_node)
		for to_be_masked in conflict_pkgs:
			# For missed update messages, find out which
			# atoms matched to_be_selected that did not
			# match to_be_masked.
			parent_atoms = \
				self._dynamic_config._parent_atoms.get(to_be_masked, set())
			conflict_atoms = set(parent_atom for parent_atom in all_parents \
				if parent_atom not in parent_atoms)
			backtrack_data.append((to_be_masked, conflict_atoms))

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
			elif any(pkg > existing_node for pkg in conflict_pkgs):
				backtrack_data.reverse()

		to_be_masked = backtrack_data[-1][0]

		self._dynamic_config._backtrack_infos.setdefault(
			"slot conflict", []).append(backtrack_data)
		self._dynamic_config._need_restart = True
		if debug:
			msg = []
			msg.append("")
			msg.append("")
			msg.append("backtracking due to slot conflict:")
			msg.append("   first package:  %s" % existing_node)
			msg.append("  package to mask: %s" % to_be_masked)
			msg.append("      slot: %s" % slot_atom)
			msg.append("   parents: %s" % ", ".join( \
				"(%s, '%s')" % (ppkg, atom) for ppkg, atom in all_parents))
			msg.append("")
			writemsg_level("".join("%s\n" % l for l in msg),
				noiselevel=-1, level=logging.DEBUG)

	def _slot_conflict_backtrack_abi(self, pkg, slot_nodes, conflict_atoms):
		"""
		If one or more conflict atoms have a slot/sub-slot dep that can be resolved
		by rebuilding the parent package, then schedule the rebuild via
		backtracking, and return True. Otherwise, return False.
		"""

		found_update = False
		for parent_atom, conflict_pkgs in conflict_atoms.items():
			parent, atom = parent_atom
			if atom.slot_operator != "=" or not parent.built:
				continue

			if pkg not in conflict_pkgs:
				continue

			for other_pkg in slot_nodes:
				if other_pkg in conflict_pkgs:
					continue

				dep = Dependency(atom=atom, child=other_pkg,
					parent=parent, root=pkg.root)

				if self._slot_operator_update_probe(dep):
					self._slot_operator_update_backtrack(dep)
					found_update = True

		return found_update

	def _slot_operator_update_backtrack(self, dep, new_child_slot=None):
		if new_child_slot is None:
			child = dep.child
		else:
			child = new_child_slot
		if "--debug" in self._frozen_config.myopts:
			msg = []
			msg.append("")
			msg.append("")
			msg.append("backtracking due to missed slot abi update:")
			msg.append("   child package:  %s" % child)
			if new_child_slot is not None:
				msg.append("   new child slot package:  %s" % new_child_slot)
			msg.append("   parent package: %s" % dep.parent)
			msg.append("   atom: %s" % dep.atom)
			msg.append("")
			writemsg_level("\n".join(msg),
				noiselevel=-1, level=logging.DEBUG)
		backtrack_infos = self._dynamic_config._backtrack_infos
		config = backtrack_infos.setdefault("config", {})

		# mask unwanted binary packages if necessary
		abi_masks = {}
		if new_child_slot is None:
			if not child.installed:
				abi_masks.setdefault(child, {})["slot_operator_mask_built"] = None
		if not dep.parent.installed:
			abi_masks.setdefault(dep.parent, {})["slot_operator_mask_built"] = None
		if abi_masks:
			config.setdefault("slot_operator_mask_built", {}).update(abi_masks)

		# trigger replacement of installed packages if necessary
		abi_reinstalls = set()
		if dep.parent.installed:
			abi_reinstalls.add((dep.parent.root, dep.parent.slot_atom))
		if new_child_slot is None and child.installed:
			abi_reinstalls.add((child.root, child.slot_atom))
		if abi_reinstalls:
			config.setdefault("slot_operator_replace_installed",
				set()).update(abi_reinstalls)

		self._dynamic_config._need_restart = True

	def _slot_operator_update_probe(self, dep, new_child_slot=False):
		"""
		slot/sub-slot := operators tend to prevent updates from getting pulled in,
		since installed packages pull in packages with the slot/sub-slot that they
		were built against. Detect this case so that we can schedule rebuilds
		and reinstalls when appropriate.
		NOTE: This function only searches for updates that involve upgrades
			to higher versions, since the logic required to detect when a
			downgrade would be desirable is not implemented.
		"""

		if dep.child.installed and \
			self._frozen_config.excluded_pkgs.findAtomForPackage(dep.child,
			modified_use=self._pkg_use_enabled(dep.child)):
			return None

		if dep.parent.installed and \
			self._frozen_config.excluded_pkgs.findAtomForPackage(dep.parent,
			modified_use=self._pkg_use_enabled(dep.parent)):
			return None

		debug = "--debug" in self._frozen_config.myopts
		want_downgrade = None

		for replacement_parent in self._iter_similar_available(dep.parent,
			dep.parent.slot_atom):

			for atom in replacement_parent.validated_atoms:
				if not atom.slot_operator == "=" or \
					atom.blocker or \
					atom.cp != dep.atom.cp:
					continue

				# Discard USE deps, we're only searching for an approximate
				# pattern, and dealing with USE states is too complex for
				# this purpose.
				atom = atom.without_use

				if replacement_parent.built and \
					portage.dep._match_slot(atom, dep.child):
					# Our selected replacement_parent appears to be built
					# for the existing child selection. So, discard this
					# parent and search for another.
					break

				for pkg in self._iter_similar_available(
					dep.child, atom):
					if pkg.slot == dep.child.slot and \
						pkg.sub_slot == dep.child.sub_slot:
						# If slot/sub-slot is identical, then there's
						# no point in updating.
						continue
					if new_child_slot:
						if pkg.slot == dep.child.slot:
							continue
						if pkg < dep.child:
							# the new slot only matters if the
							# package version is higher
							continue
					else:
						if pkg.slot != dep.child.slot:
							continue
						if pkg < dep.child:
							if want_downgrade is None:
								want_downgrade = self._downgrade_probe(dep.child)
							# be careful not to trigger a rebuild when
							# the only version available with a
							# different slot_operator is an older version
							if not want_downgrade:
								continue

					if debug:
						msg = []
						msg.append("")
						msg.append("")
						msg.append("slot_operator_update_probe:")
						msg.append("   existing child package:  %s" % dep.child)
						msg.append("   existing parent package: %s" % dep.parent)
						msg.append("   new child package:  %s" % pkg)
						msg.append("   new parent package: %s" % replacement_parent)
						msg.append("")
						writemsg_level("\n".join(msg),
							noiselevel=-1, level=logging.DEBUG)

					return pkg

		if debug:
			msg = []
			msg.append("")
			msg.append("")
			msg.append("slot_operator_update_probe:")
			msg.append("   existing child package:  %s" % dep.child)
			msg.append("   existing parent package: %s" % dep.parent)
			msg.append("   new child package:  %s" % None)
			msg.append("   new parent package: %s" % None)
			msg.append("")
			writemsg_level("\n".join(msg),
				noiselevel=-1, level=logging.DEBUG)

		return None

	def _downgrade_probe(self, pkg):
		"""
		Detect cases where a downgrade of the given package is considered
		desirable due to the current version being masked or unavailable.
		"""
		available_pkg = None
		for available_pkg in self._iter_similar_available(pkg,
			pkg.slot_atom):
			if available_pkg >= pkg:
				# There's an available package of the same or higher
				# version, so downgrade seems undesirable.
				return False

		return available_pkg is not None

	def _iter_similar_available(self, graph_pkg, atom):
		"""
		Given a package that's in the graph, do a rough check to
		see if a similar package is available to install. The given
		graph_pkg itself may be yielded only if it's not installed.
		"""

		usepkgonly = "--usepkgonly" in self._frozen_config.myopts
		useoldpkg_atoms = self._frozen_config.useoldpkg_atoms
		use_ebuild_visibility = self._frozen_config.myopts.get(
			'--use-ebuild-visibility', 'n') != 'n'

		for pkg in self._iter_match_pkgs_any(
			graph_pkg.root_config, atom):
			if pkg.cp != graph_pkg.cp:
				# discard old-style virtual match
				continue
			if pkg.installed:
				continue
			if pkg in self._dynamic_config._runtime_pkg_mask:
				continue
			if self._frozen_config.excluded_pkgs.findAtomForPackage(pkg,
				modified_use=self._pkg_use_enabled(pkg)):
				continue
			if not self._pkg_visibility_check(pkg):
				continue
			if pkg.built:
				if self._equiv_binary_installed(pkg):
					continue
				if not (not use_ebuild_visibility and
					(usepkgonly or useoldpkg_atoms.findAtomForPackage(
					pkg, modified_use=self._pkg_use_enabled(pkg)))) and \
					not self._equiv_ebuild_visible(pkg):
					continue
			yield pkg

	def _slot_operator_trigger_reinstalls(self):
		"""
		Search for packages with slot-operator deps on older slots, and schedule
		rebuilds if they can link to a newer slot that's in the graph.
		"""

		rebuild_if_new_slot = self._dynamic_config.myparams.get(
			"rebuild_if_new_slot", "y") == "y"

		for slot_key, slot_info in self._dynamic_config._slot_operator_deps.items():

			for dep in slot_info:
				if not (dep.parent and
					isinstance(dep.parent, Package) and dep.parent.built):
					continue

				# Check for slot update first, since we don't want to
				# trigger reinstall of the child package when a newer
				# slot will be used instead.
				if rebuild_if_new_slot:
					new_child = self._slot_operator_update_probe(dep,
						new_child_slot=True)
					if new_child:
						self._slot_operator_update_backtrack(dep,
							new_child_slot=new_child)
						break

				if dep.want_update:
					if self._slot_operator_update_probe(dep):
						self._slot_operator_update_backtrack(dep)
						break

	def _reinstall_for_flags(self, pkg, forced_flags,
		orig_use, orig_iuse, cur_use, cur_iuse):
		"""Return a set of flags that trigger reinstallation, or None if there
		are no such flags."""

		# binpkg_respect_use: Behave like newuse by default. If newuse is
		# False and changed_use is True, then behave like changed_use.
		binpkg_respect_use = (pkg.built and
			self._dynamic_config.myparams.get("binpkg_respect_use")
			in ("y", "auto"))
		newuse = "--newuse" in self._frozen_config.myopts
		changed_use = "changed-use" == self._frozen_config.myopts.get("--reinstall")
		feature_flags = _get_feature_flags(
			_get_eapi_attrs(pkg.metadata["EAPI"]))

		if newuse or (binpkg_respect_use and not changed_use):
			flags = set(orig_iuse.symmetric_difference(
				cur_iuse).difference(forced_flags))
			flags.update(orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use)))
			flags.difference_update(feature_flags)
			if flags:
				return flags

		elif changed_use or binpkg_respect_use:
			flags = set(orig_iuse.intersection(orig_use).symmetric_difference(
				cur_iuse.intersection(cur_use)))
			flags.difference_update(feature_flags)
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
		@return: All args given in the input together with additional
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

				if add_to_digraph:
					self._dynamic_config.digraph.add(arg, None,
						priority=BlockerDepPriority.instance)

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
		if dep.blocker:
			if not buildpkgonly and \
				not nodeps and \
				not dep.collapsed_priority.ignored and \
				not dep.collapsed_priority.optional and \
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

		if not dep_pkg:
			if (dep.collapsed_priority.optional or
				dep.collapsed_priority.ignored):
				# This is an unnecessary build-time dep.
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
					if debug:
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
						if debug:
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

		self._rebuild.add(dep_pkg, dep)

		ignore = dep.collapsed_priority.ignored and \
			not self._dynamic_config._traverse_ignored_deps
		if not ignore and not self._add_pkg(dep_pkg, dep):
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
		"""
		Adds a package to the depgraph, queues dependencies, and handles
		slot conflicts.
		"""
		debug = "--debug" in self._frozen_config.myopts
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

		if debug:
			writemsg_level(
				"\n%s%s %s\n" % ("Child:".ljust(15), pkg,
				pkg_use_display(pkg, self._frozen_config.myopts,
				modified_use=self._pkg_use_enabled(pkg))),
				level=logging.DEBUG, noiselevel=-1)
			if isinstance(myparent,
				(PackageArg, AtomArg)):
				# For PackageArg and AtomArg types, it's
				# redundant to display the atom attribute.
				writemsg_level(
					"%s%s\n" % ("Parent Dep:".ljust(15), myparent),
					level=logging.DEBUG, noiselevel=-1)
			else:
				# Display the specific atom from SetArg or
				# Package types.
				uneval = ""
				if dep.atom is not dep.atom.unevaluated_atom:
					uneval = " (%s)" % (dep.atom.unevaluated_atom,)
				writemsg_level(
					"%s%s%s required by %s\n" %
					("Parent Dep:".ljust(15), dep.atom, uneval, myparent),
					level=logging.DEBUG, noiselevel=-1)

		# Ensure that the dependencies of the same package
		# are never processed more than once.
		previously_added = pkg in self._dynamic_config.digraph

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

		# NOTE: REQUIRED_USE checks are delayed until after
		# package selection, since we want to prompt the user
		# for USE adjustment rather than have REQUIRED_USE
		# affect package selection and || dep choices.
		if not pkg.built and pkg.metadata.get("REQUIRED_USE") and \
			eapi_has_required_use(pkg.metadata["EAPI"]):
			required_use_is_sat = check_required_use(
				pkg.metadata["REQUIRED_USE"],
				self._pkg_use_enabled(pkg),
				pkg.iuse.is_valid_flag,
				eapi=pkg.metadata["EAPI"])
			if not required_use_is_sat:
				if dep.atom is not None and dep.parent is not None:
					self._add_parent_atom(pkg, (dep.parent, dep.atom))

				if arg_atoms:
					for parent_atom in arg_atoms:
						parent, atom = parent_atom
						self._add_parent_atom(pkg, parent_atom)

				atom = dep.atom
				if atom is None:
					atom = Atom("=" + pkg.cpv)
				self._dynamic_config._unsatisfied_deps_for_display.append(
					((pkg.root, atom),
					{"myparent" : dep.parent, "show_req_use" : pkg}))
				self._dynamic_config._skip_restart = True
				return 0

		if not pkg.onlydeps:

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
					self._add_slot_conflict(pkg)
					if debug:
						writemsg_level(
							"%s%s %s\n" % ("Slot Conflict:".ljust(15),
							existing_node, pkg_use_display(existing_node,
							self._frozen_config.myopts,
							modified_use=self._pkg_use_enabled(existing_node))),
							level=logging.DEBUG, noiselevel=-1)

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
				except portage.exception.InvalidDependString:
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

		# This section determines whether we go deeper into dependencies or not.
		# We want to go deeper on a few occasions:
		# Installing package A, we need to make sure package A's deps are met.
		# emerge --deep <pkgspec>; we need to recursively check dependencies of pkgspec
		# If we are in --nodeps (no recursion) mode, we obviously only check 1 level of dependencies.
		if arg_atoms and depth > 0:
			for parent, atom in arg_atoms:
				if parent.reset_depth:
					depth = 0
					break

		if previously_added and pkg.depth is not None:
			depth = min(pkg.depth, depth)
		pkg.depth = depth
		deep = self._dynamic_config.myparams.get("deep", 0)
		update = "--update" in self._frozen_config.myopts

		dep.want_update = (not self._dynamic_config._complete_mode and
			(arg_atoms or update) and
			not (deep is not True and depth > deep))

		dep.child = pkg
		if (not pkg.onlydeps and
			dep.atom and dep.atom.slot_operator_built):
			self._add_slot_operator_dep(dep)

		recurse = deep is True or depth + 1 <= deep
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

	def _add_slot_operator_dep(self, dep):
		slot_key = (dep.root, dep.child.slot_atom)
		slot_info = self._dynamic_config._slot_operator_deps.get(slot_key)
		if slot_info is None:
			slot_info = []
			self._dynamic_config._slot_operator_deps[slot_key] = slot_info
		slot_info.append(dep)

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

		myroot = pkg.root
		metadata = pkg.metadata
		removal_action = "remove" in self._dynamic_config.myparams
		eapi_attrs = _get_eapi_attrs(pkg.metadata["EAPI"])

		edepend={}
		for k in Package._dep_keys:
			edepend[k] = metadata[k]

		if not pkg.built and \
			"--buildpkgonly" in self._frozen_config.myopts and \
			"deep" not in self._dynamic_config.myparams:
			edepend["RDEPEND"] = ""
			edepend["PDEPEND"] = ""

		ignore_build_time_deps = False
		if pkg.built and not removal_action:
			if self._dynamic_config.myparams.get("bdeps", "n") == "y":
				# Pull in build time deps as requested, but marked them as
				# "optional" since they are not strictly required. This allows
				# more freedom in the merge order calculation for solving
				# circular dependencies. Don't convert to PDEPEND since that
				# could make --with-bdeps=y less effective if it is used to
				# adjust merge order to prevent built_with_use() calls from
				# failing.
				pass
			else:
				ignore_build_time_deps = True

		if removal_action and self._dynamic_config.myparams.get("bdeps", "y") == "n":
			# Removal actions never traverse ignored buildtime
			# dependencies, so it's safe to discard them early.
			edepend["DEPEND"] = ""
			edepend["HDEPEND"] = ""
			ignore_build_time_deps = True

		ignore_depend_deps = ignore_build_time_deps
		ignore_hdepend_deps = ignore_build_time_deps

		if removal_action:
			depend_root = myroot
		else:
			if eapi_attrs.hdepend:
				depend_root = myroot
			else:
				depend_root = self._frozen_config._running_root.root
				root_deps = self._frozen_config.myopts.get("--root-deps")
				if root_deps is not None:
					if root_deps is True:
						depend_root = myroot
					elif root_deps == "rdeps":
						ignore_depend_deps = True

		# If rebuild mode is not enabled, it's safe to discard ignored
		# build-time dependencies. If you want these deps to be traversed
		# in "complete" mode then you need to specify --with-bdeps=y.
		if not self._rebuild.rebuild:
			if ignore_depend_deps:
				edepend["DEPEND"] = ""
			if ignore_hdepend_deps:
				edepend["HDEPEND"] = ""

		deps = (
			(depend_root, edepend["DEPEND"],
				self._priority(buildtime=True,
				optional=(pkg.built or ignore_depend_deps),
				ignored=ignore_depend_deps)),
			(self._frozen_config._running_root.root, edepend["HDEPEND"],
				self._priority(buildtime=True,
				optional=(pkg.built or ignore_hdepend_deps),
				ignored=ignore_hdepend_deps)),
			(myroot, edepend["RDEPEND"],
				self._priority(runtime=True)),
			(myroot, edepend["PDEPEND"],
				self._priority(runtime_post=True))
		)

		debug = "--debug" in self._frozen_config.myopts

		for dep_root, dep_string, dep_priority in deps:
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
						uselist=self._pkg_use_enabled(pkg),
						is_valid_flag=pkg.iuse.is_valid_flag,
						opconvert=True, token_class=Atom,
						eapi=pkg.metadata['EAPI'])
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
							uselist=self._pkg_use_enabled(pkg),
							opconvert=True, token_class=Atom,
							eapi=pkg.metadata['EAPI'])
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

				if not self._add_pkg_dep_string(
					pkg, dep_root, dep_priority, dep_string,
					allow_unsatisfied):
					return 0

		self._dynamic_config._traversed_pkg_deps.add(pkg)
		return 1

	def _add_pkg_dep_string(self, pkg, dep_root, dep_priority, dep_string,
		allow_unsatisfied):
		_autounmask_backup = self._dynamic_config._autounmask
		if dep_priority.optional or dep_priority.ignored:
			# Temporarily disable autounmask for deps that
			# don't necessarily need to be satisfied.
			self._dynamic_config._autounmask = False
		try:
			return self._wrapped_add_pkg_dep_string(
				pkg, dep_root, dep_priority, dep_string,
				allow_unsatisfied)
		finally:
			self._dynamic_config._autounmask = _autounmask_backup

	def _wrapped_add_pkg_dep_string(self, pkg, dep_root, dep_priority,
		dep_string, allow_unsatisfied):
		depth = pkg.depth + 1
		deep = self._dynamic_config.myparams.get("deep", 0)
		recurse_satisfied = deep is True or depth <= deep
		debug = "--debug" in self._frozen_config.myopts
		strict = pkg.type_name != "installed"

		if debug:
			writemsg_level("\nParent:    %s\n" % (pkg,),
				noiselevel=-1, level=logging.DEBUG)
			dep_repr = portage.dep.paren_enclose(dep_string,
				unevaluated_atom=True, opconvert=True)
			writemsg_level("Depstring: %s\n" % (dep_repr,),
				noiselevel=-1, level=logging.DEBUG)
			writemsg_level("Priority:  %s\n" % (dep_priority,),
				noiselevel=-1, level=logging.DEBUG)

		try:
			selected_atoms = self._select_atoms(dep_root,
				dep_string, myuse=self._pkg_use_enabled(pkg), parent=pkg,
				strict=strict, priority=dep_priority)
		except portage.exception.InvalidDependString:
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
		traversed_virt_pkgs = set()

		reinstall_atoms = self._frozen_config.reinstall_atoms
		for atom, child in self._minimize_children(
			pkg, dep_priority, root_config, selected_atoms[pkg]):

			# If this was a specially generated virtual atom
			# from dep_check, map it back to the original, in
			# order to avoid distortion in places like display
			# or conflict resolution code.
			is_virt = hasattr(atom, '_orig_atom')
			atom = getattr(atom, '_orig_atom', atom)

			if atom.blocker and \
				(dep_priority.optional or dep_priority.ignored):
				# For --with-bdeps, ignore build-time only blockers
				# that originate from built packages.
				continue

			mypriority = dep_priority.copy()
			if not atom.blocker:
				inst_pkgs = [inst_pkg for inst_pkg in
					reversed(vardb.match_pkgs(atom))
					if not reinstall_atoms.findAtomForPackage(inst_pkg,
							modified_use=self._pkg_use_enabled(inst_pkg))]
				if inst_pkgs:
					for inst_pkg in inst_pkgs:
						if self._pkg_visibility_check(inst_pkg):
							# highest visible
							mypriority.satisfied = inst_pkg
							break
					if not mypriority.satisfied:
						# none visible, so use highest
						mypriority.satisfied = inst_pkgs[0]

			dep = Dependency(atom=atom,
				blocker=atom.blocker, child=child, depth=depth, parent=pkg,
				priority=mypriority, root=dep_root)

			# In some cases, dep_check will return deps that shouldn't
			# be proccessed any further, so they are identified and
			# discarded here. Try to discard as few as possible since
			# discarded dependencies reduce the amount of information
			# available for optimization of merge order.
			ignored = False
			if not atom.blocker and \
				not recurse_satisfied and \
				mypriority.satisfied and \
				mypriority.satisfied.visible and \
				dep.child is not None and \
				not dep.child.installed and \
				self._dynamic_config._slot_pkg_map[dep.child.root].get(
				dep.child.slot_atom) is None:
				myarg = None
				try:
					myarg = next(self._iter_atoms_for_pkg(dep.child), None)
				except InvalidDependString:
					if not dep.child.installed:
						raise

				if myarg is None:
					# Existing child selection may not be valid unless
					# it's added to the graph immediately, since "complete"
					# mode may select a different child later.
					ignored = True
					dep.child = None
					self._dynamic_config._ignored_deps.append(dep)

			if not ignored:
				if dep_priority.ignored and \
					not self._dynamic_config._traverse_ignored_deps:
					if is_virt and dep.child is not None:
						traversed_virt_pkgs.add(dep.child)
					dep.child = None
					self._dynamic_config._ignored_deps.append(dep)
				else:
					if not self._add_dep(dep,
						allow_unsatisfied=allow_unsatisfied):
						return 0
					if is_virt and dep.child is not None:
						traversed_virt_pkgs.add(dep.child)

		selected_atoms.pop(pkg)

		# Add selected indirect virtual deps to the graph. This
		# takes advantage of circular dependency avoidance that's done
		# by dep_zapdeps. We preserve actual parent/child relationships
		# here in order to avoid distorting the dependency graph like
		# <=portage-2.1.6.x did.
		for virt_dep, atoms in selected_atoms.items():

			virt_pkg = virt_dep.child
			if virt_pkg not in traversed_virt_pkgs:
				continue

			if debug:
				writemsg_level("\nCandidates: %s: %s\n" % \
					(virt_pkg.cpv, [str(x) for x in atoms]),
					noiselevel=-1, level=logging.DEBUG)

			if not dep_priority.ignored or \
				self._dynamic_config._traverse_ignored_deps:

				inst_pkgs = [inst_pkg for inst_pkg in
					reversed(vardb.match_pkgs(virt_dep.atom))
					if not reinstall_atoms.findAtomForPackage(inst_pkg,
							modified_use=self._pkg_use_enabled(inst_pkg))]
				if inst_pkgs:
					for inst_pkg in inst_pkgs:
						if self._pkg_visibility_check(inst_pkg):
							# highest visible
							virt_dep.priority.satisfied = inst_pkg
							break
					if not virt_dep.priority.satisfied:
						# none visible, so use highest
						virt_dep.priority.satisfied = inst_pkgs[0]

				if not self._add_pkg(virt_pkg, virt_dep):
					return 0

			for atom, child in self._minimize_children(
				pkg, self._priority(runtime=True), root_config, atoms):

				# If this was a specially generated virtual atom
				# from dep_check, map it back to the original, in
				# order to avoid distortion in places like display
				# or conflict resolution code.
				is_virt = hasattr(atom, '_orig_atom')
				atom = getattr(atom, '_orig_atom', atom)

				# This is a GLEP 37 virtual, so its deps are all runtime.
				mypriority = self._priority(runtime=True)
				if not atom.blocker:
					inst_pkgs = [inst_pkg for inst_pkg in
						reversed(vardb.match_pkgs(atom))
						if not reinstall_atoms.findAtomForPackage(inst_pkg,
								modified_use=self._pkg_use_enabled(inst_pkg))]
					if inst_pkgs:
						for inst_pkg in inst_pkgs:
							if self._pkg_visibility_check(inst_pkg):
								# highest visible
								mypriority.satisfied = inst_pkg
								break
						if not mypriority.satisfied:
							# none visible, so use highest
							mypriority.satisfied = inst_pkgs[0]

				# Dependencies of virtuals are considered to have the
				# same depth as the virtual itself.
				dep = Dependency(atom=atom,
					blocker=atom.blocker, child=child, depth=virt_dep.depth,
					parent=virt_pkg, priority=mypriority, root=dep_root,
					collapsed_parent=pkg, collapsed_priority=dep_priority)

				ignored = False
				if not atom.blocker and \
					not recurse_satisfied and \
					mypriority.satisfied and \
					mypriority.satisfied.visible and \
					dep.child is not None and \
					not dep.child.installed and \
					self._dynamic_config._slot_pkg_map[dep.child.root].get(
					dep.child.slot_atom) is None:
					myarg = None
					try:
						myarg = next(self._iter_atoms_for_pkg(dep.child), None)
					except InvalidDependString:
						if not dep.child.installed:
							raise

					if myarg is None:
						ignored = True
						dep.child = None
						self._dynamic_config._ignored_deps.append(dep)

				if not ignored:
					if dep_priority.ignored and \
						not self._dynamic_config._traverse_ignored_deps:
						if is_virt and dep.child is not None:
							traversed_virt_pkgs.add(dep.child)
						dep.child = None
						self._dynamic_config._ignored_deps.append(dep)
					else:
						if not self._add_dep(dep,
							allow_unsatisfied=allow_unsatisfied):
							return 0
						if is_virt and dep.child is not None:
							traversed_virt_pkgs.add(dep.child)

		if debug:
			writemsg_level("\nExiting... %s\n" % (pkg,),
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

		for pkgs in cp_pkg_map.values():
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
			# Give similar treatment to slot/sub-slot atoms.
			conflict_atoms = []
			normal_atoms = []
			abi_atoms = []
			for atom in cp_atoms:
				if atom.slot_operator_built:
					abi_atoms.append(atom)
					continue
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

			for atom in chain(abi_atoms, conflict_atoms, normal_atoms):
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
		for x in dep_struct:
			if isinstance(x, list):
				if x and x[0] == "||":
					self._queue_disjunction(pkg, dep_root, dep_priority, [x])
				else:
					for y in self._queue_disjunctive_deps(
						pkg, dep_root, dep_priority, x):
						yield y
			else:
				# Note: Eventually this will check for PROPERTIES=virtual
				# or whatever other metadata gets implemented for this
				# purpose.
				if x.cp.startswith('virtual/'):
					self._queue_disjunction(pkg, dep_root, dep_priority, [x])
				else:
					yield x

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
		if not self._add_pkg_dep_string(
			pkg, dep_root, dep_priority, dep_struct, allow_unsatisfied):
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
		@return: a list of atoms containing categories (possibly empty)
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
		eroot = root_config.root
		root = root_config.settings['ROOT']
		vardb = self._frozen_config.trees[eroot]["vartree"].dbapi
		real_vardb = self._frozen_config._trees_orig[eroot]["vartree"].dbapi
		portdb = self._frozen_config.trees[eroot]["porttree"].dbapi
		bindb = self._frozen_config.trees[eroot]["bintree"].dbapi
		pkgsettings = self._frozen_config.pkgsettings[eroot]
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
				mykey = None
				cat = mytbz2.getfile("CATEGORY")
				if cat is not None:
					cat = _unicode_decode(cat.strip(),
						encoding=_encodings['repo.content'])
					mykey = cat + "/" + os.path.basename(x)[:-5]

				if mykey is None:
					writemsg(colorize("BAD", "\n*** Package is missing CATEGORY metadata: %s.\n\n" % x), noiselevel=-1)
					self._dynamic_config._skip_restart = True
					return 0, myfavorites
				elif os.path.realpath(x) != \
					os.path.realpath(bindb.bintree.getname(mykey)):
					writemsg(colorize("BAD", "\n*** You need to adjust PKGDIR to emerge this package.\n\n"), noiselevel=-1)
					self._dynamic_config._skip_restart = True
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
						self._dynamic_config._skip_restart = True
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
				if not x.startswith(eroot):
					portage.writemsg(("\n\n!!! '%s' does not start with" + \
						" $EROOT.\n") % x, noiselevel=-1)
					self._dynamic_config._skip_restart = True
					return 0, []
				# Queue these up since it's most efficient to handle
				# multiple files in a single iter_owners() call.
				lookup_owners.append(x)
			elif x.startswith("." + os.sep) or \
				x.startswith(".." + os.sep):
				f = os.path.abspath(x)
				if not f.startswith(eroot):
					portage.writemsg(("\n\n!!! '%s' (resolved from '%s') does not start with" + \
						" $EROOT.\n") % (f, x), noiselevel=-1)
					self._dynamic_config._skip_restart = True
					return 0, []
				lookup_owners.append(f)
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
					self._dynamic_config._skip_restart = True
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
					self._dynamic_config._skip_restart = True
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

				if atom.use and atom.use.conditional:
					writemsg(
						("\n\n!!! '%s' contains a conditional " + \
						"which is not allowed.\n") % (x,), noiselevel=-1)
					writemsg("!!! Please check ebuild(5) for full details.\n")
					self._dynamic_config._skip_restart = True
					return (0,[])

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
				relative_paths.append(x[len(root)-1:])

			owners = set()
			for pkg, relative_path in \
				real_vardb._owners.iter_owners(relative_paths):
				owners.add(pkg.mycpv)
				if not search_for_multiple:
					break

			if not owners:
				portage.writemsg(("\n\n!!! '%s' is not claimed " + \
					"by any package.\n") % lookup_owners[0], noiselevel=-1)
				self._dynamic_config._skip_restart = True
				return 0, []

			for cpv in owners:
				pkg = vardb._pkg_str(cpv, None)
				atom = Atom("%s:%s" % (pkg.cp, pkg.slot))
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

		args.extend(self._gen_reinstall_sets())
		self._set_args(args)

		myfavorites = set(myfavorites)
		for arg in args:
			if isinstance(arg, (AtomArg, PackageArg)):
				myfavorites.add(arg.atom)
			elif isinstance(arg, SetArg):
				if not arg.internal:
					myfavorites.add(arg.arg)
		myfavorites = list(myfavorites)

		if debug:
			portage.writemsg("\n", noiselevel=-1)
		# Order needs to be preserved since a feature of --nodeps
		# is to allow the user to force a specific merge order.
		self._dynamic_config._initial_arg_list = args[:]
	
		return self._resolve(myfavorites)

	def _gen_reinstall_sets(self):

		atom_list = []
		for root, atom in self._rebuild.rebuild_list:
			atom_list.append((root, '__auto_rebuild__', atom))
		for root, atom in self._rebuild.reinstall_list:
			atom_list.append((root, '__auto_reinstall__', atom))
		for root, atom in self._dynamic_config._slot_operator_replace_installed:
			atom_list.append((root, '__auto_slot_operator_replace_installed__', atom))

		set_dict = {}
		for root, set_name, atom in atom_list:
			set_dict.setdefault((root, set_name), []).append(atom)

		for (root, set_name), atoms in set_dict.items():
			yield SetArg(arg=(SETPREFIX + set_name),
				# Set reset_depth=False here, since we don't want these
				# special sets to interact with depth calculations (see
				# the emerge --deep=DEPTH option), though we want them
				# to behave like normal arguments in most other respects.
				pset=InternalPackageSet(initial_atoms=atoms),
				force_reinstall=True,
				internal=True,
				reset_depth=False,
				root_config=self._frozen_config.roots[root])

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
		args = self._dynamic_config._initial_arg_list[:]

		for arg in self._expand_set_args(args, add_to_digraph=True):
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
							if not self.need_restart():
								sys.stderr.write(("\n\n!!! Problem " + \
									"resolving dependencies for %s\n") % \
									arg.arg)
							return 0, myfavorites
						continue
					if debug:
						writemsg_level("\n      Arg: %s\n     Atom: %s\n" %
							(arg, atom), noiselevel=-1, level=logging.DEBUG)
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
					if pkg.installed and \
						"selective" not in self._dynamic_config.myparams and \
						not self._frozen_config.excluded_pkgs.findAtomForPackage(
						pkg, modified_use=self._pkg_use_enabled(pkg)):
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
						if self.need_restart():
							pass
						elif isinstance(arg, SetArg):
							writemsg(("\n\n!!! Problem resolving " + \
								"dependencies for %s from %s\n") % \
								(atom, arg.arg), noiselevel=-1)
						else:
							writemsg(("\n\n!!! Problem resolving " + \
								"dependencies for %s\n") % \
								(atom,), noiselevel=-1)
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

		if (self._dynamic_config._slot_collision_info and
			not self._accept_blocker_conflicts()) or \
			(self._dynamic_config._allow_backtracking and
			"slot conflict" in self._dynamic_config._backtrack_infos):
			return False, myfavorites

		if self._rebuild.trigger_rebuilds():
			backtrack_infos = self._dynamic_config._backtrack_infos
			config = backtrack_infos.setdefault("config", {})
			config["rebuild_list"] = self._rebuild.rebuild_list
			config["reinstall_list"] = self._rebuild.reinstall_list
			self._dynamic_config._need_restart = True
			return False, myfavorites

		if "config" in self._dynamic_config._backtrack_infos and \
			("slot_operator_mask_built" in self._dynamic_config._backtrack_infos["config"] or
			"slot_operator_replace_installed" in self._dynamic_config._backtrack_infos["config"]) and \
			self.need_restart():
			return False, myfavorites

		if not self._dynamic_config._prune_rebuilds and \
			self._dynamic_config._slot_operator_replace_installed and \
			self._get_missed_updates():
			# When there are missed updates, we might have triggered
			# some unnecessary rebuilds (see bug #439688). So, prune
			# all the rebuilds and backtrack with the problematic
			# updates masked. The next backtrack run should pull in
			# any rebuilds that are really needed, and this
			# prune_rebuilds path should never be entered more than
			# once in a series of backtracking nodes (in order to
			# avoid a backtracking loop).
			backtrack_infos = self._dynamic_config._backtrack_infos
			config = backtrack_infos.setdefault("config", {})
			config["prune_rebuilds"] = True
			self._dynamic_config._need_restart = True
			return False, myfavorites

		# Any failures except those due to autounmask *alone* should return
		# before this point, since the success_without_autounmask flag that's
		# set below is reserved for cases where there are *zero* other
		# problems. For reference, see backtrack_depgraph, where it skips the
		# get_best_run() call when success_without_autounmask is True.

		digraph_nodes = self._dynamic_config.digraph.nodes

		if any(x in digraph_nodes for x in
			self._dynamic_config._needed_unstable_keywords) or \
			any(x in digraph_nodes for x in
			self._dynamic_config._needed_p_mask_changes) or \
			any(x in digraph_nodes for x in
			self._dynamic_config._needed_use_config_changes) or \
			any(x in digraph_nodes for x in
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
			pkg = vardb._pkg_str(cpv, None)
			if pkg.cp == highest_pkg.cp:
				slots.add(pkg.slot)

		slots.add(highest_pkg.slot)
		if len(slots) == 1:
			return []
		greedy_pkgs = []
		slots.remove(highest_pkg.slot)
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
		blocker_dep_keys = Package._dep_keys
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

		if not isinstance(depstring, list):
			eapi = None
			is_valid_flag = None
			if parent is not None:
				eapi = parent.metadata['EAPI']
				if not parent.installed:
					is_valid_flag = parent.iuse.is_valid_flag
			depstring = portage.dep.use_reduce(depstring,
				uselist=myuse, opconvert=True, token_class=Atom,
				is_valid_flag=is_valid_flag, eapi=eapi)

		if (self._dynamic_config.myparams.get(
			"ignore_built_slot_operator_deps", "n") == "y" and
			parent and parent.built):
			ignore_built_slot_operator_deps(depstring)

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
			# backup state for restoration, in case of recursive
			# calls to this method
			backup_state = mytrees.copy()
			try:
				# clear state from previous call, in case this
				# call is recursive (we have a backup, that we
				# will use to restore it later)
				mytrees.pop("pkg_use_enabled", None)
				mytrees.pop("parent", None)
				mytrees.pop("atom_graph", None)
				mytrees.pop("priority", None)

				mytrees["pkg_use_enabled"] = self._pkg_use_enabled
				if parent is not None:
					mytrees["parent"] = parent
					mytrees["atom_graph"] = atom_graph
				if priority is not None:
					mytrees["priority"] = priority

				mycheck = portage.dep_check(depstring, None,
					pkgsettings, myuse=myuse,
					myroot=root, trees=trees)
			finally:
				# restore state
				self._dynamic_config._autounmask = _autounmask_backup
				mytrees.pop("pkg_use_enabled", None)
				mytrees.pop("parent", None)
				mytrees.pop("atom_graph", None)
				mytrees.pop("priority", None)
				mytrees.update(backup_state)
			if not mycheck[0]:
				raise portage.exception.InvalidDependString(mycheck[1])
		if parent is None:
			selected_atoms = mycheck[1]
		elif parent not in atom_graph:
			selected_atoms = {parent : mycheck[1]}
		else:
			# Recursively traversed virtual dependencies, and their
			# direct dependencies, are considered to have the same
			# depth as direct dependencies.
			if parent.depth is None:
				virt_depth = None
			else:
				virt_depth = parent.depth + 1
			chosen_atom_ids = frozenset(id(atom) for atom in mycheck[1])
			selected_atoms = OrderedDict()
			node_stack = [(parent, None, None)]
			traversed_nodes = set()
			while node_stack:
				node, node_parent, parent_atom = node_stack.pop()
				traversed_nodes.add(node)
				if node is parent:
					k = parent
				else:
					if node_parent is parent:
						if priority is None:
							node_priority = None
						else:
							node_priority = priority.copy()
					else:
						# virtuals only have runtime deps
						node_priority = self._priority(runtime=True)

					k = Dependency(atom=parent_atom,
						blocker=parent_atom.blocker, child=node,
						depth=virt_depth, parent=node_parent,
						priority=node_priority, root=node.root)

				child_atoms = []
				selected_atoms[k] = child_atoms
				for atom_node in atom_graph.child_nodes(node):
					child_atom = atom_node[0]
					if id(child_atom) not in chosen_atom_ids:
						continue
					child_atoms.append(child_atom)
					for child_node in atom_graph.child_nodes(atom_node):
						if child_node in traversed_nodes:
							continue
						if not portage.match_from_list(
							child_atom, [child_node]):
							# Typically this means that the atom
							# specifies USE deps that are unsatisfied
							# by the selected package. The caller will
							# record this as an unsatisfied dependency
							# when necessary.
							continue
						node_stack.append((child_node, node, child_atom))

		return selected_atoms

	def _expand_virt_from_graph(self, root, atom):
		if not isinstance(atom, Atom):
			atom = Atom(atom)
		graphdb = self._dynamic_config.mydbapi[root]
		match = graphdb.match_pkgs(atom)
		if not match:
			yield atom
			return
		pkg = match[-1]
		if not pkg.cpv.startswith("virtual/"):
			yield atom
			return
		try:
			rdepend = self._select_atoms_from_graph(
				pkg.root, pkg.metadata.get("RDEPEND", ""),
				myuse=self._pkg_use_enabled(pkg),
				parent=pkg, strict=False)
		except InvalidDependString as e:
			writemsg_level("!!! Invalid RDEPEND in " + \
				"'%svar/db/pkg/%s/RDEPEND': %s\n" % \
				(pkg.root, pkg.cpv, e),
				noiselevel=-1, level=logging.ERROR)
			yield atom
			return

		for atoms in rdepend.values():
			for atom in atoms:
				if hasattr(atom, "_orig_atom"):
					# Ignore virtual atoms since we're only
					# interested in expanding the real atoms.
					continue
				yield atom

	def _virt_deps_visible(self, pkg, ignore_use=False):
		"""
		Assumes pkg is a virtual package. Traverses virtual deps recursively
		and returns True if all deps are visible, False otherwise. This is
		useful for checking if it will be necessary to expand virtual slots,
		for cases like bug #382557.
		"""
		try:
			rdepend = self._select_atoms(
				pkg.root, pkg.metadata.get("RDEPEND", ""),
				myuse=self._pkg_use_enabled(pkg),
				parent=pkg, priority=self._priority(runtime=True))
		except InvalidDependString as e:
			if not pkg.installed:
				raise
			writemsg_level("!!! Invalid RDEPEND in " + \
				"'%svar/db/pkg/%s/RDEPEND': %s\n" % \
				(pkg.root, pkg.cpv, e),
				noiselevel=-1, level=logging.ERROR)
			return False

		for atoms in rdepend.values():
			for atom in atoms:
				if ignore_use:
					atom = atom.without_use
				pkg, existing = self._select_package(
					pkg.root, atom)
				if pkg is None or not self._pkg_visibility_check(pkg):
					return False

		return True

	def _get_dep_chain(self, start_node, target_atom=None,
		unsatisfied_dependency=False):
		"""
		Returns a list of (atom, node_type) pairs that represent a dep chain.
		If target_atom is None, the first package shown is pkg's parent.
		If target_atom is not None the first package shown is pkg.
		If unsatisfied_dependency is True, the first parent is select who's
		dependency is not satisfied by 'pkg'. This is need for USE changes.
		(Does not support target_atom.)
		"""
		traversed_nodes = set()
		dep_chain = []
		node = start_node
		child = None
		all_parents = self._dynamic_config._parent_atoms
		graph = self._dynamic_config.digraph

		if target_atom is not None and isinstance(node, Package):
			affecting_use = set()
			for dep_str in Package._dep_keys:
				try:
					affecting_use.update(extract_affecting_use(
						node.metadata[dep_str], target_atom,
						eapi=node.metadata["EAPI"]))
				except InvalidDependString:
					if not node.installed:
						raise
			affecting_use.difference_update(node.use.mask, node.use.force)
			pkg_name = _unicode_decode("%s") % (node.cpv,)
			if affecting_use:
				usedep = []
				for flag in affecting_use:
					if flag in self._pkg_use_enabled(node):
						usedep.append(flag)
					else:
						usedep.append("-"+flag)
				pkg_name += "[%s]" % ",".join(usedep)

			dep_chain.append((pkg_name, node.type_name))


		# To build a dep chain for the given package we take
		# "random" parents form the digraph, except for the
		# first package, because we want a parent that forced
		# the corresponding change (i.e '>=foo-2', instead 'foo').

		traversed_nodes.add(start_node)

		start_node_parent_atoms = {}
		for ppkg, patom in all_parents.get(node, []):
			# Get a list of suitable atoms. For use deps
			# (aka unsatisfied_dependency is not None) we
			# need that the start_node doesn't match the atom.
			if not unsatisfied_dependency or \
				not InternalPackageSet(initial_atoms=(patom,)).findAtomForPackage(start_node):
				start_node_parent_atoms.setdefault(patom, []).append(ppkg)

		if start_node_parent_atoms:
			# If there are parents in all_parents then use one of them.
			# If not, then this package got pulled in by an Arg and
			# will be correctly handled by the code that handles later
			# packages in the dep chain.
			best_match = best_match_to_list(node.cpv, start_node_parent_atoms)

			child = node
			for ppkg in start_node_parent_atoms[best_match]:
				node = ppkg
				if ppkg in self._dynamic_config._initial_arg_list:
					# Stop if reached the top level of the dep chain.
					break

		while node is not None:
			traversed_nodes.add(node)

			if node not in graph:
				# The parent is not in the graph due to backtracking.
				break

			elif isinstance(node, DependencyArg):
				if graph.parent_nodes(node):
					node_type = "set"
				else:
					node_type = "argument"
				dep_chain.append((_unicode_decode("%s") % (node,), node_type))

			elif node is not start_node:
				for ppkg, patom in all_parents[child]:
					if ppkg == node:
						if child is start_node and unsatisfied_dependency and \
							InternalPackageSet(initial_atoms=(patom,)).findAtomForPackage(child):
							# This atom is satisfied by child, there must be another atom.
							continue
						atom = patom.unevaluated_atom
						break

				dep_strings = set()
				priorities = graph.nodes[node][0].get(child)
				if priorities is None:
					# This edge comes from _parent_atoms and was not added to
					# the graph, and _parent_atoms does not contain priorities.
					for k in Package._dep_keys:
						dep_strings.add(node.metadata[k])
				else:
					for priority in priorities:
						if priority.buildtime:
							for k in Package._buildtime_keys:
								dep_strings.add(node.metadata[k])
						if priority.runtime:
							dep_strings.add(node.metadata["RDEPEND"])
						if priority.runtime_post:
							dep_strings.add(node.metadata["PDEPEND"])

				affecting_use = set()
				for dep_str in dep_strings:
					try:
						affecting_use.update(extract_affecting_use(
							dep_str, atom, eapi=node.metadata["EAPI"]))
					except InvalidDependString:
						if not node.installed:
							raise

				#Don't show flags as 'affecting' if the user can't change them,
				affecting_use.difference_update(node.use.mask, \
					node.use.force)

				pkg_name = _unicode_decode("%s") % (node.cpv,)
				if affecting_use:
					usedep = []
					for flag in affecting_use:
						if flag in self._pkg_use_enabled(node):
							usedep.append(flag)
						else:
							usedep.append("-"+flag)
					pkg_name += "[%s]" % ",".join(usedep)

				dep_chain.append((pkg_name, node.type_name))

			# When traversing to parents, prefer arguments over packages
			# since arguments are root nodes. Never traverse the same
			# package twice, in order to prevent an infinite loop.
			child = node
			selected_parent = None
			parent_arg = None
			parent_merge = None
			parent_unsatisfied = None

			for parent in self._dynamic_config.digraph.parent_nodes(node):
				if parent in traversed_nodes:
					continue
				if isinstance(parent, DependencyArg):
					parent_arg = parent
				else:
					if isinstance(parent, Package) and \
						parent.operation == "merge":
						parent_merge = parent
					if unsatisfied_dependency and node is start_node:
						# Make sure that pkg doesn't satisfy parent's dependency.
						# This ensures that we select the correct parent for use
						# flag changes.
						for ppkg, atom in all_parents[start_node]:
							if parent is ppkg:
								atom_set = InternalPackageSet(initial_atoms=(atom,))
								if not atom_set.findAtomForPackage(start_node):
									parent_unsatisfied = parent
								break
					else:
						selected_parent = parent

			if parent_unsatisfied is not None:
				selected_parent = parent_unsatisfied
			elif parent_merge is not None:
				# Prefer parent in the merge list (bug #354747).
				selected_parent = parent_merge
			elif parent_arg is not None:
				if self._dynamic_config.digraph.parent_nodes(parent_arg):
					selected_parent = parent_arg
				else:
					dep_chain.append(
						(_unicode_decode("%s") % (parent_arg,), "argument"))
					selected_parent = None

			node = selected_parent
		return dep_chain

	def _get_dep_chain_as_comment(self, pkg, unsatisfied_dependency=False):
		dep_chain = self._get_dep_chain(pkg, unsatisfied_dependency=unsatisfied_dependency)
		display_list = []
		for node, node_type in dep_chain:
			if node_type == "argument":
				display_list.append("required by %s (argument)" % node)
			else:
				display_list.append("required by %s" % node)

		msg = "#" + ", ".join(display_list) + "\n"
		return msg


	def _show_unsatisfied_dep(self, root, atom, myparent=None, arg=None,
		check_backtrack=False, check_autounmask_breakage=False, show_req_use=None):
		"""
		When check_backtrack=True, no output is produced and
		the method either returns or raises _backtrack_mask if
		a matching package has been masked by backtracking.
		"""
		backtrack_mask = False
		autounmask_broke_use_dep = False
		atom_set = InternalPackageSet(initial_atoms=(atom.without_use,),
			allow_repo=True)
		atom_set_with_use = InternalPackageSet(initial_atoms=(atom,),
			allow_repo=True)
		xinfo = '"%s"' % atom.unevaluated_atom
		if arg:
			xinfo='"%s"' % arg
		if isinstance(myparent, AtomArg):
			xinfo = _unicode_decode('"%s"') % (myparent,)
		# Discard null/ from failed cpv_expand category expansion.
		xinfo = xinfo.replace("null/", "")
		if root != self._frozen_config._running_root.root:
			xinfo = "%s for %s" % (xinfo, root)
		masked_packages = []
		missing_use = []
		missing_use_adjustable = set()
		required_use_unsatisfied = []
		masked_pkg_instances = set()
		have_eapi_mask = False
		pkgsettings = self._frozen_config.pkgsettings[root]
		root_config = self._frozen_config.roots[root]
		portdb = self._frozen_config.roots[root].trees["porttree"].dbapi
		vardb = self._frozen_config.roots[root].trees["vartree"].dbapi
		bindb = self._frozen_config.roots[root].trees["bintree"].dbapi
		dbs = self._dynamic_config._filtered_trees[root]["dbs"]
		for db, pkg_type, built, installed, db_keys in dbs:
			if installed:
				continue
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
					if metadata is not None and \
						portage.eapi_is_supported(metadata["EAPI"]):
						if not repo:
							repo = metadata.get('repository')
						pkg = self._pkg(cpv, pkg_type, root_config,
							installed=installed, myrepo=repo)
						# pkg.metadata contains calculated USE for ebuilds,
						# required later for getMissingLicenses.
						metadata = pkg.metadata
						if pkg.invalid:
							# Avoid doing any operations with packages that
							# have invalid metadata. It would be unsafe at
							# least because it could trigger unhandled
							# exceptions in places like check_required_use().
							masked_packages.append(
								(root_config, pkgsettings, cpv, repo, metadata, mreasons))
							continue
						if not atom_set.findAtomForPackage(pkg,
							modified_use=self._pkg_use_enabled(pkg)):
							continue
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
									if atom_set_with_use.findAtomForPackage(pkg):
										autounmask_broke_use_dep = True
									if not mreasons:
										continue
							except InvalidAtom:
								writemsg("violated_conditionals raised " + \
									"InvalidAtom: '%s' parent: %s" % \
									(atom, myparent), noiselevel=-1)
								raise
						if not mreasons and \
							not pkg.built and \
							pkg.metadata.get("REQUIRED_USE") and \
							eapi_has_required_use(pkg.metadata["EAPI"]):
							if not check_required_use(
								pkg.metadata["REQUIRED_USE"],
								self._pkg_use_enabled(pkg),
								pkg.iuse.is_valid_flag,
								eapi=pkg.metadata["EAPI"]):
								required_use_unsatisfied.append(pkg)
								continue
						root_slot = (pkg.root, pkg.slot_atom)
						if pkg.built and root_slot in self._rebuild.rebuild_list:
							mreasons = ["need to rebuild from source"]
						elif pkg.installed and root_slot in self._rebuild.reinstall_list:
							mreasons = ["need to rebuild from source"]
						elif pkg.built and not mreasons:
							mreasons = ["use flag configuration mismatch"]
					masked_packages.append(
						(root_config, pkgsettings, cpv, repo, metadata, mreasons))

		if check_backtrack:
			if backtrack_mask:
				raise self._backtrack_mask()
			else:
				return

		if check_autounmask_breakage:
			if autounmask_broke_use_dep:
				raise self._autounmask_breakage()
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
				if any(x in untouchable_flags for x in
					chain(need_enable, need_disable)):
					continue

				missing_use_adjustable.add(pkg)
				required_use = pkg.metadata.get("REQUIRED_USE")
				required_use_warning = ""
				if required_use:
					old_use = self._pkg_use_enabled(pkg)
					new_use = set(self._pkg_use_enabled(pkg))
					for flag in need_enable:
						new_use.add(flag)
					for flag in need_disable:
						new_use.discard(flag)
					if check_required_use(required_use, old_use,
						pkg.iuse.is_valid_flag, eapi=pkg.metadata["EAPI"]) \
						and not check_required_use(required_use, new_use,
						pkg.iuse.is_valid_flag, eapi=pkg.metadata["EAPI"]):
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
					if any(x in untouchable_flags for x in involved_flags):
						continue

					required_use = myparent.metadata.get("REQUIRED_USE")
					required_use_warning = ""
					if required_use:
						old_use = self._pkg_use_enabled(myparent)
						new_use = set(self._pkg_use_enabled(myparent))
						for flag in involved_flags:
							if flag in old_use:
								new_use.discard(flag)
							else:
								new_use.add(flag)
						if check_required_use(required_use, old_use,
							myparent.iuse.is_valid_flag,
							eapi=myparent.metadata["EAPI"]) and \
							not check_required_use(required_use, new_use,
							myparent.iuse.is_valid_flag,
							eapi=myparent.metadata["EAPI"]):
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

		if required_use_unsatisfied:
			# If there's a higher unmasked version in missing_use_adjustable
			# then we want to show that instead.
			for pkg in missing_use_adjustable:
				if pkg not in masked_pkg_instances and \
					pkg > required_use_unsatisfied[0]:
					required_use_unsatisfied = False
					break

		mask_docs = False

		if show_req_use is None and required_use_unsatisfied:
			# We have an unmasked package that only requires USE adjustment
			# in order to satisfy REQUIRED_USE, and nothing more. We assume
			# that the user wants the latest version, so only the first
			# instance is displayed.
			show_req_use = required_use_unsatisfied[0]

		if show_req_use is not None:

			pkg = show_req_use
			output_cpv = pkg.cpv + _repo_separator + pkg.repo
			writemsg("\n!!! " + \
				colorize("BAD", "The ebuild selected to satisfy ") + \
				colorize("INFORM", xinfo) + \
				colorize("BAD", " has unmet requirements.") + "\n",
				noiselevel=-1)
			use_display = pkg_use_display(pkg, self._frozen_config.myopts)
			writemsg("- %s %s\n" % (output_cpv, use_display),
				noiselevel=-1)
			writemsg("\n  The following REQUIRED_USE flag constraints " + \
				"are unsatisfied:\n", noiselevel=-1)
			reduced_noise = check_required_use(
				pkg.metadata["REQUIRED_USE"],
				self._pkg_use_enabled(pkg),
				pkg.iuse.is_valid_flag,
				eapi=pkg.metadata["EAPI"]).tounicode()
			writemsg("    %s\n" % \
				human_readable_required_use(reduced_noise),
				noiselevel=-1)
			normalized_required_use = \
				" ".join(pkg.metadata["REQUIRED_USE"].split())
			if reduced_noise != normalized_required_use:
				writemsg("\n  The above constraints " + \
					"are a subset of the following complete expression:\n",
					noiselevel=-1)
				writemsg("    %s\n" % \
					human_readable_required_use(normalized_required_use),
					noiselevel=-1)
			writemsg("\n", noiselevel=-1)

		elif show_missing_use:
			writemsg("\nemerge: there are no ebuilds built with USE flags to satisfy "+green(xinfo)+".\n", noiselevel=-1)
			writemsg("!!! One of the following packages is required to complete your request:\n", noiselevel=-1)
			for pkg, mreasons in show_missing_use:
				writemsg("- "+pkg.cpv+_repo_separator+pkg.repo+" ("+", ".join(mreasons)+")\n", noiselevel=-1)

		elif masked_packages:
			writemsg("\n!!! " + \
				colorize("BAD", "All ebuilds that could satisfy ") + \
				colorize("INFORM", xinfo) + \
				colorize("BAD", " have been masked.") + "\n", noiselevel=-1)
			writemsg("!!! One of the following masked packages is required to complete your request:\n", noiselevel=-1)
			have_eapi_mask = show_masked_packages(masked_packages)
			if have_eapi_mask:
				writemsg("\n", noiselevel=-1)
				msg = ("The current version of portage supports " + \
					"EAPI '%s'. You must upgrade to a newer version" + \
					" of portage before EAPI masked packages can" + \
					" be installed.") % portage.const.EAPI
				writemsg("\n".join(textwrap.wrap(msg, 75)), noiselevel=-1)
			writemsg("\n", noiselevel=-1)
			mask_docs = True
		else:
			cp_exists = False
			if not atom.cp.startswith("null/"):
				for pkg in self._iter_match_pkgs_any(
					root_config, Atom(atom.cp)):
					cp_exists = True
					break

			writemsg("\nemerge: there are no ebuilds to satisfy "+green(xinfo)+".\n", noiselevel=-1)
			if isinstance(myparent, AtomArg) and \
				not cp_exists and \
				self._frozen_config.myopts.get(
				"--misspell-suggestions", "y") != "n":
				cp = myparent.atom.cp.lower()
				cat, pkg = portage.catsplit(cp)
				if cat == "null":
					cat = None

				writemsg("\nemerge: searching for similar names..."
					, noiselevel=-1)

				all_cp = set()
				all_cp.update(vardb.cp_all())
				if "--usepkgonly" not in self._frozen_config.myopts:
					all_cp.update(portdb.cp_all())
				if "--usepkg" in self._frozen_config.myopts:
					all_cp.update(bindb.cp_all())
				# discard dir containing no ebuilds
				all_cp.discard(cp)

				orig_cp_map = {}
				for cp_orig in all_cp:
					orig_cp_map.setdefault(cp_orig.lower(), []).append(cp_orig)
				all_cp = set(orig_cp_map)

				if cat:
					matches = difflib.get_close_matches(cp, all_cp)
				else:
					pkg_to_cp = {}
					for other_cp in list(all_cp):
						other_pkg = portage.catsplit(other_cp)[1]
						if other_pkg == pkg:
							# Check for non-identical package that
							# differs only by upper/lower case.
							identical = True
							for cp_orig in orig_cp_map[other_cp]:
								if portage.catsplit(cp_orig)[1] != \
									portage.catsplit(atom.cp)[1]:
									identical = False
									break
							if identical:
								# discard dir containing no ebuilds
								all_cp.discard(other_cp)
								continue
						pkg_to_cp.setdefault(other_pkg, set()).add(other_cp)
					pkg_matches = difflib.get_close_matches(pkg, pkg_to_cp)
					matches = []
					for pkg_match in pkg_matches:
						matches.extend(pkg_to_cp[pkg_match])

				matches_orig_case = []
				for cp in matches:
					matches_orig_case.extend(orig_cp_map[cp])
				matches = matches_orig_case

				if len(matches) == 1:
					writemsg("\nemerge: Maybe you meant " + matches[0] + "?\n"
						, noiselevel=-1)
				elif len(matches) > 1:
					writemsg(
						"\nemerge: Maybe you meant any of these: %s?\n" % \
						(", ".join(matches),), noiselevel=-1)
				else:
					# Generally, this would only happen if
					# all dbapis are empty.
					writemsg(" nothing similar found.\n"
						, noiselevel=-1)
		msg = []
		if not isinstance(myparent, AtomArg):
			# It's redundant to show parent for AtomArg since
			# it's the same as 'xinfo' displayed above.
			dep_chain = self._get_dep_chain(myparent, atom)
			for node, node_type in dep_chain:
				msg.append('(dependency required by "%s" [%s])' % \
						(colorize('INFORM', _unicode_decode("%s") % \
						(node)), node_type))

		if msg:
			writemsg("\n".join(msg), noiselevel=-1)
			writemsg("\n", noiselevel=-1)

		if mask_docs:
			show_mask_docs()
			writemsg("\n", noiselevel=-1)

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
		atom_exp = dep_expand(atom, mydb=db, settings=root_config.settings)
		cp_list = db.cp_list(atom_exp.cp)
		matched_something = False
		installed = pkg_type == 'installed'

		if cp_list:
			atom_set = InternalPackageSet(initial_atoms=(atom,),
				allow_repo=True)
			if atom.repo is None and hasattr(db, "getRepositories"):
				repo_list = db.getRepositories()
			else:
				repo_list = [atom.repo]

			# descending order
			cp_list.reverse()
			for cpv in cp_list:
				# Call match_from_list on one cpv at a time, in order
				# to avoid unnecessary match_from_list comparisons on
				# versions that are never yielded from this method.
				if not match_from_list(atom_exp, [cpv]):
					continue
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
						# Also, parts of the match that require metadata access
						# are deferred until we have cached the metadata in a
						# Package instance.
						if not atom_set.findAtomForPackage(pkg,
							modified_use=self._pkg_use_enabled(pkg)):
							continue
						matched_something = True
						yield pkg

		# USE=multislot can make an installed package appear as if
		# it doesn't satisfy a slot dependency. Rebuilding the ebuild
		# won't do any good as long as USE=multislot is enabled since
		# the newly built package still won't have the expected slot.
		# Therefore, assume that such SLOT dependencies are already
		# satisfied rather than forcing a rebuild.
		if not matched_something and installed and \
			atom.slot is not None and not atom.slot_operator_built:

			if "remove" in self._dynamic_config.myparams:
				# We need to search the portdbapi, which is not in our
				# normal dbs list, in order to find the real SLOT.
				portdb = self._frozen_config.trees[root_config.root]["porttree"].dbapi
				db_keys = list(portdb._aux_cache_keys)
				dbs = [(portdb, "ebuild", False, False, db_keys)]
			else:
				dbs = self._dynamic_config._filtered_trees[root_config.root]["dbs"]

			cp_list = db.cp_list(atom_exp.cp)
			if cp_list:
				atom_set = InternalPackageSet(
					initial_atoms=(atom.without_slot,), allow_repo=True)
				atom_exp_without_slot = atom_exp.without_slot
				cp_list.reverse()
				for cpv in cp_list:
					if not match_from_list(atom_exp_without_slot, [cpv]):
						continue
					slot_available = False
					for other_db, other_type, other_built, \
						other_installed, other_keys in dbs:
						try:
							if portage.dep._match_slot(atom,
								other_db._pkg_str(_unicode(cpv), None)):
								slot_available = True
								break
						except (KeyError, InvalidData):
							pass
					if not slot_available:
						continue
					inst_pkg = self._pkg(cpv, "installed",
						root_config, installed=installed, myrepo=atom.repo)
					# Remove the slot from the atom and verify that
					# the package matches the resulting atom.
					if atom_set.findAtomForPackage(inst_pkg):
						yield inst_pkg
						return

	def _select_pkg_highest_available(self, root, atom, onlydeps=False):
		cache_key = (root, atom, atom.unevaluated_atom, onlydeps, self._dynamic_config._autounmask)
		ret = self._dynamic_config._highest_pkg_cache.get(cache_key)
		if ret is not None:
			return ret
		ret = self._select_pkg_highest_available_imp(root, atom, onlydeps=onlydeps)
		self._dynamic_config._highest_pkg_cache[cache_key] = ret
		pkg, existing = ret
		if pkg is not None:
			if self._pkg_visibility_check(pkg) and \
				not (pkg.installed and pkg.masks):
				self._dynamic_config._visible_pkgs[pkg.root].cpv_inject(pkg)
		return ret

	def _want_installed_pkg(self, pkg):
		"""
		Given an installed package returned from select_pkg, return
		True if the user has not explicitly requested for this package
		to be replaced (typically via an atom on the command line).
		"""
		if self._frozen_config.excluded_pkgs.findAtomForPackage(pkg,
			modified_use=self._pkg_use_enabled(pkg)):
			return True

		arg = False
		try:
			for arg, atom in self._iter_atoms_for_pkg(pkg):
				if arg.force_reinstall:
					return False
		except InvalidDependString:
			pass

		if "selective" in self._dynamic_config.myparams:
			return True

		return not arg

	def _equiv_ebuild_visible(self, pkg, autounmask_level=None):
		try:
			pkg_eb = self._pkg(
				pkg.cpv, "ebuild", pkg.root_config, myrepo=pkg.repo)
		except portage.exception.PackageNotFound:
			pkg_eb_visible = False
			for pkg_eb in self._iter_match_pkgs(pkg.root_config,
				"ebuild", Atom("=%s" % (pkg.cpv,))):
				if self._pkg_visibility_check(pkg_eb, autounmask_level):
					pkg_eb_visible = True
					break
			if not pkg_eb_visible:
				return False
		else:
			if not self._pkg_visibility_check(pkg_eb, autounmask_level):
				return False

		return True

	def _equiv_binary_installed(self, pkg):
		build_time = pkg.metadata.get('BUILD_TIME')
		if not build_time:
			return False

		try:
			inst_pkg = self._pkg(pkg.cpv, "installed",
				pkg.root_config, installed=True)
		except PackageNotFound:
			return False

		return build_time == inst_pkg.metadata.get('BUILD_TIME')

	class _AutounmaskLevel(object):
		__slots__ = ("allow_use_changes", "allow_unstable_keywords", "allow_license_changes", \
			"allow_missing_keywords", "allow_unmasks")

		def __init__(self):
			self.allow_use_changes = False
			self.allow_license_changes = False
			self.allow_unstable_keywords = False
			self.allow_missing_keywords = False
			self.allow_unmasks = False

	def _autounmask_levels(self):
		"""
		Iterate over the different allowed things to unmask.

		0. USE
		1. USE + license
		2. USE + ~arch + license
		3. USE + ~arch + license + missing keywords
		4. USE + ~arch + license + masks
		5. USE + ~arch + license + missing keywords + masks

		Some thoughts:
			* Do least invasive changes first.
			* Try unmasking alone before unmasking + missing keywords
				to avoid -9999 versions if possible
		"""

		if self._dynamic_config._autounmask is not True:
			return

		autounmask_keep_masks = self._frozen_config.myopts.get("--autounmask-keep-masks", "n") != "n"
		autounmask_level = self._AutounmaskLevel()

		autounmask_level.allow_use_changes = True
		yield autounmask_level

		autounmask_level.allow_license_changes = True
		yield autounmask_level

		for only_use_changes in (False,):

			autounmask_level.allow_unstable_keywords = (not only_use_changes)
			autounmask_level.allow_license_changes = (not only_use_changes)

			for missing_keyword, unmask in ((False,False), (True, False), (False, True), (True, True)):

				if (only_use_changes or autounmask_keep_masks) and (missing_keyword or unmask):
					break

				autounmask_level.allow_missing_keywords = missing_keyword
				autounmask_level.allow_unmasks = unmask

				yield autounmask_level


	def _select_pkg_highest_available_imp(self, root, atom, onlydeps=False):
		pkg, existing = self._wrapped_select_pkg_highest_available_imp(root, atom, onlydeps=onlydeps)

		default_selection = (pkg, existing)

		def reset_pkg(pkg):
			if pkg is not None and \
				pkg.installed and \
				not self._want_installed_pkg(pkg):
				pkg = None

		if self._dynamic_config._autounmask is True:
			reset_pkg(pkg)

			for autounmask_level in self._autounmask_levels():
				if pkg is not None:
					break

				pkg, existing = \
					self._wrapped_select_pkg_highest_available_imp(
						root, atom, onlydeps=onlydeps,
						autounmask_level=autounmask_level)

				reset_pkg(pkg)
			
			if self._dynamic_config._need_restart:
				return None, None

		if pkg is None:
			# This ensures that we can fall back to an installed package
			# that may have been rejected in the autounmask path above.
			return default_selection

		return pkg, existing

	def _pkg_visibility_check(self, pkg, autounmask_level=None, trust_graph=True):

		if pkg.visible:
			return True

		if trust_graph and pkg in self._dynamic_config.digraph:
			# Sometimes we need to temporarily disable
			# dynamic_config._autounmask, but for overall
			# consistency in dependency resolution, in most
			# cases we want to treat packages in the graph
			# as though they are visible.
			return True

		if not self._dynamic_config._autounmask or autounmask_level is None:
			return False

		pkgsettings = self._frozen_config.pkgsettings[pkg.root]
		root_config = self._frozen_config.roots[pkg.root]
		mreasons = _get_masking_status(pkg, pkgsettings, root_config, use=self._pkg_use_enabled(pkg))

		masked_by_unstable_keywords = False
		masked_by_missing_keywords = False
		missing_licenses = None
		masked_by_something_else = False
		masked_by_p_mask = False

		for reason in mreasons:
			hint = reason.unmask_hint

			if hint is None:
				masked_by_something_else = True
			elif hint.key == "unstable keyword":
				masked_by_unstable_keywords = True
				if hint.value == "**":
					masked_by_missing_keywords = True
			elif hint.key == "p_mask":
				masked_by_p_mask = True
			elif hint.key == "license":
				missing_licenses = hint.value
			else:
				masked_by_something_else = True

		if masked_by_something_else:
			return False

		if pkg in self._dynamic_config._needed_unstable_keywords:
			#If the package is already keyworded, remove the mask.
			masked_by_unstable_keywords = False
			masked_by_missing_keywords = False

		if pkg in self._dynamic_config._needed_p_mask_changes:
			#If the package is already keyworded, remove the mask.
			masked_by_p_mask = False

		if missing_licenses:
			#If the needed licenses are already unmasked, remove the mask.
			missing_licenses.difference_update(self._dynamic_config._needed_license_changes.get(pkg, set()))

		if not (masked_by_unstable_keywords or masked_by_p_mask or missing_licenses):
			#Package has already been unmasked.
			return True

		if (masked_by_unstable_keywords and not autounmask_level.allow_unstable_keywords) or \
			(masked_by_missing_keywords and not autounmask_level.allow_missing_keywords) or \
			(masked_by_p_mask and not autounmask_level.allow_unmasks) or \
			(missing_licenses and not autounmask_level.allow_license_changes):
			#We are not allowed to do the needed changes.
			return False

		if masked_by_unstable_keywords:
			self._dynamic_config._needed_unstable_keywords.add(pkg)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_unstable_keywords", set())
			backtrack_infos["config"]["needed_unstable_keywords"].add(pkg)

		if masked_by_p_mask:
			self._dynamic_config._needed_p_mask_changes.add(pkg)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_p_mask_changes", set())
			backtrack_infos["config"]["needed_p_mask_changes"].add(pkg)

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
		if pkg.built:
			return pkg.use.enabled
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

			for key in Package._dep_keys + ("LICENSE",):
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
					not any(x in atom.use.required for x in changes):
					continue
				else:
					return True

			return False

		if new_changes != old_changes:
			#Don't do the change if it violates REQUIRED_USE.
			required_use = pkg.metadata.get("REQUIRED_USE")
			if required_use and check_required_use(required_use, old_use,
				pkg.iuse.is_valid_flag, eapi=pkg.metadata["EAPI"]) and \
				not check_required_use(required_use, new_use,
				pkg.iuse.is_valid_flag, eapi=pkg.metadata["EAPI"]):
				return old_use

			if any(x in pkg.use.mask for x in new_changes) or \
				any(x in pkg.use.force for x in new_changes):
				return old_use

			self._dynamic_config._needed_use_config_changes[pkg] = (new_use, new_changes)
			backtrack_infos = self._dynamic_config._backtrack_infos
			backtrack_infos.setdefault("config", {})
			backtrack_infos["config"].setdefault("needed_use_config_changes", [])
			backtrack_infos["config"]["needed_use_config_changes"].append((pkg, (new_use, new_changes)))
			if want_restart_for_use_change(pkg, new_use):
				self._dynamic_config._need_restart = True
		return new_use

	def _wrapped_select_pkg_highest_available_imp(self, root, atom, onlydeps=False, autounmask_level=None):
		root_config = self._frozen_config.roots[root]
		pkgsettings = self._frozen_config.pkgsettings[root]
		dbs = self._dynamic_config._filtered_trees[root]["dbs"]
		vardb = self._frozen_config.roots[root].trees["vartree"].dbapi
		# List of acceptable packages, ordered by type preference.
		matched_packages = []
		matched_pkgs_ignore_use = []
		highest_version = None
		if not isinstance(atom, portage.dep.Atom):
			atom = portage.dep.Atom(atom)
		atom_cp = atom.cp
		have_new_virt = atom_cp.startswith("virtual/") and \
			self._have_new_virt(root, atom_cp)
		atom_set = InternalPackageSet(initial_atoms=(atom,), allow_repo=True)
		existing_node = None
		myeb = None
		rebuilt_binaries = 'rebuilt_binaries' in self._dynamic_config.myparams
		usepkg = "--usepkg" in self._frozen_config.myopts
		usepkgonly = "--usepkgonly" in self._frozen_config.myopts
		empty = "empty" in self._dynamic_config.myparams
		selective = "selective" in self._dynamic_config.myparams
		reinstall = False
		avoid_update = "--update" not in self._frozen_config.myopts
		dont_miss_updates = "--update" in self._frozen_config.myopts
		use_ebuild_visibility = self._frozen_config.myopts.get(
			'--use-ebuild-visibility', 'n') != 'n'
		reinstall_atoms = self._frozen_config.reinstall_atoms
		usepkg_exclude = self._frozen_config.usepkg_exclude
		useoldpkg_atoms = self._frozen_config.useoldpkg_atoms
		matched_oldpkg = []
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
					if pkg.cp != atom_cp and have_new_virt:
						# pull in a new-style virtual instead
						continue
					if pkg in self._dynamic_config._runtime_pkg_mask:
						# The package has been masked by the backtracking logic
						continue
					root_slot = (pkg.root, pkg.slot_atom)
					if pkg.built and root_slot in self._rebuild.rebuild_list:
						continue
					if (pkg.installed and
						root_slot in self._rebuild.reinstall_list):
						continue

					if not pkg.installed and \
						self._frozen_config.excluded_pkgs.findAtomForPackage(pkg, \
							modified_use=self._pkg_use_enabled(pkg)):
						continue

					if built and not installed and usepkg_exclude.findAtomForPackage(pkg, \
						modified_use=self._pkg_use_enabled(pkg)):
						break

					useoldpkg = useoldpkg_atoms.findAtomForPackage(pkg, \
						modified_use=self._pkg_use_enabled(pkg))

					if packages_with_invalid_use_config and (not built or not useoldpkg) and \
						(not pkg.installed or dont_miss_updates):
						# Check if a higher version was rejected due to user
						# USE configuration. The packages_with_invalid_use_config
						# list only contains unbuilt ebuilds since USE can't
						# be changed for built packages.
						higher_version_rejected = False
						repo_priority = pkg.repo_priority
						for rejected in packages_with_invalid_use_config:
							if rejected.cp != pkg.cp:
								continue
							if rejected > pkg:
								higher_version_rejected = True
								break
							if portage.dep.cpvequal(rejected.cpv, pkg.cpv):
								# If version is identical then compare
								# repo priority (see bug #350254).
								rej_repo_priority = rejected.repo_priority
								if rej_repo_priority is not None and \
									(repo_priority is None or
									rej_repo_priority > repo_priority):
									higher_version_rejected = True
									break
						if higher_version_rejected:
							continue

					cpv = pkg.cpv
					reinstall_for_flags = None

					if not pkg.installed or \
						(matched_packages and not avoid_update):
						# Only enforce visibility on installed packages
						# if there is at least one other visible package
						# available. By filtering installed masked packages
						# here, packages that have been masked since they
						# were installed can be automatically downgraded
						# to an unmasked version. NOTE: This code needs to
						# be consistent with masking behavior inside
						# _dep_check_composite_db, in order to prevent
						# incorrect choices in || deps like bug #351828.

						if not self._pkg_visibility_check(pkg, autounmask_level):
							continue

						# Enable upgrade or downgrade to a version
						# with visible KEYWORDS when the installed
						# version is masked by KEYWORDS, but never
						# reinstall the same exact version only due
						# to a KEYWORDS mask. See bug #252167.

						if pkg.type_name != "ebuild" and matched_packages:
							# Don't re-install a binary package that is
							# identical to the currently installed package
							# (see bug #354441).
							identical_binary = False
							if usepkg and pkg.installed:
								for selected_pkg in matched_packages:
									if selected_pkg.type_name == "binary" and \
										selected_pkg.cpv == pkg.cpv and \
										selected_pkg.metadata.get('BUILD_TIME') == \
										pkg.metadata.get('BUILD_TIME'):
										identical_binary = True
										break

							if not identical_binary:
								# If the ebuild no longer exists or it's
								# keywords have been dropped, reject built
								# instances (installed or binary).
								# If --usepkgonly is enabled, assume that
								# the ebuild status should be ignored.
								if not use_ebuild_visibility and (usepkgonly or useoldpkg):
									if pkg.installed and pkg.masks:
										continue
								elif not self._equiv_ebuild_visible(pkg,
									autounmask_level=autounmask_level):
									continue

					# Calculation of USE for unbuilt ebuilds is relatively
					# expensive, so it is only performed lazily, after the
					# above visibility checks are complete.

					myarg = None
					try:
						for myarg, myarg_atom in self._iter_atoms_for_pkg(pkg):
							if myarg.force_reinstall:
								reinstall = True
								break
					except InvalidDependString:
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
						if autounmask_level and autounmask_level.allow_use_changes and not pkg.built:
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
							if any(x in atom.use.enabled for x in missing_disabled):
								use_match = False
								can_adjust_use = False
							need_enabled = atom.use.enabled.difference(use)
							if need_enabled:
								need_enabled = need_enabled.difference(missing_enabled)
								if need_enabled:
									use_match = False
									if can_adjust_use:
										if any(x in pkg.use.mask for x in need_enabled):
											can_adjust_use = False

						if atom.use.disabled:
							if any(x in atom.use.disabled for x in missing_enabled):
								use_match = False
								can_adjust_use = False
							need_disabled = atom.use.disabled.intersection(use)
							if need_disabled:
								need_disabled = need_disabled.difference(missing_disabled)
								if need_disabled:
									use_match = False
									if can_adjust_use:
										if any(x in pkg.use.force and x not in
											pkg.use.mask for x in need_disabled):
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
					if built and not useoldpkg and (not installed or matched_pkgs_ignore_use) and \
						("--newuse" in self._frozen_config.myopts or \
						"--reinstall" in self._frozen_config.myopts or \
						(not installed and self._dynamic_config.myparams.get(
						"binpkg_respect_use") in ("y", "auto"))):
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
						if myeb and not usepkgonly and not useoldpkg:
							cur_iuse = myeb.iuse.all
						reinstall_for_flags = self._reinstall_for_flags(pkg,
							forced_flags, old_use, iuses, now_use, cur_iuse)
						if reinstall_for_flags:
							if not pkg.installed:
								self._dynamic_config.ignored_binaries.setdefault(pkg, set()).update(reinstall_for_flags)
							break
					# Compare current config to installed package
					# and do not reinstall if possible.
					if not installed and not useoldpkg and \
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
							self._reinstall_for_flags(pkg,
							forced_flags, old_use, old_iuse,
							cur_use, cur_iuse)
						if reinstall_for_flags:
							reinstall = True
					if reinstall_atoms.findAtomForPackage(pkg, \
							modified_use=self._pkg_use_enabled(pkg)):
						reinstall = True
					if not built:
						myeb = pkg
					elif useoldpkg:
						matched_oldpkg.append(pkg)
					matched_packages.append(pkg)
					if reinstall_for_flags:
						self._dynamic_config._reinstall_nodes[pkg] = \
							reinstall_for_flags
					break

		if not matched_packages:
			return None, None

		if "--debug" in self._frozen_config.myopts:
			for pkg in matched_packages:
				portage.writemsg("%s %s%s%s\n" % \
					((pkg.type_name + ":").rjust(10),
					pkg.cpv, _repo_separator, pkg.repo), noiselevel=-1)

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
				unbuilt_pkg = None
				for pkg in matched_packages:
					if pkg.installed:
						inst_pkg = pkg
					elif pkg.built:
						built_pkg = pkg
					else:
						if unbuilt_pkg is None or pkg > unbuilt_pkg:
							unbuilt_pkg = pkg
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

					if unbuilt_pkg is not None and unbuilt_pkg > built_pkg:
						pass
					elif "--rebuilt-binaries-timestamp" in self._frozen_config.myopts:
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
					if pkg.installed and self._pkg_visibility_check(pkg, autounmask_level):
						return pkg, existing_node

			visible_matches = []
			if matched_oldpkg:
				visible_matches = [pkg.cpv for pkg in matched_oldpkg \
					if self._pkg_visibility_check(pkg, autounmask_level)]
			if not visible_matches:
				visible_matches = [pkg.cpv for pkg in matched_packages \
					if self._pkg_visibility_check(pkg, autounmask_level)]
			if visible_matches:
				bestmatch = portage.best(visible_matches)
			else:
				# all are masked, so ignore visibility
				bestmatch = portage.best([pkg.cpv for pkg in matched_packages])
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
		matches = list(self._iter_match_pkgs(self._frozen_config.roots[root],
			"installed", atom))
		if not matches:
			return None, None
		if len(matches) > 1:
			matches.reverse() # ascending order
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

		complete_if_new_use = self._dynamic_config.myparams.get(
			"complete_if_new_use", "y") == "y"
		complete_if_new_ver = self._dynamic_config.myparams.get(
			"complete_if_new_ver", "y") == "y"
		rebuild_if_new_slot = self._dynamic_config.myparams.get(
			"rebuild_if_new_slot", "y") == "y"
		complete_if_new_slot = rebuild_if_new_slot

		if "complete" not in self._dynamic_config.myparams and \
			(complete_if_new_use or
			complete_if_new_ver or complete_if_new_slot):
			# Enable complete mode if an installed package will change somehow.
			use_change = False
			version_change = False
			for node in self._dynamic_config.digraph:
				if not isinstance(node, Package) or \
					node.operation != "merge":
					continue
				vardb = self._frozen_config.roots[
					node.root].trees["vartree"].dbapi

				if complete_if_new_use or complete_if_new_ver:
					inst_pkg = vardb.match_pkgs(node.slot_atom)
					if inst_pkg and inst_pkg[0].cp == node.cp:
						inst_pkg = inst_pkg[0]
						if complete_if_new_ver and \
							(inst_pkg < node or node < inst_pkg):
							version_change = True
							break

						# Intersect enabled USE with IUSE, in order to
						# ignore forced USE from implicit IUSE flags, since
						# they're probably irrelevant and they are sensitive
						# to use.mask/force changes in the profile.
						if complete_if_new_use and \
							(node.iuse.all != inst_pkg.iuse.all or
							self._pkg_use_enabled(node).intersection(node.iuse.all) !=
							self._pkg_use_enabled(inst_pkg).intersection(inst_pkg.iuse.all)):
							use_change = True
							break

				if complete_if_new_slot:
					cp_list = vardb.match_pkgs(Atom(node.cp))
					if (cp_list and cp_list[0].cp == node.cp and
						not any(node.slot == pkg.slot for pkg in cp_list)):
						version_change = True
						break

			if use_change or version_change:
				self._dynamic_config.myparams["complete"] = True

		if "complete" not in self._dynamic_config.myparams:
			return 1

		self._load_vdb()

		# Put the depgraph into a mode that causes it to only
		# select packages that have already been added to the
		# graph or those that are installed and have not been
		# scheduled for replacement. Also, toggle the "deep"
		# parameter so that all dependencies are traversed and
		# accounted for.
		self._dynamic_config._complete_mode = True
		self._select_atoms = self._select_atoms_from_graph
		if "remove" in self._dynamic_config.myparams:
			self._select_package = self._select_pkg_from_installed
		else:
			self._select_package = self._select_pkg_from_graph
			self._dynamic_config._traverse_ignored_deps = True
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
				("remove" in self._dynamic_config.myparams or
				self._frozen_config.myopts.get("--root-deps") is not None):
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
				already_deep:
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

		# Ensure that we use the specially optimized RootConfig instance
		# that refers to FakeVartree instead of the real vartree.
		root_config = self._frozen_config.roots[root_config.root]
		pkg = self._frozen_config._pkg_cache.get(
			Package._gen_hash_key(cpv=cpv, type_name=type_name,
			repo_name=myrepo, root_config=root_config,
			installed=installed, onlydeps=onlydeps))
		if pkg is None and onlydeps and not installed:
			# Maybe it already got pulled in as a "merge" node.
			pkg = self._dynamic_config.mydbapi[root_config.root].get(
				Package._gen_hash_key(cpv=cpv, type_name=type_name,
				repo_name=myrepo, root_config=root_config,
				installed=installed, onlydeps=False))

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
		installed simultaneously. Also add runtime blockers from all installed
		packages if any of them haven't been added already (bug 128809)."""

		if "--buildpkgonly" in self._frozen_config.myopts or \
			"--nodeps" in self._frozen_config.myopts:
			return True

		if True:
			# Pull in blockers from all installed packages that haven't already
			# been pulled into the depgraph, in order to ensure that they are
			# respected (bug 128809). Due to the performance penalty that is
			# incurred by all the additional dep_check calls that are required,
			# blockers returned from dep_check are cached on disk by the
			# BlockerCache class.

			# For installed packages, always ignore blockers from DEPEND since
			# only runtime dependencies should be relevant for packages that
			# are already built.
			dep_keys = Package._runtime_keys
			for myroot in self._frozen_config.trees:

				if self._frozen_config.myopts.get("--root-deps") is not None and \
					myroot != self._frozen_config.target_root:
					continue

				vardb = self._frozen_config.trees[myroot]["vartree"].dbapi
				pkgsettings = self._frozen_config.pkgsettings[myroot]
				root_config = self._frozen_config.roots[myroot]
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
						if not self._pkg_visibility_check(pkg,
							trust_graph=False) and \
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
								pkg, depstr, _unicode_decode("%s") % (e,))
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
								pkg, depstr,
								_unicode_decode("Invalid Atom: %s") % (e,))
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

	def _implicit_libc_deps(self, mergelist, graph):
		"""
		Create implicit dependencies on libc, in order to ensure that libc
		is installed as early as possible (see bug #303567).
		"""
		libc_pkgs = {}
		implicit_libc_roots = (self._frozen_config._running_root.root,)
		for root in implicit_libc_roots:
			graphdb = self._dynamic_config.mydbapi[root]
			vardb = self._frozen_config.trees[root]["vartree"].dbapi
			for atom in self._expand_virt_from_graph(root,
 				portage.const.LIBC_PACKAGE_ATOM):
				if atom.blocker:
					continue
				match = graphdb.match_pkgs(atom)
				if not match:
					continue
				pkg = match[-1]
				if pkg.operation == "merge" and \
					not vardb.cpv_exists(pkg.cpv):
					libc_pkgs.setdefault(pkg.root, set()).add(pkg)

		if not libc_pkgs:
			return

		earlier_libc_pkgs = set()

		for pkg in mergelist:
			if not isinstance(pkg, Package):
				# a satisfied blocker
				continue
			root_libc_pkgs = libc_pkgs.get(pkg.root)
			if root_libc_pkgs is not None and \
				pkg.operation == "merge":
				if pkg in root_libc_pkgs:
					earlier_libc_pkgs.add(pkg)
				else:
					for libc_pkg in root_libc_pkgs:
						if libc_pkg in earlier_libc_pkgs:
							graph.add(libc_pkg, pkg,
								priority=DepPriority(buildtime=True))

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
		self._implicit_libc_deps(mergelist,
			self._dynamic_config._scheduler_graph)

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

		self.break_refs()
		sched_config = \
			_scheduler_graph_config(trees, pruned_pkg_cache, graph, mergelist)

		return sched_config

	def break_refs(self):
		"""
		Break any references in Package instances that lead back to the depgraph.
		This is useful if you want to hold references to packages without also
		holding the depgraph on the heap. It should only be called after the
		depgraph and _frozen_config will not be used for any more calculations.
		"""
		for root_config in self._frozen_config.roots.values():
			root_config.update(self._frozen_config._trees_orig[
				root_config.root]["root_config"])
			# Both instances are now identical, so discard the
			# original which should have no other references.
			self._frozen_config._trees_orig[
				root_config.root]["root_config"] = root_config

	def _resolve_conflicts(self):

		if "complete" not in self._dynamic_config.myparams and \
			self._dynamic_config._allow_backtracking and \
			self._dynamic_config._slot_collision_nodes and \
			not self._accept_blocker_conflicts():
			self._dynamic_config.myparams["complete"] = True

		if not self._complete_graph():
			raise self._unknown_internal_error()

		self._process_slot_conflicts()

		self._slot_operator_trigger_reinstalls()

		if not self._validate_blockers():
			self._dynamic_config._skip_restart = True
			raise self._unknown_internal_error()

	def _serialize_tasks(self):

		debug = "--debug" in self._frozen_config.myopts

		if debug:
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
		implicit_libc_roots = (running_root,)
		for root in implicit_libc_roots:
			libc_pkgs = set()
			vardb = self._frozen_config.trees[root]["vartree"].dbapi
			graphdb = self._dynamic_config.mydbapi[root]
			for atom in self._expand_virt_from_graph(root,
				portage.const.LIBC_PACKAGE_ATOM):
				if atom.blocker:
					continue
				match = graphdb.match_pkgs(atom)
				if not match:
					continue
				pkg = match[-1]
				if pkg.operation == "merge" and \
					not vardb.cpv_exists(pkg.cpv):
					libc_pkgs.add(pkg)

			if libc_pkgs:
				# If there's also an os-headers upgrade, we need to
				# pull that in first. See bug #328317.
				for atom in self._expand_virt_from_graph(root,
					portage.const.OS_HEADERS_PACKAGE_ATOM):
					if atom.blocker:
						continue
					match = graphdb.match_pkgs(atom)
					if not match:
						continue
					pkg = match[-1]
					if pkg.operation == "merge" and \
						not vardb.cpv_exists(pkg.cpv):
						asap_nodes.append(pkg)

				asap_nodes.extend(libc_pkgs)

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

		while mygraph:
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
				for i in range(priority_range.SOFT,
					priority_range.MEDIUM_SOFT + 1):
					ignore_priority = priority_range.ignore_priority[i]
					for node in asap_nodes:
						if not mygraph.child_nodes(node,
							ignore_priority=ignore_priority):
							selected_nodes = [node]
							asap_nodes.remove(node)
							break
					if selected_nodes:
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
						good_uninstalls = None
						if len(nodes) > 1:
							good_uninstalls = []
							for node in nodes:
								if node.operation == "uninstall":
									good_uninstalls.append(node)

							if good_uninstalls:
								nodes = good_uninstalls
							else:
								nodes = nodes

						if good_uninstalls or len(nodes) == 1 or \
							(ignore_priority is None and \
							not asap_nodes and not tree_mode):
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
							if asap_nodes:
								prefer_asap_parents = (True, False)
							else:
								prefer_asap_parents = (False,)
							for check_asap_parent in prefer_asap_parents:
								if check_asap_parent:
									for node in nodes:
										parents = mygraph.parent_nodes(node,
											ignore_priority=DepPrioritySatisfiedRange.ignore_soft)
										if any(x in asap_nodes for x in parents):
											selected_nodes = [node]
											break
								else:
									for node in nodes:
										if mygraph.parent_nodes(node):
											selected_nodes = [node]
											break
								if selected_nodes:
									break
						if selected_nodes:
							break

			if not selected_nodes:
				nodes = get_nodes(ignore_priority=priority_range.ignore_medium)
				if nodes:
					mergeable_nodes = set(nodes)
					if prefer_asap and asap_nodes:
						nodes = asap_nodes
					# When gathering the nodes belonging to a runtime cycle,
					# we want to minimize the number of nodes gathered, since
					# this tends to produce a more optimal merge order.
					# Ignoring all medium_soft deps serves this purpose.
					# In the case of multiple runtime cycles, where some cycles
					# may depend on smaller independent cycles, it's optimal
					# to merge smaller independent cycles before other cycles
					# that depend on them. Therefore, we search for the
					# smallest cycle in order to try and identify and prefer
					# these smaller independent cycles.
					ignore_priority = priority_range.ignore_medium_soft
					smallest_cycle = None
					for node in nodes:
						if not mygraph.parent_nodes(node):
							continue
						selected_nodes = set()
						if gather_deps(ignore_priority,
							mergeable_nodes, selected_nodes, node):
							# When selecting asap_nodes, we need to ensure
							# that we haven't selected a large runtime cycle
							# that is obviously sub-optimal. This will be
							# obvious if any of the non-asap selected_nodes
							# is a leaf node when medium_soft deps are
							# ignored.
							if prefer_asap and asap_nodes and \
								len(selected_nodes) > 1:
								for node in selected_nodes.difference(
									asap_nodes):
									if not mygraph.child_nodes(node,
										ignore_priority =
										DepPriorityNormalRange.ignore_medium_soft):
										selected_nodes = None
										break
							if selected_nodes:
								if smallest_cycle is None or \
									len(selected_nodes) < len(smallest_cycle):
									smallest_cycle = selected_nodes

					selected_nodes = smallest_cycle

					if selected_nodes and debug:
						writemsg("\nruntime cycle digraph (%s nodes):\n\n" %
							(len(selected_nodes),), noiselevel=-1)
						cycle_digraph = mygraph.copy()
						cycle_digraph.difference_update([x for x in
							cycle_digraph if x not in selected_nodes])
						cycle_digraph.debug_print()
						writemsg("\n", noiselevel=-1)

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
						# Merge PDEPEND asap for bug #180045.
						asap_nodes.append(child)

			if selected_nodes and len(selected_nodes) > 1:
				if not isinstance(selected_nodes, list):
					selected_nodes = list(selected_nodes)
				selected_nodes.sort(key=cmp_sort_key(cmp_circular_bias))

			if not selected_nodes and myblocker_uninstalls:
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

			if not selected_nodes and myblocker_uninstalls:
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
				self._dynamic_config._skip_restart = True
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
			self._dynamic_config._skip_restart = True
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

		if handler.circular_dep_message is None:
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
			not (self._dynamic_config._displayed_list is not None and \
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
			for pkg, parent_atoms in conflict_pkgs.items():

				# Prefer packages that are not directly involved in a conflict.
				# It can be essential to see all the packages here, so don't
				# omit any. If the list is long, people can simply use a pager.
				preferred_parents = set()
				for parent_atom in parent_atoms:
					parent, atom = parent_atom
					if parent not in conflict_pkgs:
						preferred_parents.add(parent_atom)

				ordered_list = list(preferred_parents)
				if len(parent_atoms) > len(ordered_list):
					for parent_atom in parent_atoms:
						if parent_atom not in preferred_parents:
							ordered_list.append(parent_atom)

				msg.append(indent + "%s pulled in by\n" % pkg)

				for parent_atom in ordered_list:
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

				msg.append("\n")

			writemsg("".join(msg), noiselevel=-1)

		if "--quiet" not in self._frozen_config.myopts:
			show_blocker_docs_link()

	def display(self, mylist, favorites=[], verbosity=None):

		# This is used to prevent display_problems() from
		# redundantly displaying this exact same merge list
		# again via _show_merge_list().
		self._dynamic_config._displayed_list = mylist
		display = Display()

		return display(self, mylist, favorites, verbosity)

	def _display_autounmask(self):
		"""
		Display --autounmask message and optionally write it to config files
		(using CONFIG_PROTECT). The message includes the comments and the changes.
		"""

		autounmask_write = self._frozen_config.myopts.get("--autounmask-write", "n") == True
		autounmask_unrestricted_atoms = \
			self._frozen_config.myopts.get("--autounmask-unrestricted-atoms", "n") == True
		quiet = "--quiet" in self._frozen_config.myopts
		pretend = "--pretend" in self._frozen_config.myopts
		ask = "--ask" in self._frozen_config.myopts
		enter_invalid = '--ask-enter-invalid' in self._frozen_config.myopts

		def check_if_latest(pkg):
			is_latest = True
			is_latest_in_slot = True
			dbs = self._dynamic_config._filtered_trees[pkg.root]["dbs"]
			root_config = self._frozen_config.roots[pkg.root]

			for db, pkg_type, built, installed, db_keys in dbs:
				for other_pkg in self._iter_match_pkgs(root_config, pkg_type, Atom(pkg.cp)):
					if other_pkg.cp != pkg.cp:
						# old-style PROVIDE virtual means there are no
						# normal matches for this pkg_type
						break
					if other_pkg > pkg:
						is_latest = False
						if other_pkg.slot_atom == pkg.slot_atom:
							is_latest_in_slot = False
							break
					else:
						# iter_match_pkgs yields highest version first, so
						# there's no need to search this pkg_type any further
						break

				if not is_latest_in_slot:
					break

			return is_latest, is_latest_in_slot

		#Set of roots we have autounmask changes for.
		roots = set()

		masked_by_missing_keywords = False
		unstable_keyword_msg = {}
		for pkg in self._dynamic_config._needed_unstable_keywords:
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				root = pkg.root
				roots.add(root)
				unstable_keyword_msg.setdefault(root, [])
				is_latest, is_latest_in_slot = check_if_latest(pkg)
				pkgsettings = self._frozen_config.pkgsettings[pkg.root]
				mreasons = _get_masking_status(pkg, pkgsettings, pkg.root_config,
					use=self._pkg_use_enabled(pkg))
				for reason in mreasons:
					if reason.unmask_hint and \
						reason.unmask_hint.key == 'unstable keyword':
						keyword = reason.unmask_hint.value
						if keyword == "**":
							masked_by_missing_keywords = True

						unstable_keyword_msg[root].append(self._get_dep_chain_as_comment(pkg))
						if autounmask_unrestricted_atoms:
							if is_latest:
								unstable_keyword_msg[root].append(">=%s %s\n" % (pkg.cpv, keyword))
							elif is_latest_in_slot:
								unstable_keyword_msg[root].append(">=%s:%s %s\n" % (pkg.cpv, pkg.slot, keyword))
							else:
								unstable_keyword_msg[root].append("=%s %s\n" % (pkg.cpv, keyword))
						else:
							unstable_keyword_msg[root].append("=%s %s\n" % (pkg.cpv, keyword))

		p_mask_change_msg = {}
		for pkg in self._dynamic_config._needed_p_mask_changes:
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				root = pkg.root
				roots.add(root)
				p_mask_change_msg.setdefault(root, [])
				is_latest, is_latest_in_slot = check_if_latest(pkg)
				pkgsettings = self._frozen_config.pkgsettings[pkg.root]
				mreasons = _get_masking_status(pkg, pkgsettings, pkg.root_config,
					use=self._pkg_use_enabled(pkg))
				for reason in mreasons:
					if reason.unmask_hint and \
						reason.unmask_hint.key == 'p_mask':
						keyword = reason.unmask_hint.value

						comment, filename = portage.getmaskingreason(
							pkg.cpv, metadata=pkg.metadata,
							settings=pkgsettings,
							portdb=pkg.root_config.trees["porttree"].dbapi,
							return_location=True)

						p_mask_change_msg[root].append(self._get_dep_chain_as_comment(pkg))
						if filename:
							p_mask_change_msg[root].append("# %s:\n" % filename)
						if comment:
							comment = [line for line in
								comment.splitlines() if line]
							for line in comment:
								p_mask_change_msg[root].append("%s\n" % line)
						if autounmask_unrestricted_atoms:
							if is_latest:
								p_mask_change_msg[root].append(">=%s\n" % pkg.cpv)
							elif is_latest_in_slot:
								p_mask_change_msg[root].append(">=%s:%s\n" % (pkg.cpv, pkg.slot))
							else:
								p_mask_change_msg[root].append("=%s\n" % pkg.cpv)
						else:
							p_mask_change_msg[root].append("=%s\n" % pkg.cpv)

		use_changes_msg = {}
		for pkg, needed_use_config_change in self._dynamic_config._needed_use_config_changes.items():
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				root = pkg.root
				roots.add(root)
				use_changes_msg.setdefault(root, [])
				is_latest, is_latest_in_slot = check_if_latest(pkg)
				changes = needed_use_config_change[1]
				adjustments = []
				for flag, state in changes.items():
					if state:
						adjustments.append(flag)
					else:
						adjustments.append("-" + flag)
				use_changes_msg[root].append(self._get_dep_chain_as_comment(pkg, unsatisfied_dependency=True))
				if is_latest:
					use_changes_msg[root].append(">=%s %s\n" % (pkg.cpv, " ".join(adjustments)))
				elif is_latest_in_slot:
					use_changes_msg[root].append(">=%s:%s %s\n" % (pkg.cpv, pkg.slot, " ".join(adjustments)))
				else:
					use_changes_msg[root].append("=%s %s\n" % (pkg.cpv, " ".join(adjustments)))

		license_msg = {}
		for pkg, missing_licenses in self._dynamic_config._needed_license_changes.items():
			self._show_merge_list()
			if pkg in self._dynamic_config.digraph:
				root = pkg.root
				roots.add(root)
				license_msg.setdefault(root, [])
				is_latest, is_latest_in_slot = check_if_latest(pkg)

				license_msg[root].append(self._get_dep_chain_as_comment(pkg))
				if is_latest:
					license_msg[root].append(">=%s %s\n" % (pkg.cpv, " ".join(sorted(missing_licenses))))
				elif is_latest_in_slot:
					license_msg[root].append(">=%s:%s %s\n" % (pkg.cpv, pkg.slot, " ".join(sorted(missing_licenses))))
				else:
					license_msg[root].append("=%s %s\n" % (pkg.cpv, " ".join(sorted(missing_licenses))))

		def find_config_file(abs_user_config, file_name):
			"""
			Searches /etc/portage for an appropriate file to append changes to.
			If the file_name is a file it is returned, if it is a directory, the
			last file in it is returned. Order of traversal is the identical to
			portage.util.grablines(recursive=True).

			file_name - String containing a file name like "package.use"
			return value - String. Absolute path of file to write to. None if
			no suitable file exists.
			"""
			file_path = os.path.join(abs_user_config, file_name)

			try:
				os.lstat(file_path)
			except OSError as e:
				if e.errno == errno.ENOENT:
					# The file doesn't exist, so we'll
					# simply create it.
					return file_path

				# Disk or file system trouble?
				return None

			last_file_path = None
			stack = [file_path]
			while stack:
				p = stack.pop()
				try:
					st = os.stat(p)
				except OSError:
					pass
				else:
					if stat.S_ISREG(st.st_mode):
						last_file_path = p
					elif stat.S_ISDIR(st.st_mode):
						if os.path.basename(p) in _ignorecvs_dirs:
							continue
						try:
							contents = os.listdir(p)
						except OSError:
							pass
						else:
							contents.sort(reverse=True)
							for child in contents:
								if child.startswith(".") or \
									child.endswith("~"):
									continue
								stack.append(os.path.join(p, child))

			return last_file_path

		write_to_file = autounmask_write and not pretend
		#Make sure we have a file to write to before doing any write.
		file_to_write_to = {}
		problems = []
		if write_to_file:
			for root in roots:
				settings = self._frozen_config.roots[root].settings
				abs_user_config = os.path.join(
					settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH)

				if root in unstable_keyword_msg:
					if not os.path.exists(os.path.join(abs_user_config,
						"package.keywords")):
						filename = "package.accept_keywords"
					else:
						filename = "package.keywords"
					file_to_write_to[(abs_user_config, "package.keywords")] = \
						find_config_file(abs_user_config, filename)

				if root in p_mask_change_msg:
					file_to_write_to[(abs_user_config, "package.unmask")] = \
						find_config_file(abs_user_config, "package.unmask")

				if root in use_changes_msg:
					file_to_write_to[(abs_user_config, "package.use")] = \
						find_config_file(abs_user_config, "package.use")

				if root in license_msg:
					file_to_write_to[(abs_user_config, "package.license")] = \
						find_config_file(abs_user_config, "package.license")

			for (abs_user_config, f), path in file_to_write_to.items():
				if path is None:
					problems.append("!!! No file to write for '%s'\n" % os.path.join(abs_user_config, f))

			write_to_file = not problems

		def format_msg(lines):
			lines = lines[:]
			for i, line in enumerate(lines):
				if line.startswith("#"):
					continue
				lines[i] = colorize("INFORM", line.rstrip()) + "\n"
			return "".join(lines)

		for root in roots:
			settings = self._frozen_config.roots[root].settings
			abs_user_config = os.path.join(
				settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH)

			if len(roots) > 1:
				writemsg("\nFor %s:\n" % abs_user_config, noiselevel=-1)

			if root in unstable_keyword_msg:
				writemsg("\nThe following " + colorize("BAD", "keyword changes") + \
					" are necessary to proceed:\n", noiselevel=-1)
				writemsg(format_msg(unstable_keyword_msg[root]), noiselevel=-1)

			if root in p_mask_change_msg:
				writemsg("\nThe following " + colorize("BAD", "mask changes") + \
					" are necessary to proceed:\n", noiselevel=-1)
				writemsg(format_msg(p_mask_change_msg[root]), noiselevel=-1)

			if root in use_changes_msg:
				writemsg("\nThe following " + colorize("BAD", "USE changes") + \
					" are necessary to proceed:\n", noiselevel=-1)
				writemsg(format_msg(use_changes_msg[root]), noiselevel=-1)

			if root in license_msg:
				writemsg("\nThe following " + colorize("BAD", "license changes") + \
					" are necessary to proceed:\n", noiselevel=-1)
				writemsg(format_msg(license_msg[root]), noiselevel=-1)

		protect_obj = {}
		if write_to_file:
			for root in roots:
				settings = self._frozen_config.roots[root].settings
				protect_obj[root] = ConfigProtect(settings["EROOT"], \
					shlex_split(settings.get("CONFIG_PROTECT", "")),
					shlex_split(settings.get("CONFIG_PROTECT_MASK", "")))

		def write_changes(root, changes, file_to_write_to):
			file_contents = None
			try:
				file_contents = io.open(
					_unicode_encode(file_to_write_to,
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['content'],
					errors='replace').readlines()
			except IOError as e:
				if e.errno == errno.ENOENT:
					file_contents = []
				else:
					problems.append("!!! Failed to read '%s': %s\n" % \
						(file_to_write_to, e))
			if file_contents is not None:
				file_contents.extend(changes)
				if protect_obj[root].isprotected(file_to_write_to):
					# We want to force new_protect_filename to ensure
					# that the user will see all our changes via
					# dispatch-conf, even if file_to_write_to doesn't
					# exist yet, so we specify force=True.
					file_to_write_to = new_protect_filename(file_to_write_to,
						force=True)
				try:
					write_atomic(file_to_write_to, "".join(file_contents))
				except PortageException:
					problems.append("!!! Failed to write '%s'\n" % file_to_write_to)

		if not quiet and (p_mask_change_msg or masked_by_missing_keywords):
			msg = [
				"",
				"NOTE: The --autounmask-keep-masks option will prevent emerge",
				"      from creating package.unmask or ** keyword changes."
			]
			for line in msg:
				if line:
					line = colorize("INFORM", line)
				writemsg(line + "\n", noiselevel=-1)

		if ask and write_to_file and file_to_write_to:
			prompt = "\nWould you like to add these " + \
				"changes to your config files?"
			if userquery(prompt, enter_invalid) == 'No':
				write_to_file = False

		if write_to_file and file_to_write_to:
			for root in roots:
				settings = self._frozen_config.roots[root].settings
				abs_user_config = os.path.join(
					settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH)
				ensure_dirs(abs_user_config)

				if root in unstable_keyword_msg:
					write_changes(root, unstable_keyword_msg[root],
						file_to_write_to.get((abs_user_config, "package.keywords")))

				if root in p_mask_change_msg:
					write_changes(root, p_mask_change_msg[root],
						file_to_write_to.get((abs_user_config, "package.unmask")))

				if root in use_changes_msg:
					write_changes(root, use_changes_msg[root],
						file_to_write_to.get((abs_user_config, "package.use")))

				if root in license_msg:
					write_changes(root, license_msg[root],
						file_to_write_to.get((abs_user_config, "package.license")))

		if problems:
			writemsg("\nThe following problems occurred while writing autounmask changes:\n", \
				noiselevel=-1)
			writemsg("".join(problems), noiselevel=-1)
		elif write_to_file and roots:
			writemsg("\nAutounmask changes successfully written. Remember to run dispatch-conf.\n", \
				noiselevel=-1)
		elif not pretend and not autounmask_write and roots:
			writemsg("\nUse --autounmask-write to write changes to config files (honoring CONFIG_PROTECT).\n", \
				noiselevel=-1)


	def display_problems(self):
		"""
		Display problems with the dependency graph such as slot collisions.
		This is called internally by display() to show the problems _after_
		the merge list where it is most likely to be seen, but if display()
		is not going to be called then this method should be called explicitly
		to ensure that the user is notified of problems with the graph.
		"""

		if self._dynamic_config._circular_deps_for_display is not None:
			self._show_circular_deps(
				self._dynamic_config._circular_deps_for_display)

		# The slot conflict display has better noise reduction than
		# the unsatisfied blockers display, so skip unsatisfied blockers
		# display if there are slot conflicts (see bug #385391).
		if self._dynamic_config._slot_collision_info:
			self._show_slot_collision_notice()
		elif self._dynamic_config._unsatisfied_blockers_for_display is not None:
			self._show_unsatisfied_blockers(
				self._dynamic_config._unsatisfied_blockers_for_display)
		else:
			self._show_missed_update()

		self._show_ignored_binaries()

		self._display_autounmask()

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

		for pargs, kwargs in self._dynamic_config._unsatisfied_deps_for_display:
			self._show_unsatisfied_dep(*pargs, **kwargs)

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
			if arg.internal:
				# __auto_* sets
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
			if a.startswith(SETPREFIX):
				filename = "world_sets"
			else:
				filename = "world"
			writemsg_stdout(
				">>> Recording %s in \"%s\" favorites file...\n" %
				(colorize("INFORM", _unicode(a)), filename), noiselevel=-1)
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
		if isinstance(favorites, list):
			args = self._load_favorites(favorites)
		else:
			args = []

		fakedb = self._dynamic_config.mydbapi
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

	class _autounmask_breakage(_internal_exception):
		"""
		This is raised by _show_unsatisfied_dep() when it's called with
		check_autounmask_breakage=True and a matching package has been
		been disqualified due to autounmask changes.
		"""

	def need_restart(self):
		return self._dynamic_config._need_restart and \
			not self._dynamic_config._skip_restart

	def success_without_autounmask(self):
		return self._dynamic_config._success_without_autounmask

	def autounmask_breakage_detected(self):
		try:
			for pargs, kwargs in self._dynamic_config._unsatisfied_deps_for_display:
				self._show_unsatisfied_dep(
					*pargs, check_autounmask_breakage=True, **kwargs)
		except self._autounmask_breakage:
			return True
		return False

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

	def cp_list(self, cp):
		"""
		Emulate cp_list just so it can be used to check for existence
		of new-style virtuals. Since it's a waste of time to return
		more than one cpv for this use case, a maximum of one cpv will
		be returned.
		"""
		if isinstance(cp, Atom):
			atom = cp
		else:
			atom = Atom(cp)
		ret = []
		for pkg in self._depgraph._iter_match_pkgs_any(
			self._depgraph._frozen_config.roots[self._root], atom):
			if pkg.cp == cp:
				ret.append(pkg.cpv)
				break

		return ret

	def match(self, atom):
		cache_key = (atom, atom.unevaluated_atom)
		ret = self._match_cache.get(cache_key)
		if ret is not None:
			return ret[:]

		ret = []
		pkg, existing = self._depgraph._select_package(self._root, atom)

		if pkg is not None and self._visible(pkg):
			self._cpv_pkg_map[pkg.cpv] = pkg
			ret.append(pkg.cpv)

		if pkg is not None and \
			atom.slot is None and \
			pkg.cp.startswith("virtual/") and \
			(("remove" not in self._depgraph._dynamic_config.myparams and
			"--update" not in self._depgraph._frozen_config.myopts) or
			not ret or
			not self._depgraph._virt_deps_visible(pkg, ignore_use=True)):
			# For new-style virtual lookahead that occurs inside dep_check()
			# for bug #141118, examine all slots. This is needed so that newer
			# slots will not unnecessarily be pulled in when a satisfying lower
			# slot is already installed. For example, if virtual/jdk-1.5 is
			# satisfied via gcj-jdk then there's no need to pull in a newer
			# slot to satisfy a virtual/jdk dependency, unless --update is
			# enabled.
			slots = set()
			slots.add(pkg.slot)
			for virt_pkg in self._depgraph._iter_match_pkgs_any(
				self._depgraph._frozen_config.roots[self._root], atom):
				if virt_pkg.cp != pkg.cp:
					continue
				slots.add(virt_pkg.slot)

			slots.remove(pkg.slot)
			while slots:
				slot_atom = atom.with_slot(slots.pop())
				pkg, existing = self._depgraph._select_package(
					self._root, slot_atom)
				if not pkg:
					continue
				if not self._visible(pkg):
					continue
				self._cpv_pkg_map[pkg.cpv] = pkg
				ret.append(pkg.cpv)

			if len(ret) > 1:
				self._cpv_sort_ascending(ret)

		self._match_cache[cache_key] = ret
		return ret[:]

	def _visible(self, pkg):
		if pkg.installed and not self._depgraph._want_installed_pkg(pkg):
			return False
		if pkg.installed and \
			(pkg.masks or not self._depgraph._pkg_visibility_check(pkg)):
			# Account for packages with masks (like KEYWORDS masks)
			# that are usually ignored in visibility checks for
			# installed packages, in order to handle cases like
			# bug #350285.
			myopts = self._depgraph._frozen_config.myopts
			use_ebuild_visibility = myopts.get(
				'--use-ebuild-visibility', 'n') != 'n'
			avoid_update = "--update" not in myopts and \
				"remove" not in self._depgraph._dynamic_config.myparams
			usepkgonly = "--usepkgonly" in myopts
			if not avoid_update:
				if not use_ebuild_visibility and usepkgonly:
					return False
				elif not self._depgraph._equiv_ebuild_visible(pkg):
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
			if highest_visible is not None and pkg < highest_visible:
				return False
		elif in_graph != pkg:
			# Mask choices for packages that would trigger a slot
			# conflict with a previously selected package.
			return False
		return True

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
		spinner.update == spinner.update_quiet:
		return

	if spinner.update != spinner.update_basic:
		# update_basic is used for non-tty output,
		# so don't output backspaces in that case.
		portage.writemsg_stdout("\b\b")

	portage.writemsg_stdout("... done!\n")

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

	debug = "--debug" in myopts
	mydepgraph = None
	max_retries = myopts.get('--backtrack', 10)
	max_depth = max(1, (max_retries + 1) / 2)
	allow_backtracking = max_retries > 0
	backtracker = Backtracker(max_depth)
	backtracked = 0

	frozen_config = _frozen_depgraph_config(settings, trees,
		myopts, spinner)

	while backtracker:

		if debug and mydepgraph is not None:
			writemsg_level(
				"\n\nbacktracking try %s \n\n" % \
				backtracked, noiselevel=-1, level=logging.DEBUG)
			mydepgraph.display_problems()

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

		if debug:
			writemsg_level(
				"\n\nbacktracking aborted after %s tries\n\n" % \
				backtracked, noiselevel=-1, level=logging.DEBUG)
			mydepgraph.display_problems()

		mydepgraph = depgraph(settings, trees, myopts, myparams, spinner,
			frozen_config=frozen_config,
			allow_backtracking=False,
			backtrack_parameters=backtracker.get_best_run())
		success, favorites = mydepgraph.select_files(myfiles)

	if not success and mydepgraph.autounmask_breakage_detected():
		if debug:
			writemsg_level(
				"\n\nautounmask breakage detected\n\n",
				noiselevel=-1, level=logging.DEBUG)
			mydepgraph.display_problems()
		myopts["--autounmask"] = "n"
		mydepgraph = depgraph(settings, trees, myopts, myparams, spinner,
			frozen_config=frozen_config, allow_backtracking=False)
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
	@return: (success, depgraph, dropped_tasks)
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
					# We need to traverse all priorities here, in order to
					# ensure that a package with an unsatisfied depenedency
					# won't get pulled in, even indirectly via a soft
					# dependency.
					unsatisfied_parents[parent_node] = parent_node
					unsatisfied_stack.append(parent_node)

			unsatisfied_tuples = frozenset(tuple(parent_node)
				for parent_node in unsatisfied_parents
				if isinstance(parent_node, Package))
			pruned_mergelist = []
			for x in mergelist:
				if isinstance(x, list) and \
					tuple(x) not in unsatisfied_tuples:
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

			del e, graph, traversed_nodes, \
				unsatisfied_parents, unsatisfied_stack
			continue
		else:
			break
	return (success, mydepgraph, dropped_tasks)

def get_mask_info(root_config, cpv, pkgsettings,
	db, pkg_type, built, installed, db_keys, myrepo = None, _pkg_use_enabled=None):
	try:
		metadata = dict(zip(db_keys,
			db.aux_get(cpv, db_keys, myrepo=myrepo)))
	except KeyError:
		metadata = None

	if metadata is None:
		mreasons = ["corruption"]
	else:
		eapi = metadata['EAPI']
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
		eapi_masked = metadata is not None and \
			not portage.eapi_is_supported(metadata["EAPI"])
		if eapi_masked:
			have_eapi_mask = True
			# When masked by EAPI, metadata is mostly useless since
			# it doesn't contain essential things like SLOT.
			metadata = None
		comment, filename = None, None
		if not eapi_masked and \
			"package.mask" in mreasons:
			comment, filename = \
				portage.getmaskingreason(
				cpv, metadata=metadata,
				settings=pkgsettings,
				portdb=root_config.trees["porttree"].dbapi,
				return_location=True)
		missing_licenses = []
		if not eapi_masked and metadata is not None:
			try:
				missing_licenses = \
					pkgsettings._getMissingLicenses(
						cpv, metadata)
			except portage.exception.InvalidDependString:
				# This will have already been reported
				# above via mreasons.
				pass

		writemsg("- "+output_cpv+" (masked by: "+", ".join(mreasons)+")\n",
			noiselevel=-1)

		if comment and comment not in shown_comments:
			writemsg(filename + ":\n" + comment + "\n",
				noiselevel=-1)
			shown_comments.add(comment)
		portdb = root_config.trees["porttree"].dbapi
		for l in missing_licenses:
			l_path = portdb.findLicensePath(l)
			if l in shown_licenses:
				continue
			msg = ("A copy of the '%s' license" + \
			" is located at '%s'.\n\n") % (l, l_path)
			writemsg(msg, noiselevel=-1)
			shown_licenses.add(l)
	return have_eapi_mask

def show_mask_docs():
	writemsg("For more information, see the MASKED PACKAGES "
		"section in the emerge\n", noiselevel=-1)
	writemsg("man page or refer to the Gentoo Handbook.\n", noiselevel=-1)

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

	if pkg.invalid:
		for msgs in pkg.invalid.values():
			for msg in msgs:
				mreasons.append(
					_MaskReason("invalid", "invalid: %s" % (msg,)))

	if not pkg.metadata["SLOT"]:
		mreasons.append(
			_MaskReason("invalid", "SLOT: undefined"))

	return mreasons
