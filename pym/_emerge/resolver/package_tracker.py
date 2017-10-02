# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# Refactored in Sept 2017 by Daniel Robbins to allow for slot rebuilds to be detected in real-time with minimal code,
# and various other improvements. Needs to be validated to ensure it doesn't break any assumptions in existing Portage
# code. This works for a Funtoo non-backtracking slot-overhaul version of depgraph.py but I want to get it working
# for upstream Gentoo portage as well, with backtracking. I also plan to add more verbose documentation once the code
# has settled.

# Notable changes:
#
# add_installed_pkg() is deprecated as add_pkg() now determines if package is installed by looking at pkg.installed.
# Just replace add_installed_pkg() calls with add_pkg() calls.
#
# Some caching has been removed as the code is in flux, and can be added back later as necessary. Shouldn't impact
# functionality, just speed.
#
# the PackageTracker() constructor now takes a dynamic_config instance as its first argument so it can access the
# digraph.
#
# get_subslot_rebuilds() is the new method that very efficiently identifies necessary subslot rebuilds.
#
# Various unused methods were removed. Hopefully I didn't remove too much for upstream gentoo Portage.
#
# Trying to document behavior as well as key variables and assumptions of code.

from __future__ import print_function

import bisect
import collections

import portage
from _emerge.Package import Package
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.dep:Atom,match_from_list',
	'portage.util:cmp_sort_key',
	'portage.versions:vercmp',
)

_PackageConflict = collections.namedtuple("_PackageConflict", ["root", "pkgs", "atom", "description"])

class PackageConflict(_PackageConflict):
	"""
	Class to track the reason for a conflict and the conflicting packages.
	"""
	def __iter__(self):
		return iter(self.pkgs)

	def __contains__(self, pkg):
		return pkg in self.pkgs

	def __len__(self):
		return len(self.pkgs)

