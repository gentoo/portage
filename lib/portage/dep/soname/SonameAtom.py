# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

import sys

from portage import _encodings, _unicode_encode

class SonameAtom(object):

	__slots__ = ("multilib_category", "soname", "_hash_key",
		"_hash_value")

	# Distiguishes package atoms from other atom types
	package = False

	def __init__(self, multilib_category, soname):
		object.__setattr__(self, "multilib_category", multilib_category)
		object.__setattr__(self, "soname", soname)
		object.__setattr__(self, "_hash_key",
			(multilib_category, soname))
		object.__setattr__(self, "_hash_value", hash(self._hash_key))

	def __setattr__(self, name, value):
		raise AttributeError("SonameAtom instances are immutable",
			self.__class__, name, value)

	def __hash__(self):
		return self._hash_value

	def __eq__(self, other):
		try:
			return self._hash_key == other._hash_key
		except AttributeError:
			return False

	def __ne__(self, other):
		try:
			return self._hash_key != other._hash_key
		except AttributeError:
			return True

	def __repr__(self):
		return "%s('%s', '%s')" % (
			self.__class__.__name__,
			self.multilib_category,
			self.soname
		)

	def __str__(self):
		return "%s: %s" % (self.multilib_category, self.soname)

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

	def match(self, pkg):
		"""
		Check if the given package instance matches this atom. Unbuilt
		ebuilds, which do not have soname metadata, will never match.

		@param pkg: a Package instance
		@type pkg: Package
		@return: True if this atom matches pkg, otherwise False
		@rtype: bool
		"""
		return pkg.provides is not None and self in pkg.provides
