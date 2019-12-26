# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	'autouse', 'best_from_dict', 'check_config_instance', 'config',
]

import copy
from itertools import chain
import grp
import logging
import platform
import pwd
import re
import sys
import traceback
import warnings

from _emerge.Package import Package
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.data:portage_gid',
	'portage.dep.soname.SonameAtom:SonameAtom',
	'portage.dbapi.vartree:vartree',
	'portage.package.ebuild.doebuild:_phase_func_map',
	'portage.util.compression_probe:_compressors',
	'portage.util.locale:check_locale,split_LC_ALL',
)
from portage import bsd_chflags, \
	load_mod, os, selinux, _unicode_decode
from portage.const import CACHE_PATH, \
	DEPCACHE_PATH, INCREMENTALS, MAKE_CONF_FILE, \
	MODULES_FILE_PATH, PORTAGE_BASE_PATH, \
	PRIVATE_PATH, PROFILE_PATH, USER_CONFIG_PATH, \
	USER_VIRTUALS_FILE
from portage.dbapi import dbapi
from portage.dep import Atom, isvalidatom, match_from_list, use_reduce, _repo_separator, _slot_separator
from portage.eapi import (eapi_exports_AA, eapi_exports_merge_type,
	eapi_supports_prefix, eapi_exports_replace_vars, _get_eapi_attrs)
from portage.env.loaders import KeyValuePairFileLoader
from portage.exception import InvalidDependString, PortageException
from portage.localization import _
from portage.output import colorize
from portage.process import fakeroot_capable, sandbox_capable
from portage.repository.config import (
	allow_profile_repo_deps,
	load_repository_config,
)
from portage.util import ensure_dirs, getconfig, grabdict, \
	grabdict_package, grabfile, grabfile_package, LazyItemsDict, \
	normalize_path, shlex_split, stack_dictlist, stack_dicts, stack_lists, \
	writemsg, writemsg_level, _eapi_cache
from portage.util.install_mask import _raise_exc
from portage.util.path import first_existing
from portage.util._path import exists_raise_eaccess, isdir_raise_eaccess
from portage.versions import catpkgsplit, catsplit, cpv_getkey, _pkg_str

from portage.package.ebuild._config import special_env_vars
from portage.package.ebuild._config.env_var_validation import validate_cmd_var
from portage.package.ebuild._config.features_set import features_set
from portage.package.ebuild._config.KeywordsManager import KeywordsManager
from portage.package.ebuild._config.LicenseManager import LicenseManager
from portage.package.ebuild._config.UseManager import UseManager
from portage.package.ebuild._config.LocationsManager import LocationsManager
from portage.package.ebuild._config.MaskManager import MaskManager
from portage.package.ebuild._config.VirtualsManager import VirtualsManager
from portage.package.ebuild._config.helper import ordered_by_atom_specificity, prune_incremental
from portage.package.ebuild._config.unpack_dependencies import load_unpack_dependencies_configuration


_feature_flags_cache = {}

def _get_feature_flags(eapi_attrs):
	cache_key = (eapi_attrs.feature_flag_test,)
	flags = _feature_flags_cache.get(cache_key)
	if flags is not None:
		return flags

	flags = []
	if eapi_attrs.feature_flag_test:
		flags.append("test")

	flags = frozenset(flags)
	_feature_flags_cache[cache_key] = flags
	return flags

def autouse(myvartree, use_cache=1, mysettings=None):
	warnings.warn("portage.autouse() is deprecated",
		DeprecationWarning, stacklevel=2)
	return ""

def check_config_instance(test):
	if not isinstance(test, config):
		raise TypeError("Invalid type for config object: %s (should be %s)" % (test.__class__, config))

def best_from_dict(key, top_dict, key_order, EmptyOnError=1, FullCopy=1, AllowEmpty=1):
	for x in key_order:
		if x in top_dict and key in top_dict[x]:
			if FullCopy:
				return copy.deepcopy(top_dict[x][key])
			return top_dict[x][key]
	if EmptyOnError:
		return ""
	raise KeyError("Key not found in list; '%s'" % key)

def _lazy_iuse_regex(iuse_implicit):
	"""
	The PORTAGE_IUSE value is lazily evaluated since re.escape() is slow
	and the value is only used when an ebuild phase needs to be executed
	(it's used only to generate QA notices).
	"""
	# Escape anything except ".*" which is supposed to pass through from
	# _get_implicit_iuse().
	regex = sorted(re.escape(x) for x in iuse_implicit)
	regex = "^(%s)$" % "|".join(regex)
	regex = regex.replace("\\.\\*", ".*")
	return regex

class _iuse_implicit_match_cache:

	def __init__(self, settings):
		self._iuse_implicit_re = re.compile("^(%s)$" % \
			"|".join(settings._get_implicit_iuse()))
		self._cache = {}

	def __call__(self, flag):
		"""
		Returns True if the flag is matched, False otherwise.
		"""
		try:
			return self._cache[flag]
		except KeyError:
			m = self._iuse_implicit_re.match(flag) is not None
			self._cache[flag] = m
			return m

