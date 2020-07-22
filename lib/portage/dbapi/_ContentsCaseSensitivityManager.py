# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class ContentsCaseSensitivityManager:
	"""
	Implicitly handles case transformations that are needed for
	case-insensitive support.
	"""

	def __init__(self, db):
		"""
		@param db: A dblink instance
		@type db: vartree.dblink
		"""
		self.getcontents = db.getcontents

		if "case-insensitive-fs" in db.settings.features:
			self.unmap_key = self._unmap_key_case_insensitive
			self.contains = self._contains_case_insensitive
			self.keys = self._keys_case_insensitive

		self._contents_insensitive = None
		self._reverse_key_map = None

	def clear_cache(self):
		"""
		Clear all cached contents data.
		"""
		self._contents_insensitive = None
		self._reverse_key_map = None

	def keys(self):
		"""
		Iterate over all contents keys, which are transformed to
		lowercase when appropriate, for use in case-insensitive
		comparisons.
		@rtype: iterator
		@return: An iterator over all the contents keys
		"""
		return iter(self.getcontents())

	def contains(self, key):
		"""
		Check if the given key is contained in the contents, using
		case-insensitive comparison when appropriate.
		@param key: A filesystem path (including ROOT and EPREFIX)
		@type key: str
		@rtype: bool
		@return: True if the given key is contained in the contents,
			False otherwise
		"""
		return key in self.getcontents()

	def unmap_key(self, key):
		"""
		Map a key (from the keys method) back to its case-preserved
		form.
		@param key: A filesystem path (including ROOT and EPREFIX)
		@type key: str
		@rtype: str
		@return: The case-preserved form of key
		"""
		return key

	def _case_insensitive_init(self):
		"""
		Initialize data structures for case-insensitive support.
		"""
		self._contents_insensitive = dict(
			(k.lower(), v) for k, v in self.getcontents().items())
		self._reverse_key_map = dict(
			(k.lower(), k) for k in self.getcontents())

	def _keys_case_insensitive(self):
		if self._contents_insensitive is None:
			self._case_insensitive_init()
		return iter(self._contents_insensitive)

	_keys_case_insensitive.__doc__ = keys.__doc__

	def _contains_case_insensitive(self, key):
		if self._contents_insensitive is None:
			self._case_insensitive_init()
		return key.lower() in self._contents_insensitive

	_contains_case_insensitive.__doc__ = contains.__doc__

	def _unmap_key_case_insensitive(self, key):
		if self._reverse_key_map is None:
			self._case_insensitive_init()
		return self._reverse_key_map[key]

	_unmap_key_case_insensitive.__doc__ = unmap_key.__doc__
