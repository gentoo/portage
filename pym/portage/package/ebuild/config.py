# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	'autouse', 'best_from_dict', 'check_config_instance', 'config',
]

import codecs
import copy
import errno
import logging
import re
import sys
import warnings

try:
	from configparser import SafeConfigParser, ParsingError
except ImportError:
	from ConfigParser import SafeConfigParser, ParsingError

import portage
from portage import bsd_chflags, eapi_is_supported, \
	load_mod, os, selinux, _encodings, _unicode_encode, _unicode_decode
from portage.const import CACHE_PATH, CUSTOM_PROFILE_PATH, \
	DEPCACHE_PATH, GLOBAL_CONFIG_PATH, INCREMENTALS, MAKE_CONF_FILE, \
	MODULES_FILE_PATH, PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, \
	PRIVATE_PATH, PROFILE_PATH, USER_CONFIG_PATH, USER_VIRTUALS_FILE
from portage.data import portage_gid
from portage.dbapi import dbapi
from portage.dbapi.porttree import portdbapi
from portage.dbapi.vartree import vartree
from portage.dep import Atom, best_match_to_list, dep_opconvert, \
	flatten, isvalidatom, match_from_list, match_to_list, \
	paren_reduce, remove_slot, use_reduce
from portage.env.loaders import KeyValuePairFileLoader
from portage.exception import DirectoryNotFound, InvalidAtom, \
	InvalidDependString, ParseError, PortageException
from portage.localization import _
from portage.output import colorize
from portage.process import fakeroot_capable, sandbox_capable
from portage.util import ensure_dirs, getconfig, grabdict, \
	grabdict_package, grabfile, grabfile_package, LazyItemsDict, \
	normalize_path, shlex_split, stack_dictlist, stack_dicts, stack_lists, \
	writemsg, writemsg_level
from portage.versions import catpkgsplit, catsplit, cpv_getkey

if sys.hexversion >= 0x3000000:
	basestring = str

def autouse(myvartree, use_cache=1, mysettings=None):
	"""
	autuse returns a list of USE variables auto-enabled to packages being installed

	@param myvartree: Instance of the vartree class (from /var/db/pkg...)
	@type myvartree: vartree
	@param use_cache: read values from cache
	@type use_cache: Boolean
	@param mysettings: Instance of config
	@type mysettings: config
	@rtype: string
	@returns: A string containing a list of USE variables that are enabled via use.defaults
	"""
	if mysettings is None:
		mysettings = portage.settings
	if mysettings.profile_path is None:
		return ""
	myusevars=""
	usedefaults = mysettings.use_defs
	for myuse in usedefaults:
		dep_met = True
		for mydep in usedefaults[myuse]:
			if not myvartree.dep_match(mydep,use_cache=True):
				dep_met = False
				break
		if dep_met:
			myusevars += " "+myuse
	return myusevars

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

class _local_repo_config(object):
	__slots__ = ('aliases', 'eclass_overrides', 'masters', 'name',)
	def __init__(self, name, repo_opts):
		self.name = name

		aliases = repo_opts.get('aliases')
		if aliases is not None:
			aliases = tuple(aliases.split())
		self.aliases = aliases

		eclass_overrides = repo_opts.get('eclass-overrides')
		if eclass_overrides is not None:
			eclass_overrides = tuple(eclass_overrides.split())
		self.eclass_overrides = eclass_overrides

		masters = repo_opts.get('masters')
		if masters is not None:
			masters = tuple(masters.split())
		self.masters = masters