class PackageTracker(object):

	def __init__(self, soname_deps=False):
		"""
		@param soname_deps: enable soname match support
		@type soname_deps: bool
		"""
		# _installed_map records the list of to-be-merged packages.
		self._installed_map = collections.defaultdict(list)

		# _queued_map records the list of already-installed packages.
		self._queued_map = collections.defaultdict(list)

		# List of package keys that may contain conflicts.
		# The insertion order is used to track first potential conflict, second potential, etc.
		self._multi_pkgs = []

		self._subslot_replacements = {}

		if soname_deps:
			self._provides_index = collections.defaultdict(list)
		else:
			self._provides_index = None

	def add_pkg(self, pkg):

		cp_key = pkg.root, pkg.cp

		if pkg.installed:
			target = self._installed_map
			other = self._queued_map
		else:
			target = self._queued_map
			other = self._installed_map

		# don't add multiple copies of the same package
		if any(foo is pkg for foo in target):
			return

		# add package
		target[cp_key].append(pkg)

		# use classic logic for tracking multi_pkgs:
		if not pkg.installed:
			if len(target[cp_key]) == 2:
				self._multi_pkgs.append(cp_key)

		to_remove = []

		# if adding installed pkg, we look at queued pkgs, and vice versa:
		for other_pkg in other.get(cp_key, []):
			if pkg.slot_atom == other_pkg.slot_atom:
				if pkg.cpv == other_pkg.cpv:

					# adding an installed package will wipe out the matching to-be-merged package, and vice-versa:
					to_remove.append(other_pkg)

				# we are processing a to-be-merged pkg and found an installed pkg with differing sub-slot:
				if not pkg.installed and pkg.sub_slot != other_pkg.sub_slot:

					# found sub-slot replacement/upgrade! We can look at parents to easily figure out sub-slot rebuilds.
					self._subslot_replacements[cp_key] = True

		# do all removals outside of the previous loop, since we don't want to modify a dict while iterating over it:
		for other_pkg in to_remove:
			other[cp_key].remove(other_pkg)

		if (self._provides_index is not None and pkg.provides is not None):
			index = self._provides_index
			root = pkg.root
			for atom in pkg.provides:
				# Use bisect.insort for ordered match results.
				bisect.insort(index[(root, atom)], pkg)

	def remove_pkg(self, pkg):
		cp_key = pkg.root, pkg.cp
		for my_map in [ self._queued_map, self._installed_map ]:
			try:
				my_map.get(cp_key, []).remove(pkg)
			except ValueError:
				if my_map is self._queued_map:
					raise KeyError(pkg)
				else:
					pass
			if not my_map[cp_key]:
				del my_map[cp_key]

		if len(self._queued_map[cp_key]) == 1:
			self._multi_pkgs = [other_cp_key for other_cp_key in self._multi_pkgs if other_cp_key != cp_key]

		# This code is necessary to ensure that self._subslot_replacements is properly updated when a pkg is removed
		# from the package tracker:

		if not pkg.installed and cp_key in self._subslot_replacements:
			del self._subslot_replacements[cp_key]

		if self._provides_index is not None:
			index = self._provides_index
			root = pkg.root
			for atom in pkg.provides:
				key = (root, atom)
				items = index[key]
				try:
					items.remove(pkg)
				except ValueError:
					pass
				if not items:
					del index[key]

	def discard_pkg(self, pkg):
		try:
			self.remove_pkg(pkg)
		except KeyError:
			pass

	def get_subslot_rebuilds(self, dynamic_config):

		out = []
		for root, pkg in self._subslot_replacements.keys():
			# we have identified a subslot replacement. Parents will need to be rebuilt:
			for node in dynamic_config.digraph.parent_nodes(pkg):
				if isinstance(node, Package):
					out.append((pkg,node))
		return out

	def match(self, root, atom, installed=True):
		"""
		Iterates over the packages matching 'atom'.
		If 'installed' is True, installed non-replaced
		packages may also be returned.
		"""

		# TODO: add caching back

		if atom.soname:
			return iter(self._provides_index.get((root, atom), []))

		cp_key = root, atom.cp
		candidates = self._queued_map.get(cp_key, [])[:]

		if installed:
			candidates.extend(self._installed_map.get(cp_key, []))

		ret = match_from_list(atom, candidates)
		ret.sort(key=cmp_sort_key(lambda x, y: vercmp(x.version, y.version)))

		return iter(ret)

	def conflicts(self):
		"""
		Iterates over the currently existing conflicts.
		"""
		out = []

		for cp_key in self._multi_pkgs:

			# A cp_key in _multi_pkgs has a /potential/ conflict. We need to interrogate the contents of the
			# cp_key to see.

			# Categorize packages according to cpv and slot.
			slot_map = collections.defaultdict(list)
			cpv_map = collections.defaultdict(list)
			# for each to-be-merged package:
			for pkg in self._queued_map[cp_key]:
				# confusing: note that pkg.slot_atom actually contains "catpkg:slot"
				slot_key = pkg.root, pkg.slot_atom
				cpv_key = pkg.root, pkg.cpv
				slot_map[slot_key].append(pkg)
				cpv_map[cpv_key].append(pkg)

			# for each "catpkg:slot" value:
			for slot_key in slot_map:
				# slot_pkgs = all packages to-be-installed in the same slot
				slot_pkgs = slot_map[slot_key]
				if len(slot_pkgs) > 1:
					out.append(PackageConflict(
						description = "slot conflict",
						root = slot_key[0],
						atom = slot_key[1],
						pkgs = tuple(slot_pkgs),
					))

			# CPV conflicts. This is where we have two different versions in the same slot.
			for cpv_key in cpv_map:
				cpv_pkgs = cpv_map[cpv_key]
				if len(cpv_pkgs) > 1:
					# Make sure this cpv conflict is not a slot conflict at the same time.
					# Ignore it if it is.
					slots = set(pkg.slot for pkg in cpv_pkgs)
					if len(slots) > 1:
						out.append(PackageConflict(
							description = "cpv conflict",
							root = cpv_key[0],
							atom = cpv_key[1],
							pkgs = tuple(cpv_pkgs),
							))

		return out

	def slot_conflicts(self):
		"""
		Iterates over present slot conflicts.
		This is only intended for consumers that haven't been
		updated to deal with other kinds of conflicts.
		This funcion should be removed once all consumers are updated.
		"""
		return (conflict for conflict in self.conflicts() \
			if conflict.description == "slot conflict")

	def all_pkgs(self, root):
		"""
		Iterates over all packages for the given root
		present in the tracker, including the installed
		packages.
		"""

		for mymap in [ self._queued_map, self._installed_map ]:
			for cp_key in mymap:
				if cp_key[0] == root:
					for pkg in mymap[cp_key]:
						yield pkg

	def contains(self, pkg, installed=True):
		"""
		Checks if the package is in the tracker.
		If 'installed' is True, returns True for
		non-replaced installed packages.
		"""
		cp_key = pkg.root, pkg.cp

		for other in self._queued_map.get(cp_key, []):
			if other is pkg:
				return True

		if installed:
			for installed in self._installed_map.get(cp_key, []):
				if installed is pkg:
					return True

		return False

	def __contains__(self, pkg):
		"""
		Checks if the package is in the tracker.
		Returns True for non-replaced installed packages.
		"""
		return self.contains(pkg, installed=True)


class PackageTrackerDbapiWrapper(object):
	"""
	A wrapper class that provides parts of the legacy
	dbapi interface. Remove it once all consumers have
	died.
	"""
	def __init__(self, root, package_tracker):
		self._root = root
		self._package_tracker = package_tracker

	def cpv_inject(self, pkg):
		self._package_tracker.add_pkg(pkg)

	def match_pkgs(self, atom):
		ret = sorted(self._package_tracker.match(self._root, atom),
			key=cmp_sort_key(lambda x, y: vercmp(x.version, y.version)))
		return ret

	def __iter__(self):
		return self._package_tracker.all_pkgs(self._root)

	def match(self, atom, use_cache=None):
		return self.match_pkgs(atom)

	def cp_list(self, cp):
		return self.match_pkgs(Atom(cp))

# vim: ts=4 sw=4 noet tw=120
