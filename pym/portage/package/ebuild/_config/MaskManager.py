# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'MaskManager',
)

from itertools import chain
from portage import os
from portage.dep import ExtendedAtomDict, match_from_list
from portage.util import grabfile_package, stack_lists
from portage.versions import cpv_getkey

class MaskManager(object):

	def __init__(self, pmask_locations, abs_user_config,
		user_config=True, strict_umatched_removal=False):
		self._punmaskdict = ExtendedAtomDict(list)
		self._pmaskdict = ExtendedAtomDict(list)

		repo_profiles, profiles = pmask_locations

		#Read profile/package.mask form every repo. Stack them immediately
		#to make sure that -atoms don't effect other repos.
		repo_pkgmasklines = []
		repo_pkgunmasklines = []
		for x in repo_profiles:
			repo_pkgmasklines.append(stack_lists([grabfile_package(
				os.path.join(x, "package.mask"), recursive=1, remember_source_file=True, verify_eapi=True)], \
					incremental=1, remember_source_file=True,
					warn_for_unmatched_removal=True,
					strict_warn_for_unmatched_removal=strict_umatched_removal))
			repo_pkgunmasklines.append(stack_lists([grabfile_package(
				os.path.join(x, "package.unmask"), recursive=1, remember_source_file=True, verify_eapi=True)], \
				incremental=1, remember_source_file=True,
				warn_for_unmatched_removal=True,
				strict_warn_for_unmatched_removal=strict_umatched_removal))
		repo_pkgmasklines = list(chain.from_iterable(repo_pkgmasklines))
		repo_pkgunmasklines = list(chain.from_iterable(repo_pkgunmasklines))

		#Read package.mask form the user's profile. Stack them in the end
		#to allow profiles to override masks from their parent profiles.
		profile_pkgmasklines = []
		profile_pkgunmasklines = []
		for x in profiles:
			profile_pkgmasklines.append(grabfile_package(
				os.path.join(x, "package.mask"), recursive=1, remember_source_file=True, verify_eapi=True))
			profile_pkgunmasklines.append(grabfile_package(
				os.path.join(x, "package.unmask"), recursive=1, remember_source_file=True, verify_eapi=True))
		profile_pkgmasklines = stack_lists(profile_pkgmasklines, incremental=1, \
			remember_source_file=True, warn_for_unmatched_removal=True,
			strict_warn_for_unmatched_removal=strict_umatched_removal)
		profile_pkgunmasklines = stack_lists(profile_pkgunmasklines, incremental=1, \
			remember_source_file=True, warn_for_unmatched_removal=True,
			strict_warn_for_unmatched_removal=strict_umatched_removal)

		#Read /etc/portage/package.mask. Don't stack it to allow the user to
		#remove mask atoms from everywhere with -atoms.
		user_pkgmasklines = []
		user_pkgunmasklines = []
		if user_config:
			user_pkgmasklines = grabfile_package(
				os.path.join(abs_user_config, "package.mask"), recursive=1, \
				allow_wildcard=True, remember_source_file=True, verify_eapi=False)
			user_pkgunmasklines = grabfile_package(
				os.path.join(abs_user_config, "package.unmask"), recursive=1, \
				allow_wildcard=True, remember_source_file=True, verify_eapi=False)

		#Stack everything together. At this point, only user_pkgmasklines may contain -atoms.
		#Don't warn for unmatched -atoms here, since we don't do it for any other user config file.
		pkgmasklines = stack_lists([repo_pkgmasklines, profile_pkgmasklines, user_pkgmasklines], \
			incremental=1, remember_source_file=True, warn_for_unmatched_removal=False)
		pkgunmasklines = stack_lists([repo_pkgunmasklines, profile_pkgunmasklines, user_pkgunmasklines], \
			incremental=1, remember_source_file=True, warn_for_unmatched_removal=False)

		for x, source_file in pkgmasklines:
			self._pmaskdict.setdefault(x.cp, []).append(x)

		for x, source_file in pkgunmasklines:
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
