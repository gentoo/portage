# Copyright 2015-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import bisect
import collections

class DbapiProvidesIndex:
	"""
	The DbapiProvidesIndex class is used to wrap existing dbapi
	interfaces, index packages by the sonames that they provide, and
	implement the dbapi.match method for SonameAtom instances. Since
	this class acts as a wrapper, it can be used conditionally, so that
	soname indexing overhead is avoided when soname dependency
	resolution is disabled.

	Since it's possible for soname atom match results to consist of
	packages with multiple categories or names, it is essential that
	Package.__lt__ behave meaningfully when Package.cp is dissimilar,
	so that match results will be correctly ordered by version for each
	value of Package.cp.
	"""

	_copy_attrs = ('aux_get', 'aux_update', 'categories', 'cpv_all',
		'cpv_exists', 'cp_all', 'cp_list', 'getfetchsizes',
		'settings', '_aux_cache_keys', '_clear_cache',
		'_cpv_sort_ascending', '_iuse_implicit_cnstr', '_pkg_str',
		'_pkg_str_aux_keys')

	def __init__(self, db):
		self._db = db
		for k in self._copy_attrs:
			try:
				setattr(self, k, getattr(db, k))
			except AttributeError:
				pass
		self._provides_index = collections.defaultdict(list)

	def match(self, atom, use_cache=DeprecationWarning):
		if atom.soname:
			result = self._match_soname(atom)
		else:
			result = self._db.match(atom)
		return result

	def _match_soname(self, atom):
		result = self._provides_index.get(atom)
		if result is None:
			result = []
		else:
			result = [pkg.cpv for pkg in result]
		return result

	def _provides_inject(self, pkg):
		index = self._provides_index
		for atom in pkg.provides:
			# Use bisect.insort for ordered match results.
			bisect.insort(index[atom], pkg)

class PackageDbapiProvidesIndex(DbapiProvidesIndex):
	"""
	This class extends DbapiProvidesIndex in order to make it suitable
	for wrapping a PackageVirtualDbapi instance.
	"""

	_copy_attrs = DbapiProvidesIndex._copy_attrs + (
		"clear", "get", "_cpv_map")

	def clear(self):
		self._db.clear()
		self._provides_index.clear()

	def __bool__(self):
		return bool(self._db)

	def __iter__(self):
		return iter(self._db)

	def __contains__(self, item):
		return item in self._db

	def match_pkgs(self, atom):
		return [self._db._cpv_map[cpv] for cpv in self.match(atom)]

	def cpv_inject(self, pkg):
		self._db.cpv_inject(pkg)
		self._provides_inject(pkg)

	def cpv_remove(self, pkg):
		self._db.cpv_remove(pkg)
		index = self._provides_index
		for atom in pkg.provides:
			items = index[atom]
			try:
				items.remove(pkg)
			except ValueError:
				pass
			if not items:
				del index[atom]
