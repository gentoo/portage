# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class ShelveUnicodeWrapper(object):
	"""
	Convert unicode to str and back again, since python-2.x shelve
	module doesn't support unicode.
	"""
	def __init__(self, shelve_instance):
		self._shelve = shelve_instance

	def _encode(self, s):
		if isinstance(s, unicode):
			s = s.encode('utf_8')
		return s

	def __len__(self):
		return len(self._shelve)

	def __contains__(self, k):
		return self._encode(k) in self._shelve

	def __iter__(self):
		return self._shelve.__iter__()

	def items(self):
		return self._shelve.iteritems()

	def __setitem__(self, k, v):
		self._shelve[self._encode(k)] = self._encode(v)

	def __getitem__(self, k):
		return self._shelve[self._encode(k)]

	def __delitem__(self, k):
		del self._shelve[self._encode(k)]

	def get(self, k, *args):
		return self._shelve.get(self._encode(k), *args)

	def close(self):
		self._shelve.close()

	def clear(self):
		self._shelve.clear()
