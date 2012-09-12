# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'LocationsManager',
)

import collections
import io
import warnings

import portage
from portage import os, eapi_is_supported, _encodings, _unicode_encode
from portage.const import CUSTOM_PROFILE_PATH, GLOBAL_CONFIG_PATH, \
	PROFILE_PATH, USER_CONFIG_PATH
from portage.exception import DirectoryNotFound, ParseError
from portage.localization import _
from portage.util import ensure_dirs, grabfile, \
	normalize_path, shlex_split, writemsg
from portage.repository.config import parse_layout_conf, \
	_portage1_profiles_allow_directories


_PORTAGE1_DIRECTORIES = frozenset([
	'package.mask', 'package.provided',
	'package.use', 'package.use.mask', 'package.use.force',
	'use.mask', 'use.force'])

_profile_node = collections.namedtuple('_profile_node',
	'location portage1_directories')

_allow_parent_colon = frozenset(
	["portage-2"])

class LocationsManager(object):

	def __init__(self, config_root=None, eprefix=None, config_profile_path=None, local_config=True, \
		target_root=None):
		self.user_profile_dir = None
		self._local_repo_conf_path = None
		self.eprefix = eprefix
		self.config_root = config_root
		self.target_root = target_root
		self._user_config = local_config

		if self.eprefix is None:
			self.eprefix = portage.const.EPREFIX

		if self.config_root is None:
			self.config_root = self.eprefix + os.sep

		self.config_root = normalize_path(os.path.abspath(
			self.config_root)).rstrip(os.path.sep) + os.path.sep

		self._check_var_directory("PORTAGE_CONFIGROOT", self.config_root)
		self.abs_user_config = os.path.join(self.config_root, USER_CONFIG_PATH)
		self.config_profile_path = config_profile_path

	def load_profiles(self, repositories, known_repository_paths):
		known_repository_paths = set(os.path.realpath(x)
			for x in known_repository_paths)

		known_repos = []
		for x in known_repository_paths:
			try:
				layout_data = {"profile-formats":
					repositories.get_repo_for_location(x).profile_formats}
			except KeyError:
				layout_data = parse_layout_conf(x)[0]
			# force a trailing '/' for ease of doing startswith checks
			known_repos.append((x + '/', layout_data))
		known_repos = tuple(known_repos)

		if self.config_profile_path is None:
			self.config_profile_path = \
				os.path.join(self.config_root, PROFILE_PATH)
			if os.path.isdir(self.config_profile_path):
				self.profile_path = self.config_profile_path
			else:
				self.config_profile_path = \
					os.path.join(self.config_root, 'etc', 'make.profile')
				if os.path.isdir(self.config_profile_path):
					self.profile_path = self.config_profile_path
				else:
					self.profile_path = None
		else:
			# NOTE: repoman may pass in an empty string
			# here, in order to create an empty profile
			# for checking dependencies of packages with
			# empty KEYWORDS.
			self.profile_path = self.config_profile_path


		# The symlink might not exist or might not be a symlink.
		self.profiles = []
		self.profiles_complex = []
		if self.profile_path:
			try:
				self._addProfile(os.path.realpath(self.profile_path),
					repositories, known_repos)
			except ParseError as e:
				writemsg(_("!!! Unable to parse profile: '%s'\n") % \
					self.profile_path, noiselevel=-1)
				writemsg("!!! ParseError: %s\n" % str(e), noiselevel=-1)
				self.profiles = []
				self.profiles_complex = []

		if self._user_config and self.profiles:
			custom_prof = os.path.join(
				self.config_root, CUSTOM_PROFILE_PATH)
			if os.path.exists(custom_prof):
				self.user_profile_dir = custom_prof
				self.profiles.append(custom_prof)
				self.profiles_complex.append(_profile_node(custom_prof, True))
			del custom_prof

		self.profiles = tuple(self.profiles)
		self.profiles_complex = tuple(self.profiles_complex)

	def _check_var_directory(self, varname, var):
		if not os.path.isdir(var):
			writemsg(_("!!! Error: %s='%s' is not a directory. "
				"Please correct this.\n") % (varname, var),
				noiselevel=-1)
			raise DirectoryNotFound(var)

	def _addProfile(self, currentPath, repositories, known_repos):
		current_abs_path = os.path.abspath(currentPath)
		allow_directories = True
		allow_parent_colon = True
		repo_loc = None
		compat_mode = False
		intersecting_repos = [x for x in known_repos if current_abs_path.startswith(x[0])]
		if intersecting_repos:
			# protect against nested repositories.  Insane configuration, but the longest
			# path will be the correct one.
			repo_loc, layout_data = max(intersecting_repos, key=lambda x:len(x[0]))
			allow_directories = any(x in _portage1_profiles_allow_directories
				for x in layout_data['profile-formats'])
			compat_mode = layout_data['profile-formats'] == ('portage-1-compat',)
			allow_parent_colon = any(x in _allow_parent_colon
				for x in layout_data['profile-formats'])

		if compat_mode:
			offenders = _PORTAGE1_DIRECTORIES.intersection(os.listdir(currentPath))
			offenders = sorted(x for x in offenders
				if os.path.isdir(os.path.join(currentPath, x)))
			if offenders:
				warnings.warn(_("Profile '%(profile_path)s' in repository "
					"'%(repo_name)s' is implicitly using 'portage-1' profile format, but "
					"the repository profiles are not marked as that format.  This will break "
					"in the future.  Please either convert the following paths "
					"to files, or add\nprofile-formats = portage-1\nto the "
					"repositories layout.conf.  Files: '%(files)s'\n")
					% dict(profile_path=currentPath, repo_name=repo_loc,
						files=', '.join(offenders)))

		parentsFile = os.path.join(currentPath, "parent")
		eapi_file = os.path.join(currentPath, "eapi")
		f = None
		try:
			f = io.open(_unicode_encode(eapi_file,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace')
			eapi = f.readline().strip()
		except IOError:
			pass
		else:
			if not eapi_is_supported(eapi):
				raise ParseError(_(
					"Profile contains unsupported "
					"EAPI '%s': '%s'") % \
					(eapi, os.path.realpath(eapi_file),))
		finally:
			if f is not None:
				f.close()
		if os.path.exists(parentsFile):
			parents = grabfile(parentsFile)
			if not parents:
				raise ParseError(
					_("Empty parent file: '%s'") % parentsFile)
			for parentPath in parents:
				abs_parent = parentPath[:1] == os.sep
				if not abs_parent and allow_parent_colon:
					parentPath = self._expand_parent_colon(parentsFile,
						parentPath, repo_loc, repositories)

				# NOTE: This os.path.join() call is intended to ignore
				# currentPath if parentPath is already absolute.
				parentPath = normalize_path(os.path.join(
					currentPath, parentPath))

				if abs_parent or repo_loc is None or \
					not parentPath.startswith(repo_loc):
					# It seems that this parent may point outside
					# of the current repo, so realpath it.
					parentPath = os.path.realpath(parentPath)

				if os.path.exists(parentPath):
					self._addProfile(parentPath, repositories, known_repos)
				else:
					raise ParseError(
						_("Parent '%s' not found: '%s'") %  \
						(parentPath, parentsFile))

		self.profiles.append(currentPath)
		self.profiles_complex.append(
			_profile_node(currentPath, allow_directories))

	def _expand_parent_colon(self, parentsFile, parentPath,
		repo_loc, repositories):
		colon = parentPath.find(":")
		if colon == -1:
			return parentPath

		if colon == 0:
			if repo_loc is None:
				raise ParseError(
					_("Parent '%s' not found: '%s'") %  \
					(parentPath, parentsFile))
			else:
				parentPath = normalize_path(os.path.join(
					repo_loc, 'profiles', parentPath[colon+1:]))
		else:
			p_repo_name = parentPath[:colon]
			try:
				p_repo_loc = repositories.get_location_for_name(p_repo_name)
			except KeyError:
				raise ParseError(
					_("Parent '%s' not found: '%s'") %  \
					(parentPath, parentsFile))
			else:
				parentPath = normalize_path(os.path.join(
					p_repo_loc, 'profiles', parentPath[colon+1:]))

		return parentPath

	def set_root_override(self, root_overwrite=None):
		# Allow ROOT setting to come from make.conf if it's not overridden
		# by the constructor argument (from the calling environment).
		if self.target_root is None and root_overwrite is not None:
			self.target_root = root_overwrite
			if not self.target_root.strip():
				self.target_root = None
		if self.target_root is None:
			self.target_root = "/"

		self.target_root = normalize_path(os.path.abspath(
			self.target_root)).rstrip(os.path.sep) + os.path.sep

		ensure_dirs(self.target_root)
		self._check_var_directory("ROOT", self.target_root)

		self.eroot = self.target_root.rstrip(os.sep) + self.eprefix + os.sep

		# make.globals should not be relative to config_root
		# because it only contains constants. However, if EPREFIX
		# is set then there are two possible scenarios:
		# 1) If $ROOT == "/" then make.globals should be
		#    relative to EPREFIX.
		# 2) If $ROOT != "/" then the correct location of
		#    make.globals needs to be specified in the constructor
		#    parameters, since it's a property of the host system
		#    (and the current config represents the target system).
		self.global_config_path = GLOBAL_CONFIG_PATH
		if self.eprefix:
			if self.target_root == "/":
				# case (1) above
				self.global_config_path = os.path.join(self.eprefix,
					GLOBAL_CONFIG_PATH.lstrip(os.sep))
			else:
				# case (2) above
				# For now, just assume make.globals is relative
				# to EPREFIX.
				# TODO: Pass in more info to the constructor,
				# so we know the host system configuration.
				self.global_config_path = os.path.join(self.eprefix,
					GLOBAL_CONFIG_PATH.lstrip(os.sep))

	def set_port_dirs(self, portdir, portdir_overlay):
		self.portdir = portdir
		self.portdir_overlay = portdir_overlay
		if self.portdir_overlay is None:
			self.portdir_overlay = ""

		self.overlay_profiles = []
		for ov in shlex_split(self.portdir_overlay):
			ov = normalize_path(ov)
			profiles_dir = os.path.join(ov, "profiles")
			if os.path.isdir(profiles_dir):
				self.overlay_profiles.append(profiles_dir)

		self.profile_locations = [os.path.join(portdir, "profiles")] + self.overlay_profiles
		self.profile_and_user_locations = self.profile_locations[:]
		if self._user_config:
			self.profile_and_user_locations.append(self.abs_user_config)

		self.profile_locations = tuple(self.profile_locations)
		self.profile_and_user_locations = tuple(self.profile_and_user_locations)
