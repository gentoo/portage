# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.exception import InvalidData
from portage.localization import _
from portage.dep.soname.SonameAtom import SonameAtom

_error_empty_category = _("Multilib category empty: %s")
_error_missing_category = _("Multilib category missing: %s")
_error_duplicate_category = _("Multilib category occurs"
	" more than once: %s")

def parse_soname_deps(s):
	"""
	Parse a REQUIRES or PROVIDES dependency string, and raise
	InvalidData if necessary.

	@param s: REQUIRES or PROVIDES string
	@type s: str
	@rtype: iter
	@return: An iterator of SonameAtom instances
	"""

	categories = set()
	category = None
	previous_soname = None
	for soname in s.split():
		if soname.endswith(":"):
			if category is not None and previous_soname is None:
					raise InvalidData(_error_empty_category % category)

			category = soname[:-1]
			previous_soname = None
			if category in categories:
				raise InvalidData(_error_duplicate_category % category)
			categories.add(category)

		elif category is None:
			raise InvalidData(_error_missing_category % soname)
		else:
			previous_soname = soname
			yield SonameAtom(category, soname)

	if category is not None and previous_soname is None:
		raise InvalidData(_error_empty_category % category)
