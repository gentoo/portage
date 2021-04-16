# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'MaskManager',
)

import warnings

from portage import os
from portage.dep import ExtendedAtomDict, match_from_list
from portage.localization import _
from portage.repository.config import allow_profile_repo_deps
from portage.util import append_repo, grabfile_package, stack_lists, writemsg
from portage.versions import _pkg_str

class MaskManager:

	def __init__(self, repositories, profiles, abs_user_config,
		user_config=True, strict_umatched_removal=False):
		self._punmaskdict = ExtendedAtomDict(list)
		self._pmaskdict = ExtendedAtomDict(list)
		# Preserves atoms that are eliminated by negative
		# incrementals in user_pkgmasklines.
		self._pmaskdict_raw = ExtendedAtomDict(list)

		#Read profile/package.mask from every repo.
		#Repositories inherit masks from their parent profiles and
		#are able to remove mask from them with -atoms.
		#Such a removal affects only the current repo, but not the parent.
		#Add ::repo specs to every atom to make sure atoms only affect
		#packages from the current repo.

		# Cache the repository-wide package.mask files as a particular
		# repo may be often referenced by others as the master.
		pmask_cache = {}

		def grab_pmask(loc, repo_config):
			if loc not in pmask_cache:
				path = os.path.join(loc, 'profiles', 'package.mask')
				pmask_cache[loc] = grabfile_package(path,
						recursive=repo_config.portage1_profiles,
						remember_source_file=True, verify_eapi=True,
						eapi_default=repo_config.eapi,
						allow_repo=allow_profile_repo_deps(repo_config),
						allow_build_id=("build-id"
						in repo_config.profile_formats))
				if repo_config.portage1_profiles_compat and os.path.isdir(path):
					warnings.warn(_("Repository '%(repo_name)s' is implicitly using "
						"'portage-1' profile format in its profiles/package.mask, but "
						"the repository profiles are not marked as that format.  This will break "
						"in the future.  Please either convert the following paths "
						"to files, or add\nprofile-formats = portage-1\nto the "
						"repository's layout.conf.\n")
						% dict(repo_name=repo_config.name))

			return pmask_cache[loc]

		repo_pkgmasklines = []
		for repo in repositories.repos_with_profiles():
			lines = []
			repo_lines = grab_pmask(repo.location, repo)
			removals = frozenset(line[0][1:] for line in repo_lines
				if line[0][:1] == "-")
			matched_removals = set()
			for master in repo.masters:
				master_lines = grab_pmask(master.location, master)
				for line in master_lines:
					if line[0] in removals:
						matched_removals.add(line[0])
				# Since we don't stack masters recursively, there aren't any
				# atoms earlier in the stack to be matched by negative atoms in
				# master_lines. Also, repo_lines may contain negative atoms
				# that are intended to negate atoms from a different master
				# than the one with which we are currently stacking. Therefore,
				# we disable warn_for_unmatched_removal here (see bug #386569).
				lines.append(stack_lists([master_lines, repo_lines], incremental=1,
					remember_source_file=True, warn_for_unmatched_removal=False))

			# It's safe to warn for unmatched removal if masters have not
			# been overridden by the user, which is guaranteed when
			# user_config is false (when called by repoman).
			if repo.masters:
				unmatched_removals = removals.difference(matched_removals)
				if unmatched_removals and not user_config:
					source_file = os.path.join(repo.location,
						"profiles", "package.mask")
					unmatched_removals = list(unmatched_removals)
					if len(unmatched_removals) > 3:
						writemsg(
							_("--- Unmatched removal atoms in %s: %s and %s more\n") %
							(source_file,
							", ".join("-" + x for x in unmatched_removals[:3]),
							len(unmatched_removals) - 3), noiselevel=-1)
					else:
						writemsg(
							_("--- Unmatched removal atom(s) in %s: %s\n") %
							(source_file,
							", ".join("-" + x for x in unmatched_removals)),
							noiselevel=-1)

			else:
				lines.append(stack_lists([repo_lines], incremental=1,
					remember_source_file=True, warn_for_unmatched_removal=not user_config,
					strict_warn_for_unmatched_removal=strict_umatched_removal))
			repo_pkgmasklines.extend(append_repo(stack_lists(lines), repo.name, remember_source_file=True))

		repo_pkgunmasklines = []
		for repo in repositories.repos_with_profiles():
			if not repo.portage1_profiles:
				continue
			repo_lines = grabfile_package(os.path.join(repo.location, "profiles", "package.unmask"), \
				recursive=1, remember_source_file=True,
				verify_eapi=True, eapi_default=repo.eapi,
				allow_repo=allow_profile_repo_deps(repo),
				allow_build_id=("build-id" in repo.profile_formats))
			lines = stack_lists([repo_lines], incremental=1, \
				remember_source_file=True, warn_for_unmatched_removal=True,
				strict_warn_for_unmatched_removal=strict_umatched_removal)
			repo_pkgunmasklines.extend(append_repo(lines, repo.name, remember_source_file=True))

		#Read package.mask from the user's profile. Stack them in the end
		#to allow profiles to override masks from their parent profiles.
		profile_pkgmasklines = []
		profile_pkgunmasklines = []
		for x in profiles:
			profile_pkgmasklines.append(grabfile_package(
				os.path.join(x.location, "package.mask"),
				recursive=x.portage1_directories,
				remember_source_file=True, verify_eapi=True,
				eapi=x.eapi, eapi_default=None,
				allow_repo=allow_profile_repo_deps(x),
				allow_build_id=x.allow_build_id))
			if x.portage1_directories:
				profile_pkgunmasklines.append(grabfile_package(
					os.path.join(x.location, "package.unmask"),
					recursive=x.portage1_directories,
					remember_source_file=True, verify_eapi=True,
					eapi=x.eapi, eapi_default=None,
					allow_repo=allow_profile_repo_deps(x),
					allow_build_id=x.allow_build_id))
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
				allow_wildcard=True, allow_repo=True,
				remember_source_file=True, verify_eapi=False,
				allow_build_id=True)
			user_pkgunmasklines = grabfile_package(
				os.path.join(abs_user_config, "package.unmask"), recursive=1, \
				allow_wildcard=True, allow_repo=True,
				remember_source_file=True, verify_eapi=False,
				allow_build_id=True)

		#Stack everything together. At this point, only user_pkgmasklines may contain -atoms.
		#Don't warn for unmatched -atoms here, since we don't do it for any other user config file.
		raw_pkgmasklines = stack_lists([repo_pkgmasklines, profile_pkgmasklines], \
			incremental=1, remember_source_file=True, warn_for_unmatched_removal=False, ignore_repo=True)
		pkgmasklines = stack_lists([repo_pkgmasklines, profile_pkgmasklines, user_pkgmasklines], \
			incremental=1, remember_source_file=True, warn_for_unmatched_removal=False, ignore_repo=True)
		pkgunmasklines = stack_lists([repo_pkgunmasklines, profile_pkgunmasklines, user_pkgunmasklines], \
			incremental=1, remember_source_file=True, warn_for_unmatched_removal=False, ignore_repo=True)

		for x, source_file in raw_pkgmasklines:
			self._pmaskdict_raw.setdefault(x.cp, []).append(x)

		for x, source_file in pkgmasklines:
			self._pmaskdict.setdefault(x.cp, []).append(x)

		for x, source_file in pkgunmasklines:
			self._punmaskdict.setdefault(x.cp, []).append(x)

		for d in (self._pmaskdict_raw, self._pmaskdict, self._punmaskdict):
			for k, v in d.items():
				d[k] = tuple(v)

	def _getMaskAtom(self, cpv, slot, repo, unmask_atoms=None):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask.

		@param cpv: The package name
		@type cpv: String
		@param slot: The package's slot
		@type slot: String
		@param repo: The package's repository [optional]
		@type repo: String
		@param unmask_atoms: if desired pass in self._punmaskdict.get(cp)
		@type unmask_atoms: list
		@rtype: String
		@return: A matching atom string or None if one is not found.
		"""

		try:
			cpv.slot
		except AttributeError:
			pkg = _pkg_str(cpv, slot=slot, repo=repo)
		else:
			pkg = cpv

		mask_atoms = self._pmaskdict.get(pkg.cp)
		if mask_atoms:
			pkg_list = [pkg]
			for x in mask_atoms:
				if not match_from_list(x, pkg_list):
					continue
				if unmask_atoms:
					for y in unmask_atoms:
						if match_from_list(y, pkg_list):
							return None
				return x
		return None


	def getMaskAtom(self, cpv, slot, repo):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask.

		@param cpv: The package name
		@type cpv: String
		@param slot: The package's slot
		@type slot: String
		@param repo: The package's repository [optional]
		@type repo: String
		@rtype: String
		@return: A matching atom string or None if one is not found.
		"""

		try:
			cpv.slot
		except AttributeError:
			pkg = _pkg_str(cpv, slot=slot, repo=repo)
		else:
			pkg = cpv

		return self._getMaskAtom(pkg, slot, repo,
			self._punmaskdict.get(pkg.cp))


	def getRawMaskAtom(self, cpv, slot, repo):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists. It HAS NOT! been cancelled by any package.unmask.

		@param cpv: The package name
		@type cpv: String
		@param slot: The package's slot
		@type slot: String
		@param repo: The package's repository [optional]
		@type repo: String
		@rtype: String
		@return: A matching atom string or None if one is not found.
		"""

		return self._getMaskAtom(cpv, slot, repo)
