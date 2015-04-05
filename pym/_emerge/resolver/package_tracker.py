# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import bisect
import collections

import portage
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
	"""
	This class tracks packages which are currently
	installed and packages which have been pulled into
	the dependency graph.

	It automatically tracks conflicts between packages.

	Possible conflicts:
		1) Packages that share the same SLOT.
		2) Packages with the same cpv.
		Not yet implemented:
		3) Packages that block each other.
	"""

	def __init__(self, soname_deps=False):
		"""
		@param soname_deps: enable soname match support
		@type soname_deps: bool
		"""
		# Mapping from package keys to set of packages.
		self._cp_pkg_map = collections.defaultdict(list)
		self._cp_vdb_pkg_map = collections.defaultdict(list)
		# List of package keys that may contain conflicts.
		# The insetation order must be preserved.
		self._multi_pkgs = []

		# Cache for result of conflicts().
		self._conflicts_cache = None

		# Records for each pulled package which installed package
		# are replaced.
		self._replacing = collections.defaultdict(list)
		# Records which pulled packages replace this package.
		self._replaced_by = collections.defaultdict(list)

		self._match_cache = collections.defaultdict(dict)
		if soname_deps:
			self._provides_index = collections.defaultdict(list)
		else:
			self._provides_index = None

	def add_pkg(self, pkg):
		"""
		Add a new package to the tracker. Records conflicts as necessary.
		"""
		cp_key = pkg.root, pkg.cp

		if any(other is pkg for other in self._cp_pkg_map[cp_key]):
			return

		self._cp_pkg_map[cp_key].append(pkg)

		if len(self._cp_pkg_map[cp_key]) > 1:
			self._conflicts_cache = None
			if len(self._cp_pkg_map[cp_key]) == 2:
				self._multi_pkgs.append(cp_key)

		self._replacing[pkg] = []
		for installed in self._cp_vdb_pkg_map.get(cp_key, []):
			if installed.slot_atom == pkg.slot_atom or \
				installed.cpv == pkg.cpv:
				self._replacing[pkg].append(installed)
				self._replaced_by[installed].append(pkg)

		self._add_provides(pkg)

		self._match_cache.pop(cp_key, None)

	def _add_provides(self, pkg):
		if (self._provides_index is not None and
			pkg.provides is not None):
			index = self._provides_index
			root = pkg.root
			for atom in pkg.provides:
				# Use bisect.insort for ordered match results.
				bisect.insort(index[(root, atom)], pkg)

	def add_installed_pkg(self, installed):
		"""
		Add an installed package during vdb load. These packages
		are not returned by matched_pull as long as add_pkg hasn't
		been called with them. They are only returned by match_final.
		"""
		cp_key = installed.root, installed.cp
		if any(other is installed for other in self._cp_vdb_pkg_map[cp_key]):
			return

		self._cp_vdb_pkg_map[cp_key].append(installed)

		for pkg in self._cp_pkg_map.get(cp_key, []):
			if installed.slot_atom == pkg.slot_atom or \
				installed.cpv == pkg.cpv:
				self._replacing[pkg].append(installed)
				self._replaced_by[installed].append(pkg)

		self._match_cache.pop(cp_key, None)

	def remove_pkg(self, pkg):
		"""
		Removes the package from the tracker.
		Raises KeyError if it isn't present.
		"""
		cp_key = pkg.root, pkg.cp
		try:
			self._cp_pkg_map.get(cp_key, []).remove(pkg)
		except ValueError:
			raise KeyError(pkg)

		if self._cp_pkg_map[cp_key]:
			self._conflicts_cache = None

		if not self._cp_pkg_map[cp_key]:
			del self._cp_pkg_map[cp_key]
		elif len(self._cp_pkg_map[cp_key]) == 1:
			self._multi_pkgs = [other_cp_key for other_cp_key in self._multi_pkgs \
			if other_cp_key != cp_key]

		for installed in self._replacing[pkg]:
			self._replaced_by[installed].remove(pkg)
			if not self._replaced_by[installed]:
				del self._replaced_by[installed]
		del self._replacing[pkg]

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

		self._match_cache.pop(cp_key, None)

	def discard_pkg(self, pkg):
		"""
		Removes the package from the tracker.
		Does not raises KeyError if it is not present.
		"""
		try:
			self.remove_pkg(pkg)
		except KeyError:
			pass

	def match(self, root, atom, installed=True):
		"""
		Iterates over the packages matching 'atom'.
		If 'installed' is True, installed non-replaced
		packages may also be returned.
		"""
		if atom.soname:
			return iter(self._provides_index.get((root, atom), []))

		cp_key = root, atom.cp
		cache_key = root, atom, atom.unevaluated_atom, installed
		try:
			return iter(self._match_cache.get(cp_key, {})[cache_key])
		except KeyError:
			pass

		candidates = self._cp_pkg_map.get(cp_key, [])[:]

		if installed:
			for installed in self._cp_vdb_pkg_map.get(cp_key, []):
				if installed not in self._replaced_by:
					candidates.append(installed)

		ret = match_from_list(atom, candidates)
		ret.sort(key=cmp_sort_key(lambda x, y: vercmp(x.version, y.version)))
		self._match_cache[cp_key][cache_key] = ret

		return iter(ret)

	def conflicts(self):
		"""
		Iterates over the curently existing conflicts.
		"""
		if self._conflicts_cache is None:
			self._conflicts_cache = []

			for cp_key in self._multi_pkgs:

				# Categorize packages according to cpv and slot.
				slot_map = collections.defaultdict(list)
				cpv_map = collections.defaultdict(list)
				for pkg in self._cp_pkg_map[cp_key]:
					slot_key = pkg.root, pkg.slot_atom
					cpv_key = pkg.root, pkg.cpv
					slot_map[slot_key].append(pkg)
					cpv_map[cpv_key].append(pkg)

				# Slot conflicts.
				for slot_key in slot_map:
					slot_pkgs = slot_map[slot_key]
					if len(slot_pkgs) > 1:
						self._conflicts_cache.append(PackageConflict(
							description = "slot conflict",
							root = slot_key[0],
							atom = slot_key[1],
							pkgs = tuple(slot_pkgs),
							))

				# CPV conflicts.
				for cpv_key in cpv_map:
					cpv_pkgs = cpv_map[cpv_key]
					if len(cpv_pkgs) > 1:
						# Make sure this cpv conflict is not a slot conflict at the same time.
						# Ignore it if it is.
						slots = set(pkg.slot for pkg in cpv_pkgs)
						if len(slots) > 1:
							self._conflicts_cache.append(PackageConflict(
								description = "cpv conflict",
								root = cpv_key[0],
								atom = cpv_key[1],
								pkgs = tuple(cpv_pkgs),
								))

		return iter(self._conflicts_cache)

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
		for cp_key in self._cp_pkg_map:
			if cp_key[0] == root:
				for pkg in self._cp_pkg_map[cp_key]:
					yield pkg

		for cp_key in self._cp_vdb_pkg_map:
			if cp_key[0] == root:
				for installed in self._cp_vdb_pkg_map[cp_key]:
					if installed not in self._replaced_by:
						yield installed

	def contains(self, pkg, installed=True):
		"""
		Checks if the package is in the tracker.
		If 'installed' is True, returns True for
		non-replaced installed packages.
		"""
		cp_key = pkg.root, pkg.cp
		for other in self._cp_pkg_map.get(cp_key, []):
			if other is pkg:
				return True

		if installed:
			for installed in self._cp_vdb_pkg_map.get(cp_key, []):
				if installed is pkg and \
					installed not in self._replaced_by:
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
	A wrpper class that provides parts of the legacy
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
