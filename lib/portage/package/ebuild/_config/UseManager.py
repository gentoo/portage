# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'UseManager',
)

from _emerge.Package import Package
from portage import os
from portage.dep import Atom, dep_getrepo, dep_getslot, ExtendedAtomDict, remove_slot, _get_useflag_re, _repo_separator
from portage.eapi import eapi_has_use_aliases, eapi_supports_stable_use_forcing_and_masking
from portage.exception import InvalidAtom
from portage.localization import _
from portage.repository.config import allow_profile_repo_deps
from portage.util import grabfile, grabdict, grabdict_package, read_corresponding_eapi_file, stack_lists, writemsg
from portage.versions import _pkg_str

from portage.package.ebuild._config.helper import ordered_by_atom_specificity

class UseManager:

	def __init__(self, repositories, profiles, abs_user_config, is_stable,
		user_config=True):
		#	file				variable
		#--------------------------------
		#	repositories
		#--------------------------------
		#	use.mask			_repo_usemask_dict
		#	use.stable.mask			_repo_usestablemask_dict
		#	use.force			_repo_useforce_dict
		#	use.stable.force		_repo_usestableforce_dict
		#	use.aliases			_repo_usealiases_dict
		#	package.use.mask		_repo_pusemask_dict
		#	package.use.stable.mask		_repo_pusestablemask_dict
		#	package.use.force		_repo_puseforce_dict
		#	package.use.stable.force	_repo_pusestableforce_dict
		#	package.use.aliases		_repo_pusealiases_dict
		#--------------------------------
		#	profiles
		#--------------------------------
		#	use.mask			_usemask_list
		#	use.stable.mask			_usestablemask_list
		#	use.force			_useforce_list
		#	use.stable.force		_usestableforce_list
		#	package.use.mask		_pusemask_list
		#	package.use.stable.mask		_pusestablemask_list
		#	package.use			_pkgprofileuse
		#	package.use.force		_puseforce_list
		#	package.use.stable.force	_pusestableforce_list
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

		self._user_config = user_config
		self._is_stable = is_stable
		self._repo_usemask_dict = self._parse_repository_files_to_dict_of_tuples("use.mask", repositories)
		self._repo_usestablemask_dict = \
			self._parse_repository_files_to_dict_of_tuples("use.stable.mask",
				repositories, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._repo_useforce_dict = self._parse_repository_files_to_dict_of_tuples("use.force", repositories)
		self._repo_usestableforce_dict = \
			self._parse_repository_files_to_dict_of_tuples("use.stable.force",
				repositories, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._repo_pusemask_dict = self._parse_repository_files_to_dict_of_dicts("package.use.mask", repositories)
		self._repo_pusestablemask_dict = \
			self._parse_repository_files_to_dict_of_dicts("package.use.stable.mask",
				repositories, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._repo_puseforce_dict = self._parse_repository_files_to_dict_of_dicts("package.use.force", repositories)
		self._repo_pusestableforce_dict = \
			self._parse_repository_files_to_dict_of_dicts("package.use.stable.force",
				repositories, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._repo_puse_dict = self._parse_repository_files_to_dict_of_dicts("package.use", repositories)

		self._usemask_list = self._parse_profile_files_to_tuple_of_tuples("use.mask", profiles)
		self._usestablemask_list = \
			self._parse_profile_files_to_tuple_of_tuples("use.stable.mask",
				profiles, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._useforce_list = self._parse_profile_files_to_tuple_of_tuples("use.force", profiles)
		self._usestableforce_list = \
			self._parse_profile_files_to_tuple_of_tuples("use.stable.force",
				profiles, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._pusemask_list = self._parse_profile_files_to_tuple_of_dicts("package.use.mask", profiles)
		self._pusestablemask_list = \
			self._parse_profile_files_to_tuple_of_dicts("package.use.stable.mask",
				profiles, eapi_filter=eapi_supports_stable_use_forcing_and_masking)
		self._pkgprofileuse = self._parse_profile_files_to_tuple_of_dicts("package.use", profiles, juststrings=True)
		self._puseforce_list = self._parse_profile_files_to_tuple_of_dicts("package.use.force", profiles)
		self._pusestableforce_list = \
			self._parse_profile_files_to_tuple_of_dicts("package.use.stable.force",
				profiles, eapi_filter=eapi_supports_stable_use_forcing_and_masking)

		self._pusedict = self._parse_user_files_to_extatomdict("package.use", abs_user_config, user_config)

		self._repo_usealiases_dict = self._parse_repository_usealiases(repositories)
		self._repo_pusealiases_dict = self._parse_repository_packageusealiases(repositories)

		self.repositories = repositories

	def _parse_file_to_tuple(self, file_name, recursive=True,
		eapi_filter=None, eapi=None, eapi_default="0"):
		"""
		@param file_name: input file name
		@type file_name: str
		@param recursive: triggers recursion if the input file is a
			directory
		@type recursive: bool
		@param eapi_filter: a function that accepts a single eapi
			argument, and returns true if the current file type
			is supported by the given EAPI
		@type eapi_filter: callable
		@param eapi: the EAPI of the current profile node, which allows
			a call to read_corresponding_eapi_file to be skipped
		@type eapi: str
		@param eapi_default: the default EAPI which applies if the
			current profile node does not define a local EAPI
		@type eapi_default: str
		@rtype: tuple
		@return: collection of USE flags
		"""
		ret = []
		lines = grabfile(file_name, recursive=recursive)
		if eapi is None:
			eapi = read_corresponding_eapi_file(
				file_name, default=eapi_default)
		if eapi_filter is not None and not eapi_filter(eapi):
			if lines:
				writemsg(_("--- EAPI '%s' does not support '%s': '%s'\n") %
					(eapi, os.path.basename(file_name), file_name),
					noiselevel=-1)
			return ()
		useflag_re = _get_useflag_re(eapi)
		for prefixed_useflag in lines:
			if prefixed_useflag[:1] == "-":
				useflag = prefixed_useflag[1:]
			else:
				useflag = prefixed_useflag
			if useflag_re.match(useflag) is None:
				writemsg(_("--- Invalid USE flag in '%s': '%s'\n") %
					(file_name, prefixed_useflag), noiselevel=-1)
			else:
				ret.append(prefixed_useflag)
		return tuple(ret)

	def _parse_file_to_dict(self, file_name, juststrings=False, recursive=True,
		eapi_filter=None, user_config=False, eapi=None, eapi_default="0",
		allow_repo=False, allow_build_id=False):
		"""
		@param file_name: input file name
		@type file_name: str
		@param juststrings: store dict values as space-delimited strings
			instead of tuples
		@type juststrings: bool
		@param recursive: triggers recursion if the input file is a
			directory
		@type recursive: bool
		@param eapi_filter: a function that accepts a single eapi
			argument, and returns true if the current file type
			is supported by the given EAPI
		@type eapi_filter: callable
		@param user_config: current file is part of the local
			configuration (not repository content)
		@type user_config: bool
		@param eapi: the EAPI of the current profile node, which allows
			a call to read_corresponding_eapi_file to be skipped
		@type eapi: str
		@param eapi_default: the default EAPI which applies if the
			current profile node does not define a local EAPI
		@type eapi_default: str
		@param allow_build_id: allow atoms to specify a particular
			build-id
		@type allow_build_id: bool
		@rtype: tuple
		@return: collection of USE flags
		"""
		ret = {}
		location_dict = {}
		if eapi is None:
			eapi = read_corresponding_eapi_file(file_name,
				default=eapi_default)
		extended_syntax = eapi is None and user_config
		if extended_syntax:
			ret = ExtendedAtomDict(dict)
		else:
			ret = {}
		allow_repo = allow_repo or extended_syntax
		file_dict = grabdict_package(file_name, recursive=recursive,
			allow_wildcard=extended_syntax, allow_repo=allow_repo,
			verify_eapi=(not extended_syntax), eapi=eapi,
			eapi_default=eapi_default, allow_build_id=allow_build_id,
			allow_use=False)
		if eapi is not None and eapi_filter is not None and not eapi_filter(eapi):
			if file_dict:
				writemsg(_("--- EAPI '%s' does not support '%s': '%s'\n") %
					(eapi, os.path.basename(file_name), file_name),
					noiselevel=-1)
			return ret
		useflag_re = _get_useflag_re(eapi)
		for k, v in file_dict.items():
			useflags = []
			use_expand_prefix = ''
			for prefixed_useflag in v:
				if extended_syntax and prefixed_useflag == "\n":
					use_expand_prefix = ""
					continue
				if extended_syntax and prefixed_useflag[-1] == ":":
					use_expand_prefix = prefixed_useflag[:-1].lower() + "_"
					continue

				if prefixed_useflag[:1] == "-":
					useflag = use_expand_prefix + prefixed_useflag[1:]
					prefixed_useflag = "-" + useflag
				else:
					useflag = use_expand_prefix + prefixed_useflag
					prefixed_useflag = useflag
				if useflag_re.match(useflag) is None:
					writemsg(_("--- Invalid USE flag for '%s' in '%s': '%s'\n") %
						(k, file_name, prefixed_useflag), noiselevel=-1)
				else:
					useflags.append(prefixed_useflag)
			location_dict.setdefault(k, []).extend(useflags)
		for k, v in location_dict.items():
			if juststrings:
				v = " ".join(v)
			else:
				v = tuple(v)
			ret.setdefault(k.cp, {})[k] = v
		return ret

	def _parse_user_files_to_extatomdict(self, file_name, location, user_config):
		ret = ExtendedAtomDict(dict)
		if user_config:
			pusedict = grabdict_package(
				os.path.join(location, file_name),
				recursive=1, newlines=1, allow_wildcard=True,
				allow_repo=True, verify_eapi=False,
				allow_build_id=True, allow_use=False)
			for k, v in pusedict.items():
				l = []
				use_expand_prefix = ''
				for flag in v:
					if flag == "\n":
						use_expand_prefix = ""
						continue
					if flag[-1] == ":":
						use_expand_prefix = flag[:-1].lower() + "_"
						continue
					if flag[0] == "-":
						nv = "-" + use_expand_prefix + flag[1:]
					else:
						nv = use_expand_prefix + flag
					l.append(nv)
				ret.setdefault(k.cp, {})[k] = tuple(l)

		return ret

	def _parse_repository_files_to_dict_of_tuples(self, file_name, repositories, eapi_filter=None):
		ret = {}
		for repo in repositories.repos_with_profiles():
			ret[repo.name] = self._parse_file_to_tuple(
				os.path.join(repo.location, "profiles", file_name),
				eapi_filter=eapi_filter, eapi_default=repo.eapi)
		return ret

	def _parse_repository_files_to_dict_of_dicts(self, file_name, repositories, eapi_filter=None):
		ret = {}
		for repo in repositories.repos_with_profiles():
			ret[repo.name] = self._parse_file_to_dict(
				os.path.join(repo.location, "profiles", file_name),
				eapi_filter=eapi_filter, eapi_default=repo.eapi,
				allow_repo=allow_profile_repo_deps(repo),
				allow_build_id=("build-id" in repo.profile_formats))
		return ret

	def _parse_profile_files_to_tuple_of_tuples(self, file_name, locations,
		eapi_filter=None):
		return tuple(self._parse_file_to_tuple(
			os.path.join(profile.location, file_name),
			recursive=profile.portage1_directories,
			eapi_filter=eapi_filter, eapi=profile.eapi,
			eapi_default=None) for profile in locations)

	def _parse_profile_files_to_tuple_of_dicts(self, file_name, locations,
		juststrings=False, eapi_filter=None):
		return tuple(self._parse_file_to_dict(
			os.path.join(profile.location, file_name), juststrings,
			recursive=profile.portage1_directories, eapi_filter=eapi_filter,
			user_config=profile.user_config, eapi=profile.eapi,
			eapi_default=None, allow_build_id=profile.allow_build_id,
			allow_repo=allow_profile_repo_deps(profile))
			for profile in locations)

	def _parse_repository_usealiases(self, repositories):
		ret = {}
		for repo in repositories.repos_with_profiles():
			file_name = os.path.join(repo.location, "profiles", "use.aliases")
			eapi = read_corresponding_eapi_file(
				file_name, default=repo.eapi)
			useflag_re = _get_useflag_re(eapi)
			raw_file_dict = grabdict(file_name, recursive=True)
			file_dict = {}
			for real_flag, aliases in raw_file_dict.items():
				if useflag_re.match(real_flag) is None:
					writemsg(_("--- Invalid real USE flag in '%s': '%s'\n") % (file_name, real_flag), noiselevel=-1)
				else:
					for alias in aliases:
						if useflag_re.match(alias) is None:
							writemsg(_("--- Invalid USE flag alias for '%s' real USE flag in '%s': '%s'\n") %
								(real_flag, file_name, alias), noiselevel=-1)
						else:
							if any(alias in v for k, v in file_dict.items() if k != real_flag):
								writemsg(_("--- Duplicated USE flag alias in '%s': '%s'\n") %
									(file_name, alias), noiselevel=-1)
							else:
								file_dict.setdefault(real_flag, []).append(alias)
			ret[repo.name] = file_dict
		return ret

	def _parse_repository_packageusealiases(self, repositories):
		ret = {}
		for repo in repositories.repos_with_profiles():
			file_name = os.path.join(repo.location, "profiles", "package.use.aliases")
			eapi = read_corresponding_eapi_file(
				file_name, default=repo.eapi)
			useflag_re = _get_useflag_re(eapi)
			lines = grabfile(file_name, recursive=True)
			file_dict = {}
			for line in lines:
				elements = line.split()
				atom = elements[0]
				try:
					atom = Atom(atom, eapi=eapi)
				except InvalidAtom:
					writemsg(_("--- Invalid atom in '%s': '%s'\n") % (file_name, atom))
					continue
				if len(elements) == 1:
					writemsg(_("--- Missing real USE flag for '%s' in '%s'\n") % (atom, file_name), noiselevel=-1)
					continue
				real_flag = elements[1]
				if useflag_re.match(real_flag) is None:
					writemsg(_("--- Invalid real USE flag for '%s' in '%s': '%s'\n") % (atom, file_name, real_flag), noiselevel=-1)
				else:
					for alias in elements[2:]:
						if useflag_re.match(alias) is None:
							writemsg(_("--- Invalid USE flag alias for '%s' real USE flag for '%s' in '%s': '%s'\n") %
								(real_flag, atom, file_name, alias), noiselevel=-1)
						else:
							# Duplicated USE flag aliases in entries for different atoms
							# matching the same package version are detected in getUseAliases().
							if any(alias in v for k, v in file_dict.get(atom.cp, {}).get(atom, {}).items() if k != real_flag):
								writemsg(_("--- Duplicated USE flag alias for '%s' in '%s': '%s'\n") %
									(atom, file_name, alias), noiselevel=-1)
							else:
								file_dict.setdefault(atom.cp, {}).setdefault(atom, {}).setdefault(real_flag, []).append(alias)
			ret[repo.name] = file_dict
		return ret

	def _isStable(self, pkg):
		if self._user_config:
			try:
				return pkg.stable
			except AttributeError:
				# KEYWORDS is unavailable (prior to "depend" phase)
				return False

		try:
			pkg._metadata
		except AttributeError:
			# KEYWORDS is unavailable (prior to "depend" phase)
			return False

		# Since repoman uses different config instances for
		# different profiles, we have to be careful to do the
		# stable check against the correct profile here.
		return self._is_stable(pkg)

	def getUseMask(self, pkg=None, stable=None):
		if pkg is None:
			return frozenset(stack_lists(
				self._usemask_list, incremental=True))

		slot = None
		cp = getattr(pkg, "cp", None)
		if cp is None:
			slot = dep_getslot(pkg)
			repo = dep_getrepo(pkg)
			pkg = _pkg_str(remove_slot(pkg), slot=slot, repo=repo)
			cp = pkg.cp

		if stable is None:
			stable = self._isStable(pkg)

		usemask = []

		if hasattr(pkg, "repo") and pkg.repo != Package.UNKNOWN_REPO:
			repos = []
			try:
				repos.extend(repo.name for repo in
					self.repositories[pkg.repo].masters)
			except KeyError:
				pass
			repos.append(pkg.repo)
			for repo in repos:
				usemask.append(self._repo_usemask_dict.get(repo, {}))
				if stable:
					usemask.append(self._repo_usestablemask_dict.get(repo, {}))
				cpdict = self._repo_pusemask_dict.get(repo, {}).get(cp)
				if cpdict:
					pkg_usemask = ordered_by_atom_specificity(cpdict, pkg)
					if pkg_usemask:
						usemask.extend(pkg_usemask)
				if stable:
					cpdict = self._repo_pusestablemask_dict.get(repo, {}).get(cp)
					if cpdict:
						pkg_usemask = ordered_by_atom_specificity(cpdict, pkg)
						if pkg_usemask:
							usemask.extend(pkg_usemask)

		for i, pusemask_dict in enumerate(self._pusemask_list):
			if self._usemask_list[i]:
				usemask.append(self._usemask_list[i])
			if stable and self._usestablemask_list[i]:
				usemask.append(self._usestablemask_list[i])
			cpdict = pusemask_dict.get(cp)
			if cpdict:
				pkg_usemask = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_usemask:
					usemask.extend(pkg_usemask)
			if stable:
				cpdict = self._pusestablemask_list[i].get(cp)
				if cpdict:
					pkg_usemask = ordered_by_atom_specificity(cpdict, pkg)
					if pkg_usemask:
						usemask.extend(pkg_usemask)

		return frozenset(stack_lists(usemask, incremental=True))

	def getUseForce(self, pkg=None, stable=None):
		if pkg is None:
			return frozenset(stack_lists(
				self._useforce_list, incremental=True))

		cp = getattr(pkg, "cp", None)
		if cp is None:
			slot = dep_getslot(pkg)
			repo = dep_getrepo(pkg)
			pkg = _pkg_str(remove_slot(pkg), slot=slot, repo=repo)
			cp = pkg.cp

		if stable is None:
			stable = self._isStable(pkg)

		useforce = []

		if hasattr(pkg, "repo") and pkg.repo != Package.UNKNOWN_REPO:
			repos = []
			try:
				repos.extend(repo.name for repo in
					self.repositories[pkg.repo].masters)
			except KeyError:
				pass
			repos.append(pkg.repo)
			for repo in repos:
				useforce.append(self._repo_useforce_dict.get(repo, {}))
				if stable:
					useforce.append(self._repo_usestableforce_dict.get(repo, {}))
				cpdict = self._repo_puseforce_dict.get(repo, {}).get(cp)
				if cpdict:
					pkg_useforce = ordered_by_atom_specificity(cpdict, pkg)
					if pkg_useforce:
						useforce.extend(pkg_useforce)
				if stable:
					cpdict = self._repo_pusestableforce_dict.get(repo, {}).get(cp)
					if cpdict:
						pkg_useforce = ordered_by_atom_specificity(cpdict, pkg)
						if pkg_useforce:
							useforce.extend(pkg_useforce)

		for i, puseforce_dict in enumerate(self._puseforce_list):
			if self._useforce_list[i]:
				useforce.append(self._useforce_list[i])
			if stable and self._usestableforce_list[i]:
				useforce.append(self._usestableforce_list[i])
			cpdict = puseforce_dict.get(cp)
			if cpdict:
				pkg_useforce = ordered_by_atom_specificity(cpdict, pkg)
				if pkg_useforce:
					useforce.extend(pkg_useforce)
			if stable:
				cpdict = self._pusestableforce_list[i].get(cp)
				if cpdict:
					pkg_useforce = ordered_by_atom_specificity(cpdict, pkg)
					if pkg_useforce:
						useforce.extend(pkg_useforce)

		return frozenset(stack_lists(useforce, incremental=True))

	def getUseAliases(self, pkg):
		if hasattr(pkg, "eapi") and not eapi_has_use_aliases(pkg.eapi):
			return {}

		cp = getattr(pkg, "cp", None)
		if cp is None:
			slot = dep_getslot(pkg)
			repo = dep_getrepo(pkg)
			pkg = _pkg_str(remove_slot(pkg), slot=slot, repo=repo)
			cp = pkg.cp

		usealiases = {}

		if hasattr(pkg, "repo") and pkg.repo != Package.UNKNOWN_REPO:
			repos = []
			try:
				repos.extend(repo.name for repo in
					self.repositories[pkg.repo].masters)
			except KeyError:
				pass
			repos.append(pkg.repo)
			for repo in repos:
				usealiases_dict = self._repo_usealiases_dict.get(repo, {})
				for real_flag, aliases in usealiases_dict.items():
					for alias in aliases:
						if any(alias in v for k, v in usealiases.items() if k != real_flag):
							writemsg(_("--- Duplicated USE flag alias for '%s%s%s': '%s'\n") %
								(pkg.cpv, _repo_separator, pkg.repo, alias), noiselevel=-1)
						else:
							usealiases.setdefault(real_flag, []).append(alias)
				cp_usealiases_dict = self._repo_pusealiases_dict.get(repo, {}).get(cp)
				if cp_usealiases_dict:
					usealiases_dict_list = ordered_by_atom_specificity(cp_usealiases_dict, pkg)
					for usealiases_dict in usealiases_dict_list:
						for real_flag, aliases in usealiases_dict.items():
							for alias in aliases:
								if any(alias in v for k, v in usealiases.items() if k != real_flag):
									writemsg(_("--- Duplicated USE flag alias for '%s%s%s': '%s'\n") %
										(pkg.cpv, _repo_separator, pkg.repo, alias), noiselevel=-1)
								else:
									usealiases.setdefault(real_flag, []).append(alias)

		return usealiases

	def getPUSE(self, pkg):
		cp = getattr(pkg, "cp", None)
		if cp is None:
			slot = dep_getslot(pkg)
			repo = dep_getrepo(pkg)
			pkg = _pkg_str(remove_slot(pkg), slot=slot, repo=repo)
			cp = pkg.cp
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
