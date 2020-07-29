# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.dep import Atom
from portage.exception import InvalidData
from portage.versions import _pkg_str

class IndexedVardb:
	"""
	A vardbapi interface that sacrifices validation in order to
	improve performance. It takes advantage of vardbdbapi._aux_cache,
	which is backed by vdb_metadata.pickle. Since _aux_cache is
	not updated for every single merge/unmerge (see
	_aux_cache_threshold), the list of packages is obtained directly
	from the real vardbapi instance. If a package is missing from
	_aux_cache, then its metadata is obtained using the normal
	(validated) vardbapi.aux_get method.

	For performance reasons, the match method only supports package
	name and version constraints.
	"""

	# Match returns unordered results.
	match_unordered = True

	_copy_attrs = ('cpv_exists',
		'_aux_cache_keys', '_cpv_sort_ascending')

	def __init__(self, vardb):
		self._vardb = vardb

		for k in self._copy_attrs:
			setattr(self, k, getattr(vardb, k))

		self._cp_map = None

	def cp_all(self, sort=True):
		"""
		Returns an ordered iterator instead of a list, so that search
		results can be displayed incrementally.
		"""
		if self._cp_map is not None:
			return iter(sorted(self._cp_map)) if sort else iter(self._cp_map)

		delta_data = self._vardb._cache_delta.loadRace()
		if delta_data is None:
			return self._iter_cp_all()

		self._vardb._cache_delta.applyDelta(delta_data)

		self._cp_map = cp_map = {}
		for cpv in self._vardb._aux_cache["packages"]:
			try:
				cpv = _pkg_str(cpv, db=self._vardb)
			except InvalidData:
				continue

			cp_list = cp_map.get(cpv.cp)
			if cp_list is None:
				cp_list = []
				cp_map[cpv.cp] = cp_list
			cp_list.append(cpv)

		return iter(sorted(self._cp_map)) if sort else iter(self._cp_map)

	def _iter_cp_all(self):
		self._cp_map = cp_map = {}
		previous_cp = None
		for cpv in self._vardb._iter_cpv_all(sort = True):
			cp = portage.cpv_getkey(cpv)
			if cp is not None:
				cp_list = cp_map.get(cp)
				if cp_list is None:
					cp_list = []
					cp_map[cp] = cp_list
				cp_list.append(cpv)
				if previous_cp is not None and \
					previous_cp != cp:
					yield previous_cp
				previous_cp = cp

		if previous_cp is not None:
			yield previous_cp

	def match(self, atom):
		"""
		For performance reasons, only package name and version
		constraints are supported, and the returned list is
		unordered.
		"""
		if not isinstance(atom, Atom):
			atom = Atom(atom)
		cp_list = self._cp_map.get(atom.cp)
		if cp_list is None:
			return []

		if atom == atom.cp:
			return cp_list[:]
		return portage.match_from_list(atom, cp_list)

	def aux_get(self, cpv, attrs, myrepo=None):
		pkg_data = self._vardb._aux_cache["packages"].get(cpv)
		if not isinstance(pkg_data, tuple) or \
			len(pkg_data) != 2 or \
			not isinstance(pkg_data[1], dict):
			pkg_data = None
		if pkg_data is None:
			# It may be missing from _aux_cache due to
			# _aux_cache_threshold.
			return self._vardb.aux_get(cpv, attrs)
		metadata = pkg_data[1]
		return [metadata.get(k, "") for k in attrs]
