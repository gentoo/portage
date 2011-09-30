# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2

from portage.cache import cache_errors
from portage.cache.cache_errors import InvalidRestriction
from portage.cache.mappings import ProtectedDict
import sys
import warnings

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int

class database(object):
	# this is for metadata/cache transfer.
	# basically flags the cache needs be updated when transfered cache to cache.
	# leave this.

	complete_eclass_entries = True
	autocommits = False
	cleanse_keys = False
	serialize_eclasses = True

	def __init__(self, location, label, auxdbkeys, readonly=False):
		""" initialize the derived class; specifically, store label/keys"""
		self._known_keys = auxdbkeys
		self.location = location
		self.label = label
		self.readonly = readonly
		self.sync_rate = 0
		self.updates = 0
		self.is_authorative = False
	
	def __getitem__(self, cpv):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the __eclasses__ conversion.
		that said, if the class handles it, they can override it."""
		if self.updates > self.sync_rate:
			self.commit()
			self.updates = 0
		d=self._getitem(cpv)
		if self.serialize_eclasses and "_eclasses_" in d:
			d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"])
		elif "_eclasses_" not in d:
			d["_eclasses_"] = {}
		mtime = d.get('_mtime_')
		if mtime is None:
			raise cache_errors.CacheCorruption(cpv,
				'_mtime_ field is missing')
		try:
			mtime = long(mtime)
		except ValueError:
			raise cache_errors.CacheCorruption(cpv,
				'_mtime_ conversion to long failed: %s' % (mtime,))
		d['_mtime_'] = mtime
		return d

	def _getitem(self, cpv):
		"""get cpv's values.
		override this in derived classess"""
		raise NotImplementedError

	def __setitem__(self, cpv, values):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		if self.cleanse_keys:
			d=ProtectedDict(values)
			for k, v in list(d.items()):
				if not v:
					del d[k]
			if self.serialize_eclasses and "_eclasses_" in values:
				d["_eclasses_"] = serialize_eclasses(d["_eclasses_"])
		elif self.serialize_eclasses and "_eclasses_" in values:
			d = ProtectedDict(values)
			d["_eclasses_"] = serialize_eclasses(d["_eclasses_"])
		else:
			d = values
		self._setitem(cpv, d)
		if not self.autocommits:
			self.updates += 1
			if self.updates > self.sync_rate:
				self.commit()
				self.updates = 0

	def _setitem(self, name, values):
		"""__setitem__ calls this after readonly checks.  override it in derived classes
		note _eclassees_ key *must* be handled"""
		raise NotImplementedError

	def __delitem__(self, cpv):
		"""delete a key from the cache.
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		if not self.autocommits:
			self.updates += 1
		self._delitem(cpv)
		if self.updates > self.sync_rate:
			self.commit()
			self.updates = 0

	def _delitem(self,cpv):
		"""__delitem__ calls this after readonly checks.  override it in derived classes"""
		raise NotImplementedError

	def has_key(self, cpv):
		return cpv in self

	def keys(self):
		return list(self)

	def iterkeys(self):
		return iter(self)

	def iteritems(self):
		for x in self:
			yield (x, self[x])

	def items(self):
		return list(self.iteritems())

	def sync(self, rate=0):
		self.sync_rate = rate
		if(rate == 0):
			self.commit()

	def commit(self):
		if not self.autocommits:
			raise NotImplementedError

	def __contains__(self, cpv):
		"""This method should always be overridden.  It is provided only for
		backward compatibility with modules that override has_key instead.  It
		will automatically raise a NotImplementedError if has_key has not been
		overridden."""
		if self.has_key is database.has_key:
			# prevent a possible recursive loop
			raise NotImplementedError
		warnings.warn("portage.cache.template.database.has_key() is "
			"deprecated, override __contains__ instead",
			DeprecationWarning)
		return self.has_key(cpv)

	def __iter__(self):
		"""This method should always be overridden.  It is provided only for
		backward compatibility with modules that override iterkeys instead.  It
		will automatically raise a NotImplementedError if iterkeys has not been
		overridden."""
		if self.iterkeys is database.iterkeys:
			# prevent a possible recursive loop
			raise NotImplementedError(self)
		return iter(self.keys())

	def get(self, k, x=None):
		try:
			return self[k]
		except KeyError:
			return x

	def get_matches(self, match_dict):
		"""generic function for walking the entire cache db, matching restrictions to
		filter what cpv's are returned.  Derived classes should override this if they
		can implement a faster method then pulling each cpv:values, and checking it.
		
		For example, RDBMS derived classes should push the matching logic down to the
		actual RDBM."""

		import re
		restricts = {}
		for key,match in match_dict.items():
			# XXX this sucks.
			try:
				if isinstance(match, basestring):
					restricts[key] = re.compile(match).match
				else:
					restricts[key] = re.compile(match[0],match[1]).match
			except re.error as e:
				raise InvalidRestriction(key, match, e)
			if key not in self.__known_keys:
				raise InvalidRestriction(key, match, "Key isn't valid")

		for cpv in self:
			cont = True
			vals = self[cpv]
			for key, match in restricts.items():
				if not match(vals[key]):
					cont = False
					break
			if cont:
				yield cpv

	if sys.hexversion >= 0x3000000:
		keys = __iter__
		items = iteritems

def serialize_eclasses(eclass_dict):
	"""takes a dict, returns a string representing said dict"""
	"""The "new format", which causes older versions of <portage-2.1.2 to
	traceback with a ValueError due to failed long() conversion.  This format
	isn't currently written, but the the capability to read it is already built
	in.
	return "\t".join(["%s\t%s" % (k, str(v)) \
		for k, v in eclass_dict.iteritems()])
	"""
	if not eclass_dict:
		return ""
	return "\t".join(k + "\t%s\t%s" % eclass_dict[k] \
		for k in sorted(eclass_dict))

def reconstruct_eclasses(cpv, eclass_string):
	"""returns a dict when handed a string generated by serialize_eclasses"""
	eclasses = eclass_string.rstrip().lstrip().split("\t")
	if eclasses == [""]:
		# occasionally this occurs in the fs backends.  they suck.
		return {}
	
	if len(eclasses) % 2 != 0 and len(eclasses) % 3 != 0:
		raise cache_errors.CacheCorruption(cpv, "_eclasses_ was of invalid len %i" % len(eclasses))
	d={}
	try:
		if eclasses[1].isdigit():
			for x in range(0, len(eclasses), 2):
				d[eclasses[x]] = ("", long(eclasses[x + 1]))
		else:
			# The old format contains paths that will be discarded.
			for x in range(0, len(eclasses), 3):
				d[eclasses[x]] = (eclasses[x + 1], long(eclasses[x + 2]))
	except IndexError:
		raise cache_errors.CacheCorruption(cpv,
			"_eclasses_ was of invalid len %i" % len(eclasses))
	except ValueError:
		raise cache_errors.CacheCorruption(cpv, "_eclasses_ mtime conversion to long failed")
	del eclasses
	return d
