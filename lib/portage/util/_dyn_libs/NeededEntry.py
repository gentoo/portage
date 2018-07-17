# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

import sys

from portage import _encodings, _unicode_encode
from portage.exception import InvalidData
from portage.localization import _

class NeededEntry(object):
	"""
	Represents one entry (line) from a NEEDED.ELF.2 file. The entry
	must have 5 or more semicolon-delimited fields in order to be
	considered valid. The sixth field is optional, corresponding
	to the multilib category. The multilib_category attribute is
	None if the corresponding field is either empty or missing.
	"""

	__slots__ = ("arch", "filename", "multilib_category", "needed",
		"runpaths", "soname")

	_MIN_FIELDS = 5
	_MULTILIB_CAT_INDEX = 5

	@classmethod
	def parse(cls, filename, line):
		"""
		Parse a NEEDED.ELF.2 entry. Raises InvalidData if necessary.

		@param filename: file name for use in exception messages
		@type filename: str
		@param line: a single line of text from a NEEDED.ELF.2 file,
			without a trailing newline
		@type line: str
		@rtype: NeededEntry
		@return: A new NeededEntry instance containing data from line
		"""
		fields = line.split(";")
		if len(fields) < cls._MIN_FIELDS:
			raise InvalidData(_("Wrong number of fields "
				"in %s: %s\n\n") % (filename, line))

		obj = cls()
		# Extra fields may exist (for future extensions).
		if (len(fields) > cls._MULTILIB_CAT_INDEX and
			fields[cls._MULTILIB_CAT_INDEX]):
			obj.multilib_category = fields[cls._MULTILIB_CAT_INDEX]
		else:
			obj.multilib_category = None

		del fields[cls._MIN_FIELDS:]
		obj.arch, obj.filename, obj.soname, rpaths, needed = fields
		obj.runpaths = tuple(filter(None, rpaths.split(":")))
		obj.needed = tuple(filter(None, needed.split(",")))

		return obj

	def __str__(self):
		"""
		Format this entry for writing to a NEEDED.ELF.2 file.
		"""
		return ";".join([
				self.arch,
				self.filename,
				self.soname,
				":".join(self.runpaths),
				",".join(self.needed),
				(self.multilib_category if self.multilib_category
				is not None else "")
		]) + "\n"

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__(),
				encoding=_encodings['content'])

		__str__.__doc__ = __unicode__.__doc__
