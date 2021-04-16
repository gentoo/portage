# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import io
import logging
import warnings
import re
import typing

import portage
from portage import eclass_cache, os
from portage.checksum import get_valid_checksum_keys
from portage.const import (PORTAGE_BASE_PATH, REPO_NAME_LOC, USER_CONFIG_PATH)
from portage.eapi import (
	eapi_allows_directories_on_profile_level_and_repository_level,
	eapi_has_repo_deps,
)
from portage.env.loaders import KeyValuePairFileLoader
from portage.util import (normalize_path, read_corresponding_eapi_file, shlex_split,
	stack_lists, writemsg, writemsg_level, _recursive_file_list)
from portage.util.configparser import (SafeConfigParser, ConfigParserError,
	read_configs)
from portage.util._path import isdir_raise_eaccess
from portage.util.path import first_existing
from portage.localization import _
from portage import _unicode_decode
from portage import _unicode_encode
from portage import _encodings
from portage import manifest
import portage.sync

_profile_node = collections.namedtuple(
	"_profile_node",
	(
		"location",
		"portage1_directories",
		"user_config",
		"profile_formats",
		"eapi",
		"allow_build_id",
		"show_deprecated_warning",
	),
)

# Characters prohibited by repoman's file.name check.
_invalid_path_char_re = re.compile(r'[^a-zA-Z0-9._\-+/]')

_valid_profile_formats = frozenset(
	['pms', 'portage-1', 'portage-2', 'profile-bashrcs', 'profile-set',
	'profile-default-eapi', 'build-id', 'profile-repo-deps'])

_portage1_profiles_allow_directories = frozenset(
	["portage-1-compat", "portage-1", 'portage-2'])

_repo_name_sub_re = re.compile(r'[^\w-]')

def _gen_valid_repo(name):
	"""
	Substitute hyphen in place of characters that don't conform to PMS 3.1.5,
	and strip hyphen from left side if necessary. This returns None if the
	given name contains no valid characters.
	"""
	name = _repo_name_sub_re.sub(' ', name.strip())
	name = '-'.join(name.split())
	name = name.lstrip('-')
	if not name:
		name = None
	return name

def _find_invalid_path_char(path, pos=0, endpos=None):
	"""
	Returns the position of the first invalid character found in basename,
	or -1 if no invalid characters are found.
	"""
	if endpos is None:
		endpos = len(path)

	m = _invalid_path_char_re.search(path, pos=pos, endpos=endpos)
	if m is not None:
		return m.start()

	return -1

