# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'MaskManager',
)

from portage import os
from portage.dep import ExtendedAtomDict, match_from_list
from portage.util import grabfile_package, stack_lists
from portage.versions import cpv_getkey

class MaskManager(object):

	def __init__(self, pmask_locations, abs_user_config, user_config=True):
		self._punmaskdict = ExtendedAtomDict(list)
		self._pmaskdict = ExtendedAtomDict(list)

		pkgmasklines = []
		pkgunmasklines = []
		for x in pmask_locations:
			pkgmasklines.append(grabfile_package(
				os.path.join(x, "package.mask"), recursive=1))
			pkgunmasklines.append(grabfile_package(
				os.path.join(x, "package.unmask"), recursive=1))

		if user_config:
			pkgmasklines.append(grabfile_package(
				os.path.join(abs_user_config, "package.mask"), recursive=1, allow_wildcard=True))
			pkgunmasklines.append(grabfile_package(
				os.path.join(abs_user_config, "package.unmask"), recursive=1, allow_wildcard=True))

		pkgmasklines = stack_lists(pkgmasklines, incremental=1)
		pkgunmasklines = stack_lists(pkgunmasklines, incremental=1)

		for x in pkgmasklines:
			self._pmaskdict.setdefault(x.cp, []).append(x)

		for x in pkgunmasklines:
			self._punmaskdict.setdefault(x.cp, []).append(x)

		for d in (self._pmaskdict, self._punmaskdict):
			for k, v in d.items():
				d[k] = tuple(v)

	def getMaskAtom(self, cpv, slot):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask. PROVIDE
		is not checked, so atoms will not be found for old-style virtuals.

		@param cpv: The package name
		@type cpv: String
		@param slot: The package's slot
		@type slot: String
		@rtype: String
		@return: An matching atom string or None if one is not found.
		"""

		cp = cpv_getkey(cpv)
		mask_atoms = self._pmaskdict.get(cp)
		if mask_atoms:
			pkg_list = ["%s:%s" % (cpv, slot)]
			unmask_atoms = self._punmaskdict.get(cp)
			for x in mask_atoms:
				if not match_from_list(x, pkg_list):
					continue
				if unmask_atoms:
					for y in unmask_atoms:
						if match_from_list(y, pkg_list):
							return None
				return x
		return None
