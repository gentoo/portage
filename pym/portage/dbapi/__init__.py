# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["dbapi"]

import re

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.dbapi.dep_expand:dep_expand@_dep_expand',
	'portage.dep:Atom,match_from_list,_match_slot',
	'portage.output:colorize',
	'portage.util:cmp_sort_key,writemsg',
	'portage.versions:catsplit,catpkgsplit,vercmp,_pkg_str',
)

from portage import os
from portage import auxdbkeys
from portage.eapi import _get_eapi_attrs
from portage.exception import InvalidData
from portage.localization import _
from _emerge.Package import Package

class dbapi(object):
	_category_re = re.compile(r'^\w[-.+\w]*$', re.UNICODE)
	_categories = None
	_use_mutable = False
	_known_keys = frozenset(x for x in auxdbkeys
		if not x.startswith("UNUSED_0"))
	_pkg_str_aux_keys = ("EAPI", "KEYWORDS", "SLOT", "repository")

	def __init__(self):
		pass

	@property
	def categories(self):
		"""
		Use self.cp_all() to generate a category list. Mutable instances
		can delete the self._categories attribute in cases when the cached
		categories become invalid and need to be regenerated.
		"""
		if self._categories is not None:
			return self._categories
		self._categories = tuple(sorted(set(catsplit(x)[0] \
			for x in self.cp_all())))
		return self._categories

	def close_caches(self):
		pass

	def cp_list(self, cp, use_cache=1):
		raise NotImplementedError(self)

	@staticmethod
	def _cmp_cpv(cpv1, cpv2):
		return vercmp(cpv1.version, cpv2.version)

	@staticmethod
	def _cpv_sort_ascending(cpv_list):
		"""
		Use this to sort self.cp_list() results in ascending
		order. It sorts in place and returns None.
		"""
		if len(cpv_list) > 1:
			# If the cpv includes explicit -r0, it has to be preserved
			# for consistency in findname and aux_get calls, so use a
			# dict to map strings back to their original values.
			cpv_list.sort(key=cmp_sort_key(dbapi._cmp_cpv))

	def cpv_all(self):
		"""Return all CPVs in the db
		Args:
			None
		Returns:
			A list of Strings, 1 per CPV

		This function relies on a subclass implementing cp_all, this is why the hasattr is there
		"""

		if not hasattr(self, "cp_all"):
			raise NotImplementedError
		cpv_list = []
		for cp in self.cp_all():
			cpv_list.extend(self.cp_list(cp))
		return cpv_list

	def cp_all(self):
		""" Implement this in a child class
		Args
			None
		Returns:
			A list of strings 1 per CP in the datastore
		"""
		return NotImplementedError

	def aux_get(self, mycpv, mylist, myrepo=None):
		"""Return the metadata keys in mylist for mycpv
		Args:
			mycpv - "sys-apps/foo-1.0"
			mylist - ["SLOT","DEPEND","HOMEPAGE"]
			myrepo - The repository name.
		Returns: 
			a list of results, in order of keys in mylist, such as:
			["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		"""
		raise NotImplementedError
	
	def aux_update(self, cpv, metadata_updates):
		"""
		Args:
		  cpv - "sys-apps/foo-1.0"
			metadata_updates = { key : newvalue }
		Returns:
			None
		"""
		raise NotImplementedError

	def match(self, origdep, use_cache=1):
		"""Given a dependency, try to find packages that match
		Args:
			origdep - Depend atom
			use_cache - Boolean indicating if we should use the cache or not
			NOTE: Do we ever not want the cache?
		Returns:
			a list of packages that match origdep
		"""
		mydep = _dep_expand(origdep, mydb=self, settings=self.settings)
		return list(self._iter_match(mydep,
			self.cp_list(mydep.cp, use_cache=use_cache)))

	def _iter_match(self, atom, cpv_iter):
		cpv_iter = iter(match_from_list(atom, cpv_iter))
		if atom.repo:
			cpv_iter = self._iter_match_repo(atom, cpv_iter)
		if atom.slot:
			cpv_iter = self._iter_match_slot(atom, cpv_iter)
		if atom.unevaluated_atom.use:
			cpv_iter = self._iter_match_use(atom, cpv_iter)
		return cpv_iter

	def _pkg_str(self, cpv, repo):
		"""
		This is used to contruct _pkg_str instances on-demand during
		matching. If cpv is a _pkg_str instance with slot attribute,
		then simply return it. Otherwise, fetch metadata and construct
		a _pkg_str instance. This may raise KeyError or InvalidData.
		"""
		try:
			cpv.slot
		except AttributeError:
			pass
		else:
			return cpv

		metadata = dict(zip(self._pkg_str_aux_keys,
			self.aux_get(cpv, self._pkg_str_aux_keys, myrepo=repo)))

		return _pkg_str(cpv, metadata=metadata, settings=self.settings)

	def _iter_match_repo(self, atom, cpv_iter):
		for cpv in cpv_iter:
			try:
				pkg_str = self._pkg_str(cpv, atom.repo)
			except (KeyError, InvalidData):
				pass
			else:
				if pkg_str.repo == atom.repo:
					yield pkg_str

	def _iter_match_slot(self, atom, cpv_iter):
		for cpv in cpv_iter:
			try:
				pkg_str = self._pkg_str(cpv, atom.repo)
			except (KeyError, InvalidData):
				pass
			else:
				if _match_slot(atom, pkg_str):
					yield pkg_str

	def _iter_match_use(self, atom, cpv_iter):
		"""
		1) Check for required IUSE intersection (need implicit IUSE here).
		2) Check enabled/disabled flag states.
		"""

		aux_keys = ["EAPI", "IUSE", "KEYWORDS", "SLOT", "USE", "repository"]
		for cpv in cpv_iter:
			try:
				metadata = dict(zip(aux_keys,
					self.aux_get(cpv, aux_keys, myrepo=atom.repo)))
			except KeyError:
				continue

			if not self._match_use(atom, cpv, metadata):
				continue

			yield cpv

	def _match_use(self, atom, cpv, metadata):
		eapi_attrs = _get_eapi_attrs(metadata["EAPI"])
		if eapi_attrs.iuse_effective:
			iuse_implicit_match = self.settings._iuse_effective_match
		else:
			iuse_implicit_match = self.settings._iuse_implicit_match
		iuse = frozenset(x.lstrip('+-') for x in metadata["IUSE"].split())

		for x in atom.unevaluated_atom.use.required:
			if x not in iuse and not iuse_implicit_match(x):
				return False

		if atom.use is None:
			pass

		elif not self._use_mutable:
			# Use IUSE to validate USE settings for built packages,
			# in case the package manager that built this package
			# failed to do that for some reason (or in case of
			# data corruption).
			use = frozenset(x for x in metadata["USE"].split()
				if x in iuse or iuse_implicit_match(x))
			missing_enabled = atom.use.missing_enabled.difference(iuse)
			missing_disabled = atom.use.missing_disabled.difference(iuse)

			if atom.use.enabled:
				if any(x in atom.use.enabled for x in missing_disabled):
					return False
				need_enabled = atom.use.enabled.difference(use)
				if need_enabled:
					if any(x not in missing_enabled for x in need_enabled):
						return False

			if atom.use.disabled:
				if any(x in atom.use.disabled for x in missing_enabled):
					return False
				need_disabled = atom.use.disabled.intersection(use)
				if need_disabled:
					if any(x not in missing_disabled for x in need_disabled):
						return False

		elif not self.settings.local_config:
			# Check masked and forced flags for repoman.
			try:
				cpv.slot
			except AttributeError:
				pkg = _pkg_str(cpv, metadata=metadata, settings=self.settings)
			else:
				pkg = cpv
			usemask = self.settings._getUseMask(pkg)
			if any(x in usemask for x in atom.use.enabled):
				return False

			useforce = self.settings._getUseForce(pkg)
			if any(x in useforce and x not in usemask
				for x in atom.use.disabled):
				return False

			# Check unsatisfied use-default deps
			if atom.use.enabled:
				missing_disabled = atom.use.missing_disabled.difference(iuse)
				if any(x in atom.use.enabled for x in missing_disabled):
					return False
			if atom.use.disabled:
				missing_enabled = atom.use.missing_enabled.difference(iuse)
				if any(x in atom.use.disabled for x in missing_enabled):
					return False

		return True

	def invalidentry(self, mypath):
		if '/-MERGING-' in mypath:
			if os.path.exists(mypath):
				writemsg(colorize("BAD", _("INCOMPLETE MERGE:"))+" %s\n" % mypath,
					noiselevel=-1)
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath, noiselevel=-1)

	def update_ents(self, updates, onProgress=None, onUpdate=None):
		"""
		Update metadata of all packages for package moves.
		@param updates: A list of move commands, or dict of {repo_name: list}
		@type updates: list or dict
		@param onProgress: A progress callback function
		@type onProgress: a callable that takes 2 integer arguments: maxval and curval
		@param onUpdate: A progress callback function called only
			for packages that are modified by updates.
		@type onUpdate: a callable that takes 2 integer arguments:
			maxval and curval
		"""
		cpv_all = self.cpv_all()
		cpv_all.sort()
		maxval = len(cpv_all)
		aux_get = self.aux_get
		aux_update = self.aux_update
		meta_keys = Package._dep_keys + ("EAPI", "PROVIDE", "repository")
		repo_dict = None
		if isinstance(updates, dict):
			repo_dict = updates
		if onUpdate:
			onUpdate(maxval, 0)
		if onProgress:
			onProgress(maxval, 0)
		for i, cpv in enumerate(cpv_all):
			metadata = dict(zip(meta_keys, aux_get(cpv, meta_keys)))
			eapi = metadata.pop('EAPI')
			repo = metadata.pop('repository')
			if repo_dict is None:
				updates_list = updates
			else:
				try:
					updates_list = repo_dict[repo]
				except KeyError:
					try:
						updates_list = repo_dict['DEFAULT']
					except KeyError:
						continue

			if not updates_list:
				continue

			metadata_updates = \
				portage.update_dbentries(updates_list, metadata, eapi=eapi)
			if metadata_updates:
				aux_update(cpv, metadata_updates)
				if onUpdate:
					onUpdate(maxval, i+1)
			if onProgress:
				onProgress(maxval, i+1)

	def move_slot_ent(self, mylist, repo_match=None):
		"""This function takes a sequence:
		Args:
			mylist: a sequence of (atom, originalslot, newslot)
			repo_match: callable that takes single repo_name argument
				and returns True if the update should be applied
		Returns:
			The number of slotmoves this function did
		"""
		atom = mylist[1]
		origslot = mylist[2]
		newslot = mylist[3]

		try:
			atom.with_slot
		except AttributeError:
			atom = Atom(atom).with_slot(origslot)
		else:
			atom = atom.with_slot(origslot)

		origmatches = self.match(atom)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			try:
				mycpv = self._pkg_str(mycpv, atom.repo)
			except (KeyError, InvalidData):
				continue
			if repo_match is not None and not repo_match(mycpv.repo):
				continue
			moves += 1
			if "/" not in newslot and \
				mycpv.sub_slot and \
				mycpv.sub_slot not in (mycpv.slot, newslot):
				newslot = "%s/%s" % (newslot, mycpv.sub_slot)
			mydata = {"SLOT": newslot+"\n"}
			self.aux_update(mycpv, mydata)
		return moves
