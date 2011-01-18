# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["dbapi"]

import re

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.dbapi.dep_expand:dep_expand@_dep_expand',
	'portage.dep:match_from_list',
	'portage.output:colorize',
	'portage.util:cmp_sort_key,writemsg',
	'portage.versions:catsplit,catpkgsplit,vercmp',
)

from portage import os
from portage import auxdbkeys
from portage.localization import _

class dbapi(object):
	_category_re = re.compile(r'^\w[-.+\w]*$')
	_categories = None
	_use_mutable = False
	_known_keys = frozenset(x for x in auxdbkeys
		if not x.startswith("UNUSED_0"))
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

	def _cpv_sort_ascending(self, cpv_list):
		"""
		Use this to sort self.cp_list() results in ascending
		order. It sorts in place and returns None.
		"""
		if len(cpv_list) > 1:
			# If the cpv includes explicit -r0, it has to be preserved
			# for consistency in findname and aux_get calls, so use a
			# dict to map strings back to their original values.
			ver_map = {}
			for cpv in cpv_list:
				ver_map[cpv] = '-'.join(catpkgsplit(cpv)[2:])
			def cmp_cpv(cpv1, cpv2):
				return vercmp(ver_map[cpv1], ver_map[cpv2])
			cpv_list.sort(key=cmp_sort_key(cmp_cpv))

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

	def _iter_match(self, atom, cpv_iter, myrepo=None):
		cpv_iter = iter(match_from_list(atom, cpv_iter))
		if atom.slot:
			cpv_iter = self._iter_match_slot(atom, cpv_iter, myrepo)
		if atom.unevaluated_atom.use:
			cpv_iter = self._iter_match_use(atom, cpv_iter, myrepo)
		if atom.repo:
			cpv_iter = self._iter_match_repo(atom, cpv_iter, myrepo)
		return cpv_iter

	def _iter_match_repo(self, atom, cpv_iter, myrepo=None):
		for cpv in cpv_iter:
			try:
				if self.aux_get(cpv, ["repository"], myrepo=myrepo)[0] == atom.repo:
					yield cpv
			except KeyError:
				continue

	def _iter_match_slot(self, atom, cpv_iter, myrepo=None):
		for cpv in cpv_iter:
			try:
				if self.aux_get(cpv, ["SLOT"], myrepo=myrepo)[0] == atom.slot:
					yield cpv
			except KeyError:
				continue

	def _iter_match_use(self, atom, cpv_iter, myrepo = None):
		"""
		1) Check for required IUSE intersection (need implicit IUSE here).
		2) Check enabled/disabled flag states.
		"""

		iuse_implicit_match = self.settings._iuse_implicit_match
		for cpv in cpv_iter:
			try:
				iuse, slot, use = self.aux_get(cpv, ["IUSE", "SLOT", "USE"], myrepo=myrepo)
			except KeyError:
				continue
			iuse = frozenset(x.lstrip('+-') for x in iuse.split())
			missing_iuse = False
			for x in atom.unevaluated_atom.use.required:
				if x not in iuse and not iuse_implicit_match(x):
					missing_iuse = True
					break
			if missing_iuse:
				continue
			if not atom.use:
				pass
			elif not self._use_mutable:
				# Use IUSE to validate USE settings for built packages,
				# in case the package manager that built this package
				# failed to do that for some reason (or in case of
				# data corruption).
				use = frozenset(x for x in use.split() if x in iuse or \
					iuse_implicit_match(x))
				missing_enabled = atom.use.missing_enabled.difference(iuse)
				missing_disabled = atom.use.missing_disabled.difference(iuse)

				if atom.use.enabled:
					if atom.use.enabled.intersection(missing_disabled):
						continue
					need_enabled = atom.use.enabled.difference(use)
					if need_enabled:
						need_enabled = need_enabled.difference(missing_enabled)
						if need_enabled:
							continue

				if atom.use.disabled:
					if atom.use.disabled.intersection(missing_enabled):
						continue
					need_disabled = atom.use.disabled.intersection(use)
					if need_disabled:
						need_disabled = need_disabled.difference(missing_disabled)
						if need_disabled:
							continue
			else:
				# Check masked and forced flags for repoman.
				mysettings = getattr(self, 'settings', None)
				if mysettings is not None and not mysettings.local_config:

					pkg = "%s:%s" % (cpv, slot)
					usemask = mysettings._getUseMask(pkg)
					if usemask.intersection(atom.use.enabled):
						continue

					useforce = mysettings._getUseForce(pkg).difference(usemask)
					if useforce.intersection(atom.use.disabled):
						continue

			yield cpv

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
		meta_keys = ["DEPEND", "RDEPEND", "PDEPEND", "PROVIDE", 'repository']
		repo_dict = None
		if isinstance(updates, dict):
			repo_dict = updates
		from portage.update import update_dbentries
		if onUpdate:
			onUpdate(maxval, 0)
		if onProgress:
			onProgress(maxval, 0)
		for i, cpv in enumerate(cpv_all):
			metadata = dict(zip(meta_keys, aux_get(cpv, meta_keys)))
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

			metadata_updates = update_dbentries(updates_list, metadata)
			if metadata_updates:
				aux_update(cpv, metadata_updates)
				if onUpdate:
					onUpdate(maxval, i+1)
			if onProgress:
				onProgress(maxval, i+1)

	def move_slot_ent(self, mylist, repo_match=None):
		"""This function takes a sequence:
		Args:
			mylist: a sequence of (package, originalslot, newslot)
			repo_match: callable that takes single repo_name argument
				and returns True if the update should be applied
		Returns:
			The number of slotmoves this function did
		"""
		pkg = mylist[1]
		origslot = mylist[2]
		newslot = mylist[3]
		origmatches = self.match(pkg)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			slot = self.aux_get(mycpv, ["SLOT"])[0]
			if slot != origslot:
				continue
			if repo_match is not None \
				and not repo_match(self.aux_get(mycpv, ['repository'])[0]):
				continue
			moves += 1
			mydata = {"SLOT": newslot+"\n"}
			self.aux_update(mycpv, mydata)
		return moves