class RepoConfig:
	"""Stores config of one repository"""

	__slots__ = (
		'aliases',
		'allow_missing_manifest',
		'allow_provide_virtual',
		'auto_sync',
		'cache_formats',
		'clone_depth',
		'create_manifest',
		'disable_manifest',
		'eapi',
		'eclass_db',
		'eclass_locations',
		'eclass_overrides',
		'find_invalid_path_char',
		'force',
		'format',
		'local_config',
		'location',
		'main_repo',
		'manifest_hashes',
		'manifest_required_hashes',
		'masters',
		'missing_repo_name',
		'module_specific_options',
		'name',
		'portage1_profiles',
		'portage1_profiles_compat',
		'priority',
		'profile_formats',
		'properties_allowed',
		'restrict_allowed',
		'sign_commit',
		'sign_manifest',
		'strict_misc_digests',
		'sync_allow_hardlinks',
		'sync_depth',
		'sync_hooks_only_on_change',
		'sync_openpgp_keyserver',
		'sync_openpgp_key_path',
		'sync_openpgp_key_refresh',
		'sync_openpgp_key_refresh_retry_count',
		'sync_openpgp_key_refresh_retry_delay_exp_base',
		'sync_openpgp_key_refresh_retry_delay_max',
		'sync_openpgp_key_refresh_retry_delay_mult',
		'sync_openpgp_key_refresh_retry_overall_timeout',
		'sync_rcu',
		'sync_rcu_spare_snapshots',
		'sync_rcu_store_dir',
		'sync_rcu_ttl_days',
		'sync_type',
		'sync_umask',
		'sync_uri',
		'sync_user',
		'thin_manifest',
		'update_changelog',
		'user_location',
		'_eapis_banned',
		'_eapis_deprecated',
		'_masters_orig',
		)

	def __init__(self, name, repo_opts, local_config=True):
		"""Build a RepoConfig with options in repo_opts
		   Try to read repo_name in repository location, but if
		   it is not found use variable name as repository name"""

		force = repo_opts.get('force')
		if force is not None:
			force = tuple(force.split())
		self.force = force
		if force is None:
			force = ()

		self.local_config = local_config

		if local_config or 'aliases' in force:
			aliases = repo_opts.get('aliases')
			if aliases is not None:
				aliases = tuple(aliases.split())
		else:
			aliases = None

		self.aliases = aliases

		if local_config or 'eclass-overrides' in force:
			eclass_overrides = repo_opts.get('eclass-overrides')
			if eclass_overrides is not None:
				eclass_overrides = tuple(eclass_overrides.split())
		else:
			eclass_overrides = None

		self.eclass_overrides = eclass_overrides
		# Eclass databases and locations are computed later.
		self.eclass_db = None
		self.eclass_locations = None

		if local_config or 'masters' in force:
			# Masters from repos.conf override layout.conf.
			masters = repo_opts.get('masters')
			if masters is not None:
				masters = tuple(masters.split())
		else:
			masters = None

		self.masters = masters

		#The main-repo key makes only sense for the 'DEFAULT' section.
		self.main_repo = repo_opts.get('main-repo')

		priority = repo_opts.get('priority')
		if priority is not None:
			try:
				priority = int(priority)
			except ValueError:
				priority = None
		self.priority = priority

		sync_type = repo_opts.get('sync-type')
		if sync_type is not None:
			sync_type = sync_type.strip()
		self.sync_type = sync_type or None

		sync_umask = repo_opts.get('sync-umask')
		if sync_umask is not None:
			sync_umask = sync_umask.strip()
		self.sync_umask = sync_umask or None

		sync_uri = repo_opts.get('sync-uri')
		if sync_uri is not None:
			sync_uri = sync_uri.strip()
		self.sync_uri = sync_uri or None

		sync_user = repo_opts.get('sync-user')
		if sync_user is not None:
			sync_user = sync_user.strip()
		self.sync_user = sync_user or None

		auto_sync = repo_opts.get('auto-sync', 'yes')
		if auto_sync is not None:
			auto_sync = auto_sync.strip().lower()
		self.auto_sync = auto_sync

		self.clone_depth = repo_opts.get('clone-depth')
		self.sync_depth = repo_opts.get('sync-depth')

		self.sync_hooks_only_on_change = repo_opts.get(
			'sync-hooks-only-on-change', 'false').lower() in ('true', 'yes')

		self.strict_misc_digests = repo_opts.get(
			'strict-misc-digests', 'true').lower() in ('true', 'yes')

		self.sync_allow_hardlinks = repo_opts.get(
			'sync-allow-hardlinks', 'true').lower() in ('true', 'yes')

		self.sync_openpgp_keyserver = repo_opts.get(
			'sync-openpgp-keyserver', '').strip().lower() or None

		self.sync_openpgp_key_path = repo_opts.get(
			'sync-openpgp-key-path', None)

		self.sync_openpgp_key_refresh = repo_opts.get(
			'sync-openpgp-key-refresh', 'true').lower() in ('true', 'yes')

		for k in ('sync_openpgp_key_refresh_retry_count',
			'sync_openpgp_key_refresh_retry_delay_exp_base',
			'sync_openpgp_key_refresh_retry_delay_max',
			'sync_openpgp_key_refresh_retry_delay_mult',
			'sync_openpgp_key_refresh_retry_overall_timeout'):
			setattr(self, k, repo_opts.get(k.replace('_', '-'), None))

		self.sync_rcu = repo_opts.get(
			'sync-rcu', 'false').lower() in ('true', 'yes')

		self.sync_rcu_store_dir = repo_opts.get('sync-rcu-store-dir')

		for k in ('sync-rcu-spare-snapshots', 'sync-rcu-ttl-days'):
			v = repo_opts.get(k, '').strip() or None
			if v:
				try:
					v = int(v)
				except (OverflowError, ValueError):
					writemsg(_("!!! Invalid %s setting for repo"
						" %s: %s\n") % (k, name, v), noiselevel=-1)
					v = None
			setattr(self, k.replace('-', '_'), v)

		self.module_specific_options = {}

		# Not implemented.
		repo_format = repo_opts.get('format')
		if repo_format is not None:
			repo_format = repo_format.strip()
		self.format = repo_format

		self.user_location = None
		location = repo_opts.get('location')
		if location is not None and location.strip():
			if os.path.isdir(location) or portage._sync_mode:
				# The user_location is required for sync-rcu support,
				# since it manages a symlink which resides at that
				# location (and realpath is irreversible).
				self.user_location = location
				location = os.path.realpath(location)
		else:
			location = None
		self.location = location

		missing = True
		self.name = name
		if self.location is not None:
			self.name, missing = self._read_valid_repo_name(self.location)
			if missing:
				# The name from repos.conf has to be used here for
				# things like emerge-webrsync to work when the repo
				# is empty (bug #484950).
				if name is not None:
					self.name = name
				if portage._sync_mode:
					missing = False

		elif name == "DEFAULT":
			missing = False

		self.eapi = None
		self.missing_repo_name = missing
		# sign_commit is disabled by default, since it requires Git >=1.7.9,
		# and key_id configured by `git config user.signingkey key_id`
		self.sign_commit = False
		self.sign_manifest = True
		self.thin_manifest = False
		self.allow_missing_manifest = False
		self.allow_provide_virtual = False
		self.create_manifest = True
		self.disable_manifest = False
		self.manifest_hashes = None
		self.manifest_required_hashes = None
		self.update_changelog = False
		self.cache_formats = None
		self.portage1_profiles = True
		self.portage1_profiles_compat = False
		self.find_invalid_path_char = _find_invalid_path_char
		self._masters_orig = None

		# Parse layout.conf.
		if self.location:
			layout_data = parse_layout_conf(self.location, self.name)[0]
			self._masters_orig = layout_data['masters']

			# layout.conf masters may be overridden here if we have a masters
			# setting from the user's repos.conf
			if self.masters is None:
				self.masters = layout_data['masters']

			if (local_config or 'aliases' in force) and layout_data['aliases']:
				aliases = self.aliases
				if aliases is None:
					aliases = ()
				# repos.conf aliases come after layout.conf aliases, giving
				# them the ability to do incremental overrides
				self.aliases = layout_data['aliases'] + tuple(aliases)

			if layout_data['repo-name']:
				# allow layout.conf to override repository name
				# useful when having two copies of the same repo enabled
				# to avoid modifying profiles/repo_name in one of them
				self.name = layout_data['repo-name']
				self.missing_repo_name = False

			for value in ('allow-missing-manifest',
				'cache-formats',
				'create-manifest', 'disable-manifest', 'manifest-hashes',
				'manifest-required-hashes', 'profile-formats', 'properties-allowed', 'restrict-allowed',
				'sign-commit', 'sign-manifest', 'thin-manifest', 'update-changelog'):
				setattr(self, value.lower().replace("-", "_"), layout_data[value])

			# If profile-formats specifies a default EAPI, then set
			# self.eapi to that, otherwise set it to "0" as specified
			# by PMS.
			self.eapi = layout_data.get(
				'profile_eapi_when_unspecified', '0')

			eapi = read_corresponding_eapi_file(
				os.path.join(self.location, REPO_NAME_LOC),
				default=self.eapi)

			self.portage1_profiles = eapi_allows_directories_on_profile_level_and_repository_level(eapi) or \
				any(x in _portage1_profiles_allow_directories for x in layout_data['profile-formats'])
			self.portage1_profiles_compat = not eapi_allows_directories_on_profile_level_and_repository_level(eapi) and \
				layout_data['profile-formats'] == ('portage-1-compat',)

			self._eapis_banned = frozenset(layout_data['eapis-banned'])
			self._eapis_deprecated = frozenset(layout_data['eapis-deprecated'])

	def set_module_specific_opt(self, opt, val):
		self.module_specific_options[opt] = val

	def eapi_is_banned(self, eapi):
		return eapi in self._eapis_banned

	def eapi_is_deprecated(self, eapi):
		return eapi in self._eapis_deprecated

	def iter_pregenerated_caches(self, auxdbkeys, readonly=True, force=False):
		"""
		Reads layout.conf cache-formats from left to right and yields cache
		instances for each supported type that's found. If no cache-formats
		are specified in layout.conf, 'pms' type is assumed if the
		metadata/cache directory exists or force is True.
		"""
		formats = self.cache_formats
		if not formats:
			if not force:
				return
			# The default egencache format was 'pms' prior to portage-2.1.11.32
			# (portage versions prior to portage-2.1.11.14 will NOT
			# recognize md5-dict format unless it is explicitly listed in
			# layout.conf).
			formats = ('md5-dict',)

		for fmt in formats:
			name = None
			if fmt == 'pms':
				from portage.cache.metadata import database
				name = 'metadata/cache'
			elif fmt == 'md5-dict':
				from portage.cache.flat_hash import md5_database as database
				name = 'metadata/md5-cache'

			if name is not None:
				yield database(self.location, name,
					auxdbkeys, readonly=readonly)

	def get_pregenerated_cache(self, auxdbkeys, readonly=True, force=False):
		"""
		Returns the first cache instance yielded from
		iter_pregenerated_caches(), or None if no cache is available or none
		of the available formats are supported.
		"""
		return next(self.iter_pregenerated_caches(
			auxdbkeys, readonly=readonly, force=force), None)

	def load_manifest(self, *args, **kwds):
		kwds['thin'] = self.thin_manifest
		kwds['allow_missing'] = self.allow_missing_manifest
		kwds['allow_create'] = self.create_manifest
		kwds['hashes'] = self.manifest_hashes
		kwds['required_hashes'] = self.manifest_required_hashes
		kwds['strict_misc_digests'] = self.strict_misc_digests
		if self.disable_manifest:
			kwds['from_scratch'] = True
		kwds['find_invalid_path_char'] = self.find_invalid_path_char
		return manifest.Manifest(*args, **kwds)

	def update(self, new_repo):
		"""Update repository with options in another RepoConfig"""

		keys = set(self.__slots__)
		keys.discard("missing_repo_name")
		for k in keys:
			v = getattr(new_repo, k, None)
			if v is not None:
				setattr(self, k, v)

		if new_repo.name is not None:
			self.missing_repo_name = new_repo.missing_repo_name

	@property
	def writable(self):
		"""
		Check if self.location is writable, or permissions are sufficient
		to create it if it does not exist yet.
		@rtype: bool
		@return: True if self.location is writable or can be created,
			False otherwise
		"""
		return os.access(first_existing(self.location), os.W_OK)

	@staticmethod
	def _read_valid_repo_name(repo_path):
		name, missing = RepoConfig._read_repo_name(repo_path)
		# We must ensure that the name conforms to PMS 3.1.5
		# in order to avoid InvalidAtom exceptions when we
		# use it to generate atoms.
		name = _gen_valid_repo(name)
		if not name:
			# name only contains invalid characters
			name = "x-" + os.path.basename(repo_path)
			name = _gen_valid_repo(name)
			# If basename only contains whitespace then the
			# end result is name = 'x-'.
		return name, missing

	@staticmethod
	def _read_repo_name(repo_path):
		"""
		Read repo_name from repo_path.
		Returns repo_name, missing.
		"""
		repo_name_path = os.path.join(repo_path, REPO_NAME_LOC)
		f = None
		try:
			f = io.open(
				_unicode_encode(repo_name_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
			return f.readline().strip(), False
		except EnvironmentError:
			return "x-" + os.path.basename(repo_path), True
		finally:
			if f is not None:
				f.close()

	def info_string(self):
		"""
		Returns a formatted string containing informations about the repository.
		Used by emerge --info.
		"""
		indent = " " * 4
		repo_msg = []
		repo_msg.append(self.name)
		if self.format:
			repo_msg.append(indent + "format: " + self.format)
		if self.location:
			repo_msg.append(indent + "location: " + self.location)
		if not self.strict_misc_digests:
			repo_msg.append(indent + "strict-misc-digests: false")
		if not self.sync_openpgp_key_refresh:
			repo_msg.append(indent + "sync-openpgp-key-refresh: no")
		if self.sync_type:
			repo_msg.append(indent + "sync-type: " + self.sync_type)
		if self.sync_umask:
			repo_msg.append(indent + "sync-umask: " + self.sync_umask)
		if self.sync_uri:
			repo_msg.append(indent + "sync-uri: " + self.sync_uri)
		if self.sync_user:
			repo_msg.append(indent + "sync-user: " + self.sync_user)
		if self.masters:
			repo_msg.append(indent + "masters: " + " ".join(master.name for master in self.masters))
		if self.priority is not None:
			repo_msg.append(indent + "priority: " + str(self.priority))
		if self.aliases:
			repo_msg.append(indent + "aliases: " + " ".join(self.aliases))
		if self.eclass_overrides:
			repo_msg.append(indent + "eclass-overrides: " + \
				" ".join(self.eclass_overrides))
		for o, v in self.module_specific_options.items():
			if v is not None:
				repo_msg.append(indent + o + ": " + v)
		repo_msg.append("")
		return "\n".join(repo_msg)

	def __repr__(self):
		return "<portage.repository.config.RepoConfig(name=%r, location=%r)>" % (self.name, _unicode_decode(self.location))

	def __str__(self):
		d = {}
		for k in self.__slots__:
			d[k] = getattr(self, k, None)
		return "%s" % (d,)


class RepoConfigLoader:
	"""Loads and store config of several repositories, loaded from PORTDIR_OVERLAY or repos.conf"""

	@staticmethod
	def _add_repositories(portdir, portdir_overlay, prepos,
		ignored_map, local_config, default_portdir):
		"""Add overlays in PORTDIR_OVERLAY as repositories"""
		overlays = []
		portdir_orig = None
		if portdir:
			portdir = normalize_path(portdir)
			portdir_orig = portdir
			overlays.append(portdir)
		try:
			port_ov = [normalize_path(i) for i in shlex_split(portdir_overlay)]
		except ValueError as e:
			#File "/usr/lib/python3.2/shlex.py", line 168, in read_token
			#	raise ValueError("No closing quotation")
			writemsg(_("!!! Invalid PORTDIR_OVERLAY:"
				" %s: %s\n") % (e, portdir_overlay), noiselevel=-1)
			port_ov = []
		overlays.extend(port_ov)
		default_repo_opts = {}
		if prepos['DEFAULT'].aliases is not None:
			default_repo_opts['aliases'] = \
				' '.join(prepos['DEFAULT'].aliases)
		if prepos['DEFAULT'].eclass_overrides is not None:
			default_repo_opts['eclass-overrides'] = \
				' '.join(prepos['DEFAULT'].eclass_overrides)
		if prepos['DEFAULT'].masters is not None:
			default_repo_opts['masters'] = \
				' '.join(prepos['DEFAULT'].masters)

		if overlays:
			# We need a copy of the original repos.conf data, since we're
			# going to modify the prepos dict and some of the RepoConfig
			# objects that we put in prepos may have to be discarded if
			# they get overridden by a repository with the same name but
			# a different location. This is common with repoman, for example,
			# when temporarily overriding an rsync repo with another copy
			# of the same repo from CVS.
			repos_conf = prepos.copy()
			#overlay priority is negative because we want them to be looked before any other repo
			base_priority = 0
			for ov in overlays:
				# Ignore missing directory for 'gentoo' so that
				# first sync with emerge-webrsync is possible.
				if isdir_raise_eaccess(ov) or \
					(base_priority == 0 and ov is portdir):
					repo_opts = default_repo_opts.copy()
					repo_opts['location'] = ov
					name = prepos['DEFAULT'].main_repo if ov is portdir else None
					repo = RepoConfig(name, repo_opts, local_config=local_config)
					# repos_conf_opts contains options from repos.conf
					repos_conf_opts = repos_conf.get(repo.name)
					if repos_conf_opts is not None:
						# Selectively copy only the attributes which
						# repos.conf is allowed to override.
						for k in (
							'aliases',
							'auto_sync',
							'clone_depth',
							'eclass_overrides',
							'force',
							'masters',
							'module_specific_options',
							'priority',
							'strict_misc_digests',
							'sync_allow_hardlinks',
							'sync_depth',
							'sync_hooks_only_on_change',
							'sync_openpgp_keyserver',
							'sync_openpgp_key_path',
							'sync_openpgp_key_refresh',
							'sync_openpgp_key_refresh_retry_count',
							'sync_openpgp_key_refresh_retry_delay_exp_base',
							'sync_openpgp_key_refresh_retry_delay_max',
							'sync_openpgp_key_refresh_retry_delay_mult',
							'sync_openpgp_key_refresh_retry_overall_timeout',
							'sync_rcu',
							'sync_rcu_spare_snapshots',
							'sync_rcu_store_dir',
							'sync_rcu_ttl_days',
							'sync_type',
							'sync_umask',
							'sync_uri',
							'sync_user',
							):
							v = getattr(repos_conf_opts, k, None)
							if v is not None:
								setattr(repo, k, v)

					if repo.name in prepos:
						# Silently ignore when PORTDIR overrides the location
						# setting from the default repos.conf (bug #478544).
						old_location = prepos[repo.name].location
						if old_location is not None and \
							old_location != repo.location and \
							not (base_priority == 0 and
							old_location == default_portdir):
							ignored_map.setdefault(repo.name, []).append(old_location)
							if old_location == portdir:
								portdir = repo.location

					if repo.priority is None:
						if base_priority == 0 and ov == portdir_orig:
							# If it's the original PORTDIR setting and it's not
							# in PORTDIR_OVERLAY, then it will be assigned a
							# special priority setting later.
							pass
						else:
							repo.priority = base_priority
							base_priority += 1

					prepos[repo.name] = repo
				else:

					if not portage._sync_mode:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY (not a dir): '%s'\n") % ov, noiselevel=-1)

		return portdir

	@staticmethod
	def _parse(paths, prepos, local_config, default_opts):
		"""Parse files in paths to load config"""
		parser = SafeConfigParser(defaults=default_opts)

		recursive_paths = []
		for p in paths:
			if isinstance(p, str):
				recursive_paths.extend(_recursive_file_list(p))
			else:
				recursive_paths.append(p)

		read_configs(parser, recursive_paths)

		prepos['DEFAULT'] = RepoConfig("DEFAULT",
			parser.defaults(), local_config=local_config)

		for sname in parser.sections():
			optdict = {}
			for oname in parser.options(sname):
				optdict[oname] = parser.get(sname, oname)

			repo = RepoConfig(sname, optdict, local_config=local_config)
			for o in portage.sync.module_specific_options(repo):
				if parser.has_option(sname, o):
					repo.set_module_specific_opt(o, parser.get(sname, o))

			# Perform repos.conf sync variable validation
			portage.sync.validate_config(repo, logging)

			# For backward compatibility with locations set via PORTDIR and
			# PORTDIR_OVERLAY, delay validation of the location and repo.name
			# until after PORTDIR and PORTDIR_OVERLAY have been processed.
			prepos[sname] = repo

	def __init__(self, paths, settings):
		"""Load config from files in paths"""

		prepos = {}
		location_map = {}
		treemap = {}
		ignored_map = {}
		default_opts = {
			"EPREFIX" : settings["EPREFIX"],
			"EROOT" : settings["EROOT"],
			"PORTAGE_CONFIGROOT" : settings["PORTAGE_CONFIGROOT"],
			"ROOT" : settings["ROOT"],
		}

		if "PORTAGE_REPOSITORIES" in settings:
			portdir = ""
			portdir_overlay = ""
			# deprecated portdir_sync
			portdir_sync = ""
		else:
			portdir = settings.get("PORTDIR", "")
			portdir_overlay = settings.get("PORTDIR_OVERLAY", "")
			# deprecated portdir_sync
			portdir_sync = settings.get("SYNC", "")

		default_opts['sync-rsync-extra-opts'] = \
			settings.get("PORTAGE_RSYNC_EXTRA_OPTS", "")

		try:
			self._parse(paths, prepos, settings.local_config, default_opts)
		except ConfigParserError as e:
			writemsg(
				_("!!! Error while reading repo config file: %s\n") % e,
				noiselevel=-1)
			# The configparser state is unreliable (prone to quirky
			# exceptions) after it has thrown an error, so use empty
			# config and try to fall back to PORTDIR{,_OVERLAY}.
			prepos.clear()
			prepos['DEFAULT'] = RepoConfig('DEFAULT',
				{}, local_config=settings.local_config)
			location_map.clear()
			treemap.clear()

		repo_locations = frozenset(repo.location for repo in prepos.values())
		for repo_location in ('var/db/repos/gentoo', 'usr/portage'):
			default_portdir = os.path.join(os.sep, settings['EPREFIX'].lstrip(os.sep), repo_location)
			if default_portdir in repo_locations:
				break

		# If PORTDIR_OVERLAY contains a repo with the same repo_name as
		# PORTDIR, then PORTDIR is overridden.
		portdir = self._add_repositories(portdir, portdir_overlay, prepos,
			ignored_map, settings.local_config,
			default_portdir)
		if portdir and portdir.strip():
			portdir = os.path.realpath(portdir)

		ignored_repos = tuple((repo_name, tuple(paths)) \
			for repo_name, paths in ignored_map.items())

		self.missing_repo_names = frozenset(repo.location
			for repo in prepos.values()
			if repo.location is not None and repo.missing_repo_name)

		# Do this before expanding aliases, so that location_map and
		# treemap consistently map unaliased names whenever available.
		for repo_name, repo in list(prepos.items()):
			if repo.location is None:
				if repo_name != 'DEFAULT':
					# Skip this warning for repoman (bug #474578).
					if settings.local_config and paths:
						writemsg_level("!!! %s\n" % _("Section '%s' in repos.conf is missing location attribute") %
							repo.name, level=logging.ERROR, noiselevel=-1)
					del prepos[repo_name]
					continue
			else:
				if not portage._sync_mode:
					if not isdir_raise_eaccess(repo.location):
						writemsg_level("!!! %s\n" % _("Section '%s' in repos.conf has location attribute set "
							"to nonexistent directory: '%s'") %
							(repo_name, repo.location), level=logging.ERROR, noiselevel=-1)

						# Ignore missing directory for 'gentoo' so that
						# first sync with emerge-webrsync is possible.
						if repo.name != 'gentoo':
							del prepos[repo_name]
							continue

					# After removing support for PORTDIR_OVERLAY, the following check can be:
					# if repo.missing_repo_name:
					if repo.missing_repo_name and repo.name != repo_name:
						writemsg_level("!!! %s\n" % _("Section '%s' in repos.conf refers to repository "
							"without repository name set in '%s'") %
							(repo_name, os.path.join(repo.location, REPO_NAME_LOC)), level=logging.ERROR, noiselevel=-1)
						del prepos[repo_name]
						continue

					if repo.name != repo_name:
						writemsg_level("!!! %s\n" % _("Section '%s' in repos.conf has name different "
							"from repository name '%s' set inside repository") %
							(repo_name, repo.name), level=logging.ERROR, noiselevel=-1)
						del prepos[repo_name]
						continue

				location_map[repo.location] = repo_name
				treemap[repo_name] = repo.location

		# Add alias mappings, but never replace unaliased mappings.
		for repo_name, repo in list(prepos.items()):
			names = set()
			names.add(repo_name)
			if repo.aliases:
				aliases = stack_lists([repo.aliases], incremental=True)
				names.update(aliases)

			for name in names:
				if name in prepos and prepos[name].location is not None:
					if name == repo_name:
						# unaliased names already handled earlier
						continue
					writemsg_level(_("!!! Repository name or alias '%s', " + \
						"defined for repository '%s', overrides " + \
						"existing alias or repository.\n") % (name, repo_name), level=logging.WARNING, noiselevel=-1)
					# Never replace an unaliased mapping with
					# an aliased mapping.
					continue
				prepos[name] = repo
				if repo.location is not None:
					if repo.location not in location_map:
						# Never replace an unaliased mapping with
						# an aliased mapping.
						location_map[repo.location] = name
					treemap[name] = repo.location

		main_repo = prepos['DEFAULT'].main_repo
		if main_repo is None or main_repo not in prepos:
			#setting main_repo if it was not set in repos.conf
			main_repo = location_map.get(portdir)
			if main_repo is not None:
				prepos['DEFAULT'].main_repo = main_repo
			else:
				prepos['DEFAULT'].main_repo = None
				if portdir and not portage._sync_mode:
					writemsg(_("!!! main-repo not set in DEFAULT and PORTDIR is empty.\n"), noiselevel=-1)

		if main_repo is not None and prepos[main_repo].priority is None:
			# This happens if main-repo has been set in repos.conf.
			prepos[main_repo].priority = -1000

		# DEPRECATED Backward compatible SYNC support for old mirrorselect.
		# Feb. 2, 2015.  Version 2.2.16
		if portdir_sync and main_repo is not None:
			writemsg(_("!!! SYNC setting found in make.conf.\n    "
				"This setting is Deprecated and no longer used.  "
				"Please ensure your 'sync-type' and 'sync-uri' are set correctly"
				" in /etc/portage/repos.conf/gentoo.conf\n"),
				noiselevel=-1)


		# Include repo.name in sort key, for predictable sorting
		# even when priorities are equal.
		prepos_order = sorted(prepos.items(),
			key=lambda r:(r[1].priority or 0, r[1].name))

		# filter duplicates from aliases, by only including
		# items where repo.name == key
		prepos_order = [repo.name for (key, repo) in prepos_order
			if repo.name == key and key != 'DEFAULT' and
			repo.location is not None]

		self.prepos = prepos
		self.prepos_order = prepos_order
		self.ignored_repos = ignored_repos
		self.location_map = location_map
		self.treemap = treemap
		self._prepos_changed = True
		self._repo_location_list = []

		#The 'masters' key currently contains repo names. Replace them with the matching RepoConfig.
		for repo_name, repo in prepos.items():
			if repo_name == "DEFAULT":
				continue
			if repo.masters is None:
				if self.mainRepo() and repo_name != self.mainRepo().name:
					repo.masters = (self.mainRepo(),)
				else:
					repo.masters = ()
			else:
				if repo.masters and isinstance(repo.masters[0], RepoConfig):
					# This one has already been processed
					# because it has an alias.
					continue
				master_repos = []
				for master_name in repo.masters:
					if master_name not in prepos:
						layout_filename = os.path.join(repo.location,
							"metadata", "layout.conf")
						writemsg_level(_("Unavailable repository '%s' " \
							"referenced by masters entry in '%s'\n") % \
							(master_name, layout_filename),
							level=logging.ERROR, noiselevel=-1)
					else:
						master_repos.append(prepos[master_name])
				repo.masters = tuple(master_repos)

		#The 'eclass_overrides' key currently contains repo names. Replace them with the matching repo paths.
		for repo_name, repo in prepos.items():
			if repo_name == "DEFAULT":
				continue

			eclass_locations = []
			eclass_locations.extend(master_repo.location for master_repo in repo.masters)
			# Only append the current repo to eclass_locations if it's not
			# there already. This allows masters to have more control over
			# eclass override order, which may be useful for scenarios in
			# which there is a plan to migrate eclasses to a master repo.
			if repo.location not in eclass_locations:
				eclass_locations.append(repo.location)

			if repo.eclass_overrides:
				for other_repo_name in repo.eclass_overrides:
					if other_repo_name in self.treemap:
						eclass_locations.append(self.get_location_for_name(other_repo_name))
					else:
						writemsg_level(_("Unavailable repository '%s' " \
							"referenced by eclass-overrides entry for " \
							"'%s'\n") % (other_repo_name, repo_name), \
							level=logging.ERROR, noiselevel=-1)
			repo.eclass_locations = tuple(eclass_locations)

		eclass_dbs = {}
		for repo_name, repo in prepos.items():
			if repo_name == "DEFAULT":
				continue

			eclass_db = None
			for eclass_location in repo.eclass_locations:
				tree_db = eclass_dbs.get(eclass_location)
				if tree_db is None:
					tree_db = eclass_cache.cache(eclass_location)
					eclass_dbs[eclass_location] = tree_db
				if eclass_db is None:
					eclass_db = tree_db.copy()
				else:
					eclass_db.append(tree_db)
			repo.eclass_db = eclass_db

		for repo_name, repo in prepos.items():
			if repo_name == "DEFAULT":
				continue

			if repo._masters_orig is None and self.mainRepo() and \
				repo.name != self.mainRepo().name and not portage._sync_mode:
				# TODO: Delete masters code in lib/portage/tests/resolver/ResolverPlayground.py when deleting this warning.
				writemsg_level("!!! %s\n" % _("Repository '%s' is missing masters attribute in '%s'") %
					(repo.name, os.path.join(repo.location, "metadata", "layout.conf")) +
					"!!! %s\n" % _("Set 'masters = %s' in this file for future compatibility") %
					self.mainRepo().name, level=logging.WARNING, noiselevel=-1)

		self._prepos_changed = True
		self._repo_location_list = []

		self._check_locations()

	def repoLocationList(self):
		"""Get a list of repositories location. Replaces PORTDIR_OVERLAY"""
		if self._prepos_changed:
			_repo_location_list = []
			for repo in self.prepos_order:
				if self.prepos[repo].location is not None:
					_repo_location_list.append(self.prepos[repo].location)
			self._repo_location_list = tuple(_repo_location_list)

			self._prepos_changed = False
		return self._repo_location_list

	def mainRepoLocation(self):
		"""Returns the location of main repo"""
		main_repo = self.prepos['DEFAULT'].main_repo
		if main_repo is not None and main_repo in self.prepos:
			return self.prepos[main_repo].location
		return ''

	def mainRepo(self):
		"""Returns the main repo"""
		main_repo = self.prepos['DEFAULT'].main_repo
		if main_repo is None:
			return None
		return self.prepos[main_repo]

	def _check_locations(self):
		"""Check if repositories location are correct and show a warning message if not"""
		for (name, r) in self.prepos.items():
			if name != 'DEFAULT':
				if r.location is None:
					writemsg(_("!!! Location not set for repository %s\n") % name, noiselevel=-1)
				else:
					if not isdir_raise_eaccess(r.location) and not portage._sync_mode:
						self.prepos_order.remove(name)
						writemsg(_("!!! Invalid Repository Location"
							" (not a dir): '%s'\n") % r.location, noiselevel=-1)

	def repos_with_profiles(self):
		for repo_name in self.prepos_order:
			repo = self.prepos[repo_name]
			if repo.format != "unavailable":
				yield repo

	def get_name_for_location(self, location):
		return self.location_map[location]

	def get_location_for_name(self, repo_name):
		if repo_name is None:
			# This simplifies code in places where
			# we want to be able to pass in Atom.repo
			# even if it is None.
			return None
		return self.treemap[repo_name]

	def get_repo_for_location(self, location):
		return self.prepos[self.get_name_for_location(location)]

	def __setitem__(self, repo_name, repo):
		# self.prepos[repo_name] = repo
		raise NotImplementedError

	def __getitem__(self, repo_name):
		return self.prepos[repo_name]

	def __delitem__(self, repo_name):
		if repo_name == self.prepos['DEFAULT'].main_repo:
			self.prepos['DEFAULT'].main_repo = None
		location = self.prepos[repo_name].location
		del self.prepos[repo_name]
		if repo_name in self.prepos_order:
			self.prepos_order.remove(repo_name)
		for k, v in self.location_map.copy().items():
			if v == repo_name:
				del self.location_map[k]
		if repo_name in self.treemap:
			del self.treemap[repo_name]
		self._repo_location_list = tuple(x for x in self._repo_location_list if x != location)

	def __iter__(self):
		for repo_name in self.prepos_order:
			yield self.prepos[repo_name]

	def __contains__(self, repo_name):
		return repo_name in self.prepos

	def config_string(self):
		bool_keys = (
			"strict_misc_digests",
			"sync_allow_hardlinks",
			"sync_openpgp_key_refresh",
			"sync_rcu",
		)
		str_or_int_keys = (
			"auto_sync",
			"clone_depth",
			"format",
			"location",
			"main_repo",
			"priority",
			"sync_depth",
			"sync_openpgp_keyserver",
			"sync_openpgp_key_path",
			"sync_openpgp_key_refresh_retry_count",
			"sync_openpgp_key_refresh_retry_delay_exp_base",
			"sync_openpgp_key_refresh_retry_delay_max",
			"sync_openpgp_key_refresh_retry_delay_mult",
			"sync_openpgp_key_refresh_retry_overall_timeout",
			"sync_rcu_spare_snapshots",
			"sync_rcu_store_dir",
			"sync_rcu_ttl_days",
			"sync_type",
			"sync_umask",
			"sync_uri",
			"sync_user",
		)
		str_tuple_keys = (
			"aliases",
			"eclass_overrides",
			"force",
		)
		repo_config_tuple_keys = ("masters",)
		keys = bool_keys + str_or_int_keys + str_tuple_keys + repo_config_tuple_keys
		config_string = ""
		for repo_name, repo in sorted(self.prepos.items(), key=lambda x: (x[0] != "DEFAULT", x[0])):
			if repo_name != repo.name:
				continue
			config_string += "\n[%s]\n" % repo_name
			for key in sorted(keys):
				if key == "main_repo" and repo_name != "DEFAULT":
					continue
				if getattr(repo, key) is not None:
					if key in bool_keys:
						config_string += "%s = %s\n" % (key.replace("_", "-"),
							'true' if getattr(repo, key) else 'false')
					elif key in str_or_int_keys:
						config_string += "%s = %s\n" % (key.replace("_", "-"), getattr(repo, key))
					elif key in str_tuple_keys:
						config_string += "%s = %s\n" % (key.replace("_", "-"), " ".join(getattr(repo, key)))
					elif key in repo_config_tuple_keys:
						config_string += "%s = %s\n" % (key.replace("_", "-"), " ".join(x.name for x in getattr(repo, key)))
			for o, v in repo.module_specific_options.items():
				config_string += "%s = %s\n" % (o, v)
		return config_string.lstrip("\n")

def allow_profile_repo_deps(
	repo: typing.Union[RepoConfig, _profile_node],
) -> bool:
	if eapi_has_repo_deps(repo.eapi):
		return True

	if 'profile-repo-deps' in repo.profile_formats:
		return True

	return False

def load_repository_config(settings, extra_files=None):
	repoconfigpaths = []
	if "PORTAGE_REPOSITORIES" in settings:
		repoconfigpaths.append(io.StringIO(settings["PORTAGE_REPOSITORIES"]))
	else:
		if portage._not_installed:
			repoconfigpaths.append(os.path.join(PORTAGE_BASE_PATH, "cnf", "repos.conf"))
		else:
			repoconfigpaths.append(os.path.join(settings.global_config_path, "repos.conf"))
		repoconfigpaths.append(os.path.join(settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH, "repos.conf"))
	if extra_files:
		repoconfigpaths.extend(extra_files)
	return RepoConfigLoader(repoconfigpaths, settings)

def _get_repo_name(repo_location, cached=None):
	if cached is not None:
		return cached
	name, missing = RepoConfig._read_repo_name(repo_location)
	if missing:
		return None
	return name

def parse_layout_conf(repo_location, repo_name=None):
	eapi = read_corresponding_eapi_file(os.path.join(repo_location, REPO_NAME_LOC))

	layout_filename = os.path.join(repo_location, "metadata", "layout.conf")
	layout_file = KeyValuePairFileLoader(layout_filename, None, None)
	layout_data, layout_errors = layout_file.load()

	data = {}

	# None indicates abscence of a masters setting, which later code uses
	# to trigger a backward compatibility fallback that sets an implicit
	# master. In order to avoid this fallback behavior, layout.conf can
	# explicitly set masters to an empty value, which will result in an
	# empty tuple here instead of None.
	masters = layout_data.get('masters')
	if masters is not None:
		masters = tuple(masters.split())
	data['masters'] = masters
	data['aliases'] = tuple(layout_data.get('aliases', '').split())

	data['eapis-banned'] = tuple(layout_data.get('eapis-banned', '').split())
	data['eapis-deprecated'] = tuple(layout_data.get('eapis-deprecated', '').split())

	properties_allowed = layout_data.get('properties-allowed')
	if properties_allowed is not None:
		properties_allowed = tuple(properties_allowed.split())
	data['properties-allowed'] = properties_allowed

	restrict_allowed = layout_data.get('restrict-allowed')
	if restrict_allowed is not None:
		restrict_allowed = tuple(restrict_allowed.split())
	data['restrict-allowed'] = restrict_allowed

	data['sign-commit'] = layout_data.get('sign-commits', 'false').lower() \
		== 'true'

	data['sign-manifest'] = layout_data.get('sign-manifests', 'true').lower() \
		== 'true'

	data['thin-manifest'] = layout_data.get('thin-manifests', 'false').lower() \
		== 'true'

	data['repo-name'] = _gen_valid_repo(layout_data.get('repo-name', ''))

	manifest_policy = layout_data.get('use-manifests', 'strict').lower()
	data['allow-missing-manifest'] = manifest_policy != 'strict'
	data['create-manifest'] = manifest_policy != 'false'
	data['disable-manifest'] = manifest_policy == 'false'

	# for compatibility w/ PMS, fallback to pms; but also check if the
	# cache exists or not.
	cache_formats = layout_data.get('cache-formats', '').lower().split()
	if not cache_formats:
		# Auto-detect cache formats, and prefer md5-cache if available.
		# This behavior was deployed in portage-2.1.11.14, so that the
		# default egencache format could eventually be changed to md5-dict
		# in portage-2.1.11.32. WARNING: Versions prior to portage-2.1.11.14
		# will NOT recognize md5-dict format unless it is explicitly
		# listed in layout.conf.
		cache_formats = []
		if os.path.isdir(os.path.join(repo_location, 'metadata', 'md5-cache')):
			cache_formats.append('md5-dict')
		if os.path.isdir(os.path.join(repo_location, 'metadata', 'cache')):
			cache_formats.append('pms')
	data['cache-formats'] = tuple(cache_formats)

	manifest_hashes = layout_data.get('manifest-hashes')
	manifest_required_hashes = layout_data.get('manifest-required-hashes')

	if manifest_required_hashes is not None and manifest_hashes is None:
		repo_name = _get_repo_name(repo_location, cached=repo_name)
		warnings.warn((_("Repository named '%(repo_name)s' specifies "
			"'manifest-required-hashes' setting without corresponding "
			"'manifest-hashes'. Portage will default it to match "
			"the required set but please add the missing entry "
			"to: %(layout_filename)s") %
			{"repo_name": repo_name or 'unspecified',
			"layout_filename":layout_filename}),
			SyntaxWarning)
		manifest_hashes = manifest_required_hashes

	if manifest_hashes is not None:
		# require all the hashes unless specified otherwise
		if manifest_required_hashes is None:
			manifest_required_hashes = manifest_hashes

		manifest_required_hashes = frozenset(manifest_required_hashes.upper().split())
		manifest_hashes = frozenset(manifest_hashes.upper().split())
		missing_required_hashes = manifest_required_hashes.difference(
			manifest_hashes)
		if missing_required_hashes:
			repo_name = _get_repo_name(repo_location, cached=repo_name)
			warnings.warn((_("Repository named '%(repo_name)s' has a "
				"'manifest-hashes' setting that does not contain "
				"the '%(hash)s' hashes which are listed in "
				"'manifest-required-hashes'. Please fix that file "
				"if you want to generate valid manifests for this "
				"repository: %(layout_filename)s") %
				{"repo_name": repo_name or 'unspecified',
				"hash": ' '.join(missing_required_hashes),
				"layout_filename":layout_filename}),
				SyntaxWarning)
		unsupported_hashes = manifest_hashes.difference(
			get_valid_checksum_keys())
		if unsupported_hashes:
			repo_name = _get_repo_name(repo_location, cached=repo_name)
			warnings.warn((_("Repository named '%(repo_name)s' has a "
				"'manifest-hashes' setting that contains one "
				"or more hash types '%(hashes)s' which are not supported by "
				"this portage version. You will have to upgrade "
				"portage if you want to generate valid manifests for "
				"this repository: %(layout_filename)s") %
				{"repo_name": repo_name or 'unspecified',
				"hashes":" ".join(sorted(unsupported_hashes)),
				"layout_filename":layout_filename}),
				DeprecationWarning)

	data['manifest-hashes'] = manifest_hashes
	data['manifest-required-hashes'] = manifest_required_hashes

	data['update-changelog'] = layout_data.get('update-changelog', 'false').lower() \
		== 'true'

	raw_formats = layout_data.get('profile-formats')
	if raw_formats is None:
		if eapi_allows_directories_on_profile_level_and_repository_level(eapi):
			raw_formats = ('portage-1',)
		else:
			raw_formats = ('portage-1-compat',)
	else:
		raw_formats = set(raw_formats.split())
		unknown = raw_formats.difference(_valid_profile_formats)
		if unknown:
			repo_name = _get_repo_name(repo_location, cached=repo_name)
			warnings.warn((_("Repository named '%(repo_name)s' has unsupported "
				"profiles in use ('profile-formats = %(unknown_fmts)s' setting in "
				"'%(layout_filename)s; please upgrade portage.") %
				dict(repo_name=repo_name or 'unspecified',
				layout_filename=layout_filename,
				unknown_fmts=" ".join(unknown))),
				DeprecationWarning)
		raw_formats = tuple(raw_formats.intersection(_valid_profile_formats))
	data['profile-formats'] = raw_formats

	try:
		eapi = layout_data['profile_eapi_when_unspecified']
	except KeyError:
		pass
	else:
		if 'profile-default-eapi' not in raw_formats:
			warnings.warn((_("Repository named '%(repo_name)s' has "
				"profile_eapi_when_unspecified setting in "
				"'%(layout_filename)s', but 'profile-default-eapi' is "
				"not listed in the profile-formats field. Please "
				"report this issue to the repository maintainer.") %
				dict(repo_name=repo_name or 'unspecified',
				layout_filename=layout_filename)),
				SyntaxWarning)
		elif not portage.eapi_is_supported(eapi):
			warnings.warn((_("Repository named '%(repo_name)s' has "
				"unsupported EAPI '%(eapi)s' setting in "
				"'%(layout_filename)s'; please upgrade portage.") %
				dict(repo_name=repo_name or 'unspecified',
				eapi=eapi, layout_filename=layout_filename)),
				SyntaxWarning)
		else:
			data['profile_eapi_when_unspecified'] = eapi

	return data, layout_errors
