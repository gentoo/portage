# Copyright 2015-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.exception import InvalidData
from portage.localization import _

class NeededEntry:
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
		# We don't use scanelf -q, since that would omit libraries like
		# musl's /usr/lib/libc.so which do not have any DT_NEEDED or
		# DT_SONAME settings. Since we don't use scanelf -q, we have to
		# handle the special rpath value "  -  " below.
		rpaths = "" if rpaths == "  -  " else rpaths
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
