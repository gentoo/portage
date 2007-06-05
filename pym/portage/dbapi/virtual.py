# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


from portage.dbapi import dbapi

from portage import cpv_getkey

class fakedbapi(dbapi):
	"This is a dbapi to use for the emptytree function.  It's empty, but things can be added to it."
	def __init__(self, settings=None):
		self.cpvdict = {}
		self.cpdict = {}
		if settings is None:
			from portage import settings
		self.settings = settings
		self._match_cache = {}

	def _clear_cache(self):
		if self._match_cache:
			self._match_cache = {}

	def match(self, origdep, use_cache=1):
		result = self._match_cache.get(origdep, None)
		if result is not None:
			return result[:]
		result = dbapi.match(self, origdep, use_cache=use_cache)
		self._match_cache[origdep] = result
		return result[:]

	def cpv_exists(self, mycpv):
		return self.cpvdict.has_key(mycpv)

	def cp_list(self, mycp, use_cache=1):
		if not self.cpdict.has_key(mycp):
			return []
		else:
			return self.cpdict[mycp]

	def cp_all(self):
		returnme=[]
		for x in self.cpdict.keys():
			returnme.extend(self.cpdict[x])
		return returnme

	def cpv_all(self):
		return self.cpvdict.keys()

	def cpv_inject(self, mycpv, metadata=None):
		"""Adds a cpv from the list of available packages."""
		self._clear_cache()
		mycp = cpv_getkey(mycpv)
		self.cpvdict[mycpv] = metadata
		myslot = None
		if metadata:
			myslot = metadata.get("SLOT", None)
		if myslot and mycp in self.cpdict:
			# If necessary, remove another package in the same SLOT.
			for cpv in self.cpdict[mycp]:
				if mycpv != cpv:
					other_metadata = self.cpvdict[cpv]
					if other_metadata:
						if myslot == other_metadata.get("SLOT", None):
							self.cpv_remove(cpv)
							break
		if mycp not in self.cpdict:
			self.cpdict[mycp] = []
		if not mycpv in self.cpdict[mycp]:
			self.cpdict[mycp].append(mycpv)

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		self._clear_cache()
		mycp = cpv_getkey(mycpv)
		if self.cpvdict.has_key(mycpv):
			del	self.cpvdict[mycpv]
		if not self.cpdict.has_key(mycp):
			return
		while mycpv in self.cpdict[mycp]:
			del self.cpdict[mycp][self.cpdict[mycp].index(mycpv)]
		if not len(self.cpdict[mycp]):
			del self.cpdict[mycp]

	def aux_get(self, mycpv, wants):
		if not self.cpv_exists(mycpv):
			raise KeyError(mycpv)
		metadata = self.cpvdict[mycpv]
		if not metadata:
			return ["" for x in wants]
		return [metadata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		self._clear_cache()
		self.cpvdict[cpv].update(values)