class config:
	"""
	This class encompasses the main portage configuration.  Data is pulled from
	ROOT/PORTDIR/profiles/, from ROOT/etc/make.profile incrementally through all
	parent profiles as well as from ROOT/PORTAGE_CONFIGROOT/* for user specified
	overrides.

	Generally if you need data like USE flags, FEATURES, environment variables,
	virtuals ...etc you look in here.
	"""

	_constant_keys = frozenset(['PORTAGE_BIN_PATH', 'PORTAGE_GID',
		'PORTAGE_PYM_PATH', 'PORTAGE_PYTHONPATH'])

	_deprecated_keys = {'PORTAGE_LOGDIR': 'PORT_LOGDIR',
		'PORTAGE_LOGDIR_CLEAN': 'PORT_LOGDIR_CLEAN',
		'SIGNED_OFF_BY': 'DCO_SIGNED_OFF_BY'}

	_setcpv_aux_keys = ('BDEPEND', 'DEFINED_PHASES', 'DEPEND', 'EAPI', 'IDEPEND',
		'INHERITED', 'IUSE', 'REQUIRED_USE', 'KEYWORDS', 'LICENSE', 'PDEPEND',
		'PROPERTIES', 'RDEPEND', 'SLOT',
		'repository', 'RESTRICT', 'LICENSE',)

	_module_aliases = {
		"cache.metadata_overlay.database" : "portage.cache.flat_hash.mtime_md5_database",
		"portage.cache.metadata_overlay.database" : "portage.cache.flat_hash.mtime_md5_database",
	}

	_case_insensitive_vars = special_env_vars.case_insensitive_vars
	_default_globals = special_env_vars.default_globals
	_env_blacklist = special_env_vars.env_blacklist
	_environ_filter = special_env_vars.environ_filter
	_environ_whitelist = special_env_vars.environ_whitelist
	_environ_whitelist_re = special_env_vars.environ_whitelist_re
	_global_only_vars = special_env_vars.global_only_vars

	def __init__(self, clone=None, mycpv=None, config_profile_path=None,
		config_incrementals=None, config_root=None, target_root=None,
		sysroot=None, eprefix=None, local_config=True, env=None,
		_unmatched_removal=False, repositories=None):
		"""
		@param clone: If provided, init will use deepcopy to copy by value the instance.
		@type clone: Instance of config class.
		@param mycpv: CPV to load up (see setcpv), this is the same as calling init with mycpv=None
		and then calling instance.setcpv(mycpv).
		@type mycpv: String
		@param config_profile_path: Configurable path to the profile (usually PROFILE_PATH from portage.const)
		@type config_profile_path: String
		@param config_incrementals: List of incremental variables
			(defaults to portage.const.INCREMENTALS)
		@type config_incrementals: List
		@param config_root: path to read local config from (defaults to "/", see PORTAGE_CONFIGROOT)
		@type config_root: String
		@param target_root: the target root, which typically corresponds to the
			value of the $ROOT env variable (default is /)
		@type target_root: String
		@param sysroot: the sysroot to build against, which typically corresponds
			 to the value of the $SYSROOT env variable (default is /)
		@type sysroot: String
		@param eprefix: set the EPREFIX variable (default is portage.const.EPREFIX)
		@type eprefix: String
		@param local_config: Enables loading of local config (/etc/portage); used most by repoman to
		ignore local config (keywording and unmasking)
		@type local_config: Boolean
		@param env: The calling environment which is used to override settings.
			Defaults to os.environ if unspecified.
		@type env: dict
		@param _unmatched_removal: Enabled by repoman when the
			--unmatched-removal option is given.
		@type _unmatched_removal: Boolean
		@param repositories: Configuration of repositories.
			Defaults to portage.repository.config.load_repository_config().
		@type repositories: Instance of portage.repository.config.RepoConfigLoader class.
		"""

		# This is important when config is reloaded after emerge --sync.
		_eapi_cache.clear()

		# When initializing the global portage.settings instance, avoid
		# raising exceptions whenever possible since exceptions thrown
		# from 'import portage' or 'import portage.exceptions' statements
		# can practically render the api unusable for api consumers.
		tolerant = hasattr(portage, '_initializing_globals')
		self._tolerant = tolerant
		self._unmatched_removal = _unmatched_removal

		self.locked   = 0
		self.mycpv    = None
		self._setcpv_args_hash = None
		self.puse     = ""
		self._penv    = []
		self.modifiedkeys = []
		self.uvlist = []
		self._accept_chost_re = None
		self._accept_properties = None
		self._accept_restrict = None
		self._features_overrides = []
		self._make_defaults = None
		self._parent_stable = None
		self._soname_provided = None

		# _unknown_features records unknown features that
		# have triggered warning messages, and ensures that
		# the same warning isn't shown twice.
		self._unknown_features = set()

		self.local_config = local_config

		if clone:
			# For immutable attributes, use shallow copy for
			# speed and memory conservation.
			self._tolerant = clone._tolerant
			self._unmatched_removal = clone._unmatched_removal
			self.categories = clone.categories
			self.depcachedir = clone.depcachedir
			self.incrementals = clone.incrementals
			self.module_priority = clone.module_priority
			self.profile_path = clone.profile_path
			self.profiles = clone.profiles
			self.packages = clone.packages
			self.repositories = clone.repositories
			self.unpack_dependencies = clone.unpack_dependencies
			self._default_features_use = clone._default_features_use
			self._iuse_effective = clone._iuse_effective
			self._iuse_implicit_match = clone._iuse_implicit_match
			self._non_user_variables = clone._non_user_variables
			self._env_d_blacklist = clone._env_d_blacklist
			self._pbashrc = clone._pbashrc
			self._repo_make_defaults = clone._repo_make_defaults
			self.usemask = clone.usemask
			self.useforce = clone.useforce
			self.puse = clone.puse
			self.user_profile_dir = clone.user_profile_dir
			self.local_config = clone.local_config
			self.make_defaults_use = clone.make_defaults_use
			self.mycpv = clone.mycpv
			self._setcpv_args_hash = clone._setcpv_args_hash
			self._soname_provided = clone._soname_provided
			self._profile_bashrc = clone._profile_bashrc

			# immutable attributes (internal policy ensures lack of mutation)
			self._locations_manager = clone._locations_manager
			self._use_manager = clone._use_manager
			# force instantiation of lazy immutable objects when cloning, so
			# that they're not instantiated more than once
			self._keywords_manager_obj = clone._keywords_manager
			self._mask_manager_obj = clone._mask_manager

			# shared mutable attributes
			self._unknown_features = clone._unknown_features

			self.modules         = copy.deepcopy(clone.modules)
			self._penv = copy.deepcopy(clone._penv)

			self.configdict = copy.deepcopy(clone.configdict)
			self.configlist = [
				self.configdict['env.d'],
				self.configdict['repo'],
				self.configdict['features'],
				self.configdict['pkginternal'],
				self.configdict['globals'],
				self.configdict['defaults'],
				self.configdict['conf'],
				self.configdict['pkg'],
				self.configdict['env'],
			]
			self.lookuplist = self.configlist[:]
			self.lookuplist.reverse()
			self._use_expand_dict = copy.deepcopy(clone._use_expand_dict)
			self.backupenv  = self.configdict["backupenv"]
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.pprovideddict = copy.deepcopy(clone.pprovideddict)
			self.features = features_set(self)
			self.features._features = copy.deepcopy(clone.features._features)
			self._features_overrides = copy.deepcopy(clone._features_overrides)

			#Strictly speaking _license_manager is not immutable. Users need to ensure that
			#extract_global_changes() is called right after __init__ (if at all).
			#It also has the mutable member _undef_lic_groups. It is used to track
			#undefined license groups, to not display an error message for the same
			#group again and again. Because of this, it's useful to share it between
			#all LicenseManager instances.
			self._license_manager = clone._license_manager

			# force instantiation of lazy objects when cloning, so
			# that they're not instantiated more than once
			self._virtuals_manager_obj = copy.deepcopy(clone._virtuals_manager)

			self._accept_properties = copy.deepcopy(clone._accept_properties)
			self._ppropertiesdict = copy.deepcopy(clone._ppropertiesdict)
			self._accept_restrict = copy.deepcopy(clone._accept_restrict)
			self._paccept_restrict = copy.deepcopy(clone._paccept_restrict)
			self._penvdict = copy.deepcopy(clone._penvdict)
			self._pbashrcdict = copy.deepcopy(clone._pbashrcdict)
			self._expand_map = copy.deepcopy(clone._expand_map)

		else:
			# lazily instantiated objects
			self._keywords_manager_obj = None
			self._mask_manager_obj = None
			self._virtuals_manager_obj = None

			locations_manager = LocationsManager(config_root=config_root,
				config_profile_path=config_profile_path, eprefix=eprefix,
				local_config=local_config, target_root=target_root,
				sysroot=sysroot)
			self._locations_manager = locations_manager

			eprefix = locations_manager.eprefix
			config_root = locations_manager.config_root
			sysroot = locations_manager.sysroot
			esysroot = locations_manager.esysroot
			broot = locations_manager.broot
			abs_user_config = locations_manager.abs_user_config
			make_conf_paths = [
				os.path.join(config_root, 'etc', 'make.conf'),
				os.path.join(config_root, MAKE_CONF_FILE)
			]
			try:
				if os.path.samefile(*make_conf_paths):
					make_conf_paths.pop()
			except OSError:
				pass

			make_conf_count = 0
			make_conf = {}
			for x in make_conf_paths:
				mygcfg = getconfig(x,
					tolerant=tolerant, allow_sourcing=True,
					expand=make_conf, recursive=True)
				if mygcfg is not None:
					make_conf.update(mygcfg)
					make_conf_count += 1

			if make_conf_count == 2:
				writemsg("!!! %s\n" %
					_("Found 2 make.conf files, using both '%s' and '%s'") %
					tuple(make_conf_paths), noiselevel=-1)

			# __* variables set in make.conf are local and are not be propagated.
			make_conf = {k: v for k, v in make_conf.items() if not k.startswith("__")}

			# Allow ROOT setting to come from make.conf if it's not overridden
			# by the constructor argument (from the calling environment).
			locations_manager.set_root_override(make_conf.get("ROOT"))
			target_root = locations_manager.target_root
			eroot = locations_manager.eroot
			self.global_config_path = locations_manager.global_config_path

			# The expand_map is used for variable substitution
			# in getconfig() calls, and the getconfig() calls
			# update expand_map with the value of each variable
			# assignment that occurs. Variable substitution occurs
			# in the following order, which corresponds to the
			# order of appearance in self.lookuplist:
			#
			#   * env.d
			#   * make.globals
			#   * make.defaults
			#   * make.conf
			#
			# Notably absent is "env", since we want to avoid any
			# interaction with the calling environment that might
			# lead to unexpected results.

			env_d = getconfig(os.path.join(eroot, "etc", "profile.env"),
				tolerant=tolerant, expand=False) or {}
			expand_map = env_d.copy()
			self._expand_map = expand_map

			# Allow make.globals and make.conf to set paths relative to vars like ${EPREFIX}.
			expand_map["BROOT"] = broot
			expand_map["EPREFIX"] = eprefix
			expand_map["EROOT"] = eroot
			expand_map["ESYSROOT"] = esysroot
			expand_map["PORTAGE_CONFIGROOT"] = config_root
			expand_map["ROOT"] = target_root
			expand_map["SYSROOT"] = sysroot

			if portage._not_installed:
				make_globals_path = os.path.join(PORTAGE_BASE_PATH, "cnf", "make.globals")
			else:
				make_globals_path = os.path.join(self.global_config_path, "make.globals")
			old_make_globals = os.path.join(config_root, "etc", "make.globals")
			if os.path.isfile(old_make_globals) and \
				not os.path.samefile(make_globals_path, old_make_globals):
				# Don't warn if they refer to the same path, since
				# that can be used for backward compatibility with
				# old software.
				writemsg("!!! %s\n" %
					_("Found obsolete make.globals file: "
					"'%s', (using '%s' instead)") %
					(old_make_globals, make_globals_path),
					noiselevel=-1)

			make_globals = getconfig(make_globals_path,
				tolerant=tolerant, expand=expand_map)
			if make_globals is None:
				make_globals = {}

			for k, v in self._default_globals.items():
				make_globals.setdefault(k, v)

			if config_incrementals is None:
				self.incrementals = INCREMENTALS
			else:
				self.incrementals = config_incrementals
			if not isinstance(self.incrementals, frozenset):
				self.incrementals = frozenset(self.incrementals)

			self.module_priority    = ("user", "default")
			self.modules            = {}
			modules_file = os.path.join(config_root, MODULES_FILE_PATH)
			modules_loader = KeyValuePairFileLoader(modules_file, None, None)
			modules_dict, modules_errors = modules_loader.load()
			self.modules["user"] = modules_dict
			if self.modules["user"] is None:
				self.modules["user"] = {}
			user_auxdbmodule = \
				self.modules["user"].get("portdbapi.auxdbmodule")
			if user_auxdbmodule is not None and \
				user_auxdbmodule in self._module_aliases:
				warnings.warn("'%s' is deprecated: %s" %
				(user_auxdbmodule, modules_file))

			self.modules["default"] = {
				"portdbapi.auxdbmodule":  "portage.cache.flat_hash.mtime_md5_database",
			}

			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			self._use_expand_dict = {}
			# configlist will contain: [ env.d, globals, features, defaults, conf, pkg, backupenv, env ]
			self.configlist.append({})
			self.configdict["env.d"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["repo"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["features"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkginternal"] = self.configlist[-1]

			# env_d will be None if profile.env doesn't exist.
			if env_d:
				self.configdict["env.d"].update(env_d)

			# backupenv is used for calculating incremental variables.
			if env is None:
				env = os.environ

			# Avoid potential UnicodeDecodeError exceptions later.
			env_unicode = dict((_unicode_decode(k), _unicode_decode(v))
				for k, v in env.items())

			self.backupenv = env_unicode

			if env_d:
				# Remove duplicate values so they don't override updated
				# profile.env values later (profile.env is reloaded in each
				# call to self.regenerate).
				for k, v in env_d.items():
					try:
						if self.backupenv[k] == v:
							del self.backupenv[k]
					except KeyError:
						pass
				del k, v

			self.configdict["env"] = LazyItemsDict(self.backupenv)

			self.configlist.append(make_globals)
			self.configdict["globals"]=self.configlist[-1]

			self.make_defaults_use = []

			#Loading Repositories
			self["PORTAGE_CONFIGROOT"] = config_root
			self["ROOT"] = target_root
			self["SYSROOT"] = sysroot
			self["EPREFIX"] = eprefix
			self["EROOT"] = eroot
			self["ESYSROOT"] = esysroot
			self["BROOT"] = broot
			known_repos = []
			portdir = ""
			portdir_overlay = ""
			portdir_sync = None
			for confs in [make_globals, make_conf, self.configdict["env"]]:
				v = confs.get("PORTDIR")
				if v is not None:
					portdir = v
					known_repos.append(v)
				v = confs.get("PORTDIR_OVERLAY")
				if v is not None:
					portdir_overlay = v
					known_repos.extend(shlex_split(v))
				v = confs.get("SYNC")
				if v is not None:
					portdir_sync = v
				if 'PORTAGE_RSYNC_EXTRA_OPTS' in confs:
					self['PORTAGE_RSYNC_EXTRA_OPTS'] = confs['PORTAGE_RSYNC_EXTRA_OPTS']

			self["PORTDIR"] = portdir
			self["PORTDIR_OVERLAY"] = portdir_overlay
			if portdir_sync:
				self["SYNC"] = portdir_sync
			self.lookuplist = [self.configdict["env"]]
			if repositories is None:
				self.repositories = load_repository_config(self)
			else:
				self.repositories = repositories

			known_repos.extend(repo.location for repo in self.repositories)
			known_repos = frozenset(known_repos)

			self['PORTAGE_REPOSITORIES'] = self.repositories.config_string()
			self.backup_changes('PORTAGE_REPOSITORIES')

			#filling PORTDIR and PORTDIR_OVERLAY variable for compatibility
			main_repo = self.repositories.mainRepo()
			if main_repo is not None:
				self["PORTDIR"] = main_repo.location
				self.backup_changes("PORTDIR")
				expand_map["PORTDIR"] = self["PORTDIR"]

			# repoman controls PORTDIR_OVERLAY via the environment, so no
			# special cases are needed here.
			portdir_overlay = list(self.repositories.repoLocationList())
			if portdir_overlay and portdir_overlay[0] == self["PORTDIR"]:
				portdir_overlay = portdir_overlay[1:]

			new_ov = []
			if portdir_overlay:
				for ov in portdir_overlay:
					ov = normalize_path(ov)
					if isdir_raise_eaccess(ov) or portage._sync_mode:
						new_ov.append(portage._shell_quote(ov))
					else:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY"
							" (not a dir): '%s'\n") % ov, noiselevel=-1)

			self["PORTDIR_OVERLAY"] = " ".join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")
			expand_map["PORTDIR_OVERLAY"] = self["PORTDIR_OVERLAY"]

			locations_manager.set_port_dirs(self["PORTDIR"], self["PORTDIR_OVERLAY"])
			locations_manager.load_profiles(self.repositories, known_repos)

			profiles_complex = locations_manager.profiles_complex
			self.profiles = locations_manager.profiles
			self.profile_path = locations_manager.profile_path
			self.user_profile_dir = locations_manager.user_profile_dir

			try:
				packages_list = [grabfile_package(
					os.path.join(x.location, "packages"),
					verify_eapi=True, eapi=x.eapi, eapi_default=None,
					allow_repo=allow_profile_repo_deps(x),
					allow_build_id=x.allow_build_id)
					for x in profiles_complex]
			except EnvironmentError as e:
				_raise_exc(e)

			self.packages = tuple(stack_lists(packages_list, incremental=1))

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				# Negative atoms are filtered by the above stack_lists() call.
				if not isinstance(x, Atom):
					x = Atom(x.lstrip('*'))
				self.prevmaskdict.setdefault(x.cp, []).append(x)

			self.unpack_dependencies = load_unpack_dependencies_configuration(self.repositories)

			mygcfg = {}
			if profiles_complex:
				mygcfg_dlists = []
				for x in profiles_complex:
					# Prevent accidents triggered by USE="${USE} ..." settings
					# at the top of make.defaults which caused parent profile
					# USE to override parent profile package.use settings.
					# It would be nice to guard USE_EXPAND variables like
					# this too, but unfortunately USE_EXPAND is not known
					# until after make.defaults has been evaluated, so that
					# will require some form of make.defaults preprocessing.
					expand_map.pop("USE", None)
					mygcfg_dlists.append(
						getconfig(os.path.join(x.location, "make.defaults"),
						tolerant=tolerant, expand=expand_map,
						recursive=x.portage1_directories))
				self._make_defaults = mygcfg_dlists
				mygcfg = stack_dicts(mygcfg_dlists,
					incrementals=self.incrementals)
				if mygcfg is None:
					mygcfg = {}
			self.configlist.append(mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			mygcfg = {}
			for x in make_conf_paths:
				mygcfg.update(getconfig(x,
					tolerant=tolerant, allow_sourcing=True,
					expand=expand_map, recursive=True) or {})

			# __* variables set in make.conf are local and are not be propagated.
			mygcfg = {k: v for k, v in mygcfg.items() if not k.startswith("__")}

			# Don't allow the user to override certain variables in make.conf
			profile_only_variables = self.configdict["defaults"].get(
				"PROFILE_ONLY_VARIABLES", "").split()
			profile_only_variables = stack_lists([profile_only_variables])
			non_user_variables = set()
			non_user_variables.update(profile_only_variables)
			non_user_variables.update(self._env_blacklist)
			non_user_variables.update(self._global_only_vars)
			non_user_variables = frozenset(non_user_variables)
			self._non_user_variables = non_user_variables

			self._env_d_blacklist = frozenset(chain(
				profile_only_variables,
				self._env_blacklist,
			))
			env_d = self.configdict["env.d"]
			for k in self._env_d_blacklist:
				env_d.pop(k, None)

			for k in profile_only_variables:
				mygcfg.pop(k, None)

			self.configlist.append(mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append(LazyItemsDict())
			self.configdict["pkg"]=self.configlist[-1]

			self.configdict["backupenv"] = self.backupenv

			# Don't allow the user to override certain variables in the env
			for k in profile_only_variables:
				self.backupenv.pop(k, None)

			self.configlist.append(self.configdict["env"])

			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			# Blacklist vars that could interfere with portage internals.
			for blacklisted in self._env_blacklist:
				for cfg in self.lookuplist:
					cfg.pop(blacklisted, None)
				self.backupenv.pop(blacklisted, None)
			del blacklisted, cfg

			self["PORTAGE_CONFIGROOT"] = config_root
			self.backup_changes("PORTAGE_CONFIGROOT")
			self["ROOT"] = target_root
			self.backup_changes("ROOT")
			self["SYSROOT"] = sysroot
			self.backup_changes("SYSROOT")
			self["EPREFIX"] = eprefix
			self.backup_changes("EPREFIX")
			self["EROOT"] = eroot
			self.backup_changes("EROOT")
			self["ESYSROOT"] = esysroot
			self.backup_changes("ESYSROOT")
			self["BROOT"] = broot
			self.backup_changes("BROOT")

			# The prefix of the running portage instance is used in the
			# ebuild environment to implement the --host-root option for
			# best_version and has_version.
			self["PORTAGE_OVERRIDE_EPREFIX"] = portage.const.EPREFIX
			self.backup_changes("PORTAGE_OVERRIDE_EPREFIX")

			self._ppropertiesdict = portage.dep.ExtendedAtomDict(dict)
			self._paccept_restrict = portage.dep.ExtendedAtomDict(dict)
			self._penvdict = portage.dep.ExtendedAtomDict(dict)
			self._pbashrcdict = {}
			self._pbashrc = ()

			self._repo_make_defaults = {}
			for repo in self.repositories.repos_with_profiles():
				d = getconfig(os.path.join(repo.location, "profiles", "make.defaults"),
					tolerant=tolerant, expand=self.configdict["globals"].copy(), recursive=repo.portage1_profiles) or {}
				if d:
					for k in chain(self._env_blacklist,
						profile_only_variables, self._global_only_vars):
						d.pop(k, None)
				self._repo_make_defaults[repo.name] = d

			#Read all USE related files from profiles and optionally from user config.
			self._use_manager = UseManager(self.repositories, profiles_complex,
				abs_user_config, self._isStable, user_config=local_config)
			#Initialize all USE related variables we track ourselves.
			self.usemask = self._use_manager.getUseMask()
			self.useforce = self._use_manager.getUseForce()
			self.configdict["conf"]["USE"] = \
				self._use_manager.extract_global_USE_changes( \
					self.configdict["conf"].get("USE", ""))

			#Read license_groups and optionally license_groups and package.license from user config
			self._license_manager = LicenseManager(locations_manager.profile_locations, \
				abs_user_config, user_config=local_config)
			#Extract '*/*' entries from package.license
			self.configdict["conf"]["ACCEPT_LICENSE"] = \
				self._license_manager.extract_global_changes( \
					self.configdict["conf"].get("ACCEPT_LICENSE", ""))

			# profile.bashrc
			self._profile_bashrc = tuple(os.path.isfile(os.path.join(profile.location, 'profile.bashrc'))
				for profile in profiles_complex)

			if local_config:
				#package.properties
				propdict = grabdict_package(os.path.join(
					abs_user_config, "package.properties"), recursive=1, allow_wildcard=True, \
					allow_repo=True, verify_eapi=False,
					allow_build_id=True)
				v = propdict.pop("*/*", None)
				if v is not None:
					if "ACCEPT_PROPERTIES" in self.configdict["conf"]:
						self.configdict["conf"]["ACCEPT_PROPERTIES"] += " " + " ".join(v)
					else:
						self.configdict["conf"]["ACCEPT_PROPERTIES"] = " ".join(v)
				for k, v in propdict.items():
					self._ppropertiesdict.setdefault(k.cp, {})[k] = v

				# package.accept_restrict
				d = grabdict_package(os.path.join(
					abs_user_config, "package.accept_restrict"),
					recursive=True, allow_wildcard=True,
					allow_repo=True, verify_eapi=False,
					allow_build_id=True)
				v = d.pop("*/*", None)
				if v is not None:
					if "ACCEPT_RESTRICT" in self.configdict["conf"]:
						self.configdict["conf"]["ACCEPT_RESTRICT"] += " " + " ".join(v)
					else:
						self.configdict["conf"]["ACCEPT_RESTRICT"] = " ".join(v)
				for k, v in d.items():
					self._paccept_restrict.setdefault(k.cp, {})[k] = v

				#package.env
				penvdict = grabdict_package(os.path.join(
					abs_user_config, "package.env"), recursive=1, allow_wildcard=True, \
					allow_repo=True, verify_eapi=False,
					allow_build_id=True)
				v = penvdict.pop("*/*", None)
				if v is not None:
					global_wildcard_conf = {}
					self._grab_pkg_env(v, global_wildcard_conf)
					incrementals = self.incrementals
					conf_configdict = self.configdict["conf"]
					for k, v in global_wildcard_conf.items():
						if k in incrementals:
							if k in conf_configdict:
								conf_configdict[k] = \
									conf_configdict[k] + " " + v
							else:
								conf_configdict[k] = v
						else:
							conf_configdict[k] = v
						expand_map[k] = v

				for k, v in penvdict.items():
					self._penvdict.setdefault(k.cp, {})[k] = v

				# package.bashrc
				for profile in profiles_complex:
					if not 'profile-bashrcs' in profile.profile_formats:
						continue
					self._pbashrcdict[profile] = \
						portage.dep.ExtendedAtomDict(dict)
					bashrc = grabdict_package(os.path.join(profile.location,
						"package.bashrc"), recursive=1, allow_wildcard=True,
								allow_repo=allow_profile_repo_deps(profile),
								verify_eapi=True,
								eapi=profile.eapi, eapi_default=None,
								allow_build_id=profile.allow_build_id)
					if not bashrc:
						continue

					for k, v in bashrc.items():
						envfiles = [os.path.join(profile.location,
							"bashrc",
							envname) for envname in v]
						self._pbashrcdict[profile].setdefault(k.cp, {})\
							.setdefault(k, []).extend(envfiles)

			#getting categories from an external file now
			self.categories = [grabfile(os.path.join(x, "categories")) \
				for x in locations_manager.profile_and_user_locations]
			category_re = dbapi._category_re
			# categories used to be a tuple, but now we use a frozenset
			# for hashed category validation in pordbapi.cp_list()
			self.categories = frozenset(
				x for x in stack_lists(self.categories, incremental=1)
				if category_re.match(x) is not None)

			archlist = [grabfile(os.path.join(x, "arch.list")) \
				for x in locations_manager.profile_and_user_locations]
			archlist = sorted(stack_lists(archlist, incremental=1))
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = " ".join(archlist)

			pkgprovidedlines = []
			for x in profiles_complex:
				provpath = os.path.join(x.location, "package.provided")
				if os.path.exists(provpath):
					if _get_eapi_attrs(x.eapi).allows_package_provided:
						pkgprovidedlines.append(grabfile(provpath,
							recursive=x.portage1_directories))
					else:
						# TODO: bail out?
						writemsg((_("!!! package.provided not allowed in EAPI %s: ")
								%x.eapi)+x.location+"\n",
							noiselevel=-1)

			pkgprovidedlines = stack_lists(pkgprovidedlines, incremental=1)
			has_invalid_data = False
			for x in range(len(pkgprovidedlines)-1, -1, -1):
				myline = pkgprovidedlines[x]
				if not isvalidatom("=" + myline):
					writemsg(_("Invalid package name in package.provided: %s\n") % \
						myline, noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
				cpvr = catpkgsplit(pkgprovidedlines[x])
				if not cpvr or cpvr[0] == "null":
					writemsg(_("Invalid package name in package.provided: ")+pkgprovidedlines[x]+"\n",
						noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
			if has_invalid_data:
				writemsg(_("See portage(5) for correct package.provided usage.\n"),
					noiselevel=-1)
			self.pprovideddict = {}
			for x in pkgprovidedlines:
				x_split = catpkgsplit(x)
				if x_split is None:
					continue
				mycatpkg = cpv_getkey(x)
				if mycatpkg in self.pprovideddict:
					self.pprovideddict[mycatpkg].append(x)
				else:
					self.pprovideddict[mycatpkg]=[x]

			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			if "USE_ORDER" not in self:
				self["USE_ORDER"] = "env:pkg:conf:defaults:pkginternal:features:repo:env.d"
				self.backup_changes("USE_ORDER")

			if "CBUILD" not in self and "CHOST" in self:
				self["CBUILD"] = self["CHOST"]
				self.backup_changes("CBUILD")

			if "USERLAND" not in self:
				# Set default USERLAND so that our test cases can assume that
				# it's always set. This allows isolated-functions.sh to avoid
				# calling uname -s when sourced.
				system = platform.system()
				if system is not None and \
					(system.endswith("BSD") or system == "DragonFly"):
					self["USERLAND"] = "BSD"
				else:
					self["USERLAND"] = "GNU"
				self.backup_changes("USERLAND")

			default_inst_ids = {
				"PORTAGE_INST_GID": "0",
				"PORTAGE_INST_UID": "0",
			}

			eroot_or_parent = first_existing(eroot)
			unprivileged = False
			try:
				eroot_st = os.stat(eroot_or_parent)
			except OSError:
				pass
			else:

				if portage.data._unprivileged_mode(
					eroot_or_parent, eroot_st):
					unprivileged = True

					default_inst_ids["PORTAGE_INST_GID"] = str(eroot_st.st_gid)
					default_inst_ids["PORTAGE_INST_UID"] = str(eroot_st.st_uid)

					if "PORTAGE_USERNAME" not in self:
						try:
							pwd_struct = pwd.getpwuid(eroot_st.st_uid)
						except KeyError:
							pass
						else:
							self["PORTAGE_USERNAME"] = pwd_struct.pw_name
							self.backup_changes("PORTAGE_USERNAME")

					if "PORTAGE_GRPNAME" not in self:
						try:
							grp_struct = grp.getgrgid(eroot_st.st_gid)
						except KeyError:
							pass
						else:
							self["PORTAGE_GRPNAME"] = grp_struct.gr_name
							self.backup_changes("PORTAGE_GRPNAME")

			for var, default_val in default_inst_ids.items():
				try:
					self[var] = str(int(self.get(var, default_val)))
				except ValueError:
					writemsg(_("!!! %s='%s' is not a valid integer.  "
						"Falling back to %s.\n") % (var, self[var], default_val),
						noiselevel=-1)
					self[var] = default_val
				self.backup_changes(var)

			self.depcachedir = self.get("PORTAGE_DEPCACHEDIR")
			if self.depcachedir is None:
				self.depcachedir = os.path.join(os.sep,
					portage.const.EPREFIX, DEPCACHE_PATH.lstrip(os.sep))
				if unprivileged and target_root != os.sep:
					# In unprivileged mode, automatically make
					# depcachedir relative to target_root if the
					# default depcachedir is not writable.
					if not os.access(first_existing(self.depcachedir),
						os.W_OK):
						self.depcachedir = os.path.join(eroot,
							DEPCACHE_PATH.lstrip(os.sep))

			self["PORTAGE_DEPCACHEDIR"] = self.depcachedir
			self.backup_changes("PORTAGE_DEPCACHEDIR")

			if portage._internal_caller:
				self["PORTAGE_INTERNAL_CALLER"] = "1"
				self.backup_changes("PORTAGE_INTERNAL_CALLER")

			# initialize self.features
			self.regenerate()
			feature_use = []
			if "test" in self.features:
				feature_use.append("test")
			self.configdict["features"]["USE"] = self._default_features_use = " ".join(feature_use)
			if feature_use:
				# Regenerate USE so that the initial "test" flag state is
				# correct for evaluation of !test? conditionals in RESTRICT.
				self.regenerate()

			if unprivileged:
				self.features.add('unprivileged')

			if bsd_chflags:
				self.features.add('chflags')

			self._init_iuse()

			self._validate_commands()

			for k in self._case_insensitive_vars:
				if k in self:
					self[k] = self[k].lower()
					self.backup_changes(k)

			# The first constructed config object initializes these modules,
			# and subsequent calls to the _init() functions have no effect.
			portage.output._init(config_root=self['PORTAGE_CONFIGROOT'])
			portage.data._init(self)

		if mycpv:
			self.setcpv(mycpv)

	def _init_iuse(self):
		self._iuse_effective = self._calc_iuse_effective()
		self._iuse_implicit_match = _iuse_implicit_match_cache(self)

	@property
	def mygcfg(self):
		warnings.warn("portage.config.mygcfg is deprecated", stacklevel=3)
		return {}

	def _validate_commands(self):
		for k in special_env_vars.validate_commands:
			v = self.get(k)
			if v is not None:
				valid, v_split = validate_cmd_var(v)

				if not valid:
					if v_split:
						writemsg_level(_("%s setting is invalid: '%s'\n") % \
							(k, v), level=logging.ERROR, noiselevel=-1)

					# before deleting the invalid setting, backup
					# the default value if available
					v = self.configdict['globals'].get(k)
					if v is not None:
						default_valid, v_split = validate_cmd_var(v)
						if not default_valid:
							if v_split:
								writemsg_level(
									_("%s setting from make.globals" + \
									" is invalid: '%s'\n") % \
									(k, v), level=logging.ERROR, noiselevel=-1)
							# make.globals seems corrupt, so try for
							# a hardcoded default instead
							v = self._default_globals.get(k)

					# delete all settings for this key,
					# including the invalid one
					del self[k]
					self.backupenv.pop(k, None)
					if v:
						# restore validated default
						self.configdict['globals'][k] = v

	def _init_dirs(self):
		"""
		Create a few directories that are critical to portage operation
		"""
		if not os.access(self["EROOT"], os.W_OK):
			return

		#                                gid, mode, mask, preserve_perms
		dir_mode_map = {
			"tmp"             : (         -1, 0o1777,  0,  True),
			"var/tmp"         : (         -1, 0o1777,  0,  True),
			PRIVATE_PATH      : (portage_gid, 0o2750, 0o2, False),
			CACHE_PATH        : (portage_gid,  0o755, 0o2, False)
		}

		for mypath, (gid, mode, modemask, preserve_perms) \
			in dir_mode_map.items():
			mydir = os.path.join(self["EROOT"], mypath)
			if preserve_perms and os.path.isdir(mydir):
				# Only adjust permissions on some directories if
				# they don't exist yet. This gives freedom to the
				# user to adjust permissions to suit their taste.
				continue
			try:
				ensure_dirs(mydir, gid=gid, mode=mode, mask=modemask)
			except PortageException as e:
				writemsg(_("!!! Directory initialization failed: '%s'\n") % mydir,
					noiselevel=-1)
				writemsg("!!! %s\n" % str(e),
					noiselevel=-1)

	@property
	def _keywords_manager(self):
		if self._keywords_manager_obj is None:
			self._keywords_manager_obj = KeywordsManager(
				self._locations_manager.profiles_complex,
				self._locations_manager.abs_user_config,
				self.local_config,
				global_accept_keywords=self.configdict["defaults"].get("ACCEPT_KEYWORDS", ""))
		return self._keywords_manager_obj

	@property
	def _mask_manager(self):
		if self._mask_manager_obj is None:
			self._mask_manager_obj = MaskManager(self.repositories,
				self._locations_manager.profiles_complex,
				self._locations_manager.abs_user_config,
				user_config=self.local_config,
				strict_umatched_removal=self._unmatched_removal)
		return self._mask_manager_obj

	@property
	def _virtuals_manager(self):
		if self._virtuals_manager_obj is None:
			self._virtuals_manager_obj = VirtualsManager(self.profiles)
		return self._virtuals_manager_obj

	@property
	def pkeywordsdict(self):
		result = self._keywords_manager.pkeywordsdict.copy()
		for k, v in result.items():
			result[k] = v.copy()
		return result

	@property
	def pmaskdict(self):
		return self._mask_manager._pmaskdict.copy()

	@property
	def punmaskdict(self):
		return self._mask_manager._punmaskdict.copy()

	@property
	def soname_provided(self):
		if self._soname_provided is None:
			d = stack_dictlist((grabdict(
				os.path.join(x, "soname.provided"), recursive=True)
				for x in self.profiles), incremental=True)
			self._soname_provided = frozenset(SonameAtom(cat, soname)
				for cat, sonames in d.items() for soname in sonames)
		return self._soname_provided

	def expandLicenseTokens(self, tokens):
		""" Take a token from ACCEPT_LICENSE or package.license and expand it
		if it's a group token (indicated by @) or just return it if it's not a
		group.  If a group is negated then negate all group elements."""
		return self._license_manager.expandLicenseTokens(tokens)

	def validate(self):
		"""Validate miscellaneous settings and display warnings if necessary.
		(This code was previously in the global scope of portage.py)"""

		groups = self.get("ACCEPT_KEYWORDS", "").split()
		archlist = self.archlist()
		if not archlist:
			writemsg(_("--- 'profiles/arch.list' is empty or "
				"not available. Empty ebuild repository?\n"), noiselevel=1)
		else:
			for group in groups:
				if group not in archlist and \
					not (group.startswith("-") and group[1:] in archlist) and \
					group not in ("*", "~*", "**"):
					writemsg(_("!!! INVALID ACCEPT_KEYWORDS: %s\n") % str(group),
						noiselevel=-1)

		profile_broken = False

		# getmaskingstatus requires ARCH for ACCEPT_KEYWORDS support
		arch = self.get('ARCH')
		if not self.profile_path or not arch:
			profile_broken = True
		else:
			# If any one of these files exists, then
			# the profile is considered valid.
			for x in ("make.defaults", "parent",
				"packages", "use.force", "use.mask"):
				if exists_raise_eaccess(os.path.join(self.profile_path, x)):
					break
			else:
				profile_broken = True

		if profile_broken and not portage._sync_mode:
			abs_profile_path = None
			for x in (PROFILE_PATH, 'etc/make.profile'):
				x = os.path.join(self["PORTAGE_CONFIGROOT"], x)
				try:
					os.lstat(x)
				except OSError:
					pass
				else:
					abs_profile_path = x
					break

			if abs_profile_path is None:
				abs_profile_path = os.path.join(self["PORTAGE_CONFIGROOT"],
					PROFILE_PATH)

			writemsg(_("\n\n!!! %s is not a symlink and will probably prevent most merges.\n") % abs_profile_path,
				noiselevel=-1)
			writemsg(_("!!! It should point into a profile within %s/profiles/\n") % self["PORTDIR"])
			writemsg(_("!!! (You can safely ignore this message when syncing. It's harmless.)\n\n\n"))

		abs_user_virtuals = os.path.join(self["PORTAGE_CONFIGROOT"],
			USER_VIRTUALS_FILE)
		if os.path.exists(abs_user_virtuals):
			writemsg("\n!!! /etc/portage/virtuals is deprecated in favor of\n")
			writemsg("!!! /etc/portage/profile/virtuals. Please move it to\n")
			writemsg("!!! this new location.\n\n")

		if not sandbox_capable and \
			("sandbox" in self.features or "usersandbox" in self.features):
			if self.profile_path is not None and \
				os.path.realpath(self.profile_path) == \
				os.path.realpath(os.path.join(
				self["PORTAGE_CONFIGROOT"], PROFILE_PATH)):
				# Don't show this warning when running repoman and the
				# sandbox feature came from a profile that doesn't belong
				# to the user.
				writemsg(colorize("BAD", _("!!! Problem with sandbox"
					" binary. Disabling...\n\n")), noiselevel=-1)

		if "fakeroot" in self.features and \
			not fakeroot_capable:
			writemsg(_("!!! FEATURES=fakeroot is enabled, but the "
				"fakeroot binary is not installed.\n"), noiselevel=-1)

		if "webrsync-gpg" in self.features:
			writemsg(_("!!! FEATURES=webrsync-gpg is deprecated, see the make.conf(5) man page.\n"),
				noiselevel=-1)

		if os.getuid() == 0 and not hasattr(os, "setgroups"):
			warning_shown = False

			if "userpriv" in self.features:
				writemsg(_("!!! FEATURES=userpriv is enabled, but "
					"os.setgroups is not available.\n"), noiselevel=-1)
				warning_shown = True

			if "userfetch" in self.features:
				writemsg(_("!!! FEATURES=userfetch is enabled, but "
					"os.setgroups is not available.\n"), noiselevel=-1)
				warning_shown = True

			if warning_shown and platform.python_implementation() == 'PyPy':
				writemsg(_("!!! See https://bugs.pypy.org/issue833 for details.\n"),
					noiselevel=-1)

		binpkg_compression = self.get("BINPKG_COMPRESS")
		if binpkg_compression:
			try:
				compression = _compressors[binpkg_compression]
			except KeyError as e:
				writemsg("!!! BINPKG_COMPRESS contains invalid or "
					"unsupported compression method: %s" % e.args[0],
					noiselevel=-1)
			else:
				try:
					compression_binary = shlex_split(
						portage.util.varexpand(compression["compress"],
						mydict=self))[0]
				except IndexError as e:
					writemsg("!!! BINPKG_COMPRESS contains invalid or "
						"unsupported compression method: %s" % e.args[0],
						noiselevel=-1)
				else:
					if portage.process.find_binary(
						compression_binary) is None:
						missing_package = compression["package"]
						writemsg("!!! BINPKG_COMPRESS unsupported %s. "
							"Missing package: %s" %
							(binpkg_compression, missing_package),
							noiselevel=-1)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		mod = None
		try:
			mod = load_mod(best_mod)
		except ImportError:
			if best_mod in self._module_aliases:
				mod = load_mod(self._module_aliases[best_mod])
			elif not best_mod.startswith("cache."):
				raise
			else:
				best_mod = "portage." + best_mod
				try:
					mod = load_mod(best_mod)
				except ImportError:
					raise
		return mod

	def lock(self):
		self.locked = 1

	def unlock(self):
		self.locked = 0

	def modifying(self):
		if self.locked:
			raise Exception(_("Configuration is locked."))

	def backup_changes(self,key=None):
		self.modifying()
		if key and key in self.configdict["env"]:
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError(_("No such key defined in environment: %s") % key)

	def reset(self, keeping_pkg=0, use_cache=None):
		"""
		Restore environment from self.backupenv, call self.regenerate()
		@param keeping_pkg: Should we keep the setcpv() data or delete it.
		@type keeping_pkg: Boolean
		@rype: None
		"""

		if use_cache is not None:
			warnings.warn("The use_cache parameter for config.reset() is deprecated and without effect.",
				DeprecationWarning, stacklevel=2)

		self.modifying()
		self.configdict["env"].clear()
		self.configdict["env"].update(self.backupenv)

		self.modifiedkeys = []
		if not keeping_pkg:
			self.mycpv = None
			self._setcpv_args_hash = None
			self.puse = ""
			del self._penv[:]
			self.configdict["pkg"].clear()
			self.configdict["pkginternal"].clear()
			self.configdict["features"]["USE"] = self._default_features_use
			self.configdict["repo"].clear()
			self.configdict["defaults"]["USE"] = \
				" ".join(self.make_defaults_use)
			self.usemask = self._use_manager.getUseMask()
			self.useforce = self._use_manager.getUseForce()
		self.regenerate()

	class _lazy_vars:

		__slots__ = ('built_use', 'settings', 'values')

		def __init__(self, built_use, settings):
			self.built_use = built_use
			self.settings = settings
			self.values = None

		def __getitem__(self, k):
			if self.values is None:
				self.values = self._init_values()
			return self.values[k]

		def _init_values(self):
			values = {}
			settings = self.settings
			use = self.built_use
			if use is None:
				use = frozenset(settings['PORTAGE_USE'].split())

			values['ACCEPT_LICENSE'] = settings._license_manager.get_prunned_accept_license( \
				settings.mycpv, use, settings.get('LICENSE', ''), settings.get('SLOT'), settings.get('PORTAGE_REPO_NAME'))
			values['PORTAGE_PROPERTIES'] = self._flatten('PROPERTIES', use, settings)
			values['PORTAGE_RESTRICT'] = self._flatten('RESTRICT', use, settings)
			return values

		def _flatten(self, var, use, settings):
			try:
				restrict = set(use_reduce(settings.get(var, ''), uselist=use, flat=True))
			except InvalidDependString:
				restrict = set()
			return ' '.join(sorted(restrict))

	class _lazy_use_expand:
		"""
		Lazily evaluate USE_EXPAND variables since they are only needed when
		an ebuild shell is spawned. Variables values are made consistent with
		the previously calculated USE settings.
		"""

		def __init__(self, settings, unfiltered_use,
			use, usemask, iuse_effective,
			use_expand_split, use_expand_dict):
			self._settings = settings
			self._unfiltered_use = unfiltered_use
			self._use = use
			self._usemask = usemask
			self._iuse_effective = iuse_effective
			self._use_expand_split = use_expand_split
			self._use_expand_dict = use_expand_dict

		def __getitem__(self, key):
			prefix = key.lower() + '_'
			prefix_len = len(prefix)
			expand_flags = set( x[prefix_len:] for x in self._use \
				if x[:prefix_len] == prefix )
			var_split = self._use_expand_dict.get(key, '').split()
			# Preserve the order of var_split because it can matter for things
			# like LINGUAS.
			var_split = [ x for x in var_split if x in expand_flags ]
			var_split.extend(expand_flags.difference(var_split))
			has_wildcard = '*' in expand_flags
			if has_wildcard:
				var_split = [ x for x in var_split if x != "*" ]
			has_iuse = set()
			for x in self._iuse_effective:
				if x[:prefix_len] == prefix:
					has_iuse.add(x[prefix_len:])
			if has_wildcard:
				# * means to enable everything in IUSE that's not masked
				if has_iuse:
					usemask = self._usemask
					for suffix in has_iuse:
						x = prefix + suffix
						if x not in usemask:
							if suffix not in expand_flags:
								var_split.append(suffix)
				else:
					# If there is a wildcard and no matching flags in IUSE then
					# LINGUAS should be unset so that all .mo files are
					# installed.
					var_split = []
			# Make the flags unique and filter them according to IUSE.
			# Also, continue to preserve order for things like LINGUAS
			# and filter any duplicates that variable may contain.
			filtered_var_split = []
			remaining = has_iuse.intersection(var_split)
			for x in var_split:
				if x in remaining:
					remaining.remove(x)
					filtered_var_split.append(x)
			var_split = filtered_var_split

			return ' '.join(var_split)

	def _setcpv_recursion_gate(f):
		"""
		Raise AssertionError for recursive setcpv calls.
		"""
		def wrapper(self, *args, **kwargs):
			if hasattr(self, '_setcpv_active'):
				raise AssertionError('setcpv recursion detected')
			self._setcpv_active = True
			try:
				return f(self, *args, **kwargs)
			finally:
				del self._setcpv_active
		return wrapper

	@_setcpv_recursion_gate
	def setcpv(self, mycpv, use_cache=None, mydb=None):
		"""
		Load a particular CPV into the config, this lets us see the
		Default USE flags for a particular ebuild as well as the USE
		flags from package.use.

		@param mycpv: A cpv to load
		@type mycpv: string
		@param mydb: a dbapi instance that supports aux_get with the IUSE key.
		@type mydb: dbapi or derivative.
		@rtype: None
		"""

		if use_cache is not None:
			warnings.warn("The use_cache parameter for config.setcpv() is deprecated and without effect.",
				DeprecationWarning, stacklevel=2)

		self.modifying()

		pkg = None
		built_use = None
		explicit_iuse = None
		if not isinstance(mycpv, str):
			pkg = mycpv
			mycpv = pkg.cpv
			mydb = pkg._metadata
			explicit_iuse = pkg.iuse.all
			args_hash = (mycpv, id(pkg))
			if pkg.built:
				built_use = pkg.use.enabled
		else:
			args_hash = (mycpv, id(mydb))

		if args_hash == self._setcpv_args_hash:
			return
		self._setcpv_args_hash = args_hash

		has_changed = False
		self.mycpv = mycpv
		cat, pf = catsplit(mycpv)
		cp = cpv_getkey(mycpv)
		cpv_slot = self.mycpv
		pkginternaluse = ""
		pkginternaluse_list = []
		feature_use = []
		iuse = ""
		pkg_configdict = self.configdict["pkg"]
		previous_iuse = pkg_configdict.get("IUSE")
		previous_iuse_effective = pkg_configdict.get("IUSE_EFFECTIVE")
		previous_features = pkg_configdict.get("FEATURES")
		previous_penv = self._penv

		aux_keys = self._setcpv_aux_keys

		# Discard any existing metadata and package.env settings from
		# the previous package instance.
		pkg_configdict.clear()

		pkg_configdict["CATEGORY"] = cat
		pkg_configdict["PF"] = pf
		repository = None
		eapi = None
		if mydb:
			if not hasattr(mydb, "aux_get"):
				for k in aux_keys:
					if k in mydb:
						# Make these lazy, since __getitem__ triggers
						# evaluation of USE conditionals which can't
						# occur until PORTAGE_USE is calculated below.
						pkg_configdict.addLazySingleton(k,
							mydb.__getitem__, k)
			else:
				# When calling dbapi.aux_get(), grab USE for built/installed
				# packages since we want to save it PORTAGE_BUILT_USE for
				# evaluating conditional USE deps in atoms passed via IPC to
				# helpers like has_version and best_version.
				aux_keys = set(aux_keys)
				if hasattr(mydb, '_aux_cache_keys'):
					aux_keys = aux_keys.intersection(mydb._aux_cache_keys)
				aux_keys.add('USE')
				aux_keys = list(aux_keys)
				for k, v in zip(aux_keys, mydb.aux_get(self.mycpv, aux_keys)):
					pkg_configdict[k] = v
				built_use = frozenset(pkg_configdict.pop('USE').split())
				if not built_use:
					# Empty USE means this dbapi instance does not contain
					# built packages.
					built_use = None
			eapi = pkg_configdict['EAPI']

			repository = pkg_configdict.pop("repository", None)
			if repository is not None:
				pkg_configdict["PORTAGE_REPO_NAME"] = repository
			iuse = pkg_configdict["IUSE"]
			if pkg is None:
				self.mycpv = _pkg_str(self.mycpv, metadata=pkg_configdict,
					settings=self)
				cpv_slot = self.mycpv
			else:
				cpv_slot = pkg
			for x in iuse.split():
				if x.startswith("+"):
					pkginternaluse_list.append(x[1:])
				elif x.startswith("-"):
					pkginternaluse_list.append(x)
			pkginternaluse = " ".join(pkginternaluse_list)

		eapi_attrs = _get_eapi_attrs(eapi)

		if pkginternaluse != self.configdict["pkginternal"].get("USE", ""):
			self.configdict["pkginternal"]["USE"] = pkginternaluse
			has_changed = True

		repo_env = []
		if repository and repository != Package.UNKNOWN_REPO:
			repos = []
			try:
				repos.extend(repo.name for repo in
					self.repositories[repository].masters)
			except KeyError:
				pass
			repos.append(repository)
			for repo in repos:
				d = self._repo_make_defaults.get(repo)
				if d is None:
					d = {}
				else:
					# make a copy, since we might modify it with
					# package.use settings
					d = d.copy()
				cpdict = self._use_manager._repo_puse_dict.get(repo, {}).get(cp)
				if cpdict:
					repo_puse = ordered_by_atom_specificity(cpdict, cpv_slot)
					if repo_puse:
						for x in repo_puse:
							d["USE"] = d.get("USE", "") + " " + " ".join(x)
				if d:
					repo_env.append(d)

		if repo_env or self.configdict["repo"]:
			self.configdict["repo"].clear()
			self.configdict["repo"].update(stack_dicts(repo_env,
				incrementals=self.incrementals))
			has_changed = True

		defaults = []
		for i, pkgprofileuse_dict in enumerate(self._use_manager._pkgprofileuse):
			if self.make_defaults_use[i]:
				defaults.append(self.make_defaults_use[i])
			cpdict = pkgprofileuse_dict.get(cp)
			if cpdict:
				pkg_defaults = ordered_by_atom_specificity(cpdict, cpv_slot)
				if pkg_defaults:
					defaults.extend(pkg_defaults)
		defaults = " ".join(defaults)
		if defaults != self.configdict["defaults"].get("USE",""):
			self.configdict["defaults"]["USE"] = defaults
			has_changed = True

		useforce = self._use_manager.getUseForce(cpv_slot)
		if useforce != self.useforce:
			self.useforce = useforce
			has_changed = True

		usemask = self._use_manager.getUseMask(cpv_slot)
		if usemask != self.usemask:
			self.usemask = usemask
			has_changed = True

		oldpuse = self.puse
		self.puse = self._use_manager.getPUSE(cpv_slot)
		if oldpuse != self.puse:
			has_changed = True
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE

		if previous_features:
			# The package from the previous setcpv call had package.env
			# settings which modified FEATURES. Therefore, trigger a
			# regenerate() call in order to ensure that self.features
			# is accurate.
			has_changed = True
			# Prevent stale features USE from corrupting the evaluation
			# of USE conditional RESTRICT.
			self.configdict["features"]["USE"] = self._default_features_use

		self._penv = []
		cpdict = self._penvdict.get(cp)
		if cpdict:
			penv_matches = ordered_by_atom_specificity(cpdict, cpv_slot)
			if penv_matches:
				for x in penv_matches:
					self._penv.extend(x)

		bashrc_files = []

		for profile, profile_bashrc in zip(self._locations_manager.profiles_complex, self._profile_bashrc):
			if profile_bashrc:
				bashrc_files.append(os.path.join(profile.location, 'profile.bashrc'))
			if profile in self._pbashrcdict:
				cpdict = self._pbashrcdict[profile].get(cp)
				if cpdict:
					bashrc_matches = \
						ordered_by_atom_specificity(cpdict, cpv_slot)
					for x in bashrc_matches:
						bashrc_files.extend(x)

		self._pbashrc = tuple(bashrc_files)

		protected_pkg_keys = set(pkg_configdict)
		protected_pkg_keys.discard('USE')

		# If there are _any_ package.env settings for this package
		# then it automatically triggers config.reset(), in order
		# to account for possible incremental interaction between
		# package.use, package.env, and overrides from the calling
		# environment (configdict['env']).
		if self._penv:
			has_changed = True
			# USE is special because package.use settings override
			# it. Discard any package.use settings here and they'll
			# be added back later.
			pkg_configdict.pop('USE', None)
			self._grab_pkg_env(self._penv, pkg_configdict,
				protected_keys=protected_pkg_keys)

			# Now add package.use settings, which override USE from
			# package.env
			if self.puse:
				if 'USE' in pkg_configdict:
					pkg_configdict['USE'] = \
						pkg_configdict['USE'] + " " + self.puse
				else:
					pkg_configdict['USE'] = self.puse

		elif previous_penv:
			has_changed = True

		if not (previous_iuse == iuse and
			previous_iuse_effective is not None == eapi_attrs.iuse_effective):
			has_changed = True

		if has_changed:
			# This can modify self.features due to package.env settings.
			self.reset(keeping_pkg=1)

		if "test" in self.features:
			# This is independent of IUSE and RESTRICT, so that the same
			# value can be shared between packages with different settings,
			# which is important when evaluating USE conditional RESTRICT.
			feature_use.append("test")

		feature_use = " ".join(feature_use)
		if feature_use != self.configdict["features"]["USE"]:
			# Regenerate USE for evaluation of conditional RESTRICT.
			self.configdict["features"]["USE"] = feature_use
			self.reset(keeping_pkg=1)
			has_changed = True

		if explicit_iuse is None:
			explicit_iuse = frozenset(x.lstrip("+-") for x in iuse.split())
		if eapi_attrs.iuse_effective:
			iuse_implicit_match = self._iuse_effective_match
		else:
			iuse_implicit_match = self._iuse_implicit_match

		if pkg is None:
			raw_properties = pkg_configdict.get("PROPERTIES")
			raw_restrict = pkg_configdict.get("RESTRICT")
		else:
			raw_properties = pkg._raw_metadata["PROPERTIES"]
			raw_restrict = pkg._raw_metadata["RESTRICT"]

		restrict_test = False
		if raw_restrict:
			try:
				if built_use is not None:
					properties = use_reduce(raw_properties,
						uselist=built_use, flat=True)
					restrict = use_reduce(raw_restrict,
						uselist=built_use, flat=True)
				else:
					properties = use_reduce(raw_properties,
						uselist=frozenset(x for x in self['USE'].split()
						if x in explicit_iuse or iuse_implicit_match(x)),
						flat=True)
					restrict = use_reduce(raw_restrict,
						uselist=frozenset(x for x in self['USE'].split()
						if x in explicit_iuse or iuse_implicit_match(x)),
						flat=True)
			except PortageException:
				pass
			else:
				allow_test = self.get('ALLOW_TEST', '').split()
				restrict_test = (
					"test" in restrict and not "all" in allow_test and
					not ("test_network" in properties and "network" in allow_test))

		if restrict_test and "test" in self.features:
			# Handle it like IUSE="-test", since features USE is
			# independent of RESTRICT.
			pkginternaluse_list.append("-test")
			pkginternaluse = " ".join(pkginternaluse_list)
			self.configdict["pkginternal"]["USE"] = pkginternaluse
			# TODO: can we avoid that?
			self.reset(keeping_pkg=1)
			has_changed = True

		env_configdict = self.configdict['env']

		# Ensure that "pkg" values are always preferred over "env" values.
		# This must occur _after_ the above reset() call, since reset()
		# copies values from self.backupenv.
		for k in protected_pkg_keys:
			env_configdict.pop(k, None)

		lazy_vars = self._lazy_vars(built_use, self)
		env_configdict.addLazySingleton('ACCEPT_LICENSE',
			lazy_vars.__getitem__, 'ACCEPT_LICENSE')
		env_configdict.addLazySingleton('PORTAGE_PROPERTIES',
			lazy_vars.__getitem__, 'PORTAGE_PROPERTIES')
		env_configdict.addLazySingleton('PORTAGE_RESTRICT',
			lazy_vars.__getitem__, 'PORTAGE_RESTRICT')

		if built_use is not None:
			pkg_configdict['PORTAGE_BUILT_USE'] = ' '.join(built_use)

		# If reset() has not been called, it's safe to return
		# early if IUSE has not changed.
		if not has_changed:
			return

		# Filter out USE flags that aren't part of IUSE. This has to
		# be done for every setcpv() call since practically every
		# package has different IUSE.
		use = set(self["USE"].split())
		unfiltered_use = frozenset(use)

		if eapi_attrs.iuse_effective:
			portage_iuse = set(self._iuse_effective)
			portage_iuse.update(explicit_iuse)
			if built_use is not None:
				# When the binary package was built, the profile may have
				# had different IUSE_IMPLICIT settings, so any member of
				# the built USE setting is considered to be a member of
				# IUSE_EFFECTIVE (see bug 640318).
				portage_iuse.update(built_use)
			self.configdict["pkg"]["IUSE_EFFECTIVE"] = \
				" ".join(sorted(portage_iuse))

			self.configdict["env"]["BASH_FUNC____in_portage_iuse%%"] = (
				"() { "
				"if [[ ${#___PORTAGE_IUSE_HASH[@]} -lt 1 ]]; then "
				"  declare -gA ___PORTAGE_IUSE_HASH=(%s); "
				"fi; "
				"[[ -n ${___PORTAGE_IUSE_HASH[$1]} ]]; "
				"}" ) % " ".join('["%s"]=1' % x for x in portage_iuse)
		else:
			portage_iuse = self._get_implicit_iuse()
			portage_iuse.update(explicit_iuse)

			# The _get_implicit_iuse() returns a regular expression
			# so we can't use the (faster) map.  Fall back to
			# implementing ___in_portage_iuse() the older/slower way.

			# PORTAGE_IUSE is not always needed so it's lazily evaluated.
			self.configdict["env"].addLazySingleton(
				"PORTAGE_IUSE", _lazy_iuse_regex, portage_iuse)
			self.configdict["env"]["BASH_FUNC____in_portage_iuse%%"] = \
				"() { [[ $1 =~ ${PORTAGE_IUSE} ]]; }"

		ebuild_force_test = not restrict_test and \
			self.get("EBUILD_FORCE_TEST") == "1"

		if "test" in explicit_iuse or iuse_implicit_match("test"):
			if "test" in self.features:
				if ebuild_force_test and "test" in self.usemask:
					self.usemask = \
						frozenset(x for x in self.usemask if x != "test")
			if restrict_test or \
				("test" in self.usemask and not ebuild_force_test):
				# "test" is in IUSE and USE=test is masked, so execution
				# of src_test() probably is not reliable. Therefore,
				# temporarily disable FEATURES=test just for this package.
				self["FEATURES"] = " ".join(x for x in self.features \
					if x != "test")

		# Allow _* flags from USE_EXPAND wildcards to pass through here.
		use.difference_update([x for x in use \
			if (x not in explicit_iuse and \
			not iuse_implicit_match(x)) and x[-2:] != '_*'])

		# Use the calculated USE flags to regenerate the USE_EXPAND flags so
		# that they are consistent. For optimal performance, use slice
		# comparison instead of startswith().
		use_expand_split = set(x.lower() for \
			x in self.get('USE_EXPAND', '').split())
		lazy_use_expand = self._lazy_use_expand(
			self, unfiltered_use, use, self.usemask,
			portage_iuse, use_expand_split, self._use_expand_dict)

		use_expand_iuses = dict((k, set()) for k in use_expand_split)
		for x in portage_iuse:
			x_split = x.split('_')
			if len(x_split) == 1:
				continue
			for i in range(len(x_split) - 1):
				k = '_'.join(x_split[:i+1])
				if k in use_expand_split:
					use_expand_iuses[k].add(x)
					break

		for k, use_expand_iuse in use_expand_iuses.items():
			if k + '_*' in use:
				use.update( x for x in use_expand_iuse if x not in usemask )
			k = k.upper()
			self.configdict['env'].addLazySingleton(k,
				lazy_use_expand.__getitem__, k)

		for k in self.get("USE_EXPAND_UNPREFIXED", "").split():
			var_split = self.get(k, '').split()
			var_split = [ x for x in var_split if x in use ]
			if var_split:
				self.configlist[-1][k] = ' '.join(var_split)
			elif k in self:
				self.configlist[-1][k] = ''

		# Filtered for the ebuild environment. Store this in a separate
		# attribute since we still want to be able to see global USE
		# settings for things like emerge --info.

		self.configdict["env"]["PORTAGE_USE"] = \
			" ".join(sorted(x for x in use if x[-2:] != '_*'))

		# Clear the eapi cache here rather than in the constructor, since
		# setcpv triggers lazy instantiation of things like _use_manager.
		_eapi_cache.clear()

	def _grab_pkg_env(self, penv, container, protected_keys=None):
		if protected_keys is None:
			protected_keys = ()
		abs_user_config = os.path.join(
			self['PORTAGE_CONFIGROOT'], USER_CONFIG_PATH)
		non_user_variables = self._non_user_variables
		# Make a copy since we don't want per-package settings
		# to pollute the global expand_map.
		expand_map = self._expand_map.copy()
		incrementals = self.incrementals
		for envname in penv:
			penvfile = os.path.join(abs_user_config, "env", envname)
			penvconfig = getconfig(penvfile, tolerant=self._tolerant,
				allow_sourcing=True, expand=expand_map)
			if penvconfig is None:
				writemsg("!!! %s references non-existent file: %s\n" % \
					(os.path.join(abs_user_config, 'package.env'), penvfile),
					noiselevel=-1)
			else:
				for k, v in penvconfig.items():
					if k in protected_keys or \
						k in non_user_variables:
						writemsg("!!! Illegal variable " + \
							"'%s' assigned in '%s'\n" % \
							(k, penvfile), noiselevel=-1)
					elif k in incrementals:
						if k in container:
							container[k] = container[k] + " " + v
						else:
							container[k] = v
					else:
						container[k] = v

	def _iuse_effective_match(self, flag):
		return flag in self._iuse_effective

	def _calc_iuse_effective(self):
		"""
		Beginning with EAPI 5, IUSE_EFFECTIVE is defined by PMS.
		"""
		iuse_effective = []
		iuse_effective.extend(self.get("IUSE_IMPLICIT", "").split())

		# USE_EXPAND_IMPLICIT should contain things like ARCH, ELIBC,
		# KERNEL, and USERLAND.
		use_expand_implicit = frozenset(
			self.get("USE_EXPAND_IMPLICIT", "").split())

		# USE_EXPAND_UNPREFIXED should contain at least ARCH, and
		# USE_EXPAND_VALUES_ARCH should contain all valid ARCH flags.
		for v in self.get("USE_EXPAND_UNPREFIXED", "").split():
			if v not in use_expand_implicit:
				continue
			iuse_effective.extend(
				self.get("USE_EXPAND_VALUES_" + v, "").split())

		use_expand = frozenset(self.get("USE_EXPAND", "").split())
		for v in use_expand_implicit:
			if v not in use_expand:
				continue
			lower_v = v.lower()
			for x in self.get("USE_EXPAND_VALUES_" + v, "").split():
				iuse_effective.append(lower_v + "_" + x)

		return frozenset(iuse_effective)

	def _get_implicit_iuse(self):
		"""
		Prior to EAPI 5, these flags are considered to
		be implicit members of IUSE:
		  * Flags derived from ARCH
		  * Flags derived from USE_EXPAND_HIDDEN variables
		  * Masked flags, such as those from {,package}use.mask
		  * Forced flags, such as those from {,package}use.force
		  * build and bootstrap flags used by bootstrap.sh
		"""
		iuse_implicit = set()
		# Flags derived from ARCH.
		arch = self.configdict["defaults"].get("ARCH")
		if arch:
			iuse_implicit.add(arch)
		iuse_implicit.update(self.get("PORTAGE_ARCHLIST", "").split())

		# Flags derived from USE_EXPAND_HIDDEN variables
		# such as ELIBC, KERNEL, and USERLAND.
		use_expand_hidden = self.get("USE_EXPAND_HIDDEN", "").split()
		for x in use_expand_hidden:
			iuse_implicit.add(x.lower() + "_.*")

		# Flags that have been masked or forced.
		iuse_implicit.update(self.usemask)
		iuse_implicit.update(self.useforce)

		# build and bootstrap flags used by bootstrap.sh
		iuse_implicit.add("build")
		iuse_implicit.add("bootstrap")

		return iuse_implicit

	def _getUseMask(self, pkg, stable=None):
		return self._use_manager.getUseMask(pkg, stable=stable)

	def _getUseForce(self, pkg, stable=None):
		return self._use_manager.getUseForce(pkg, stable=stable)

	def _getMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask.

		@param cpv: The package name
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: String
		@return: A matching atom string or None if one is not found.
		"""
		return self._mask_manager.getMaskAtom(cpv, metadata["SLOT"], metadata.get('repository'))

	def _getRawMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask.

		@param cpv: The package name
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: String
		@return: A matching atom string or None if one is not found.
		"""
		return self._mask_manager.getRawMaskAtom(cpv, metadata["SLOT"], metadata.get('repository'))


	def _getProfileMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching profile atom, or None if no
		such atom exists. Note that a profile atom may or may not have a "*"
		prefix.

		@param cpv: The package name
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: String
		@return: A matching profile atom string or None if one is not found.
		"""

		warnings.warn("The config._getProfileMaskAtom() method is deprecated.",
			DeprecationWarning, stacklevel=2)

		cp = cpv_getkey(cpv)
		profile_atoms = self.prevmaskdict.get(cp)
		if profile_atoms:
			pkg = "".join((cpv, _slot_separator, metadata["SLOT"]))
			repo = metadata.get("repository")
			if repo and repo != Package.UNKNOWN_REPO:
				pkg = "".join((pkg, _repo_separator, repo))
			pkg_list = [pkg]
			for x in profile_atoms:
				if match_from_list(x, pkg_list):
					continue
				return x
		return None

	def _isStable(self, pkg):
		return self._keywords_manager.isStable(pkg,
			self.get("ACCEPT_KEYWORDS", ""),
			self.configdict["backupenv"].get("ACCEPT_KEYWORDS", ""))

	def _getKeywords(self, cpv, metadata):
		return self._keywords_manager.getKeywords(cpv, metadata["SLOT"], \
			metadata.get("KEYWORDS", ""), metadata.get("repository"))

	def _getMissingKeywords(self, cpv, metadata):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		need to accept for the given package. If the KEYWORDS are empty
		and the ** keyword has not been accepted, the returned list will
		contain ** alone (in order to distinguish from the case of "none
		missing").

		@param cpv: The package name (for package.keywords support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of KEYWORDS that have not been accepted.
		"""

		# Hack: Need to check the env directly here as otherwise stacking
		# doesn't work properly as negative values are lost in the config
		# object (bug #139600)
		backuped_accept_keywords = self.configdict["backupenv"].get("ACCEPT_KEYWORDS", "")
		global_accept_keywords = self.get("ACCEPT_KEYWORDS", "")

		return self._keywords_manager.getMissingKeywords(cpv, metadata["SLOT"], \
			metadata.get("KEYWORDS", ""), metadata.get('repository'), \
			global_accept_keywords, backuped_accept_keywords)

	def _getRawMissingKeywords(self, cpv, metadata):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		need to accept for the given package. If the KEYWORDS are empty,
		the returned list will contain ** alone (in order to distinguish
		from the case of "none missing").  This DOES NOT apply any user config
		package.accept_keywords acceptance.

		@param cpv: The package name (for package.keywords support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: lists of KEYWORDS that have not been accepted
		and the keywords it looked for.
		"""
		return self._keywords_manager.getRawMissingKeywords(cpv, metadata["SLOT"], \
			metadata.get("KEYWORDS", ""), metadata.get('repository'), \
			self.get("ACCEPT_KEYWORDS", ""))

	def _getPKeywords(self, cpv, metadata):
		global_accept_keywords = self.get("ACCEPT_KEYWORDS", "")

		return self._keywords_manager.getPKeywords(cpv, metadata["SLOT"], \
			metadata.get('repository'), global_accept_keywords)

	def _getMissingLicenses(self, cpv, metadata):
		"""
		Take a LICENSE string and return a list of any licenses that the user
		may need to accept for the given package.  The returned list will not
		contain any licenses that have already been accepted.  This method
		can throw an InvalidDependString exception.

		@param cpv: The package name (for package.license support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of licenses that have not been accepted.
		"""
		return self._license_manager.getMissingLicenses( \
			cpv, metadata["USE"], metadata["LICENSE"], metadata["SLOT"], metadata.get('repository'))

	def _getMissingProperties(self, cpv, metadata):
		"""
		Take a PROPERTIES string and return a list of any properties the user
		may need to accept for the given package.  The returned list will not
		contain any properties that have already been accepted.  This method
		can throw an InvalidDependString exception.

		@param cpv: The package name (for package.properties support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of properties that have not been accepted.
		"""
		accept_properties = self._accept_properties
		try:
			cpv.slot
		except AttributeError:
			cpv = _pkg_str(cpv, metadata=metadata, settings=self)
		cp = cpv_getkey(cpv)
		cpdict = self._ppropertiesdict.get(cp)
		if cpdict:
			pproperties_list = ordered_by_atom_specificity(cpdict, cpv)
			if pproperties_list:
				accept_properties = list(self._accept_properties)
				for x in pproperties_list:
					accept_properties.extend(x)

		properties_str = metadata.get("PROPERTIES", "")
		properties = set(use_reduce(properties_str, matchall=1, flat=True))

		acceptable_properties = set()
		for x in accept_properties:
			if x == '*':
				acceptable_properties.update(properties)
			elif x == '-*':
				acceptable_properties.clear()
			elif x[:1] == '-':
				acceptable_properties.discard(x[1:])
			else:
				acceptable_properties.add(x)

		if "?" in properties_str:
			use = metadata["USE"].split()
		else:
			use = []

		return [x for x in use_reduce(properties_str, uselist=use, flat=True)
			if x not in acceptable_properties]

	def _getMissingRestrict(self, cpv, metadata):
		"""
		Take a RESTRICT string and return a list of any tokens the user
		may need to accept for the given package.  The returned list will not
		contain any tokens that have already been accepted.  This method
		can throw an InvalidDependString exception.

		@param cpv: The package name (for package.accept_restrict support)
		@type cpv: String
		@param metadata: A dictionary of raw package metadata
		@type metadata: dict
		@rtype: List
		@return: A list of tokens that have not been accepted.
		"""
		accept_restrict = self._accept_restrict
		try:
			cpv.slot
		except AttributeError:
			cpv = _pkg_str(cpv, metadata=metadata, settings=self)
		cp = cpv_getkey(cpv)
		cpdict = self._paccept_restrict.get(cp)
		if cpdict:
			paccept_restrict_list = ordered_by_atom_specificity(cpdict, cpv)
			if paccept_restrict_list:
				accept_restrict = list(self._accept_restrict)
				for x in paccept_restrict_list:
					accept_restrict.extend(x)

		restrict_str = metadata.get("RESTRICT", "")
		all_restricts = set(use_reduce(restrict_str, matchall=1, flat=True))

		acceptable_restricts = set()
		for x in accept_restrict:
			if x == '*':
				acceptable_restricts.update(all_restricts)
			elif x == '-*':
				acceptable_restricts.clear()
			elif x[:1] == '-':
				acceptable_restricts.discard(x[1:])
			else:
				acceptable_restricts.add(x)

		if "?" in restrict_str:
			use = metadata["USE"].split()
		else:
			use = []

		return [x for x in use_reduce(restrict_str, uselist=use, flat=True)
			if x not in acceptable_restricts]

	def _accept_chost(self, cpv, metadata):
		"""
		@return True if pkg CHOST is accepted, False otherwise.
		"""
		if self._accept_chost_re is None:
			accept_chost = self.get("ACCEPT_CHOSTS", "").split()
			if not accept_chost:
				chost = self.get("CHOST")
				if chost:
					accept_chost.append(chost)
			if not accept_chost:
				self._accept_chost_re = re.compile(".*")
			elif len(accept_chost) == 1:
				try:
					self._accept_chost_re = re.compile(r'^%s$' % accept_chost[0])
				except re.error as e:
					writemsg(_("!!! Invalid ACCEPT_CHOSTS value: '%s': %s\n") % \
						(accept_chost[0], e), noiselevel=-1)
					self._accept_chost_re = re.compile("^$")
			else:
				try:
					self._accept_chost_re = re.compile(
						r'^(%s)$' % "|".join(accept_chost))
				except re.error as e:
					writemsg(_("!!! Invalid ACCEPT_CHOSTS value: '%s': %s\n") % \
						(" ".join(accept_chost), e), noiselevel=-1)
					self._accept_chost_re = re.compile("^$")

		pkg_chost = metadata.get('CHOST', '')
		return not pkg_chost or \
			self._accept_chost_re.match(pkg_chost) is not None

	def setinst(self, mycpv, mydbapi):
		"""This used to update the preferences for old-style virtuals.
		It is no-op now."""
		pass

	def reload(self):
		"""Reload things like /etc/profile.env that can change during runtime."""
		env_d_filename = os.path.join(self["EROOT"], "etc", "profile.env")
		self.configdict["env.d"].clear()
		env_d = getconfig(env_d_filename,
			tolerant=self._tolerant, expand=False)
		if env_d:
			# env_d will be None if profile.env doesn't exist.
			for k in self._env_d_blacklist:
				env_d.pop(k, None)
			self.configdict["env.d"].update(env_d)

	def regenerate(self, useonly=0, use_cache=None):
		"""
		Regenerate settings
		This involves regenerating valid USE flags, re-expanding USE_EXPAND flags
		re-stacking USE flags (-flag and -*), as well as any other INCREMENTAL
		variables.  This also updates the env.d configdict; useful in case an ebuild
		changes the environment.

		If FEATURES has already stacked, it is not stacked twice.

		@param useonly: Only regenerate USE flags (not any other incrementals)
		@type useonly: Boolean
		@rtype: None
		"""

		if use_cache is not None:
			warnings.warn("The use_cache parameter for config.regenerate() is deprecated and without effect.",
				DeprecationWarning, stacklevel=2)

		self.modifying()

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals = self.incrementals
		myincrementals = set(myincrementals)

		# Process USE last because it depends on USE_EXPAND which is also
		# an incremental!
		myincrementals.discard("USE")

		mydbs = self.configlist[:-1]
		mydbs.append(self.backupenv)

		# ACCEPT_LICENSE is a lazily evaluated incremental, so that * can be
		# used to match all licenses without every having to explicitly expand
		# it to all licenses.
		if self.local_config:
			mysplit = []
			for curdb in mydbs:
				mysplit.extend(curdb.get('ACCEPT_LICENSE', '').split())
			mysplit = prune_incremental(mysplit)
			accept_license_str = ' '.join(mysplit) or '* -@EULA'
			self.configlist[-1]['ACCEPT_LICENSE'] = accept_license_str
			self._license_manager.set_accept_license_str(accept_license_str)
		else:
			# repoman will accept any license
			self._license_manager.set_accept_license_str("*")

		# ACCEPT_PROPERTIES works like ACCEPT_LICENSE, without groups
		if self.local_config:
			mysplit = []
			for curdb in mydbs:
				mysplit.extend(curdb.get('ACCEPT_PROPERTIES', '').split())
			mysplit = prune_incremental(mysplit)
			self.configlist[-1]['ACCEPT_PROPERTIES'] = ' '.join(mysplit)
			if tuple(mysplit) != self._accept_properties:
				self._accept_properties = tuple(mysplit)
		else:
			# repoman will accept any property
			self._accept_properties = ('*',)

		if self.local_config:
			mysplit = []
			for curdb in mydbs:
				mysplit.extend(curdb.get('ACCEPT_RESTRICT', '').split())
			mysplit = prune_incremental(mysplit)
			self.configlist[-1]['ACCEPT_RESTRICT'] = ' '.join(mysplit)
			if tuple(mysplit) != self._accept_restrict:
				self._accept_restrict = tuple(mysplit)
		else:
			# repoman will accept any property
			self._accept_restrict = ('*',)

		increment_lists = {}
		for k in myincrementals:
			incremental_list = []
			increment_lists[k] = incremental_list
			for curdb in mydbs:
				v = curdb.get(k)
				if v is not None:
					incremental_list.append(v.split())

		if 'FEATURES' in increment_lists:
			increment_lists['FEATURES'].append(self._features_overrides)

		myflags = set()
		for mykey, incremental_list in increment_lists.items():

			myflags.clear()
			for mysplit in incremental_list:

				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags.clear()
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(colorize("BAD",
							_("%s values should not start with a '+': %s") % (mykey,x)) \
							+ "\n", noiselevel=-1)
						x=x[1:]
						if not x:
							continue

					if x[0] == "-":
						myflags.discard(x[1:])
						continue

					# We got here, so add it now.
					myflags.add(x)

			#store setting in last element of configlist, the original environment:
			if myflags or mykey in self:
				self.configlist[-1][mykey] = " ".join(sorted(myflags))

		# Do the USE calculation last because it depends on USE_EXPAND.
		use_expand = self.get("USE_EXPAND", "").split()
		use_expand_dict = self._use_expand_dict
		use_expand_dict.clear()
		for k in use_expand:
			v = self.get(k)
			if v is not None:
				use_expand_dict[k] = v

		use_expand_unprefixed = self.get("USE_EXPAND_UNPREFIXED", "").split()

		# In order to best accomodate the long-standing practice of
		# setting default USE_EXPAND variables in the profile's
		# make.defaults, we translate these variables into their
		# equivalent USE flags so that useful incremental behavior
		# is enabled (for sub-profiles).
		configdict_defaults = self.configdict['defaults']
		if self._make_defaults is not None:
			for i, cfg in enumerate(self._make_defaults):
				if not cfg:
					self.make_defaults_use.append("")
					continue
				use = cfg.get("USE", "")
				expand_use = []

				for k in use_expand_unprefixed:
					v = cfg.get(k)
					if v is not None:
						expand_use.extend(v.split())

				for k in use_expand_dict:
					v = cfg.get(k)
					if v is None:
						continue
					prefix = k.lower() + '_'
					for x in v.split():
						if x[:1] == '-':
							expand_use.append('-' + prefix + x[1:])
						else:
							expand_use.append(prefix + x)

				if expand_use:
					expand_use.append(use)
					use  = ' '.join(expand_use)
				self.make_defaults_use.append(use)
			self.make_defaults_use = tuple(self.make_defaults_use)
			# Preserve both positive and negative flags here, since
			# negative flags may later interact with other flags pulled
			# in via USE_ORDER.
			configdict_defaults['USE'] = ' '.join(
				filter(None, self.make_defaults_use))
			# Set to None so this code only runs once.
			self._make_defaults = None

		if not self.uvlist:
			for x in self["USE_ORDER"].split(":"):
				if x in self.configdict:
					self.uvlist.append(self.configdict[x])
			self.uvlist.reverse()

		# For optimal performance, use slice
		# comparison instead of startswith().
		iuse = self.configdict["pkg"].get("IUSE")
		if iuse is not None:
			iuse = [x.lstrip("+-") for x in iuse.split()]
		myflags = set()
		for curdb in self.uvlist:

			for k in use_expand_unprefixed:
				v = curdb.get(k)
				if v is None:
					continue
				for x in v.split():
					if x[:1] == "-":
						myflags.discard(x[1:])
					else:
						myflags.add(x)

			cur_use_expand = [x for x in use_expand if x in curdb]
			mysplit = curdb.get("USE", "").split()
			if not mysplit and not cur_use_expand:
				continue
			for x in mysplit:
				if x == "-*":
					myflags.clear()
					continue

				if x[0] == "+":
					writemsg(colorize("BAD", _("USE flags should not start "
						"with a '+': %s\n") % x), noiselevel=-1)
					x = x[1:]
					if not x:
						continue

				if x[0] == "-":
					if x[-2:] == '_*':
						prefix = x[1:-1]
						prefix_len = len(prefix)
						myflags.difference_update(
							[y for y in myflags if \
							y[:prefix_len] == prefix])
					myflags.discard(x[1:])
					continue

				if iuse is not None and x[-2:] == '_*':
					# Expand wildcards here, so that cases like
					# USE="linguas_* -linguas_en_US" work correctly.
					prefix = x[:-1]
					prefix_len = len(prefix)
					has_iuse = False
					for y in iuse:
						if y[:prefix_len] == prefix:
							has_iuse = True
							myflags.add(y)
					if not has_iuse:
						# There are no matching IUSE, so allow the
						# wildcard to pass through. This allows
						# linguas_* to trigger unset LINGUAS in
						# cases when no linguas_ flags are in IUSE.
						myflags.add(x)
				else:
					myflags.add(x)

			if curdb is configdict_defaults:
				# USE_EXPAND flags from make.defaults are handled
				# earlier, in order to provide useful incremental
				# behavior (for sub-profiles).
				continue

			for var in cur_use_expand:
				var_lower = var.lower()
				is_not_incremental = var not in myincrementals
				if is_not_incremental:
					prefix = var_lower + "_"
					prefix_len = len(prefix)
					for x in list(myflags):
						if x[:prefix_len] == prefix:
							myflags.remove(x)
				for x in curdb[var].split():
					if x[0] == "+":
						if is_not_incremental:
							writemsg(colorize("BAD", _("Invalid '+' "
								"operator in non-incremental variable "
								 "'%s': '%s'\n") % (var, x)), noiselevel=-1)
							continue
						else:
							writemsg(colorize("BAD", _("Invalid '+' "
								"operator in incremental variable "
								 "'%s': '%s'\n") % (var, x)), noiselevel=-1)
						x = x[1:]
					if x[0] == "-":
						if is_not_incremental:
							writemsg(colorize("BAD", _("Invalid '-' "
								"operator in non-incremental variable "
								 "'%s': '%s'\n") % (var, x)), noiselevel=-1)
							continue
						myflags.discard(var_lower + "_" + x[1:])
						continue
					myflags.add(var_lower + "_" + x)

		if hasattr(self, "features"):
			self.features._features.clear()
		else:
			self.features = features_set(self)
		self.features._features.update(self.get('FEATURES', '').split())
		self.features._sync_env_var()
		self.features._validate()

		myflags.update(self.useforce)
		arch = self.configdict["defaults"].get("ARCH")
		if arch:
			myflags.add(arch)

		myflags.difference_update(self.usemask)
		self.configlist[-1]["USE"]= " ".join(sorted(myflags))

		if self.mycpv is None:
			# Generate global USE_EXPAND variables settings that are
			# consistent with USE, for display by emerge --info. For
			# package instances, these are instead generated via
			# setcpv().
			for k in use_expand:
				prefix = k.lower() + '_'
				prefix_len = len(prefix)
				expand_flags = set( x[prefix_len:] for x in myflags \
					if x[:prefix_len] == prefix )
				var_split = use_expand_dict.get(k, '').split()
				var_split = [ x for x in var_split if x in expand_flags ]
				var_split.extend(sorted(expand_flags.difference(var_split)))
				if var_split:
					self.configlist[-1][k] = ' '.join(var_split)
				elif k in self:
					self.configlist[-1][k] = ''

			for k in use_expand_unprefixed:
				var_split = self.get(k, '').split()
				var_split = [ x for x in var_split if x in myflags ]
				if var_split:
					self.configlist[-1][k] = ' '.join(var_split)
				elif k in self:
					self.configlist[-1][k] = ''

	@property
	def virts_p(self):
		warnings.warn("portage config.virts_p attribute " + \
			"is deprecated, use config.get_virts_p()",
			DeprecationWarning, stacklevel=2)
		return self.get_virts_p()

	@property
	def virtuals(self):
		warnings.warn("portage config.virtuals attribute " + \
			"is deprecated, use config.getvirtuals()",
			DeprecationWarning, stacklevel=2)
		return self.getvirtuals()

	def get_virts_p(self):
		# Ensure that we don't trigger the _treeVirtuals
		# assertion in VirtualsManager._compile_virtuals().
		self.getvirtuals()
		return self._virtuals_manager.get_virts_p()

	def getvirtuals(self):
		if self._virtuals_manager._treeVirtuals is None:
			#Hack around the fact that VirtualsManager needs a vartree
			#and vartree needs a config instance.
			#This code should be part of VirtualsManager.getvirtuals().
			if self.local_config:
				temp_vartree = vartree(settings=self)
				self._virtuals_manager._populate_treeVirtuals(temp_vartree)
			else:
				self._virtuals_manager._treeVirtuals = {}

		return self._virtuals_manager.getvirtuals()

	def _populate_treeVirtuals_if_needed(self, vartree):
		"""Reduce the provides into a list by CP."""
		if self._virtuals_manager._treeVirtuals is None:
			if self.local_config:
				self._virtuals_manager._populate_treeVirtuals(vartree)
			else:
				self._virtuals_manager._treeVirtuals = {}

	def __delitem__(self,mykey):
		self.pop(mykey)

	def __getitem__(self, key):
		try:
			return self._getitem(key)
		except KeyError:
			if portage._internal_caller:
				stack = traceback.format_stack()[:-1] + traceback.format_exception(*sys.exc_info())[1:]
				try:
					# Ensure that output is written to terminal.
					with open("/dev/tty", "w") as f:
						f.write("=" * 96 + "\n")
						f.write("=" * 8 + " Traceback for invalid call to portage.package.ebuild.config.config.__getitem__ " + "=" * 8 + "\n")
						f.writelines(stack)
						f.write("=" * 96 + "\n")
				except Exception:
					pass
				raise
			else:
				warnings.warn(_("Passing nonexistent key %r to %s is deprecated. Use %s instead.") %
					(key, "portage.package.ebuild.config.config.__getitem__",
					"portage.package.ebuild.config.config.get"), DeprecationWarning, stacklevel=2)
				return ""

	def _getitem(self, mykey):

		if mykey in self._constant_keys:
			# These two point to temporary values when
			# portage plans to update itself.
			if mykey == "PORTAGE_BIN_PATH":
				return portage._bin_path
			if mykey == "PORTAGE_PYM_PATH":
				return portage._pym_path

			if mykey == "PORTAGE_PYTHONPATH":
				value = [x for x in \
					self.backupenv.get("PYTHONPATH", "").split(":") if x]
				need_pym_path = True
				if value:
					try:
						need_pym_path = not os.path.samefile(value[0],
							portage._pym_path)
					except OSError:
						pass
				if need_pym_path:
					value.insert(0, portage._pym_path)
				return ":".join(value)

			if mykey == "PORTAGE_GID":
				return "%s" % portage_gid

		for d in self.lookuplist:
			try:
				return d[mykey]
			except KeyError:
				pass

		deprecated_key = self._deprecated_keys.get(mykey)
		if deprecated_key is not None:
			value = self._getitem(deprecated_key)
			#warnings.warn(_("Key %s has been renamed to %s. Please ",
			#	"update your configuration") % (deprecated_key, mykey),
			#	UserWarning)
			return value

		raise KeyError(mykey)

	def get(self, k, x=None):
		try:
			return self._getitem(k)
		except KeyError:
			return x

	def pop(self, key, *args):
		self.modifying()
		if len(args) > 1:
			raise TypeError(
				"pop expected at most 2 arguments, got " + \
				repr(1 + len(args)))
		v = self
		for d in reversed(self.lookuplist):
			v = d.pop(key, v)
		if v is self:
			if args:
				return args[0]
			raise KeyError(key)
		return v

	def __contains__(self, mykey):
		"""Called to implement membership test operators (in and not in)."""
		try:
			self._getitem(mykey)
		except KeyError:
			return False
		else:
			return True

	def setdefault(self, k, x=None):
		v = self.get(k)
		if v is not None:
			return v
		self[k] = x
		return x

	def __iter__(self):
		keys = set()
		keys.update(self._constant_keys)
		for d in self.lookuplist:
			keys.update(d)
		return iter(keys)

	def iterkeys(self):
		return iter(self)

	def iteritems(self):
		for k in self:
			yield (k, self._getitem(k))

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		if not isinstance(myvalue, str):
			raise ValueError("Invalid type being used as a value: '%s': '%s'" % (str(mykey),str(myvalue)))

		# Avoid potential UnicodeDecodeError exceptions later.
		mykey = _unicode_decode(mykey)
		myvalue = _unicode_decode(myvalue)

		self.modifying()
		self.modifiedkeys.append(mykey)
		self.configdict["env"][mykey]=myvalue

	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		environ_filter = self._environ_filter

		eapi = self.get('EAPI')
		eapi_attrs = _get_eapi_attrs(eapi)
		phase = self.get('EBUILD_PHASE')
		emerge_from = self.get('EMERGE_FROM')
		filter_calling_env = False
		if self.mycpv is not None and \
			not (emerge_from == 'ebuild' and phase == 'setup') and \
			phase not in ('clean', 'cleanrm', 'depend', 'fetch'):
			temp_dir = self.get('T')
			if temp_dir is not None and \
				os.path.exists(os.path.join(temp_dir, 'environment')):
				filter_calling_env = True

		environ_whitelist = self._environ_whitelist
		for x, myvalue in self.iteritems():
			if x in environ_filter:
				continue
			if not isinstance(myvalue, str):
				writemsg(_("!!! Non-string value in config: %s=%s\n") % \
					(x, myvalue), noiselevel=-1)
				continue
			if filter_calling_env and \
				x not in environ_whitelist and \
				not self._environ_whitelist_re.match(x):
				# Do not allow anything to leak into the ebuild
				# environment unless it is explicitly whitelisted.
				# This ensures that variables unset by the ebuild
				# remain unset (bug #189417).
				continue
			mydict[x] = myvalue
		if "HOME" not in mydict and "BUILD_PREFIX" in mydict:
			writemsg("*** HOME not set. Setting to "+mydict["BUILD_PREFIX"]+"\n")
			mydict["HOME"]=mydict["BUILD_PREFIX"][:]

		if filter_calling_env:
			if phase:
				whitelist = []
				if "rpm" == phase:
					whitelist.append("RPMDIR")
				for k in whitelist:
					v = self.get(k)
					if v is not None:
						mydict[k] = v

		# At some point we may want to stop exporting FEATURES to the ebuild
		# environment, in order to prevent ebuilds from abusing it. In
		# preparation for that, export it as PORTAGE_FEATURES so that bashrc
		# users will be able to migrate any FEATURES conditional code to
		# use this alternative variable.
		mydict["PORTAGE_FEATURES"] = self["FEATURES"]

		# Filtered by IUSE and implicit IUSE.
		mydict["USE"] = self.get("PORTAGE_USE", "")

		# Don't export AA to the ebuild environment in EAPIs that forbid it
		if not eapi_exports_AA(eapi):
			mydict.pop("AA", None)

		if not eapi_exports_merge_type(eapi):
			mydict.pop("MERGE_TYPE", None)

		src_like_phase = (phase == 'setup' or
				_phase_func_map.get(phase, '').startswith('src_'))

		if not (src_like_phase and eapi_attrs.sysroot):
			mydict.pop("ESYSROOT", None)

		if not (src_like_phase and eapi_attrs.broot):
			mydict.pop("BROOT", None)

		# Prefix variables are supported beginning with EAPI 3, or when
		# force-prefix is in FEATURES, since older EAPIs would otherwise be
		# useless with prefix configurations. This brings compatibility with
		# the prefix branch of portage, which also supports EPREFIX for all
		# EAPIs (for obvious reasons).
		if phase == 'depend' or \
			('force-prefix' not in self.features and
			eapi is not None and not eapi_supports_prefix(eapi)):
			mydict.pop("ED", None)
			mydict.pop("EPREFIX", None)
			mydict.pop("EROOT", None)
			mydict.pop("ESYSROOT", None)

		if phase not in ("pretend", "setup", "preinst", "postinst") or \
			not eapi_exports_replace_vars(eapi):
			mydict.pop("REPLACING_VERSIONS", None)

		if phase not in ("prerm", "postrm") or \
			not eapi_exports_replace_vars(eapi):
			mydict.pop("REPLACED_BY_VERSION", None)

		if phase is not None and eapi_attrs.exports_EBUILD_PHASE_FUNC:
			phase_func = _phase_func_map.get(phase)
			if phase_func is not None:
				mydict["EBUILD_PHASE_FUNC"] = phase_func

		if eapi_attrs.posixish_locale:
			split_LC_ALL(mydict)
			mydict["LC_COLLATE"] = "C"
			# check_locale() returns None when check can not be executed.
			if check_locale(silent=True, env=mydict) is False:
				# try another locale
				for l in ("C.UTF-8", "en_US.UTF-8", "en_GB.UTF-8", "C"):
					mydict["LC_CTYPE"] = l
					if check_locale(silent=True, env=mydict):
						# TODO: output the following only once
#						writemsg(_("!!! LC_CTYPE unsupported, using %s instead\n")
#								% mydict["LC_CTYPE"])
						break
				else:
					raise AssertionError("C locale did not pass the test!")

		if not eapi_attrs.exports_PORTDIR:
			mydict.pop("PORTDIR", None)
		if not eapi_attrs.exports_ECLASSDIR:
			mydict.pop("ECLASSDIR", None)

		if not eapi_attrs.path_variables_end_with_trailing_slash:
			for v in ("D", "ED", "ROOT", "EROOT", "ESYSROOT", "BROOT"):
				if v in mydict:
					mydict[v] = mydict[v].rstrip(os.path.sep)

		# Since SYSROOT=/ interacts badly with autotools.eclass (bug 654600),
		# and no EAPI expects SYSROOT to have a trailing slash, always strip
		# the trailing slash from SYSROOT.
		if 'SYSROOT' in mydict:
			mydict['SYSROOT'] = mydict['SYSROOT'].rstrip(os.sep)

		try:
			builddir = mydict["PORTAGE_BUILDDIR"]
			distdir = mydict["DISTDIR"]
		except KeyError:
			pass
		else:
			mydict["PORTAGE_ACTUAL_DISTDIR"] = distdir
			mydict["DISTDIR"] = os.path.join(builddir, "distdir")

		return mydict

	def thirdpartymirrors(self):
		if getattr(self, "_thirdpartymirrors", None) is None:
			thirdparty_lists = []
			for repo_name in reversed(self.repositories.prepos_order):
				thirdparty_lists.append(grabdict(os.path.join(
					self.repositories[repo_name].location,
					"profiles", "thirdpartymirrors")))
			self._thirdpartymirrors = stack_dictlist(thirdparty_lists, incremental=True)
		return self._thirdpartymirrors

	def archlist(self):
		_archlist = []
		for myarch in self["PORTAGE_ARCHLIST"].split():
			_archlist.append(myarch)
			_archlist.append("~" + myarch)
		return _archlist

	def selinux_enabled(self):
		if getattr(self, "_selinux_enabled", None) is None:
			self._selinux_enabled = 0
			if "selinux" in self["USE"].split():
				if selinux:
					if selinux.is_selinux_enabled() == 1:
						self._selinux_enabled = 1
					else:
						self._selinux_enabled = 0
				else:
					writemsg(_("!!! SELinux module not found. Please verify that it was installed.\n"),
						noiselevel=-1)
					self._selinux_enabled = 0

		return self._selinux_enabled

	keys = __iter__
	items = iteritems
