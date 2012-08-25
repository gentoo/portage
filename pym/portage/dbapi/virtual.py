# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


from portage.dbapi import dbapi
from portage.dbapi.dep_expand import dep_expand
from portage.versions import cpv_getkey, _pkg_str

class fakedbapi(dbapi):
	"""A fake dbapi that allows consumers to inject/remove packages to/from it
	portage.settings is required to maintain the dbAPI.
	"""
	def __init__(self, settings=None, exclusive_slots=True):
		"""
		@param exclusive_slots: When True, injecting a package with SLOT
			metadata causes an existing package in the same slot to be
			automatically removed (default is True).
		@type exclusive_slots: Boolean
		"""
		self._exclusive_slots = exclusive_slots
		self.cpvdict = {}
		self.cpdict = {}
		if settings is None:
			from portage import settings
		self.settings = settings
		self._match_cache = {}

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
		return mycpv in self.cpvdict

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

	def cp_all(self):
		return list(self.cpdict)

	def cpv_all(self):
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
				mycpv = _pkg_str(mycpv)
			else:
				mycpv = _pkg_str(mycpv, metadata=metadata,
					settings=self.settings)

			mycp = mycpv.cp
			try:
				myslot = mycpv.slot
			except AttributeError:
				pass

		self.cpvdict[mycpv] = metadata
		if not self._exclusive_slots:
			myslot = None
		if myslot and mycp in self.cpdict:
			# If necessary, remove another package in the same SLOT.
			for cpv in self.cpdict[mycp]:
				if mycpv != cpv:
					try:
						other_slot = cpv.slot
					except AttributeError:
						pass
					else:
						if myslot == other_slot:
							self.cpv_remove(cpv)
							break

		cp_list = self.cpdict.get(mycp)
		if cp_list is None:
			cp_list = []
			self.cpdict[mycp] = cp_list
		try:
			cp_list.remove(mycpv)
		except ValueError:
			pass
		cp_list.append(mycpv)

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		self._clear_cache()
		mycp = cpv_getkey(mycpv)
		if mycpv in self.cpvdict:
			del	self.cpvdict[mycpv]
		if mycp not in self.cpdict:
			return
		while mycpv in self.cpdict[mycp]:
			del self.cpdict[mycp][self.cpdict[mycp].index(mycpv)]
		if not len(self.cpdict[mycp]):
			del self.cpdict[mycp]

	def aux_get(self, mycpv, wants, myrepo=None):
		if not self.cpv_exists(mycpv):
			raise KeyError(mycpv)
		metadata = self.cpvdict[mycpv]
		if not metadata:
			return ["" for x in wants]
		return [metadata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		self._clear_cache()
		self.cpvdict[cpv].update(values)

class testdbapi(object):
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
