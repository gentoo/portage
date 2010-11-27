# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'UseManager',
)

from portage import os
from portage.dep import ExtendedAtomDict, remove_slot, _get_useflag_re
from portage.localization import _
from portage.util import grabfile, grabdict_package, read_corresponding_eapi_file, stack_lists, writemsg
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
		#	package.use.mask		_pusemask_list
		#	package.use			_pkgprofileuse
		#	package.use.force		_puseforce_list
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

		self._usemask_list = self._parse_profile_files_to_tuple("use.mask", profiles)
		self._useforce_list = self._parse_profile_files_to_tuple("use.force", profiles)
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
				ret.setdefault(k.cp, {})[k] = tuple(v)

		return ret

	def _parse_profile_files_to_tuple(self, file_name, locations):
		ret = []
		for profile in locations:
			profile_lines = []
			path = os.path.join(profile, file_name)
			lines = grabfile(path, recursive=1)
			eapi = read_corresponding_eapi_file(path)
			useflag_re = _get_useflag_re(eapi)
			for prefixed_useflag in lines:
				if prefixed_useflag[:1] == "-":
					useflag = prefixed_useflag[1:]
				else:
					useflag = prefixed_useflag
				if useflag_re.match(useflag) is None:
					writemsg(_("--- Invalid USE flag in '%s': '%s'\n") % \
						(path, prefixed_useflag), noiselevel=-1)
				else:
					profile_lines.append(prefixed_useflag)
			ret.append(tuple(profile_lines))
		return tuple(ret)

	def _parse_profile_files_to_dict(self, file_name, locations, juststrings=False):
		ret = []
		for profile in locations:
			profile_dict = {}
			cpdict = {}
			path = os.path.join(profile, file_name)
			file_dict = grabdict_package(path, recursive=1, verify_eapi=True)
			eapi = read_corresponding_eapi_file(path)
			useflag_re = _get_useflag_re(eapi)
			for k, v in file_dict.items():
				useflags = []
				for prefixed_useflag in v:
					if prefixed_useflag[:1] == "-":
						useflag = prefixed_useflag[1:]
					else:
						useflag = prefixed_useflag
					if useflag_re.match(useflag) is None:
						writemsg(_("--- Invalid USE flag for '%s' in '%s': '%s'\n") % \
							(k, path, prefixed_useflag), noiselevel=-1)
					else:
						useflags.append(prefixed_useflag)
				profile_dict.setdefault(k, []).extend(useflags)
			for k, v in profile_dict.items():
				if juststrings:
					v = " ".join(v)
				else:
					v = tuple(v)
				cpdict.setdefault(k.cp, {})[k] = v
			ret.append(cpdict)
		return tuple(ret)

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
