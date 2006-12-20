# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import time
if not hasattr(__builtins__, "set"):
	from sets import Set as set
from cache import template
from cache.cache_errors import CacheCorruption
from cache.flat_hash import database as db_rw
from cache.metadata import database as db_ro

class database(template.database):

	autocommits = True
	serialize_eclasses = False

	def __init__(self, location, label, auxdbkeys, db_rw=db_rw, db_ro=db_ro,
		**config):
		super(database, self).__init__(location, label, auxdbkeys)
		self.db_rw = db_rw(location, label, auxdbkeys, **config)
		self.db_ro = db_ro(label,"metadata/cache",auxdbkeys)

	def __getitem__(self, cpv):
		"""funnel whiteout validation through here, since value needs to be fetched"""
		try:
			value = self.db_rw[cpv]
		except KeyError:
			return self.db_ro[cpv] # raises a KeyError when necessary
		except CacheCorruption:
			del self.db_rw[cpv]
			return self.db_ro[cpv] # raises a KeyError when necessary
		if self._is_whiteout(value):
			if self._is_whiteout_valid(cpv, value):
				raise KeyError(cpv)
			else:
				del self.db_rw[cpv]
				return self.db_ro[cpv] # raises a KeyError when necessary
		else:
			return value

	def _setitem(self, name, values):
		value_ro = self.db_ro.get(name, None)
		if value_ro is not None and \
			self._are_values_identical(value_ro, values):
			# we have matching values in the underlying db_ro
			# so it is unnecessary to store data in db_rw
			try:
				del self.db_rw[name] # delete unwanted whiteout when necessary
			except KeyError:
				pass
			return
		self.db_rw[name] = values

	def _delitem(self, cpv):
		value = self[cpv] # validates whiteout and/or raises a KeyError when necessary
		if self.db_ro.has_key(cpv):
			self.db_rw[cpv] = self._create_whiteout(value)
		else:
			del self.db_rw[cpv]

	def __contains__(self, cpv):
		try:
			self[cpv] # validates whiteout when necessary
		except KeyError:
			return False
		return True

	def iterkeys(self):
		s = set()
		for cpv in self.db_rw.iterkeys():
			if self.has_key(cpv): # validates whiteout when necessary
				yield cpv
			# set includes whiteouts so they won't be yielded later
			s.add(cpv)
		for cpv in self.db_ro.iterkeys():
			if cpv not in s:
				yield cpv

	def _is_whiteout(self, value):
		return value["EAPI"] == "whiteout"

	def _create_whiteout(self, value):
		return {"EAPI":"whiteout","_eclasses_":value["_eclasses_"],"_mtime_":value["_mtime_"]}

	def _is_whiteout_valid(self, name, value_rw):
		try:
			value_ro = self.db_ro[name]
			return self._are_values_identical(value_rw,value_ro)
		except KeyError:
			return False

	def _are_values_identical(self, value1, value2):
		if long(value1["_mtime_"]) != long(value2["_mtime_"]):
			return False
		return value1["_eclasses_"] == value2["_eclasses_"]
