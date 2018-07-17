#!/usr/bin/python -b
# Copyright 2009-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


from portage.manifest import guessManifestFileType
from portage.versions import _unicode, pkgsplit, vercmp


class ChangeLogTypeSort(_unicode):
	"""
	Helps to sort file names by file type and other criteria.
	"""
	def __new__(cls, status_change, file_name):
		return _unicode.__new__(cls, status_change + file_name)

	def __init__(self, status_change, file_name):
		_unicode.__init__(status_change + file_name)
		self.status_change = status_change
		self.file_name = file_name
		self.file_type = guessManifestFileType(file_name)

	@staticmethod
	def _file_type_lt(a, b):
		"""
		Defines an ordering between file types.
		"""
		first = a.file_type
		second = b.file_type
		if first == second:
			return False

		if first == "EBUILD":
			return True
		elif first == "MISC":
			return second in ("EBUILD",)
		elif first == "AUX":
			return second in ("EBUILD", "MISC")
		elif first == "DIST":
			return second in ("EBUILD", "MISC", "AUX")
		elif first is None:
			return False
		else:
			raise ValueError("Unknown file type '%s'" % first)

	def __lt__(self, other):
		"""
		Compare different file names, first by file type and then
		for ebuilds by version and lexicographically for others.
		EBUILD < MISC < AUX < DIST < None
		"""
		if self.__class__ != other.__class__:
			raise NotImplementedError

		# Sort by file type as defined by _file_type_lt().
		if self._file_type_lt(self, other):
			return True
		elif self._file_type_lt(other, self):
			return False

		# Files have the same type.
		if self.file_type == "EBUILD":
			# Sort by version. Lowest first.
			ver = "-".join(pkgsplit(self.file_name[:-7])[1:3])
			other_ver = "-".join(pkgsplit(other.file_name[:-7])[1:3])
			return vercmp(ver, other_ver) < 0
		else:
			# Sort lexicographically.
			return self.file_name < other.file_name
