# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

import UserDict
import weakref

class ProtectedDict(UserDict.DictMixin):
	"""
	given an initial dict, this wraps that dict storing changes in a secondary dict, protecting
	the underlying dict from changes
	"""
	__slots__=("orig","new","blacklist")

	def __init__(self, orig):
		self.orig = orig
		self.new = {}
		self.blacklist = {}


	def __setitem__(self, key, val):
		self.new[key] = val
		if key in self.blacklist:
			del self.blacklist[key]


	def __getitem__(self, key):
		if key in self.new:
			return self.new[key]
		if key in self.blacklist:
			raise KeyError(key)
		return self.orig[key]


	def __delitem__(self, key):
		if key in self.new:
			del self.new[key]
		elif key in self.orig:
			if key not in self.blacklist:
				self.blacklist[key] = True
				return
		raise KeyError(key)
			

	def __iter__(self):
		for k in self.new.iterkeys():
			yield k
		for k in self.orig.iterkeys():
			if k not in self.blacklist and k not in self.new:
				yield k


	def keys(self):
		return list(self.__iter__())


	def has_key(self, key):
		return key in self.new or (key not in self.blacklist and key in self.orig)


class LazyLoad(UserDict.DictMixin):
	"""
	Lazy loading of values for a dict
	"""
	__slots__=("pull", "d")

	def __init__(self, pull_items_func, initial_items=[]):
		self.d = {}
		for k, v in initial_items:
			self.d[k] = v
		self.pull = pull_items_func

	def __getitem__(self, key):
		if key in self.d:
			return self.d[key]
		elif self.pull != None:
			self.d.update(self.pull())
			self.pull = None
		return self.d[key]


	def __iter__(self):
		return iter(self.keys())

	def keys(self):
		if self.pull != None:
			self.d.update(self.pull())
			self.pull = None
		return self.d.keys()


	def has_key(self, key):
		return key in self


	def __contains__(self, key):
		if key in self.d:
			return True
		elif self.pull != None:
			self.d.update(self.pull())
			self.pull = None
		return key in self.d

_slot_dict_classes = weakref.WeakValueDictionary()

def slot_dict_class(keys):
	if isinstance(keys, frozenset):
		keys_set = keys
	else:
		keys_set = frozenset(keys)
	v = _slot_dict_classes.get(keys_set)
	if v is None:

		class SlotDict(object):

			_keys = keys_set
			__slots__ = ("__weakref__",) + tuple("_val_" + k for k in _keys)

			def __iter__(self):
				for k, v in self.iteritems():
					yield k

			def __len__(self):
				l = 0
				for i in self.iteritems():
					l += 1
				return l

			def keys(self):
				return list(self)

			def iteritems(self):
				for k in self._keys:
					try:
						yield (k, getattr(self, "_val_" + k))
					except AttributeError:
						pass

			def items(self):
				return list(self.iteritems())

			def itervalues(self):
				for k, v in self.itervalues():
					yield v

			def values(self):
				return list(self.itervalues())

			def __delitem__(self, k):
				try:
					delattr(self, "_val_" + k)
				except AttributeError:
					raise KeyError(k)

			def __setitem__(self, k, v):
				setattr(self, "_val_" + k, v)

			def setdefault(self, key, default=None):
				try:
					return self[key]
				except KeyError:
					self[key] = default
				return default

			def update(self, d):
				i = getattr(d, "iteritems", None)
				if i is None:
					i = d
				else:
					i = i()
				for k, v in i:
					self[k] = v

			def __getitem__(self, k):
				try:
					return getattr(self, "_val_" + k)
				except AttributeError:
					raise KeyError(k)

			def get(self, key, default=None):
				try:
					return self[key]
				except KeyError:
					return default

			def __contains__(self, k):
				return hasattr(self, "_val_" + k)

			def has_key(self, k):
				return k in self

			def pop(self, key, *args):
				if len(args) > 1:
					raise TypeError(
						"pop expected at most 2 arguments, got " + \
						repr(1 + len(args)))
				try:
					value = self[key]
				except KeyError:
					if args:
						return args[0]
					raise
				del self[key]
				return value

			def popitem(self):
				try:
					k, v = self.iteritems().next()
				except StopIteration:
					raise KeyError('container is empty')
				del self[k]
				return (k, v)

			def copy(self):
				c = self.__class__()
				c.update(self)
				return c

			def clear(self):
				for k in self._keys:
					try:
						delattr(self, "_val_" + k)
					except AttributError:
						pass

		v = SlotDict
		_slot_dict_classes[keys_set] = v
	return v
