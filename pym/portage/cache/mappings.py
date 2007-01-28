# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: mappings.py 2015 2005-09-20 23:14:26Z ferringb $

import UserDict

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

