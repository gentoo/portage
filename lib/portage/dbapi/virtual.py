# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dbapi import dbapi
from portage.dbapi.dep_expand import dep_expand
from portage.versions import cpv_getkey, _pkg_str

class fakedbapi(dbapi):
	"""A fake dbapi that allows consumers to inject/remove packages to/from it
	portage.settings is required to maintain the dbAPI.
	"""
	def __init__(self, settings=None, exclusive_slots=True,
		multi_instance=False):
		"""
		@param exclusive_slots: When True, injecting a package with SLOT
			metadata causes an existing package in the same slot to be
			automatically removed (default is True).
		@type exclusive_slots: Boolean
		@param multi_instance: When True, multiple instances with the
			same cpv may be stored simultaneously, as long as they are
			distinguishable (default is False).
		@type multi_instance: Boolean
		"""
		self._exclusive_slots = exclusive_slots
		self.cpvdict = {}
		self.cpdict = {}
		if settings is None:
			from portage import settings
		self.settings = settings
		self._match_cache = {}
		self._set_multi_instance(multi_instance)

	def _set_multi_instance(self, multi_instance):
		"""
		Enable or disable multi_instance mode. This should before any
		packages are injected, so that all packages are indexed with
		the same implementation of self._instance_key.
		"""
		if self.cpvdict:
			raise AssertionError("_set_multi_instance called after "
				"packages have already been added")
		self._multi_instance = multi_instance
		if multi_instance:
			self._instance_key = self._instance_key_multi_instance
		else:
			self._instance_key = self._instance_key_cpv

	def _instance_key_cpv(self, cpv, support_string=False):
		return cpv

	def _instance_key_multi_instance(self, cpv, support_string=False):
		try:
			return (cpv, cpv.build_id, cpv.file_size, cpv.build_time,
				cpv.mtime)
		except AttributeError:
			if not support_string:
				raise

		# Fallback for interfaces such as aux_get where API consumers
		# may pass in a plain string.
		latest = None
		for pkg in self.cp_list(cpv_getkey(cpv)):
			if pkg == cpv and (
				latest is None or
				latest.build_time < pkg.build_time):
				latest = pkg

		if latest is not None:
			return (latest, latest.build_id, latest.file_size,
				latest.build_time, latest.mtime)

		raise KeyError(cpv)

	def clear(self):
		"""
		Remove all packages.
		"""
		self._clear_cache()
		self.cpvdict.clear()
		self.cpdict.clear()

	def _clear_cache(self):
		if self._categories is not None:
			self._categories = None
		if self._match_cache:
			self._match_cache = {}

	def match(self, origdep, use_cache=1):
		atom = dep_expand(origdep, mydb=self, settings=self.settings)
		cache_key = (atom, atom.unevaluated_atom)
		result = self._match_cache.get(cache_key)
		if result is not None:
			return result[:]
		result = list(self._iter_match(atom, self.cp_list(atom.cp)))
		self._match_cache[cache_key] = result
		return result[:]

	def cpv_exists(self, mycpv, myrepo=None):
		try:
			return self._instance_key(mycpv,
				support_string=True) in self.cpvdict
		except KeyError:
			# _instance_key failure
			return False

	def cp_list(self, mycp, use_cache=1, myrepo=None):
		# NOTE: Cache can be safely shared with the match cache, since the
		# match cache uses the result from dep_expand for the cache_key.
		cache_key = (mycp, mycp)
		cachelist = self._match_cache.get(cache_key)
		if cachelist is not None:
			return cachelist[:]
		cpv_list = self.cpdict.get(mycp)
		if cpv_list is None:
			cpv_list = []
		self._cpv_sort_ascending(cpv_list)
		self._match_cache[cache_key] = cpv_list
		return cpv_list[:]

	def cp_all(self, sort=False):
		return sorted(self.cpdict) if sort else list(self.cpdict)

	def cpv_all(self):
		if self._multi_instance:
			return [x[0] for x in self.cpvdict]
		return list(self.cpvdict)

	def cpv_inject(self, mycpv, metadata=None):
		"""Adds a cpv to the list of available packages. See the
		exclusive_slots constructor parameter for behavior with
		respect to SLOT metadata.
		@param mycpv: cpv for the package to inject
		@type mycpv: str
		@param metadata: dictionary of raw metadata for aux_get() calls
		@param metadata: dict
		"""
		self._clear_cache()

		try:
			mycp = mycpv.cp
		except AttributeError:
			mycp = None
		try:
			myslot = mycpv.slot
		except AttributeError:
			myslot = None

		if mycp is None or \
			(myslot is None and metadata is not None and metadata.get('SLOT')):
			if metadata is None:
				mycpv = _pkg_str(mycpv, db=self)
			else:
				mycpv = _pkg_str(mycpv, metadata=metadata,
					settings=self.settings, db=self)

			mycp = mycpv.cp
			try:
				myslot = mycpv.slot
			except AttributeError:
				pass

		instance_key = self._instance_key(mycpv)
		self.cpvdict[instance_key] = metadata
		if not self._exclusive_slots:
			myslot = None
		if myslot and mycp in self.cpdict:
			# If necessary, remove another package in the same SLOT.
			for cpv in self.cpdict[mycp]:
				if instance_key != self._instance_key(cpv):
					try:
						other_slot = cpv.slot
					except AttributeError:
						pass
					else:
						if myslot == other_slot:
							self.cpv_remove(cpv)
							break

		cp_list = self.cpdict.get(mycp, [])
		cp_list = [x for x in cp_list
			if self._instance_key(x) != instance_key]
		cp_list.append(mycpv)
		self.cpdict[mycp] = cp_list

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		self._clear_cache()
		mycp = cpv_getkey(mycpv)
		instance_key = self._instance_key(mycpv)
		self.cpvdict.pop(instance_key, None)
		cp_list = self.cpdict.get(mycp)
		if cp_list is not None:
			cp_list = [x for x in cp_list
				if self._instance_key(x) != instance_key]
			if cp_list:
				self.cpdict[mycp] = cp_list
			else:
				del self.cpdict[mycp]

	def aux_get(self, mycpv, wants, myrepo=None):
		metadata = self.cpvdict.get(
			self._instance_key(mycpv, support_string=True))
		if metadata is None:
			raise KeyError(mycpv)
		return [metadata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		self._clear_cache()
		metadata = self.cpvdict.get(
			self._instance_key(cpv, support_string=True))
		if metadata is None:
			raise KeyError(cpv)
		metadata.update(values)

class testdbapi:
	"""A dbapi instance with completely fake functions to get by hitting disk
	TODO(antarus):
	This class really needs to be rewritten to have better stubs; but these work for now.
	The dbapi classes themselves need unit tests...and that will be a lot of work.
	"""

	def __init__(self):
		self.cpvs = {}
		def f(*args, **kwargs):
			return True
		fake_api = dir(dbapi)
		for call in fake_api:
			if not hasattr(self, call):
				setattr(self, call, f)
