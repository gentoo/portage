# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'UseManager',
)

from portage import os
from portage.dep import ExtendedAtomDict, remove_slot
from portage.util import grabfile, grabdict_package, stack_lists
from portage.versions import cpv_getkey

from portage.package.ebuild._config.helper import ordered_by_atom_specificity

class UseManager(object):

	def __init__(self, profiles, abs_user_config, user_config=True):
		#	file				variable
		#--------------------------------
		#	profiles
		#--------------------------------
		#	use.mask			_usemask_list
		#	use.force			_useforce_list
		#	package.use.mask	_pusemask_list
		#	package.use			_pkgprofileuse
		#	package.use.force	_puseforce_list
		#--------------------------------
		#	user config
		#--------------------------------
		#	package.use			_pusedict	

		# Dynamic variables tracked by the config class
		#--------------------------------
		#	profiles
		#--------------------------------
		#	usemask
		#	useforce
		#--------------------------------
		#	user config
		#--------------------------------
		#	puse

		self._usemask_list = self._parse_profile_files_to_list("use.mask", profiles)
		self._useforce_list = self._parse_profile_files_to_list("use.force", profiles)
		self._pusemask_list = self._parse_profile_files_to_dict("package.use.mask", profiles)
		self._pkgprofileuse = self._parse_profile_files_to_dict("package.use", profiles, juststrings=True)
		self._puseforce_list = self._parse_profile_files_to_dict("package.use.force", profiles)

		self._pusedict = self._parse_user_files_to_extatomdict("package.use", abs_user_config, user_config)

	def _parse_user_files_to_extatomdict(self, file_name, location, user_config):
		ret = ExtendedAtomDict(dict)
		if user_config:
			pusedict = grabdict_package(
				os.path.join(location, file_name), recursive=1, allow_wildcard=True, allow_repo=True, verify_eapi=False)
			for k, v in pusedict.items():
				ret.setdefault(k.cp, {})[k] = v

		return ret

	def _parse_profile_files_to_list(self, file_name, locations):
		return tuple(
			tuple(grabfile(os.path.join(x, file_name), recursive=1))
			for x in locations)

	def _parse_profile_files_to_dict(self, file_name, locations, juststrings=False):
		ret = []
		raw = [grabdict_package(os.path.join(x, file_name),
			juststrings=juststrings, recursive=1, verify_eapi=True) for x in locations]
		for rawdict in raw:
			cpdict = {}
			for k, v in rawdict.items():
				cpdict.setdefault(k.cp, {})[k] = v
			ret.append(cpdict)
		return ret

	def getUseMask(self, pkg=None):
		if pkg is None:
			return frozenset(stack_lists(
				self._usemask_list, incremental=True))

		cp = getattr(pkg, "cp", None)
		if cp is None:
			cp = cpv_getkey(remove_slot(pkg))
		usemask = []
		for i, pusemask_dict in enumerate(self._pusemask_list):
			if self._usemask_list[i]:
				usemask.append(self._usemask_list[i])
			cpdict = pusemask_dict.get(cp)
			if cpdict:
				pkg_usemask = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_usemask:
					usemask.extend(pkg_usemask)
		return frozenset(stack_lists(usemask, incremental=True))

	def getUseForce(self, pkg=None):
		if pkg is None:
			return frozenset(stack_lists(
				self._useforce_list, incremental=True))

		cp = getattr(pkg, "cp", None)
		if cp is None:
			cp = cpv_getkey(remove_slot(pkg))
		useforce = []
		for i, puseforce_dict in enumerate(self._puseforce_list):
			if self._useforce_list[i]:
				useforce.append(self._useforce_list[i])
			cpdict = puseforce_dict.get(cp)
			if cpdict:
				pkg_useforce = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_useforce:
					useforce.extend(pkg_useforce)
		return frozenset(stack_lists(useforce, incremental=True))

	def getPUSE(self, pkg):
		cp = getattr(pkg, "cp", None)
		if cp is None:
			cp = cpv_getkey(remove_slot(pkg))
		ret = ""
		cpdict = self._pusedict.get(cp)
		if cpdict:
			puse_matches = ordered_by_atom_specificity(cpdict, pkg)
			if puse_matches:
				puse_list = []
				for x in puse_matches:
					puse_list.extend(x)
				ret = " ".join(puse_list)
		return ret

	def extract_global_USE_changes(self, old=""):
		ret = old
		cpdict = self._pusedict.get("*/*")
		if cpdict is not None:
			v = cpdict.pop("*/*", None)
			if v is not None:
				ret = " ".join(v)
				if old:
					ret = old + " " + ret
				if not cpdict:
					#No tokens left in atom_license_map, remove it.
					del self._pusedict["*/*"]
		return ret
