# Copyright 2010-2012 Gentoo Foundation
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
import warnings

from _emerge.Package import Package
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.data:portage_gid',
	'portage.package.ebuild.doebuild:_phase_func_map',
)
from portage import bsd_chflags, \
	load_mod, os, selinux, _unicode_decode
from portage.const import CACHE_PATH, \
	DEPCACHE_PATH, INCREMENTALS, MAKE_CONF_FILE, \
	MODULES_FILE_PATH, \
	PRIVATE_PATH, PROFILE_PATH, USER_CONFIG_PATH, \
	USER_VIRTUALS_FILE
from portage.dbapi import dbapi
from portage.dbapi.porttree import portdbapi
from portage.dbapi.vartree import vartree
from portage.dep import Atom, isvalidatom, match_from_list, use_reduce, _repo_separator, _slot_separator
from portage.eapi import eapi_exports_AA, eapi_exports_merge_type, \
	eapi_supports_prefix, eapi_exports_replace_vars, _get_eapi_attrs
from portage.env.loaders import KeyValuePairFileLoader
from portage.exception import InvalidDependString, PortageException
from portage.localization import _
from portage.output import colorize
from portage.process import fakeroot_capable, sandbox_capable
from portage.repository.config import load_repository_config
from portage.util import ensure_dirs, getconfig, grabdict, \
	grabdict_package, grabfile, grabfile_package, LazyItemsDict, \
	normalize_path, shlex_split, stack_dictlist, stack_dicts, stack_lists, \
	writemsg, writemsg_level, _eapi_cache
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

if sys.hexversion >= 0x3000000:
	basestring = str

_feature_flags_cache = {}

def _get_feature_flags(eapi_attrs):
	cache_key = (eapi_attrs.feature_flag_test, eapi_attrs.feature_flag_targetroot)
	flags = _feature_flags_cache.get(cache_key)
	if flags is not None:
		return flags

	flags = []
	if eapi_attrs.feature_flag_test:
		flags.append("test")
	if eapi_attrs.feature_flag_targetroot:
		flags.append("targetroot")

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
			else:
				return top_dict[x][key]
	if EmptyOnError:
		return ""
	else:
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

class _iuse_implicit_match_cache(object):

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