class config(object):
	"""
	This class encompasses the main portage configuration.  Data is pulled from
	ROOT/PORTDIR/profiles/, from ROOT/etc/make.profile incrementally through all 
	parent profiles as well as from ROOT/PORTAGE_CONFIGROOT/* for user specified
	overrides.
	
	Generally if you need data like USE flags, FEATURES, environment variables,
	virtuals ...etc you look in here.
	"""

	_setcpv_aux_keys = ('DEFINED_PHASES', 'DEPEND', 'EAPI',
		'INHERITED', 'IUSE', 'KEYWORDS', 'LICENSE', 'PDEPEND',
		'PROPERTIES', 'PROVIDE', 'RDEPEND', 'SLOT',
		'repository', 'RESTRICT', 'LICENSE',)

	_env_blacklist = [
		"A", "AA", "CATEGORY", "DEPEND", "DESCRIPTION", "EAPI",
		"EBUILD_PHASE", "ED", "EMERGE_FROM", "EPREFIX", "EROOT",
		"HOMEPAGE", "INHERITED", "IUSE",
		"KEYWORDS", "LICENSE", "PDEPEND", "PF", "PKGUSE",
		"PORTAGE_CONFIGROOT", "PORTAGE_IUSE",
		"PORTAGE_NONFATAL", "PORTAGE_REPO_NAME",
		"PORTAGE_USE", "PROPERTIES", "PROVIDE", "RDEPEND", "RESTRICT",
		"ROOT", "SLOT", "SRC_URI"
	]

	_environ_whitelist = []

	# Whitelisted variables are always allowed to enter the ebuild
	# environment. Generally, this only includes special portage
	# variables. Ebuilds can unset variables that are not whitelisted
	# and rely on them remaining unset for future phases, without them
	# leaking back in from various locations (bug #189417). It's very
	# important to set our special BASH_ENV variable in the ebuild
	# environment in order to prevent sandbox from sourcing /etc/profile
	# in it's bashrc (causing major leakage).
	_environ_whitelist += [
		"ACCEPT_LICENSE", "BASH_ENV", "BUILD_PREFIX", "D",
		"DISTDIR", "DOC_SYMLINKS_DIR", "EAPI", "EBUILD",
		"EBUILD_EXIT_STATUS_FILE", "EBUILD_FORCE_TEST",
		"EBUILD_PHASE", "ECLASSDIR", "ECLASS_DEPTH", "ED",
		"EMERGE_FROM", "EPREFIX", "EROOT",
		"FEATURES", "FILESDIR", "HOME", "NOCOLOR", "PATH",
		"PKGDIR",
		"PKGUSE", "PKG_LOGDIR", "PKG_TMPDIR",
		"PORTAGE_ACTUAL_DISTDIR", "PORTAGE_ARCHLIST",
		"PORTAGE_BASHRC", "PM_EBUILD_HOOK_DIR",
		"PORTAGE_BINPKG_FILE", "PORTAGE_BINPKG_TAR_OPTS",
		"PORTAGE_BINPKG_TMPFILE",
		"PORTAGE_BIN_PATH",
		"PORTAGE_BUILDDIR", "PORTAGE_COLORMAP",
		"PORTAGE_CONFIGROOT", "PORTAGE_DEBUG", "PORTAGE_DEPCACHEDIR",
		"PORTAGE_GID",
		"PORTAGE_INST_GID", "PORTAGE_INST_UID",
		"PORTAGE_IUSE",
		"PORTAGE_LOG_FILE", "PORTAGE_MASTER_PID",
		"PORTAGE_PYM_PATH", "PORTAGE_QUIET",
		"PORTAGE_REPO_NAME", "PORTAGE_RESTRICT",
		"PORTAGE_TMPDIR", "PORTAGE_UPDATE_ENV",
		"PORTAGE_VERBOSE", "PORTAGE_WORKDIR_MODE",
		"PORTDIR", "PORTDIR_OVERLAY", "PREROOTPATH", "PROFILE_PATHS",
		"REPLACING_VERSIONS", "REPLACED_BY_VERSION",
		"ROOT", "ROOTPATH", "T", "TMP", "TMPDIR",
		"USE_EXPAND", "USE_ORDER", "WORKDIR",
		"XARGS",
	]

	# user config variables
	_environ_whitelist += [
		"DOC_SYMLINKS_DIR", "INSTALL_MASK", "PKG_INSTALL_MASK"
	]

	_environ_whitelist += [
		"A", "AA", "CATEGORY", "P", "PF", "PN", "PR", "PV", "PVR"
	]

	# misc variables inherited from the calling environment
	_environ_whitelist += [
		"COLORTERM", "DISPLAY", "EDITOR", "LESS",
		"LESSOPEN", "LOGNAME", "LS_COLORS", "PAGER",
		"TERM", "TERMCAP", "USER",
	]

	# tempdir settings
	_environ_whitelist += [
		"TMPDIR", "TEMP", "TMP",
	]

	# localization settings
	_environ_whitelist += [
		"LANG", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES",
		"LC_MONETARY", "LC_NUMERIC", "LC_TIME", "LC_PAPER",
		"LC_ALL",
	]

	# other variables inherited from the calling environment
	_environ_whitelist += [
		"CVS_RSH", "ECHANGELOG_USER",
		"GPG_AGENT_INFO",
		"SSH_AGENT_PID", "SSH_AUTH_SOCK",
		"STY", "WINDOW", "XAUTHORITY",
	]

	_environ_whitelist = frozenset(_environ_whitelist)

	_environ_whitelist_re = re.compile(r'^(CCACHE_|DISTCC_).*')

	# Filter selected variables in the config.environ() method so that
	# they don't needlessly propagate down into the ebuild environment.
	_environ_filter = []

	# Exclude anything that could be extremely long here (like SRC_URI)
	# since that could cause execve() calls to fail with E2BIG errors. For
	# example, see bug #262647.
	_environ_filter += [
		'DEPEND', 'RDEPEND', 'PDEPEND', 'SRC_URI',
	]

	# misc variables inherited from the calling environment
	_environ_filter += [
		"INFOPATH", "MANPATH", "USER",
	]

	# variables that break bash
	_environ_filter += [
		"HISTFILE", "POSIXLY_CORRECT",
	]

	# portage config variables and variables set directly by portage
	_environ_filter += [
		"ACCEPT_KEYWORDS", "ACCEPT_PROPERTIES", "AUTOCLEAN",
		"CLEAN_DELAY", "COLLISION_IGNORE", "CONFIG_PROTECT",
		"CONFIG_PROTECT_MASK", "EGENCACHE_DEFAULT_OPTS", "EMERGE_DEFAULT_OPTS",
		"EMERGE_LOG_DIR",
		"EMERGE_WARNING_DELAY", "FETCHCOMMAND", "FETCHCOMMAND_FTP",
		"FETCHCOMMAND_HTTP", "FETCHCOMMAND_SFTP",
		"GENTOO_MIRRORS", "NOCONFMEM", "O",
		"PORTAGE_BACKGROUND",
		"PORTAGE_BINHOST_CHUNKSIZE", "PORTAGE_CALLER",
		"PORTAGE_ELOG_CLASSES",
		"PORTAGE_ELOG_MAILFROM", "PORTAGE_ELOG_MAILSUBJECT",
		"PORTAGE_ELOG_MAILURI", "PORTAGE_ELOG_SYSTEM",
		"PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS", "PORTAGE_FETCH_RESUME_MIN_SIZE",
		"PORTAGE_GPG_DIR",
		"PORTAGE_GPG_KEY", "PORTAGE_IONICE_COMMAND",
		"PORTAGE_PACKAGE_EMPTY_ABORT",
		"PORTAGE_REPO_DUPLICATE_WARN",
		"PORTAGE_RO_DISTDIRS",
		"PORTAGE_RSYNC_EXTRA_OPTS", "PORTAGE_RSYNC_OPTS",
		"PORTAGE_RSYNC_RETRIES", "PORTAGE_SYNC_STALE",
		"PORTAGE_USE", "PORT_LOGDIR",
		"QUICKPKG_DEFAULT_OPTS",
		"RESUMECOMMAND", "RESUMECOMMAND_HTTP", "RESUMECOMMAND_HTTP",
		"RESUMECOMMAND_SFTP", "SYNC", "USE_EXPAND_HIDDEN", "USE_ORDER",
	]

	_environ_filter = frozenset(_environ_filter)

	_undef_lic_groups = set()
	_default_globals = (
		('ACCEPT_LICENSE',           '* -@EULA'),
		('ACCEPT_PROPERTIES',        '*'),
	)

	# To enhance usability, make some vars case insensitive
	# by forcing them to lower case.
	_case_insensitive_vars = ('AUTOCLEAN', 'NOCOLOR',)

	def __init__(self, clone=None, mycpv=None, config_profile_path=None,
		config_incrementals=None, config_root=None, target_root=None,
		local_config=True, env=None):
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
		@param local_config: Enables loading of local config (/etc/portage); used most by repoman to
		ignore local config (keywording and unmasking)
		@type local_config: Boolean
		@param env: The calling environment which is used to override settings.
			Defaults to os.environ if unspecified.
		@type env: dict
		"""

		# When initializing the global portage.settings instance, avoid
		# raising exceptions whenever possible since exceptions thrown
		# from 'import portage' or 'import portage.exceptions' statements
		# can practically render the api unusable for api consumers.
		tolerant = hasattr(portage, '_initializing_globals')

		self.already_in_regenerate = 0

		self.locked   = 0
		self.mycpv    = None
		self._setcpv_args_hash = None
		self.puse     = []
		self.modifiedkeys = []
		self.uvlist = []
		self._accept_chost_re = None
		self._accept_license = None
		self._accept_license_str = None
		self._license_groups = {}
		self._accept_properties = None

		self.virtuals = {}
		self.virts_p = {}
		self.dirVirtuals = None
		self.v_count  = 0

		# Virtuals obtained from the vartree
		self.treeVirtuals = {}
		# Virtuals by user specification. Includes negatives.
		self.userVirtuals = {}
		# Virtual negatives from user specifications.
		self.negVirtuals  = {}
		# Virtuals added by the depgraph via self.setinst().
		self._depgraphVirtuals = {}

		self.user_profile_dir = None
		self.local_config = local_config
		self._local_repo_configs = None
		self._local_repo_conf_path = None

		if clone:
			# For immutable attributes, use shallow copy for
			# speed and memory conservation.
			self.categories = clone.categories
			self.depcachedir = clone.depcachedir
			self.incrementals = clone.incrementals
			self.module_priority = clone.module_priority
			self.profile_path = clone.profile_path
			self.profiles = clone.profiles
			self.packages = clone.packages
			self.useforce_list = clone.useforce_list
			self.usemask_list = clone.usemask_list
			self._iuse_implicit_re = clone._iuse_implicit_re

			self.user_profile_dir = copy.deepcopy(clone.user_profile_dir)
			self.local_config = copy.deepcopy(clone.local_config)
			self._local_repo_configs = \
				copy.deepcopy(clone._local_repo_configs)
			self._local_repo_conf_path = \
				copy.deepcopy(clone._local_repo_conf_path)
			self.modules         = copy.deepcopy(clone.modules)
			self.virtuals = copy.deepcopy(clone.virtuals)
			self.dirVirtuals = copy.deepcopy(clone.dirVirtuals)
			self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
			self.userVirtuals = copy.deepcopy(clone.userVirtuals)
			self.negVirtuals  = copy.deepcopy(clone.negVirtuals)
			self._depgraphVirtuals = copy.deepcopy(clone._depgraphVirtuals)

			self.use_defs = copy.deepcopy(clone.use_defs)
			self.usemask  = copy.deepcopy(clone.usemask)
			self.pusemask_list = copy.deepcopy(clone.pusemask_list)
			self.useforce      = copy.deepcopy(clone.useforce)
			self.puseforce_list = copy.deepcopy(clone.puseforce_list)
			self.puse     = copy.deepcopy(clone.puse)
			self.make_defaults_use = copy.deepcopy(clone.make_defaults_use)
			self.pkgprofileuse = copy.deepcopy(clone.pkgprofileuse)
			self.mycpv    = copy.deepcopy(clone.mycpv)
			self._setcpv_args_hash = copy.deepcopy(clone._setcpv_args_hash)

			self.configdict = copy.deepcopy(clone.configdict)
			self.configlist = [
				self.configdict['env.d'],
				self.configdict['pkginternal'],
				self.configdict['globals'],
				self.configdict['defaults'],
				self.configdict['conf'],
				self.configdict['pkg'],
				self.configdict['auto'],
				self.configdict['env'],
			]
			self.lookuplist = self.configlist[:]
			self.lookuplist.reverse()
			self._use_expand_dict = copy.deepcopy(clone._use_expand_dict)
			self.backupenv  = self.configdict["backupenv"]
			self.pusedict   = copy.deepcopy(clone.pusedict)
			self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
			self._pkeywords_list = copy.deepcopy(clone._pkeywords_list)
			self.pmaskdict = copy.deepcopy(clone.pmaskdict)
			self.punmaskdict = copy.deepcopy(clone.punmaskdict)
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.pprovideddict = copy.deepcopy(clone.pprovideddict)
			self.features = copy.deepcopy(clone.features)

			self._accept_license = copy.deepcopy(clone._accept_license)
			self._plicensedict = copy.deepcopy(clone._plicensedict)
			self._license_groups = copy.deepcopy(clone._license_groups)
			self._accept_properties = copy.deepcopy(clone._accept_properties)
			self._ppropertiesdict = copy.deepcopy(clone._ppropertiesdict)

		else:

			def check_var_directory(varname, var):
				if not os.path.isdir(var):
					writemsg(_("!!! Error: %s='%s' is not a directory. "
						"Please correct this.\n") % (varname, var),
						noiselevel=-1)
					raise DirectoryNotFound(var)

			if config_root is None:
				config_root = "/"

			config_root = normalize_path(os.path.abspath(
				config_root)).rstrip(os.path.sep) + os.path.sep

			check_var_directory("PORTAGE_CONFIGROOT", config_root)

			self.depcachedir = DEPCACHE_PATH

			if not config_profile_path:
				config_profile_path = \
					os.path.join(config_root, PROFILE_PATH)
				if os.path.isdir(config_profile_path):
					self.profile_path = config_profile_path
				else:
					self.profile_path = None
			else:
				self.profile_path = config_profile_path

			if config_incrementals is None:
				self.incrementals = INCREMENTALS
			else:
				self.incrementals = config_incrementals
			if not isinstance(self.incrementals, tuple):
				self.incrementals = tuple(self.incrementals)

			self.module_priority    = ("user", "default")
			self.modules            = {}
			modules_loader = KeyValuePairFileLoader(
				os.path.join(config_root, MODULES_FILE_PATH), None, None)
			modules_dict, modules_errors = modules_loader.load()
			self.modules["user"] = modules_dict
			if self.modules["user"] is None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "portage.cache.metadata.database",
				"portdbapi.auxdbmodule":  "portage.cache.flat_hash.database",
			}

			self.usemask=[]
			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			self._use_expand_dict = {}
			# configlist will contain: [ env.d, globals, defaults, conf, pkg, auto, backupenv, env ]
			self.configlist.append({})
			self.configdict["env.d"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkginternal"] = self.configlist[-1]

			# The symlink might not exist or might not be a symlink.
			if self.profile_path is None:
				self.profiles = []
			else:
				self.profiles = []
				def addProfile(currentPath):
					parentsFile = os.path.join(currentPath, "parent")
					eapi_file = os.path.join(currentPath, "eapi")
					try:
						eapi = codecs.open(_unicode_encode(eapi_file,
							encoding=_encodings['fs'], errors='strict'),
							mode='r', encoding=_encodings['content'], errors='replace'
							).readline().strip()
					except IOError:
						pass
					else:
						if not eapi_is_supported(eapi):
							raise ParseError(_(
								"Profile contains unsupported "
								"EAPI '%s': '%s'") % \
								(eapi, os.path.realpath(eapi_file),))
					if os.path.exists(parentsFile):
						parents = grabfile(parentsFile)
						if not parents:
							raise ParseError(
								_("Empty parent file: '%s'") % parentsFile)
						for parentPath in parents:
							parentPath = normalize_path(os.path.join(
								currentPath, parentPath))
							if os.path.exists(parentPath):
								addProfile(parentPath)
							else:
								raise ParseError(
									_("Parent '%s' not found: '%s'") %  \
									(parentPath, parentsFile))
					self.profiles.append(currentPath)
				try:
					addProfile(os.path.realpath(self.profile_path))
				except ParseError as e:
					writemsg(_("!!! Unable to parse profile: '%s'\n") % \
						self.profile_path, noiselevel=-1)
					writemsg("!!! ParseError: %s\n" % str(e), noiselevel=-1)
					del e
					self.profiles = []
			if local_config and self.profiles:
				custom_prof = os.path.join(
					config_root, CUSTOM_PROFILE_PATH)
				if os.path.exists(custom_prof):
					self.user_profile_dir = custom_prof
					self.profiles.append(custom_prof)
				del custom_prof

			self.profiles = tuple(self.profiles)
			self.packages_list = [grabfile_package(os.path.join(x, "packages")) for x in self.profiles]
			self.packages      = tuple(stack_lists(self.packages_list, incremental=1))
			del self.packages_list
			#self.packages = grab_stacked("packages", self.profiles, grabfile, incremental_lines=1)

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				# Negative atoms are filtered by the above stack_lists() call.
				if not isinstance(x, Atom):
					x = Atom(x.lstrip('*'))
				self.prevmaskdict.setdefault(x.cp, []).append(x)

			self._pkeywords_list = []
			rawpkeywords = [grabdict_package(
				os.path.join(x, "package.keywords"), recursive=1) \
				for x in self.profiles]
			for pkeyworddict in rawpkeywords:
				cpdict = {}
				for k, v in pkeyworddict.items():
					cpdict.setdefault(k.cp, {})[k] = v
				self._pkeywords_list.append(cpdict)

			# get profile-masked use flags -- INCREMENTAL Child over parent
			self.usemask_list = tuple(
				tuple(grabfile(os.path.join(x, "use.mask"), recursive=1))
				for x in self.profiles)
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			use_defs_lists = [grabdict(os.path.join(x, "use.defaults")) for x in self.profiles]
			self.use_defs  = stack_dictlist(use_defs_lists, incremental=True)
			del use_defs_lists

			self.pusemask_list = []
			rawpusemask = [grabdict_package(os.path.join(x, "package.use.mask"),
				recursive=1) for x in self.profiles]
			for pusemaskdict in rawpusemask:
				cpdict = {}
				for k, v in pusemaskdict.items():
					cpdict.setdefault(k.cp, {})[k] = v
				self.pusemask_list.append(cpdict)
			del rawpusemask

			self.pkgprofileuse = []
			rawprofileuse = [grabdict_package(os.path.join(x, "package.use"),
				juststrings=True, recursive=1) for x in self.profiles]
			for rawpusedict in rawprofileuse:
				cpdict = {}
				for k, v in rawpusedict.items():
					cpdict.setdefault(k.cp, {})[k] = v
				self.pkgprofileuse.append(cpdict)
			del rawprofileuse

			self.useforce_list = tuple(
				tuple(grabfile(os.path.join(x, "use.force"), recursive=1))
				for x in self.profiles)
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))

			self.puseforce_list = []
			rawpuseforce = [grabdict_package(
				os.path.join(x, "package.use.force"), recursive=1) \
				for x in self.profiles]
			for rawpusefdict in rawpuseforce:
				cpdict = {}
				for k, v in rawpusefdict.items():
					cpdict.setdefault(k.cp, {})[k] = v
				self.puseforce_list.append(cpdict)
			del rawpuseforce

			make_conf = getconfig(
				os.path.join(config_root, MAKE_CONF_FILE),
				tolerant=tolerant, allow_sourcing=True)
			if make_conf is None:
				make_conf = {}

			# Allow ROOT setting to come from make.conf if it's not overridden
			# by the constructor argument (from the calling environment).
			if target_root is None and "ROOT" in make_conf:
				target_root = make_conf["ROOT"]
				if not target_root.strip():
					target_root = None
			if target_root is None:
				target_root = "/"

			target_root = normalize_path(os.path.abspath(
				target_root)).rstrip(os.path.sep) + os.path.sep

			ensure_dirs(target_root)
			check_var_directory("ROOT", target_root)

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
			expand_map = {}

			env_d = getconfig(os.path.join(target_root, "etc", "profile.env"),
				expand=expand_map)
			# env_d will be None if profile.env doesn't exist.
			if env_d:
				self.configdict["env.d"].update(env_d)
				expand_map.update(env_d)

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

			# make.globals should not be relative to config_root
			# because it only contains constants.
			for x in (GLOBAL_CONFIG_PATH, "/etc"):
				self.mygcfg = getconfig(os.path.join(x, "make.globals"),
					expand=expand_map)
				if self.mygcfg:
					break

			if self.mygcfg is None:
				self.mygcfg = {}

			for k, v in self._default_globals:
				self.mygcfg.setdefault(k, v)

			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.make_defaults_use = []
			self.mygcfg = {}
			if self.profiles:
				mygcfg_dlists = [getconfig(os.path.join(x, "make.defaults"),
					expand=expand_map) for x in self.profiles]

				for cfg in mygcfg_dlists:
					if cfg:
						self.make_defaults_use.append(cfg.get("USE", ""))
					else:
						self.make_defaults_use.append("")
				self.mygcfg = stack_dicts(mygcfg_dlists,
					incrementals=INCREMENTALS)
				if self.mygcfg is None:
					self.mygcfg = {}
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			self.mygcfg = getconfig(
				os.path.join(config_root, MAKE_CONF_FILE),
				tolerant=tolerant, allow_sourcing=True, expand=expand_map)
			if self.mygcfg is None:
				self.mygcfg = {}

			# Don't allow the user to override certain variables in make.conf
			profile_only_variables = self.configdict["defaults"].get(
				"PROFILE_ONLY_VARIABLES", "").split()
			profile_only_variables = stack_lists([profile_only_variables])
			for k in profile_only_variables:
				self.mygcfg.pop(k, None)

			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append(LazyItemsDict())
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

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

			# Prefix forward compatability, set EPREFIX to the empty string
			self["EPREFIX"] = ''
			self.backup_changes("EPREFIX")
			self["EROOT"] = target_root
			self.backup_changes("EROOT")

			self.pusedict = {}
			self.pkeywordsdict = {}
			self._plicensedict = {}
			self._ppropertiesdict = {}
			self.punmaskdict = {}
			abs_user_config = os.path.join(config_root, USER_CONFIG_PATH)

			# locations for "categories" and "arch.list" files
			locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations.extend(self.profiles)

			""" repoman controls PORTDIR_OVERLAY via the environment, so no
			special cases are needed here."""

			overlays = shlex_split(self.get('PORTDIR_OVERLAY', ''))
			if overlays:
				new_ov = []
				for ov in overlays:
					ov = normalize_path(ov)
					if os.path.isdir(ov):
						new_ov.append(ov)
					else:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY"
							" (not a dir): '%s'\n") % ov, noiselevel=-1)
				self["PORTDIR_OVERLAY"] = " ".join(new_ov)
				self.backup_changes("PORTDIR_OVERLAY")

			overlay_profiles = []
			for ov in shlex_split(self.get('PORTDIR_OVERLAY', '')):
				ov = normalize_path(ov)
				profiles_dir = os.path.join(ov, "profiles")
				if os.path.isdir(profiles_dir):
					overlay_profiles.append(profiles_dir)
			locations += overlay_profiles
			
			pmask_locations.extend(overlay_profiles)

			if local_config:
				locations.append(abs_user_config)
				pmask_locations.append(abs_user_config)
				pusedict = grabdict_package(
					os.path.join(abs_user_config, "package.use"), recursive=1)
				for k, v in pusedict.items():
					self.pusedict.setdefault(k.cp, {})[k] = v

				#package.keywords
				pkgdict = grabdict_package(
					os.path.join(abs_user_config, "package.keywords"),
					recursive=1)
				for k, v in pkgdict.items():
					# default to ~arch if no specific keyword is given
					if not v:
						mykeywordlist = []
						if self.configdict["defaults"] and \
							"ACCEPT_KEYWORDS" in self.configdict["defaults"]:
							groups = self.configdict["defaults"]["ACCEPT_KEYWORDS"].split()
						else:
							groups = []
						for keyword in groups:
							if not keyword[0] in "~-":
								mykeywordlist.append("~"+keyword)
						v = mykeywordlist
					self.pkeywordsdict.setdefault(k.cp, {})[k] = v

				#package.license
				licdict = grabdict_package(os.path.join(
					abs_user_config, "package.license"), recursive=1)
				for k, v in licdict.items():
					cp = k.cp
					cp_dict = self._plicensedict.get(cp)
					if not cp_dict:
						cp_dict = {}
						self._plicensedict[cp] = cp_dict
					cp_dict[k] = self.expandLicenseTokens(v)

				#package.properties
				propdict = grabdict_package(os.path.join(
					abs_user_config, "package.properties"), recursive=1)
				for k, v in propdict.items():
					cp = k.cp
					cp_dict = self._ppropertiesdict.get(cp)
					if not cp_dict:
						cp_dict = {}
						self._ppropertiesdict[cp] = cp_dict
					cp_dict[k] = v

				self._local_repo_configs = {}
				self._local_repo_conf_path = \
					os.path.join(abs_user_config, 'repos.conf')

				repo_conf_parser = SafeConfigParser()
				try:
					repo_conf_parser.readfp(
						codecs.open(
						_unicode_encode(self._local_repo_conf_path,
						encoding=_encodings['fs'], errors='strict'),
						mode='r', encoding=_encodings['content'], errors='replace')
					)
				except EnvironmentError as e:
					if e.errno != errno.ENOENT:
						raise
					del e
				except ParsingError as e:
					writemsg_level(
						_("!!! Error parsing '%s': %s\n")  % \
						(self._local_repo_conf_path, e),
						level=logging.ERROR, noiselevel=-1)
					del e
				else:
					repo_defaults = repo_conf_parser.defaults()
					if repo_defaults:
						self._local_repo_configs['DEFAULT'] = \
							_local_repo_config('DEFAULT', repo_defaults)
					for repo_name in repo_conf_parser.sections():
						repo_opts = repo_defaults.copy()
						for opt_name in repo_conf_parser.options(repo_name):
							repo_opts[opt_name] = \
								repo_conf_parser.get(repo_name, opt_name)
						self._local_repo_configs[repo_name] = \
							_local_repo_config(repo_name, repo_opts)

			#getting categories from an external file now
			categories = [grabfile(os.path.join(x, "categories")) for x in locations]
			category_re = dbapi._category_re
			self.categories = tuple(sorted(
				x for x in stack_lists(categories, incremental=1)
				if category_re.match(x) is not None))
			del categories

			archlist = [grabfile(os.path.join(x, "arch.list")) for x in locations]
			archlist = stack_lists(archlist, incremental=1)
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = " ".join(archlist)

			# package.mask and package.unmask
			pkgmasklines = []
			pkgunmasklines = []
			for x in pmask_locations:
				pkgmasklines.append(grabfile_package(
					os.path.join(x, "package.mask"), recursive=1))
				pkgunmasklines.append(grabfile_package(
					os.path.join(x, "package.unmask"), recursive=1))
			pkgmasklines = stack_lists(pkgmasklines, incremental=1)
			pkgunmasklines = stack_lists(pkgunmasklines, incremental=1)

			self.pmaskdict = {}
			for x in pkgmasklines:
				self.pmaskdict.setdefault(x.cp, []).append(x)

			for x in pkgunmasklines:
				self.punmaskdict.setdefault(x.cp, []).append(x)

			pkgprovidedlines = [grabfile(os.path.join(x, "package.provided"), recursive=1) for x in self.profiles]
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

			# parse licensegroups
			license_groups = self._license_groups
			for x in locations:
				for k, v in grabdict(
					os.path.join(x, "license_groups")).items():
					license_groups.setdefault(k, []).extend(v)

			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			if "USE_ORDER" not in self:
				self.backupenv["USE_ORDER"] = "env:pkg:conf:defaults:pkginternal:env.d"

			self["PORTAGE_GID"] = str(portage_gid)
			self.backup_changes("PORTAGE_GID")

			if self.get("PORTAGE_DEPCACHEDIR", None):
				self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			self["PORTAGE_DEPCACHEDIR"] = self.depcachedir
			self.backup_changes("PORTAGE_DEPCACHEDIR")

			if "CBUILD" not in self and "CHOST" in self:
				self["CBUILD"] = self["CHOST"]
				self.backup_changes("CBUILD")

			self["PORTAGE_BIN_PATH"] = PORTAGE_BIN_PATH
			self.backup_changes("PORTAGE_BIN_PATH")
			self["PORTAGE_PYM_PATH"] = PORTAGE_PYM_PATH
			self.backup_changes("PORTAGE_PYM_PATH")

			for var in ("PORTAGE_INST_UID", "PORTAGE_INST_GID"):
				try:
					self[var] = str(int(self.get(var, "0")))
				except ValueError:
					writemsg(_("!!! %s='%s' is not a valid integer.  "
						"Falling back to '0'.\n") % (var, self[var]),
						noiselevel=-1)
					self[var] = "0"
				self.backup_changes(var)

			# initialize self.features
			self.regenerate()

			if bsd_chflags:
				self.features.add('chflags')

			self["FEATURES"] = " ".join(sorted(self.features))
			self.backup_changes("FEATURES")
			global _glep_55_enabled, _validate_cache_for_unsupported_eapis
			if 'parse-eapi-ebuild-head' in self.features:
				_validate_cache_for_unsupported_eapis = False
			if 'parse-eapi-glep-55' in self.features:
				_validate_cache_for_unsupported_eapis = False
				_glep_55_enabled = True

			self._iuse_implicit_re = re.compile("^(%s)$" % \
				"|".join(self._get_implicit_iuse()))

		for k in self._case_insensitive_vars:
			if k in self:
				self[k] = self[k].lower()
				self.backup_changes(k)

		if mycpv:
			self.setcpv(mycpv)

	def _init_dirs(self):
		"""
		Create a few directories that are critical to portage operation
		"""
		if not os.access(self["ROOT"], os.W_OK):
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
			mydir = os.path.join(self["ROOT"], mypath)
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

	def expandLicenseTokens(self, tokens):
		""" Take a token from ACCEPT_LICENSE or package.license and expand it
		if it's a group token (indicated by @) or just return it if it's not a
		group.  If a group is negated then negate all group elements."""
		expanded_tokens = []
		for x in tokens:
			expanded_tokens.extend(self._expandLicenseToken(x, None))
		return expanded_tokens

	def _expandLicenseToken(self, token, traversed_groups):
		negate = False
		rValue = []
		if token.startswith("-"):
			negate = True
			license_name = token[1:]
		else:
			license_name = token
		if not license_name.startswith("@"):
			rValue.append(token)
			return rValue
		group_name = license_name[1:]
		if traversed_groups is None:
			traversed_groups = set()
		license_group = self._license_groups.get(group_name)
		if group_name in traversed_groups:
			writemsg(_("Circular license group reference"
				" detected in '%s'\n") % group_name, noiselevel=-1)
			rValue.append("@"+group_name)
		elif license_group:
			traversed_groups.add(group_name)
			for l in license_group:
				if l.startswith("-"):
					writemsg(_("Skipping invalid element %s"
						" in license group '%s'\n") % (l, group_name),
						noiselevel=-1)
				else:
					rValue.extend(self._expandLicenseToken(l, traversed_groups))
		else:
			if self._license_groups and \
				group_name not in self._undef_lic_groups:
				self._undef_lic_groups.add(group_name)
				writemsg(_("Undefined license group '%s'\n") % group_name,
					noiselevel=-1)
			rValue.append("@"+group_name)
		if negate:
			rValue = ["-" + token for token in rValue]
		return rValue

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

		abs_profile_path = os.path.join(self["PORTAGE_CONFIGROOT"],
			PROFILE_PATH)
		if not self.profile_path or (not os.path.islink(abs_profile_path) and \
			not os.path.exists(os.path.join(abs_profile_path, "parent")) and \
			os.path.exists(os.path.join(self["PORTDIR"], "profiles"))):
			writemsg(_("\a\n\n!!! %s is not a symlink and will probably prevent most merges.\n") % abs_profile_path,
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

	def loadVirtuals(self,root):
		"""Not currently used by portage."""
		writemsg("DEPRECATED: portage.config.loadVirtuals\n")
		self.getvirtuals(root)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		mod = None
		try:
			mod = load_mod(best_mod)
		except ImportError:
			if best_mod.startswith("cache."):
				best_mod = "portage." + best_mod
				try:
					mod = load_mod(best_mod)
				except ImportError:
					pass
		if mod is None:
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

	def reset(self,keeping_pkg=0,use_cache=1):
		"""
		Restore environment from self.backupenv, call self.regenerate()
		@param keeping_pkg: Should we keep the set_cpv() data or delete it.
		@type keeping_pkg: Boolean
		@param use_cache: Should self.regenerate use the cache or not
		@type use_cache: Boolean
		@rype: None
		"""
		self.modifying()
		self.configdict["env"].clear()
		self.configdict["env"].update(self.backupenv)

		self.modifiedkeys = []
		if not keeping_pkg:
			self.mycpv = None
			self.puse = ""
			self.configdict["pkg"].clear()
			self.configdict["pkginternal"].clear()
			self.configdict["defaults"]["USE"] = \
				" ".join(self.make_defaults_use)
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))
		self.regenerate(use_cache=use_cache)

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
			values['ACCEPT_LICENSE'] = self._accept_license(use, settings)
			values['PORTAGE_RESTRICT'] = self._restrict(use, settings)
			return values

		def _accept_license(self, use, settings):
			"""
			Generate a pruned version of ACCEPT_LICENSE, by intersection with
			LICENSE. This is required since otherwise ACCEPT_LICENSE might be
			too big (bigger than ARG_MAX), causing execve() calls to fail with
			E2BIG errors as in bug #262647.
			"""
			try:
				licenses = set(flatten(
					use_reduce(paren_reduce(
					settings['LICENSE']),
					uselist=use)))
			except InvalidDependString:
				licenses = set()
			licenses.discard('||')
			if settings._accept_license:
				acceptable_licenses = set()
				for x in settings._accept_license:
					if x == '*':
						acceptable_licenses.update(licenses)
					elif x == '-*':
						acceptable_licenses.clear()
					elif x[:1] == '-':
						acceptable_licenses.discard(x[1:])
					elif x in licenses:
						acceptable_licenses.add(x)

				licenses = acceptable_licenses
			return ' '.join(sorted(licenses))

		def _restrict(self, use, settings):
			try:
				restrict = set(flatten(
					use_reduce(paren_reduce(
					settings['RESTRICT']),
					uselist=use)))
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

	def setcpv(self, mycpv, use_cache=1, mydb=None):
		"""
		Load a particular CPV into the config, this lets us see the
		Default USE flags for a particular ebuild as well as the USE
		flags from package.use.

		@param mycpv: A cpv to load
		@type mycpv: string
		@param use_cache: Enables caching
		@type use_cache: Boolean
		@param mydb: a dbapi instance that supports aux_get with the IUSE key.
		@type mydb: dbapi or derivative.
		@rtype: None
		"""

		self.modifying()

		pkg = None
		built_use = None
		if not isinstance(mycpv, basestring):
			pkg = mycpv
			mycpv = pkg.cpv
			mydb = pkg.metadata
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

		aux_keys = self._setcpv_aux_keys

		# Discard any existing metadata from the previous package, but
		# preserve things like USE_EXPAND values and PORTAGE_USE which
		# might be reused.
		for k in aux_keys:
			pkg_configdict.pop(k, None)

		pkg_configdict["CATEGORY"] = cat
		pkg_configdict["PF"] = pf
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
				for k, v in zip(aux_keys, mydb.aux_get(self.mycpv, aux_keys)):
					pkg_configdict[k] = v
			repository = pkg_configdict.pop("repository", None)
			if repository is not None:
				pkg_configdict["PORTAGE_REPO_NAME"] = repository
			slot = pkg_configdict["SLOT"]
			iuse = pkg_configdict["IUSE"]
			if pkg is None:
				cpv_slot = "%s:%s" % (self.mycpv, slot)
			else:
				cpv_slot = pkg
			pkginternaluse = []
			for x in iuse.split():
				if x.startswith("+"):
					pkginternaluse.append(x[1:])
				elif x.startswith("-"):
					pkginternaluse.append(x)
			pkginternaluse = " ".join(pkginternaluse)
		if pkginternaluse != self.configdict["pkginternal"].get("USE", ""):
			self.configdict["pkginternal"]["USE"] = pkginternaluse
			has_changed = True

		defaults = []
		pos = 0
		for i, pkgprofileuse_dict in enumerate(self.pkgprofileuse):
			cpdict = pkgprofileuse_dict.get(cp)
			if cpdict:
				keys = list(cpdict)
				while keys:
					bestmatch = best_match_to_list(cpv_slot, keys)
					if bestmatch:
						keys.remove(bestmatch)
						defaults.insert(pos, cpdict[bestmatch])
					else:
						break
				del keys
			if self.make_defaults_use[i]:
				defaults.insert(pos, self.make_defaults_use[i])
			pos = len(defaults)
		defaults = " ".join(defaults)
		if defaults != self.configdict["defaults"].get("USE",""):
			self.configdict["defaults"]["USE"] = defaults
			has_changed = True

		useforce = self._getUseForce(cpv_slot)
		if useforce != self.useforce:
			self.useforce = useforce
			has_changed = True

		usemask = self._getUseMask(cpv_slot)
		if usemask != self.usemask:
			self.usemask = usemask
			has_changed = True
		oldpuse = self.puse
		self.puse = ""
		cpdict = self.pusedict.get(cp)
		if cpdict:
			keys = list(cpdict)
			while keys:
				self.pusekey = best_match_to_list(cpv_slot, keys)
				if self.pusekey:
					keys.remove(self.pusekey)
					self.puse = (" ".join(cpdict[self.pusekey])) + " " + self.puse
				else:
					break
			del keys
		if oldpuse != self.puse:
			has_changed = True
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE

		if has_changed:
			self.reset(keeping_pkg=1,use_cache=use_cache)

		# Ensure that "pkg" values are always preferred over "env" values.
		# This must occur _after_ the above reset() call, since reset()
		# copies values from self.backupenv.
		env_configdict = self.configdict['env']
		for k in pkg_configdict:
			if k != 'USE':
				env_configdict.pop(k, None)

		lazy_vars = self._lazy_vars(built_use, self)
		env_configdict.addLazySingleton('ACCEPT_LICENSE',
			lazy_vars.__getitem__, 'ACCEPT_LICENSE')
		env_configdict.addLazySingleton('PORTAGE_RESTRICT',
			lazy_vars.__getitem__, 'PORTAGE_RESTRICT')

		# If reset() has not been called, it's safe to return
		# early if IUSE has not changed.
		if not has_changed and previous_iuse == iuse:
			return

		# Filter out USE flags that aren't part of IUSE. This has to
		# be done for every setcpv() call since practically every
		# package has different IUSE.
		use = set(self["USE"].split())
		iuse_implicit = self._get_implicit_iuse()
		iuse_implicit.update(x.lstrip("+-") for x in iuse.split())

		# PORTAGE_IUSE is not always needed so it's lazily evaluated.
		self.configdict["pkg"].addLazySingleton(
			"PORTAGE_IUSE", _lazy_iuse_regex, iuse_implicit)

		ebuild_force_test = self.get("EBUILD_FORCE_TEST") == "1"
		if ebuild_force_test and \
			not hasattr(self, "_ebuild_force_test_msg_shown"):
				self._ebuild_force_test_msg_shown = True
				writemsg(_("Forcing test.\n"), noiselevel=-1)
		if "test" in self.features:
			if "test" in self.usemask and not ebuild_force_test:
				# "test" is in IUSE and USE=test is masked, so execution
				# of src_test() probably is not reliable. Therefore,
				# temporarily disable FEATURES=test just for this package.
				self["FEATURES"] = " ".join(x for x in self.features \
					if x != "test")
				use.discard("test")
			else:
				use.add("test")
				if ebuild_force_test:
					self.usemask.discard("test")

		# Allow _* flags from USE_EXPAND wildcards to pass through here.
		use.difference_update([x for x in use \
			if x not in iuse_implicit and x[-2:] != '_*'])

		# Use the calculated USE flags to regenerate the USE_EXPAND flags so
		# that they are consistent. For optimal performance, use slice
		# comparison instead of startswith().
		use_expand_split = set(x.lower() for \
			x in self.get('USE_EXPAND', '').split())
		lazy_use_expand = self._lazy_use_expand(use, self.usemask,
			iuse_implicit, use_expand_split, self._use_expand_dict)

		use_expand_iuses = {}
		for x in iuse_implicit:
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

		# Filtered for the ebuild environment. Store this in a separate
		# attribute since we still want to be able to see global USE
		# settings for things like emerge --info.

		self.configdict["pkg"]["PORTAGE_USE"] = \
			" ".join(sorted(x for x in use if x[-2:] != '_*'))

	def _get_implicit_iuse(self):
		"""
		Some flags are considered to
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
		cp = getattr(pkg, "cp", None)
		if cp is None:
			cp = cpv_getkey(remove_slot(pkg))
		usemask = []
		pos = 0
		for i, pusemask_dict in enumerate(self.pusemask_list):
			cpdict = pusemask_dict.get(cp)
			if cpdict:
				keys = list(cpdict)
				while keys:
					best_match = best_match_to_list(pkg, keys)
					if best_match:
						keys.remove(best_match)
						usemask.insert(pos, cpdict[best_match])
					else:
						break
				del keys
			if self.usemask_list[i]:
				usemask.insert(pos, self.usemask_list[i])
			pos = len(usemask)
		return set(stack_lists(usemask, incremental=True))

	def _getUseForce(self, pkg):
		cp = getattr(pkg, "cp", None)
		if cp is None:
			cp = cpv_getkey(remove_slot(pkg))
		useforce = []
		pos = 0
		for i, puseforce_dict in enumerate(self.puseforce_list):
			cpdict = puseforce_dict.get(cp)
			if cpdict:
				keys = list(cpdict)
				while keys:
					best_match = best_match_to_list(pkg, keys)
					if best_match:
						keys.remove(best_match)
						useforce.insert(pos, cpdict[best_match])
					else:
						break
				del keys
			if self.useforce_list[i]:
				useforce.insert(pos, self.useforce_list[i])
			pos = len(useforce)
		return set(stack_lists(useforce, incremental=True))

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
		@return: An matching atom string or None if one is not found.
		"""

		cp = cpv_getkey(cpv)
		mask_atoms = self.pmaskdict.get(cp)
		if mask_atoms:
			pkg_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			unmask_atoms = self.punmaskdict.get(cp)
			for x in mask_atoms:
				if not match_from_list(x, pkg_list):
					continue
				if unmask_atoms:
					for y in unmask_atoms:
						if match_from_list(y, pkg_list):
							return None
				return x
		return None

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
		@return: An matching profile atom string or None if one is not found.
		"""

		cp = cpv_getkey(cpv)
		profile_atoms = self.prevmaskdict.get(cp)
		if profile_atoms:
			pkg_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			for x in profile_atoms:
				if match_from_list(x, pkg_list):
					continue
				return x
		return None

	def _getKeywords(self, cpv, metadata):
		cp = cpv_getkey(cpv)
		pkg = "%s:%s" % (cpv, metadata["SLOT"])
		keywords = [[x for x in metadata["KEYWORDS"].split() if x != "-*"]]
		pos = len(keywords)
		for pkeywords_dict in self._pkeywords_list:
			cpdict = pkeywords_dict.get(cp)
			if cpdict:
				keys = list(cpdict)
				while keys:
					best_match = best_match_to_list(pkg, keys)
					if best_match:
						keys.remove(best_match)
						keywords.insert(pos, cpdict[best_match])
					else:
						break
			pos = len(keywords)
		return stack_lists(keywords, incremental=True)

	def _getMissingKeywords(self, cpv, metadata):
		"""
		Take a package and return a list of any KEYWORDS that the user may
		may need to accept for the given package. If the KEYWORDS are empty
		and the the ** keyword has not been accepted, the returned list will
		contain ** alone (in order to distiguish from the case of "none
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
		egroups = self.configdict["backupenv"].get(
			"ACCEPT_KEYWORDS", "").split()
		mygroups = self._getKeywords(cpv, metadata)
		# Repoman may modify this attribute as necessary.
		pgroups = self["ACCEPT_KEYWORDS"].split()
		match=0
		cp = cpv_getkey(cpv)
		pkgdict = self.pkeywordsdict.get(cp)
		matches = False
		if pkgdict:
			cpv_slot_list = ["%s:%s" % (cpv, metadata["SLOT"])]
			for atom, pkgkeywords in pkgdict.items():
				if match_from_list(atom, cpv_slot_list):
					matches = True
					pgroups.extend(pkgkeywords)
		if matches or egroups:
			pgroups.extend(egroups)
			inc_pgroups = set()
			for x in pgroups:
				if x.startswith("-"):
					if x == "-*":
						inc_pgroups.clear()
					else:
						inc_pgroups.discard(x[1:])
				else:
					inc_pgroups.add(x)
			pgroups = inc_pgroups
			del inc_pgroups
		hasstable = False
		hastesting = False
		for gp in mygroups:
			if gp == "*" or (gp == "-*" and len(mygroups) == 1):
				writemsg(_("--- WARNING: Package '%(cpv)s' uses"
					" '%(keyword)s' keyword.\n") % {"cpv": cpv, "keyword": gp}, noiselevel=-1)
				if gp == "*":
					match = 1
					break
			elif gp in pgroups:
				match=1
				break
			elif gp.startswith("~"):
				hastesting = True
			elif not gp.startswith("-"):
				hasstable = True
		if not match and \
			((hastesting and "~*" in pgroups) or \
			(hasstable and "*" in pgroups) or "**" in pgroups):
			match=1
		if match:
			missing = []
		else:
			if not mygroups:
				# If KEYWORDS is empty then we still have to return something
				# in order to distiguish from the case of "none missing".
				mygroups.append("**")
			missing = mygroups
		return missing

	def _getMissingLicenses(self, cpv, metadata):
		"""
		Take a LICENSE string and return a list any licenses that the user may
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
		accept_license = self._accept_license
		cpdict = self._plicensedict.get(cpv_getkey(cpv), None)
		if cpdict:
			accept_license = list(self._accept_license)
			cpv_slot = "%s:%s" % (cpv, metadata["SLOT"])
			for atom in match_to_list(cpv_slot, list(cpdict)):
				accept_license.extend(cpdict[atom])

		licenses = set(flatten(use_reduce(paren_reduce(
			metadata["LICENSE"]), matchall=1)))
		licenses.discard('||')

		acceptable_licenses = set()
		for x in accept_license:
			if x == '*':
				acceptable_licenses.update(licenses)
			elif x == '-*':
				acceptable_licenses.clear()
			elif x[:1] == '-':
				acceptable_licenses.discard(x[1:])
			else:
				acceptable_licenses.add(x)

		license_str = metadata["LICENSE"]
		if "?" in license_str:
			use = metadata["USE"].split()
		else:
			use = []

		license_struct = use_reduce(
			paren_reduce(license_str), uselist=use)
		license_struct = dep_opconvert(license_struct)
		return self._getMaskedLicenses(license_struct, acceptable_licenses)

	def _getMaskedLicenses(self, license_struct, acceptable_licenses):
		if not license_struct:
			return []
		if license_struct[0] == "||":
			ret = []
			for element in license_struct[1:]:
				if isinstance(element, list):
					if element:
						ret.append(self._getMaskedLicenses(
							element, acceptable_licenses))
						if not ret[-1]:
							return []
				else:
					if element in acceptable_licenses:
						return []
					ret.append(element)
			# Return all masked licenses, since we don't know which combination
			# (if any) the user will decide to unmask.
			return flatten(ret)

		ret = []
		for element in license_struct:
			if isinstance(element, list):
				if element:
					ret.extend(self._getMaskedLicenses(element,
						acceptable_licenses))
			else:
				if element not in acceptable_licenses:
					ret.append(element)
		return ret

	def _getMissingProperties(self, cpv, metadata):
		"""
		Take a PROPERTIES string and return a list of any properties the user may
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
		cpdict = self._ppropertiesdict.get(cpv_getkey(cpv), None)
		if cpdict:
			accept_properties = list(self._accept_properties)
			cpv_slot = "%s:%s" % (cpv, metadata["SLOT"])
			for atom in match_to_list(cpv_slot, list(cpdict)):
				accept_properties.extend(cpdict[atom])

		properties = set(flatten(use_reduce(paren_reduce(
			metadata["PROPERTIES"]), matchall=1)))
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

		properties_str = metadata["PROPERTIES"]
		if "?" in properties_str:
			use = metadata["USE"].split()
		else:
			use = []

		properties_struct = use_reduce(
			paren_reduce(properties_str), uselist=use)
		properties_struct = dep_opconvert(properties_struct)
		return self._getMaskedProperties(properties_struct, acceptable_properties)

	def _getMaskedProperties(self, properties_struct, acceptable_properties):
		if not properties_struct:
			return []
		if properties_struct[0] == "||":
			ret = []
			for element in properties_struct[1:]:
				if isinstance(element, list):
					if element:
						ret.append(self._getMaskedProperties(
							element, acceptable_properties))
						if not ret[-1]:
							return []
				else:
					if element in acceptable_properties:
						return[]
					ret.append(element)
			# Return all masked properties, since we don't know which combination
			# (if any) the user will decide to unmask
			return flatten(ret)

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

	def setinst(self,mycpv,mydbapi):
		"""This updates the preferences for old-style virtuals,
		affecting the behavior of dep_expand() and dep_check()
		calls. It can change dbapi.match() behavior since that
		calls dep_expand(). However, dbapi instances have
		internal match caches that are not invalidated when
		preferences are updated here. This can potentially
		lead to some inconsistency (relevant to bug #1343)."""
		self.modifying()
		if len(self.virtuals) == 0:
			self.getvirtuals()
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
		virts = flatten(use_reduce(paren_reduce(provides), uselist=myuse.split()))

		modified = False
		cp = Atom(cpv_getkey(mycpv))
		for virt in virts:
			try:
				virt = Atom(virt).cp
			except InvalidAtom:
				continue
			providers = self.virtuals.get(virt)
			if providers and cp in providers:
				continue
			providers = self._depgraphVirtuals.get(virt)
			if providers is None:
				providers = []
				self._depgraphVirtuals[virt] = providers
			if cp not in providers:
				providers.append(cp)
				modified = True

		if modified:
			self.virtuals = self.__getvirtuals_compile()

	def reload(self):
		"""Reload things like /etc/profile.env that can change during runtime."""
		env_d_filename = os.path.join(self["ROOT"], "etc", "profile.env")
		self.configdict["env.d"].clear()
		env_d = getconfig(env_d_filename, expand=False)
		if env_d:
			# env_d will be None if profile.env doesn't exist.
			self.configdict["env.d"].update(env_d)

	def _prune_incremental(self, split):
		"""
		Prune off any parts of an incremental variable that are
		made irrelevant by the latest occuring * or -*. This
		could be more aggressive but that might be confusing
		and the point is just to reduce noise a bit.
		"""
		for i, x in enumerate(reversed(split)):
			if x == '*':
				split = split[-i-1:]
				break
			elif x == '-*':
				if i == 0:
					split = []
				else:
					split = split[-i:]
				break
		return split

	def regenerate(self,useonly=0,use_cache=1):
		"""
		Regenerate settings
		This involves regenerating valid USE flags, re-expanding USE_EXPAND flags
		re-stacking USE flags (-flag and -*), as well as any other INCREMENTAL
		variables.  This also updates the env.d configdict; useful in case an ebuild
		changes the environment.

		If FEATURES has already stacked, it is not stacked twice.

		@param useonly: Only regenerate USE flags (not any other incrementals)
		@type useonly: Boolean
		@param use_cache: Enable Caching (only for autouse)
		@type use_cache: Boolean
		@rtype: None
		"""

		self.modifying()
		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals = self.incrementals
		myincrementals = set(myincrementals)
		# If self.features exists, it has already been stacked and may have
		# been mutated, so don't stack it again or else any mutations will be
		# reverted.
		if "FEATURES" in myincrementals and hasattr(self, "features"):
			myincrementals.remove("FEATURES")

		if "USE" in myincrementals:
			# Process USE last because it depends on USE_EXPAND which is also
			# an incremental!
			myincrementals.remove("USE")

		mydbs = self.configlist[:-1]
		mydbs.append(self.backupenv)

		# ACCEPT_LICENSE is a lazily evaluated incremental, so that * can be
		# used to match all licenses without every having to explicitly expand
		# it to all licenses.
		if self.local_config:
			mysplit = []
			for curdb in mydbs:
				mysplit.extend(curdb.get('ACCEPT_LICENSE', '').split())
			mysplit = self._prune_incremental(mysplit)
			accept_license_str = ' '.join(mysplit)
			self.configlist[-1]['ACCEPT_LICENSE'] = accept_license_str
			if accept_license_str != self._accept_license_str:
				self._accept_license_str = accept_license_str
				self._accept_license = tuple(self.expandLicenseTokens(mysplit))
		else:
			# repoman will accept any license
			self._accept_license = ('*',)

		# ACCEPT_PROPERTIES works like ACCEPT_LICENSE, without groups
		if self.local_config:
			mysplit = []
			for curdb in mydbs:
				mysplit.extend(curdb.get('ACCEPT_PROPERTIES', '').split())
			mysplit = self._prune_incremental(mysplit)
			self.configlist[-1]['ACCEPT_PROPERTIES'] = ' '.join(mysplit)
			if tuple(mysplit) != self._accept_properties:
				self._accept_properties = tuple(mysplit)
		else:
			# repoman will accept any property
			self._accept_properties = ('*',)

		for mykey in myincrementals:

			myflags=[]
			for curdb in mydbs:
				if mykey not in curdb:
					continue
				#variables are already expanded
				mysplit = curdb[mykey].split()

				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags = []
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(colorize("BAD",
							_("USE flags should not start with a '+': %s") % x) \
							+ "\n", noiselevel=-1)
						x=x[1:]
						if not x:
							continue

					if (x[0]=="-"):
						if (x[1:] in myflags):
							# Unset/Remove it.
							del myflags[myflags.index(x[1:])]
						continue

					# We got here, so add it now.
					if x not in myflags:
						myflags.append(x)

			myflags.sort()
			#store setting in last element of configlist, the original environment:
			if myflags or mykey in self:
				self.configlist[-1][mykey] = " ".join(myflags)
			del myflags

		# Do the USE calculation last because it depends on USE_EXPAND.
		if "auto" in self["USE_ORDER"].split(":"):
			self.configdict["auto"]["USE"] = autouse(
				vartree(root=self["ROOT"], categories=self.categories,
					settings=self),
				use_cache=use_cache, mysettings=self)
		else:
			self.configdict["auto"]["USE"] = ""

		use_expand = self.get("USE_EXPAND", "").split()
		use_expand_dict = self._use_expand_dict
		use_expand_dict.clear()
		for k in use_expand:
			v = self.get(k)
			if v is not None:
				use_expand_dict[k] = v

		if not self.uvlist:
			for x in self["USE_ORDER"].split(":"):
				if x in self.configdict:
					self.uvlist.append(self.configdict[x])
			self.uvlist.reverse()

		# For optimal performance, use slice
		# comparison instead of startswith().
		myflags = set()
		for curdb in self.uvlist:
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
					myflags.discard(x[1:])
					continue

				myflags.add(x)

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
			self.features.clear()
		else:
			self.features = set()
		self.features.update(self.configlist[-1].get('FEATURES', '').split())
		self['FEATURES'] = ' '.join(sorted(self.features))

		myflags.update(self.useforce)
		arch = self.configdict["defaults"].get("ARCH")
		if arch:
			myflags.add(arch)

		myflags.difference_update(self.usemask)
		self.configlist[-1]["USE"]= " ".join(sorted(myflags))

		self.already_in_regenerate = 0

	def get_virts_p(self, myroot=None):

		if myroot is not None:
			warnings.warn("The 'myroot' parameter for " + \
				"portage.config.get_virts_p() is deprecated",
				DeprecationWarning, stacklevel=2)

		if self.virts_p:
			return self.virts_p
		virts = self.getvirtuals()
		if virts:
			for x in virts:
				vkeysplit = x.split("/")
				if vkeysplit[1] not in self.virts_p:
					self.virts_p[vkeysplit[1]] = virts[x]
		return self.virts_p

	def getvirtuals(self, myroot=None):
		"""myroot is now ignored because, due to caching, it has always been
		broken for all but the first call."""

		if myroot is not None:
			warnings.warn("The 'myroot' parameter for " + \
				"portage.config.getvirtuals() is deprecated",
				DeprecationWarning, stacklevel=2)

		myroot = self["ROOT"]
		if self.virtuals:
			return self.virtuals

		virtuals_list = []
		for x in self.profiles:
			virtuals_file = os.path.join(x, "virtuals")
			virtuals_dict = grabdict(virtuals_file)
			atoms_dict = {}
			for k, v in virtuals_dict.items():
				try:
					virt_atom = Atom(k)
				except InvalidAtom:
					virt_atom = None
				else:
					if virt_atom.blocker or \
						str(virt_atom) != str(virt_atom.cp):
						virt_atom = None
				if virt_atom is None:
					writemsg(_("--- Invalid virtuals atom in %s: %s\n") % \
						(virtuals_file, k), noiselevel=-1)
					continue
				providers = []
				for atom in v:
					atom_orig = atom
					if atom[:1] == '-':
						# allow incrementals
						atom = atom[1:]
					try:
						atom = Atom(atom)
					except InvalidAtom:
						atom = None
					else:
						if atom.blocker:
							atom = None
					if atom is None:
						writemsg(_("--- Invalid atom in %s: %s\n") % \
							(virtuals_file, atom_orig), noiselevel=-1)
					else:
						if atom_orig == str(atom):
							# normal atom, so return as Atom instance
							providers.append(atom)
						else:
							# atom has special prefix, so return as string
							providers.append(atom_orig)
				if providers:
					atoms_dict[virt_atom] = providers
			if atoms_dict:
				virtuals_list.append(atoms_dict)

		self.dirVirtuals = stack_dictlist(virtuals_list, incremental=True)
		del virtuals_list

		for virt in self.dirVirtuals:
			# Preference for virtuals decreases from left to right.
			self.dirVirtuals[virt].reverse()

		# Repoman does not use user or tree virtuals.
		if self.local_config and not self.treeVirtuals:
			temp_vartree = vartree(myroot, None,
				categories=self.categories, settings=self)
			self._populate_treeVirtuals(temp_vartree)

		self.virtuals = self.__getvirtuals_compile()
		return self.virtuals

	def _populate_treeVirtuals(self, vartree):
		"""Reduce the provides into a list by CP."""
		for provide, cpv_list in vartree.get_all_provides().items():
			try:
				provide = Atom(provide)
			except InvalidAtom:
				continue
			self.treeVirtuals[provide.cp] = \
				[Atom(cpv_getkey(cpv)) for cpv in cpv_list]

	def __getvirtuals_compile(self):
		"""Stack installed and profile virtuals.  Preference for virtuals
		decreases from left to right.
		Order of preference:
		1. installed and in profile
		2. installed only
		3. profile only
		"""

		# Virtuals by profile+tree preferences.
		ptVirtuals   = {}

		for virt, installed_list in self.treeVirtuals.items():
			profile_list = self.dirVirtuals.get(virt, None)
			if not profile_list:
				continue
			for cp in installed_list:
				if cp in profile_list:
					ptVirtuals.setdefault(virt, [])
					ptVirtuals[virt].append(cp)

		virtuals = stack_dictlist([ptVirtuals, self.treeVirtuals,
			self.dirVirtuals, self._depgraphVirtuals])
		return virtuals

	def __delitem__(self,mykey):
		self.modifying()
		for x in self.lookuplist:
			if x != None:
				if mykey in x:
					del x[mykey]

	def __getitem__(self,mykey):
		for d in self.lookuplist:
			if mykey in d:
				return d[mykey]
		return '' # for backward compat, don't raise KeyError

	def get(self, k, x=None):
		for d in self.lookuplist:
			if k in d:
				return d[k]
		return x

	def pop(self, key, *args):
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

	def has_key(self,mykey):
		warnings.warn("portage.config.has_key() is deprecated, "
			"use the in operator instead",
			DeprecationWarning, stacklevel=2)
		return mykey in self

	def __contains__(self, mykey):
		"""Called to implement membership test operators (in and not in)."""
		for d in self.lookuplist:
			if mykey in d:
				return True
		return False

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
		for d in self.lookuplist:
			keys.update(d)
		return iter(keys)

	def iterkeys(self):
		return iter(self)

	def iteritems(self):
		for k in self:
			yield (k, self[k])

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
		phase = self.get('EBUILD_PHASE')
		filter_calling_env = False
		if phase not in ('clean', 'cleanrm', 'depend'):
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

		# Filtered by IUSE and implicit IUSE.
		mydict["USE"] = self.get("PORTAGE_USE", "")

		# Don't export AA to the ebuild environment in EAPIs that forbid it
		if eapi not in ("0", "1", "2", "3", "3_pre2"):
			mydict.pop("AA", None)

		# Prefix variables are supported starting with EAPI 3.
		if phase == 'depend' or eapi in (None, "0", "1", "2"):
			mydict.pop("ED", None)
			mydict.pop("EPREFIX", None)
			mydict.pop("EROOT", None)

		if phase == 'depend':
			mydict.pop('FILESDIR', None)

		if phase not in ("pretend", "setup", "preinst", "postinst") or \
			eapi in ("0", "1", "2", "3"):
			mydict.pop("REPLACING_VERSIONS", None)

		if phase not in ("prerm", "postrm") or \
			eapi in ("0", "1", "2", "3"):
			mydict.pop("REPLACED_BY_VERSION", None)

		return mydict

	def thirdpartymirrors(self):
		if getattr(self, "_thirdpartymirrors", None) is None:
			profileroots = [os.path.join(self["PORTDIR"], "profiles")]
			for x in self["PORTDIR_OVERLAY"].split():
				profileroots.insert(0, os.path.join(x, "profiles"))
			thirdparty_lists = [grabdict(os.path.join(x, "thirdpartymirrors")) for x in profileroots]
			self._thirdpartymirrors = stack_dictlist(thirdparty_lists, incremental=True)
		return self._thirdpartymirrors

	def archlist(self):
		return flatten([[myarch, "~" + myarch] \
			for myarch in self["PORTAGE_ARCHLIST"].split()])

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
