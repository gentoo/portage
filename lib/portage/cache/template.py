# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

from portage.cache import cache_errors
from portage.cache.cache_errors import InvalidRestriction
from portage.cache.mappings import ProtectedDict
import warnings
import operator


class database:
	# this is for metadata/cache transfer.
	# basically flags the cache needs be updated when transfered cache to cache.
	# leave this.

	complete_eclass_entries = True
	autocommits = False
	cleanse_keys = False
	serialize_eclasses = True
	validation_chf = 'mtime'
	store_eclass_paths = True

	def __init__(self, location, label, auxdbkeys, readonly=False):
		""" initialize the derived class; specifically, store label/keys"""
		self._known_keys = auxdbkeys
		self.location = location
		self.label = label
		self.readonly = readonly
		self.sync_rate = 0
		self.updates = 0

	def __getitem__(self, cpv):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the __eclasses__ conversion.
		that said, if the class handles it, they can override it."""
		if self.updates > self.sync_rate:
			self.commit()
			self.updates = 0
		d=self._getitem(cpv)

		try:
			chf_types = self.chf_types
		except AttributeError:
			chf_types = (self.validation_chf,)

		if self.serialize_eclasses and "_eclasses_" in d:
			for chf_type in chf_types:
				if '_%s_' % chf_type not in d:
					# Skip the reconstruct_eclasses call, since it's
					# a waste of time if it contains a different chf_type
					# than the current one. In the past, it was possible
					# for reconstruct_eclasses called with chf_type='md5'
					# to "successfully" return invalid data here, because
					# it was unable to distinguish between md5 data and
					# mtime data.
					continue
				try:
					d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"],
						chf_type, paths=self.store_eclass_paths)
				except cache_errors.CacheCorruption:
					if chf_type is chf_types[-1]:
						raise
				else:
					break
			else:
				raise cache_errors.CacheCorruption(cpv,
					'entry does not contain a recognized chf_type')

		elif "_eclasses_" not in d:
			d["_eclasses_"] = {}
		# Never return INHERITED, since portdbapi.aux_get() will
		# generate it automatically from _eclasses_, and we want
		# to omit it in comparisons between cache entries like
		# those that egencache uses to avoid redundant writes.
		d.pop("INHERITED", None)

		mtime_required = not any(d.get('_%s_' % x)
			for x in chf_types if x != 'mtime')

		mtime = d.get('_mtime_')
		if not mtime:
			if mtime_required:
				raise cache_errors.CacheCorruption(cpv,
					'_mtime_ field is missing')
			d.pop('_mtime_', None)
		else:
			try:
				mtime = int(mtime)
			except ValueError:
				raise cache_errors.CacheCorruption(cpv,
					'_mtime_ conversion to int failed: %s' % (mtime,))
			d['_mtime_'] = mtime
		return d

	def _getitem(self, cpv):
		"""get cpv's values.
		override this in derived classess"""
		raise NotImplementedError

	@staticmethod
	def _internal_eclasses(extern_ec_dict, chf_type, paths):
		"""
		When serialize_eclasses is False, we have to convert an external
		eclass dict containing hashed_path objects into an appropriate
		internal dict containing values of chf_type (and eclass dirs
		if store_eclass_paths is True).
		"""
		if not extern_ec_dict:
			return extern_ec_dict
		chf_getter = operator.attrgetter(chf_type)
		if paths:
			intern_ec_dict = dict((k, (v.eclass_dir, chf_getter(v)))
				for k, v in extern_ec_dict.items())
		else:
			intern_ec_dict = dict((k, chf_getter(v))
				for k, v in extern_ec_dict.items())
		return intern_ec_dict

	def __setitem__(self, cpv, values):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		d = None
		if self.cleanse_keys:
			d=ProtectedDict(values)
			for k, v in list(item for item in d.items() if item[0] != "_eclasses_"):
				if not v:
					del d[k]
		if "_eclasses_" in values:
			if d is None:
				d = ProtectedDict(values)
			if self.serialize_eclasses:
				d["_eclasses_"] = serialize_eclasses(d["_eclasses_"],
					self.validation_chf, paths=self.store_eclass_paths)
			else:
				d["_eclasses_"] = self._internal_eclasses(d["_eclasses_"],
					self.validation_chf, self.store_eclass_paths)
		elif d is None:
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

	def iterkeys(self):
		return iter(self)

	def iteritems(self):
		for x in self:
			yield (x, self[x])

	def sync(self, rate=0):
		self.sync_rate = rate
		if rate == 0:
			self.commit()

	def commit(self):
		if not self.autocommits:
			raise NotImplementedError(self)

	def __del__(self):
		# This used to be handled by an atexit hook that called
		# close_portdbapi_caches() for all portdbapi instances, but that was
		# prone to memory leaks for API consumers that needed to create/destroy
		# many portdbapi instances. So, instead we rely on __del__.
		self.sync()

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

	def validate_entry(self, entry, ebuild_hash, eclass_db):
		try:
			chf_types = self.chf_types
		except AttributeError:
			chf_types = (self.validation_chf,)

		for chf_type in chf_types:
			if self._validate_entry(chf_type, entry, ebuild_hash, eclass_db):
				return True

		return False

	def _validate_entry(self, chf_type, entry, ebuild_hash, eclass_db):
		hash_key = '_%s_' % chf_type
		try:
			entry_hash = entry[hash_key]
		except KeyError:
			return False
		else:
			if entry_hash != getattr(ebuild_hash, chf_type):
				return False
		update = eclass_db.validate_and_rewrite_cache(entry['_eclasses_'], chf_type,
			self.store_eclass_paths)
		if update is None:
			return False
		if update:
			entry['_eclasses_'] = update
		return True

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
				if isinstance(match, str):
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

	keys = __iter__
	items = iteritems


_keysorter = operator.itemgetter(0)

def serialize_eclasses(eclass_dict, chf_type='mtime', paths=True):
	"""takes a dict, returns a string representing said dict"""
	"""The "new format", which causes older versions of <portage-2.1.2 to
	traceback with a ValueError due to failed int() conversion.  This format
	isn't currently written, but the capability to read it is already built
	in.
	return "\t".join(["%s\t%s" % (k, str(v)) \
		for k, v in eclass_dict.iteritems()])
	"""
	if not eclass_dict:
		return ""
	getter = operator.attrgetter(chf_type)
	if paths:
		return "\t".join("%s\t%s\t%s" % (k, v.eclass_dir, getter(v))
			for k, v in sorted(eclass_dict.items(), key=_keysorter))
	return "\t".join("%s\t%s" % (k, getter(v))
		for k, v in sorted(eclass_dict.items(), key=_keysorter))


def _md5_deserializer(md5):
	"""
	Without this validation, it's possible for reconstruct_eclasses to
	mistakenly interpret mtime data as md5 data, and return an invalid
	data structure containing strings where ints are expected.
	"""
	if len(md5) != 32:
		raise ValueError('expected 32 hex digits')
	return md5


_chf_deserializers = {
	'md5': _md5_deserializer,
	'mtime': int,
}


def reconstruct_eclasses(cpv, eclass_string, chf_type='mtime', paths=True):
	"""returns a dict when handed a string generated by serialize_eclasses"""
	eclasses = eclass_string.rstrip().lstrip().split("\t")
	if eclasses == [""]:
		# occasionally this occurs in the fs backends.  they suck.
		return {}

	converter = _chf_deserializers.get(chf_type, lambda x: x)

	if paths:
		if len(eclasses) % 3 != 0:
			raise cache_errors.CacheCorruption(cpv, "_eclasses_ was of invalid len %i" % len(eclasses))
	elif len(eclasses) % 2 != 0:
		raise cache_errors.CacheCorruption(cpv, "_eclasses_ was of invalid len %i" % len(eclasses))
	d={}
	try:
		i = iter(eclasses)
		if paths:
			# The old format contains paths that will be discarded.
			for name, path, val in zip(i, i, i):
				d[name] = (path, converter(val))
		else:
			for name, val in zip(i, i):
				d[name] = converter(val)
	except IndexError:
		raise cache_errors.CacheCorruption(cpv,
			"_eclasses_ was of invalid len %i" % len(eclasses))
	except ValueError:
		raise cache_errors.CacheCorruption(cpv,
			"_eclasses_ not valid for chf_type {}".format(chf_type))
	del eclasses
	return d