class config(object):
	"""
	This class encompasses the main portage configuration.  Data is pulled from
	ROOT/PORTDIR/profiles/, from ROOT/etc/make.profile incrementally through all
	parent profiles as well as from ROOT/PORTAGE_CONFIGROOT/* for user specified
	overrides.

	Generally if you need data like USE flags, FEATURES, environment variables,
	virtuals ...etc you look in here.
	"""

	_constant_keys = frozenset(['PORTAGE_BIN_PATH', 'PORTAGE_GID',
		'PORTAGE_PYM_PATH'])

	_setcpv_aux_keys = ('DEFINED_PHASES', 'DEPEND', 'EAPI', 'HDEPEND',
		'INHERITED', 'IUSE', 'REQUIRED_USE', 'KEYWORDS', 'LICENSE', 'PDEPEND',
		'PROPERTIES', 'PROVIDE', 'RDEPEND', 'SLOT',
		'repository', 'RESTRICT', 'LICENSE',)

	_module_aliases = {
		"cache.metadata_overlay.database" : "portage.cache.flat_hash.database",
		"portage.cache.metadata_overlay.database" : "portage.cache.flat_hash.database",
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
		eprefix=None, local_config=True, env=None,
		_unmatched_removal=False):
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
		@param target_root: __init__ override of $ROOT env variable.
		@type target_root: String
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
		self._features_overrides = []
		self._make_defaults = None

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
			self._iuse_effective = clone._iuse_effective
			self._iuse_implicit_match = clone._iuse_implicit_match
			self._non_user_variables = clone._non_user_variables
			self._env_d_blacklist = clone._env_d_blacklist
			self._repo_make_defaults = clone._repo_make_defaults
			self.usemask = clone.usemask
			self.useforce = clone.useforce
			self.puse = clone.puse
			self.user_profile_dir = clone.user_profile_dir
			self.local_config = clone.local_config
			self.make_defaults_use = clone.make_defaults_use
			self.mycpv = clone.mycpv
			self._setcpv_args_hash = clone._setcpv_args_hash

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
			self._penvdict = copy.deepcopy(clone._penvdict)
			self._expand_map = copy.deepcopy(clone._expand_map)

		else:
			# lazily instantiated objects
			self._keywords_manager_obj = None
			self._mask_manager_obj = None
			self._virtuals_manager_obj = None

			locations_manager = LocationsManager(config_root=config_root,
				config_profile_path=config_profile_path, eprefix=eprefix,
				local_config=local_config, target_root=target_root)
			self._locations_manager = locations_manager

			eprefix = locations_manager.eprefix
			config_root = locations_manager.config_root
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

			make_conf = {}
			for x in make_conf_paths:
				make_conf.update(getconfig(x,
					tolerant=tolerant, allow_sourcing=True,
					expand=make_conf) or {})

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

			# Allow make.globals to set default paths relative to ${EPREFIX}.
			expand_map["EPREFIX"] = eprefix

			make_globals = getconfig(os.path.join(
				self.global_config_path, 'make.globals'),
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
				"portdbapi.auxdbmodule":  "portage.cache.flat_hash.database",
			}

			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			self._use_expand_dict = {}
			# configlist will contain: [ env.d, globals, defaults, conf, pkg, backupenv, env ]
			self.configlist.append({})
			self.configdict["env.d"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["repo"] = self.configlist[-1]

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
			self["EPREFIX"] = eprefix
			self["EROOT"] = eroot
			known_repos = []
			portdir = ""
			portdir_overlay = ""
			for confs in [make_globals, make_conf, self.configdict["env"]]:
				v = confs.get("PORTDIR")
				if v is not None:
					portdir = v
					known_repos.append(v)
				v = confs.get("PORTDIR_OVERLAY")
				if v is not None:
					portdir_overlay = v
					known_repos.extend(shlex_split(v))
			known_repos = frozenset(known_repos)
			self["PORTDIR"] = portdir
			self["PORTDIR_OVERLAY"] = portdir_overlay
			self.lookuplist = [self.configdict["env"]]
			self.repositories = load_repository_config(self)

			locations_manager.load_profiles(self.repositories, known_repos)

			profiles_complex = locations_manager.profiles_complex
			self.profiles = locations_manager.profiles
			self.profile_path = locations_manager.profile_path
			self.user_profile_dir = locations_manager.user_profile_dir

			packages_list = [grabfile_package(os.path.join(x, "packages"),
				verify_eapi=True) for x in self.profiles]
			self.packages = tuple(stack_lists(packages_list, incremental=1))

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				# Negative atoms are filtered by the above stack_lists() call.
				if not isinstance(x, Atom):
					x = Atom(x.lstrip('*'))
				self.prevmaskdict.setdefault(x.cp, []).append(x)


			mygcfg = {}
			if self.profiles:
				mygcfg_dlists = [getconfig(os.path.join(x, "make.defaults"),
					tolerant=tolerant, expand=expand_map)
					for x in self.profiles]
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
					expand=expand_map) or {})

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

			# The PORTAGE_OVERRIDE_EPREFIX variable propagates the EPREFIX
			# of this config instance to any portage commands or API
			# consumers running in subprocesses.
			self["EPREFIX"] = eprefix
			self.backup_changes("EPREFIX")
			self["PORTAGE_OVERRIDE_EPREFIX"] = eprefix
			self.backup_changes("PORTAGE_OVERRIDE_EPREFIX")
			self["EROOT"] = eroot
			self.backup_changes("EROOT")

			self._ppropertiesdict = portage.dep.ExtendedAtomDict(dict)
			self._penvdict = portage.dep.ExtendedAtomDict(dict)

			#filling PORTDIR and PORTDIR_OVERLAY variable for compatibility
			main_repo = self.repositories.mainRepo()
			if main_repo is not None:
				self["PORTDIR"] = main_repo.user_location
				self.backup_changes("PORTDIR")

			# repoman controls PORTDIR_OVERLAY via the environment, so no
			# special cases are needed here.
			portdir_overlay = list(self.repositories.repoUserLocationList())
			if portdir_overlay and portdir_overlay[0] == self["PORTDIR"]:
				portdir_overlay = portdir_overlay[1:]

			new_ov = []
			if portdir_overlay:
				shell_quote_re = re.compile(r"[\s\\\"'$`]")
				for ov in portdir_overlay:
					ov = normalize_path(ov)
					if os.path.isdir(ov):
						if shell_quote_re.search(ov) is not None:
							ov = portage._shell_quote(ov)
						new_ov.append(ov)
					else:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY"
							" (not a dir): '%s'\n") % ov, noiselevel=-1)

			self["PORTDIR_OVERLAY"] = " ".join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")

			locations_manager.set_port_dirs(self["PORTDIR"], self["PORTDIR_OVERLAY"])

			self._repo_make_defaults = {}
			for repo in self.repositories.repos_with_profiles():
				d = getconfig(os.path.join(repo.location, "profiles", "make.defaults"),
					tolerant=tolerant, expand=self.configdict["globals"].copy()) or {}
				if d:
					for k in chain(self._env_blacklist,
						profile_only_variables, self._global_only_vars):
						d.pop(k, None)
				self._repo_make_defaults[repo.name] = d

			#Read all USE related files from profiles and optionally from user config.
			self._use_manager = UseManager(self.repositories, profiles_complex, abs_user_config, user_config=local_config)
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

			if local_config:
				#package.properties
				propdict = grabdict_package(os.path.join(
					abs_user_config, "package.properties"), recursive=1, allow_wildcard=True, \
					allow_repo=True, verify_eapi=False)
				v = propdict.pop("*/*", None)
				if v is not None:
					if "ACCEPT_PROPERTIES" in self.configdict["conf"]:
						self.configdict["conf"]["ACCEPT_PROPERTIES"] += " " + " ".join(v)
					else:
						self.configdict["conf"]["ACCEPT_PROPERTIES"] = " ".join(v)
				for k, v in propdict.items():
					self._ppropertiesdict.setdefault(k.cp, {})[k] = v

				#package.env
				penvdict = grabdict_package(os.path.join(
					abs_user_config, "package.env"), recursive=1, allow_wildcard=True, \
					allow_repo=True, verify_eapi=False)
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
			archlist = stack_lists(archlist, incremental=1)
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = " ".join(archlist)

			pkgprovidedlines = [grabfile(
				os.path.join(x.location, "package.provided"),
				recursive=x.portage1_directories)
				for x in profiles_complex]
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
				if cpvr[0] == "virtual":
					writemsg(_("Virtual package in package.provided: %s\n") % \
						myline, noiselevel=-1)
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
				self.backupenv["USE_ORDER"] = "env:pkg:conf:defaults:pkginternal:repo:env.d"

			self.depcachedir = DEPCACHE_PATH
			if eprefix:
				# See comments about make.globals and EPREFIX
				# above. DEPCACHE_PATH is similar.
				if target_root == "/":
					# case (1) above
					self.depcachedir = os.path.join(eprefix,
						DEPCACHE_PATH.lstrip(os.sep))
				else:
					# case (2) above
					# For now, just assume DEPCACHE_PATH is relative
					# to EPREFIX.
					# TODO: Pass in more info to the constructor,
					# so we know the host system configuration.
					self.depcachedir = os.path.join(eprefix,
						DEPCACHE_PATH.lstrip(os.sep))

			if self.get("PORTAGE_DEPCACHEDIR", None):
				self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			self["PORTAGE_DEPCACHEDIR"] = self.depcachedir
			self.backup_changes("PORTAGE_DEPCACHEDIR")

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

			if eprefix:
				# For prefix environments, default to the UID and GID of
				# the top-level EROOT directory.
				try:
					eroot_st = os.stat(eroot)
				except OSError:
					pass
				else:
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

			# initialize self.features
			self.regenerate()

			if bsd_chflags:
				self.features.add('chflags')

			self._iuse_effective = self._calc_iuse_effective()
			self._iuse_implicit_match = _iuse_implicit_match_cache(self)

			self._validate_commands()

			for k in self._case_insensitive_vars:
				if k in self:
					self[k] = self[k].lower()
					self.backup_changes(k)

			if main_repo is not None and not main_repo.sync:
				main_repo_sync = self.get("SYNC")
				if main_repo_sync:
					main_repo.sync = main_repo_sync

			# The first constructed config object initializes these modules,
			# and subsequent calls to the _init() functions have no effect.
			portage.output._init(config_root=self['PORTAGE_CONFIGROOT'])
			portage.data._init(self)

		if mycpv:
			self.setcpv(mycpv)

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

	def expandLicenseTokens(self, tokens):
		""" Take a token from ACCEPT_LICENSE or package.license and expand it
		if it's a group token (indicated by @) or just return it if it's not a
		group.  If a group is negated then negate all group elements."""
		return self._license_manager.expandLicenseTokens(tokens)

	def validate(self):
		"""Validate miscellaneous settings and display warnings if necessary.
		(This code was previously in the global scope of portage.py)"""

		groups = self["ACCEPT_KEYWORDS"].split()
		archlist = self.archlist()
		if not archlist:
			writemsg(_("--- 'profiles/arch.list' is empty or "
				"not available. Empty portage tree?\n"), noiselevel=1)
		else:
			for group in groups:
				if group not in archlist and \
					not (group.startswith("-") and group[1:] in archlist) and \
					group not in ("*", "~*", "**"):
					writemsg(_("!!! INVALID ACCEPT_KEYWORDS: %s\n") % str(group),
						noiselevel=-1)

		profile_broken = not self.profile_path or \
			not os.path.exists(os.path.join(self.profile_path, "parent")) and \
			os.path.exists(os.path.join(self["PORTDIR"], "profiles"))

		if profile_broken:
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
			self.configdict["repo"].clear()
			self.configdict["defaults"]["USE"] = \
				" ".join(self.make_defaults_use)
			self.usemask = self._use_manager.getUseMask()
			self.useforce = self._use_manager.getUseForce()
		self.regenerate()

	class _lazy_vars(object):

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
				settings.mycpv, use, settings['LICENSE'], settings['SLOT'], settings.get('PORTAGE_REPO_NAME'))
			values['PORTAGE_RESTRICT'] = self._restrict(use, settings)
			return values

		def _restrict(self, use, settings):
			try:
				restrict = set(use_reduce(settings['RESTRICT'], uselist=use, flat=True))
			except InvalidDependString:
				restrict = set()
			return ' '.join(sorted(restrict))

	class _lazy_use_expand(object):
		"""
		Lazily evaluate USE_EXPAND variables since they are only needed when
		an ebuild shell is spawned. Variables values are made consistent with
		the previously calculated USE settings.
		"""

		def __init__(self, use, usemask, iuse_implicit,
			use_expand_split, use_expand_dict):
			self._use = use
			self._usemask = usemask
			self._iuse_implicit = iuse_implicit
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
			for x in self._iuse_implicit:
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

			if var_split:
				value = ' '.join(var_split)
			else:
				# Don't export empty USE_EXPAND vars unless the user config
				# exports them as empty.  This is required for vars such as
				# LINGUAS, where unset and empty have different meanings.
				if has_wildcard:
					# ebuild.sh will see this and unset the variable so
					# that things like LINGUAS work properly
					value = '*'
				else:
					if has_iuse:
						value = ''
					else:
						# It's not in IUSE, so just allow the variable content
						# to pass through if it is defined somewhere.  This
						# allows packages that support LINGUAS but don't
						# declare it in IUSE to use the variable outside of the
						# USE_EXPAND context.
						value = None

			return value

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
		if not isinstance(mycpv, basestring):
			pkg = mycpv
			mycpv = pkg.cpv
			mydb = pkg.metadata
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
		iuse = ""
		pkg_configdict = self.configdict["pkg"]
		previous_iuse = pkg_configdict.get("IUSE")
		previous_iuse_effective = pkg_configdict.get("IUSE_EFFECTIVE")
		previous_features = pkg_configdict.get("FEATURES")

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
			pkginternaluse = []
			for x in iuse.split():
				if x.startswith("+"):
					pkginternaluse.append(x[1:])
				elif x.startswith("-"):
					pkginternaluse.append(x)
			pkginternaluse = " ".join(pkginternaluse)

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

		self._penv = []
		cpdict = self._penvdict.get(cp)
		if cpdict:
			penv_matches = ordered_by_atom_specificity(cpdict, cpv_slot)
			if penv_matches:
				for x in penv_matches:
					self._penv.extend(x)

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

		if has_changed:
			self.reset(keeping_pkg=1)

		env_configdict = self.configdict['env']

		# Ensure that "pkg" values are always preferred over "env" values.
		# This must occur _after_ the above reset() call, since reset()
		# copies values from self.backupenv.
		for k in protected_pkg_keys:
			env_configdict.pop(k, None)

		lazy_vars = self._lazy_vars(built_use, self)
		env_configdict.addLazySingleton('ACCEPT_LICENSE',
			lazy_vars.__getitem__, 'ACCEPT_LICENSE')
		env_configdict.addLazySingleton('PORTAGE_RESTRICT',
			lazy_vars.__getitem__, 'PORTAGE_RESTRICT')

		if built_use is not None:
			pkg_configdict['PORTAGE_BUILT_USE'] = ' '.join(built_use)

		# If reset() has not been called, it's safe to return
		# early if IUSE has not changed.
		if not has_changed and previous_iuse == iuse and \
			(previous_iuse_effective is not None == eapi_attrs.iuse_effective):
			return

		# Filter out USE flags that aren't part of IUSE. This has to
		# be done for every setcpv() call since practically every
		# package has different IUSE.
		use = set(self["USE"].split())
		if explicit_iuse is None:
			explicit_iuse = frozenset(x.lstrip("+-") for x in iuse.split())

		if eapi_attrs.iuse_effective:
			iuse_implicit_match = self._iuse_effective_match
			portage_iuse = set(self._iuse_effective)
			portage_iuse.update(explicit_iuse)
			self.configdict["pkg"]["IUSE_EFFECTIVE"] = \
				" ".join(sorted(portage_iuse))
		else:
			iuse_implicit_match = self._iuse_implicit_match
			portage_iuse = self._get_implicit_iuse()
			portage_iuse.update(explicit_iuse)

		# PORTAGE_IUSE is not always needed so it's lazily evaluated.
		self.configdict["env"].addLazySingleton(
			"PORTAGE_IUSE", _lazy_iuse_regex, portage_iuse)

		ebuild_force_test = self.get("EBUILD_FORCE_TEST") == "1"
		if ebuild_force_test and \
			not hasattr(self, "_ebuild_force_test_msg_shown"):
				self._ebuild_force_test_msg_shown = True
				writemsg(_("Forcing test.\n"), noiselevel=-1)

		if "test" in explicit_iuse or iuse_implicit_match("test"):
			if "test" not in self.features:
				use.discard("test")
			elif "test" in self.usemask and not ebuild_force_test:
				# "test" is in IUSE and USE=test is masked, so execution
				# of src_test() probably is not reliable. Therefore,
				# temporarily disable FEATURES=test just for this package.
				self["FEATURES"] = " ".join(x for x in self.features \
					if x != "test")
				use.discard("test")
			else:
				use.add("test")
				if ebuild_force_test and "test" in self.usemask:
					self.usemask = \
						frozenset(x for x in self.usemask if x != "test")

		if eapi_attrs.feature_flag_targetroot and \
			("targetroot" in explicit_iuse or iuse_implicit_match("targetroot")):
			if self["ROOT"] != "/":
				use.add("targetroot")
			else:
				use.discard("targetroot")

		# Allow _* flags from USE_EXPAND wildcards to pass through here.
		use.difference_update([x for x in use \
			if (x not in explicit_iuse and \
			not iuse_implicit_match(x)) and x[-2:] != '_*'])

		# Use the calculated USE flags to regenerate the USE_EXPAND flags so
		# that they are consistent. For optimal performance, use slice
		# comparison instead of startswith().
		use_expand_split = set(x.lower() for \
			x in self.get('USE_EXPAND', '').split())
		lazy_use_expand = self._lazy_use_expand(use, self.usemask,
			portage_iuse, use_expand_split, self._use_expand_dict)

		use_expand_iuses = {}
		for x in portage_iuse:
			x_split = x.split('_')
			if len(x_split) == 1:
				continue
			for i in range(len(x_split) - 1):
				k = '_'.join(x_split[:i+1])
				if k in use_expand_split:
					v = use_expand_iuses.get(k)
					if v is None:
						v = set()
						use_expand_iuses[k] = v
					v.add(x)
					break

		# If it's not in IUSE, variable content is allowed
		# to pass through if it is defined somewhere.  This
		# allows packages that support LINGUAS but don't
		# declare it in IUSE to use the variable outside of the
		# USE_EXPAND context.
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

		# Controlled by FEATURES=test. Make this implicit, so handling
		# of FEATURES=test is consistent regardless of explicit IUSE.
		# Users may use use.mask/package.use.mask to control
		# FEATURES=test for all ebuilds, regardless of explicit IUSE.
		iuse_implicit.add("test")

		return iuse_implicit

	def _getUseMask(self, pkg):
		return self._use_manager.getUseMask(pkg)

	def _getUseForce(self, pkg):
		return self._use_manager.getUseForce(pkg)

	def _getMaskAtom(self, cpv, metadata):
		"""
		Take a package and return a matching package.mask atom, or None if no
		such atom exists or it has been cancelled by package.unmask. PROVIDE
		is not checked, so atoms will not be found for old-style virtuals.

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
		such atom exists or it has been cancelled by package.unmask. PROVIDE
		is not checked, so atoms will not be found for old-style virtuals.

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
		prefix. PROVIDE is not checked, so atoms will not be found for
		old-style virtuals.

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
		and the the ** keyword has not been accepted, the returned list will
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
		global_accept_keywords = self["ACCEPT_KEYWORDS"]

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
		properties.discard('||')

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

		properties_struct = use_reduce(properties_str, uselist=use, opconvert=True)
		return self._getMaskedProperties(properties_struct, acceptable_properties)

	def _getMaskedProperties(self, properties_struct, acceptable_properties):
		if not properties_struct:
			return []
		if properties_struct[0] == "||":
			ret = []
			for element in properties_struct[1:]:
				if isinstance(element, list):
					if element:
						tmp = self._getMaskedProperties(
							element, acceptable_properties)
						if not tmp:
							return []
						ret.extend(tmp)
				else:
					if element in acceptable_properties:
						return[]
					ret.append(element)
			# Return all masked properties, since we don't know which combination
			# (if any) the user will decide to unmask
			return ret

		ret = []
		for element in properties_struct:
			if isinstance(element, list):
				if element:
					ret.extend(self._getMaskedProperties(element,
						acceptable_properties))
			else:
				if element not in acceptable_properties:
					ret.append(element)
		return ret

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
		"""This updates the preferences for old-style virtuals,
		affecting the behavior of dep_expand() and dep_check()
		calls. It can change dbapi.match() behavior since that
		calls dep_expand(). However, dbapi instances have
		internal match caches that are not invalidated when
		preferences are updated here. This can potentially
		lead to some inconsistency (relevant to bug #1343)."""
		self.modifying()

		# Grab the virtuals this package provides and add them into the tree virtuals.
		if not hasattr(mydbapi, "aux_get"):
			provides = mydbapi["PROVIDE"]
		else:
			provides = mydbapi.aux_get(mycpv, ["PROVIDE"])[0]
		if not provides:
			return
		if isinstance(mydbapi, portdbapi):
			self.setcpv(mycpv, mydb=mydbapi)
			myuse = self["PORTAGE_USE"]
		elif not hasattr(mydbapi, "aux_get"):
			myuse = mydbapi["USE"]
		else:
			myuse = mydbapi.aux_get(mycpv, ["USE"])[0]
		virts = use_reduce(provides, uselist=myuse.split(), flat=True)

		# Ensure that we don't trigger the _treeVirtuals
		# assertion in VirtualsManager._compile_virtuals().
		self.getvirtuals()
		self._virtuals_manager.add_depgraph_virtuals(mycpv, virts)

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
			accept_license_str = ' '.join(mysplit)
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

					if (x[0]=="-"):
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
					if k in myincrementals:
						for x in v.split():
							if x[:1] == '-':
								expand_use.append('-' + prefix + x[1:])
							else:
								expand_use.append(prefix + x)
					else:
						for x in v.split():
							expand_use.append(prefix + x)
				if expand_use:
					expand_use.append(use)
					use  = ' '.join(expand_use)
				self.make_defaults_use.append(use)
			self.make_defaults_use = tuple(self.make_defaults_use)
			configdict_defaults['USE'] = ' '.join(
				stack_lists([x.split() for x in self.make_defaults_use]))
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
			return '' # for backward compat, don't raise KeyError

	def _getitem(self, mykey):

		if mykey in self._constant_keys:
			# These two point to temporary values when
			# portage plans to update itself.
			if mykey == "PORTAGE_BIN_PATH":
				return portage._bin_path
			elif mykey == "PORTAGE_PYM_PATH":
				return portage._pym_path

			elif mykey == "PORTAGE_GID":
				return _unicode_decode(str(portage_gid))

		for d in self.lookuplist:
			try:
				return d[mykey]
			except KeyError:
				pass

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
		else:
			self[k] = x
			return x

	def keys(self):
		return list(self)

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

	def items(self):
		return list(self.iteritems())

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		if not isinstance(myvalue, basestring):
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
		filter_calling_env = False
		if self.mycpv is not None and \
			phase not in ('clean', 'cleanrm', 'depend', 'fetch'):
			temp_dir = self.get('T')
			if temp_dir is not None and \
				os.path.exists(os.path.join(temp_dir, 'environment')):
				filter_calling_env = True

		environ_whitelist = self._environ_whitelist
		for x in self:
			if x in environ_filter:
				continue
			myvalue = self[x]
			if not isinstance(myvalue, basestring):
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

		if phase == 'depend':
			mydict.pop('FILESDIR', None)

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

		return mydict

	def thirdpartymirrors(self):
		if getattr(self, "_thirdpartymirrors", None) is None:
			profileroots = [os.path.join(self["PORTDIR"], "profiles")]
			for x in shlex_split(self.get("PORTDIR_OVERLAY", "")):
				profileroots.insert(0, os.path.join(x, "profiles"))
			thirdparty_lists = [grabdict(os.path.join(x, "thirdpartymirrors")) for x in profileroots]
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

	if sys.hexversion >= 0x3000000:
		keys = __iter__
		items = iteritems
