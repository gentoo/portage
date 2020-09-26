# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import functools
import operator
import os

import portage
from portage import _encodings
from portage.dep import Atom
from portage.exception import FileNotFound
from portage.cache.index.IndexStreamIterator import IndexStreamIterator
from portage.cache.index.pkg_desc_index import \
	pkg_desc_index_line_read, pkg_desc_index_node
from portage.util.iterators.MultiIterGroupBy import MultiIterGroupBy

class IndexedPortdb:
	"""
	A portdbapi interface that uses a package description index to
	improve performance. If the description index is missing for a
	particular repository, then all metadata for that repository is
	obtained using the normal pordbapi.aux_get method.

	For performance reasons, the match method only supports package
	name and version constraints. For the same reason, the xmatch
	method is not implemented.
	"""

	# Match returns unordered results.
	match_unordered = True

	_copy_attrs = ('cpv_exists', 'findname', 'getFetchMap',
		'_aux_cache_keys', '_cpv_sort_ascending',
		'_have_root_eclass_dir')

	def __init__(self, portdb):

		self._portdb = portdb

		for k in self._copy_attrs:
			setattr(self, k, getattr(portdb, k))

		self._desc_cache = None
		self._cp_map = None
		self._unindexed_cp_map = None

	def _init_index(self):

		cp_map = {}
		desc_cache = {}
		self._desc_cache = desc_cache
		self._cp_map = cp_map
		index_missing = []

		streams = []
		for repo_path in self._portdb.porttrees:
			outside_repo = os.path.join(self._portdb.depcachedir,
				repo_path.lstrip(os.sep))
			filenames = []
			for parent_dir in (repo_path, outside_repo):
				filenames.append(os.path.join(parent_dir,
					"metadata", "pkg_desc_index"))

			repo_name = self._portdb.getRepositoryName(repo_path)

			try:
				f = None
				for filename in filenames:
					try:
						f = io.open(filename,
							encoding=_encodings["repo.content"])
					except IOError as e:
						if e.errno not in (errno.ENOENT, errno.ESTALE):
							raise
					else:
						break

				if f is None:
					raise FileNotFound(filename)

				streams.append(iter(IndexStreamIterator(f,
					functools.partial(pkg_desc_index_line_read,
					repo = repo_name))))
			except FileNotFound:
				index_missing.append(repo_path)

		if index_missing:
			self._unindexed_cp_map = {}

			class _NonIndexedStream:
				def __iter__(self_):
					for cp in self._portdb.cp_all(
						trees = index_missing):
						# Don't call cp_list yet, since it's a waste
						# if the package name does not match the current
						# search.
						self._unindexed_cp_map[cp] = index_missing
						yield pkg_desc_index_node(cp, (), None)

			streams.append(iter(_NonIndexedStream()))

		if streams:
			if len(streams) == 1:
				cp_group_iter = ([node] for node in streams[0])
			else:
				cp_group_iter = MultiIterGroupBy(streams,
					key = operator.attrgetter("cp"))

			for cp_group in cp_group_iter:

				new_cp = None
				cp_list = cp_map.get(cp_group[0].cp)
				if cp_list is None:
					new_cp = cp_group[0].cp
					cp_list = []
					cp_map[cp_group[0].cp] = cp_list

				for entry in cp_group:
					cp_list.extend(entry.cpv_list)
					if entry.desc is not None:
						for cpv in entry.cpv_list:
							desc_cache[cpv] = entry.desc

				if new_cp is not None:
					yield cp_group[0].cp

	def cp_all(self, sort=True):
		"""
		Returns an ordered iterator instead of a list, so that search
		results can be displayed incrementally.
		"""
		if self._cp_map is None:
			return self._init_index()
		return iter(sorted(self._cp_map)) if sort else iter(self._cp_map)

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

		if self._unindexed_cp_map is not None:
			try:
				unindexed = self._unindexed_cp_map.pop(atom.cp)
			except KeyError:
				pass
			else:
				cp_list.extend(self._portdb.cp_list(atom.cp,
					mytree=unindexed))

		if atom == atom.cp:
			return cp_list[:]
		return portage.match_from_list(atom, cp_list)

	def aux_get(self, cpv, attrs, myrepo=None):
		if len(attrs) == 1 and attrs[0] == "DESCRIPTION":
			try:
				return [self._desc_cache[cpv]]
			except KeyError:
				pass
		return self._portdb.aux_get(cpv, attrs)
