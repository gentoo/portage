# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import logging
import warnings
import sys
import re

try:
	from configparser import ParsingError
	if sys.hexversion >= 0x3020000:
		from configparser import ConfigParser as SafeConfigParser
	else:
		from configparser import SafeConfigParser
except ImportError:
	from ConfigParser import SafeConfigParser, ParsingError
import portage
from portage import eclass_cache, os
from portage.const import (MANIFEST2_HASH_FUNCTIONS, MANIFEST2_REQUIRED_HASH,
	REPO_NAME_LOC, USER_CONFIG_PATH)
from portage.eapi import eapi_allows_directories_on_profile_level_and_repository_level
from portage.env.loaders import KeyValuePairFileLoader
from portage.util import (normalize_path, read_corresponding_eapi_file, shlex_split,
	stack_lists, writemsg, writemsg_level)
from portage.localization import _
from portage import _unicode_decode
from portage import _unicode_encode
from portage import _encodings
from portage import manifest

# Characters prohibited by repoman's file.name check.
_invalid_path_char_re = re.compile(r'[^a-zA-Z0-9._\-+:/]')

_valid_profile_formats = frozenset(
	['pms', 'portage-1', 'portage-2'])

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

class RepoConfig(object):
	"""Stores config of one repository"""

	__slots__ = ('aliases', 'allow_missing_manifest', 'allow_provide_virtual',
		'cache_formats', 'create_manifest', 'disable_manifest', 'eapi',
		'eclass_db', 'eclass_locations', 'eclass_overrides',
		'find_invalid_path_char', 'format', 'location',
		'main_repo', 'manifest_hashes', 'masters', 'missing_repo_name',
		'name', 'portage1_profiles', 'portage1_profiles_compat', 'priority',
		'profile_formats', 'sign_commit', 'sign_manifest', 'sync',
		'thin_manifest', 'update_changelog', 'user_location')

	def __init__(self, name, repo_opts):
		"""Build a RepoConfig with options in repo_opts
		   Try to read repo_name in repository location, but if
		   it is not found use variable name as repository name"""
		aliases = repo_opts.get('aliases')
		if aliases is not None:
			aliases = tuple(aliases.split())
		self.aliases = aliases

		eclass_overrides = repo_opts.get('eclass-overrides')
		if eclass_overrides is not None:
			eclass_overrides = tuple(eclass_overrides.split())
		self.eclass_overrides = eclass_overrides
		# Eclass databases and locations are computed later.
		self.eclass_db = None
		self.eclass_locations = None

		# Masters from repos.conf override layout.conf.
		masters = repo_opts.get('masters')
		if masters is not None:
			masters = tuple(masters.split())
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

		sync = repo_opts.get('sync')
		if sync is not None:
			sync = sync.strip()
		self.sync = sync

		format = repo_opts.get('format')
		if format is not None:
			format = format.strip()
		self.format = format

		location = repo_opts.get('location')
		self.user_location = location
		if location is not None and location.strip():
			if os.path.isdir(location):
				location = os.path.realpath(location)
		else:
			location = None
		self.location = location

		eapi = None
		missing = True
		if self.location is not None:
			eapi = read_corresponding_eapi_file(os.path.join(self.location, REPO_NAME_LOC))
			name, missing = self._read_valid_repo_name(self.location)
		elif name == "DEFAULT": 
			missing = False

		self.eapi = eapi
		self.name = name
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
		self.update_changelog = False
		self.cache_formats = None
		self.portage1_profiles = True
		self.portage1_profiles_compat = False
		self.find_invalid_path_char = _find_invalid_path_char

		# Parse layout.conf.
		if self.location:
			layout_filename = os.path.join(self.location, "metadata", "layout.conf")
			layout_data = parse_layout_conf(self.location, self.name)[0]

			# layout.conf masters may be overridden here if we have a masters
			# setting from the user's repos.conf
			if self.masters is None:
				self.masters = layout_data['masters']

			if layout_data['aliases']:
				aliases = self.aliases
				if aliases is None:
					aliases = ()
				# repos.conf aliases come after layout.conf aliases, giving
				# them the ability to do incremental overrides
				self.aliases = layout_data['aliases'] + tuple(aliases)

			for value in ('allow-missing-manifest',
				'allow-provide-virtual', 'cache-formats',
				'create-manifest', 'disable-manifest', 'manifest-hashes',
				'profile-formats',
				'sign-commit', 'sign-manifest', 'thin-manifest', 'update-changelog'):
				setattr(self, value.lower().replace("-", "_"), layout_data[value])

			self.portage1_profiles = eapi_allows_directories_on_profile_level_and_repository_level(eapi) or \
				any(x in _portage1_profiles_allow_directories for x in layout_data['profile-formats'])
			self.portage1_profiles_compat = not eapi_allows_directories_on_profile_level_and_repository_level(eapi) and \
				layout_data['profile-formats'] == ('portage-1-compat',)

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
			formats = ('pms',)

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
		if self.user_location:
			repo_msg.append(indent + "location: " + self.user_location)
		if self.sync:
			repo_msg.append(indent + "sync: " + self.sync)
		if self.masters:
			repo_msg.append(indent + "masters: " + " ".join(master.name for master in self.masters))
		if self.priority is not None:
			repo_msg.append(indent + "priority: " + str(self.priority))
		if self.aliases:
			repo_msg.append(indent + "aliases: " + " ".join(self.aliases))
		if self.eclass_overrides:
			repo_msg.append(indent + "eclass_overrides: " + \
				" ".join(self.eclass_overrides))
		repo_msg.append("")
		return "\n".join(repo_msg)

	def __repr__(self):
		return "<portage.repository.config.RepoConfig(name='%s', location='%s')>" % (self.name, _unicode_decode(self.location))

	def __str__(self):
		d = {}
		for k in self.__slots__:
			d[k] = getattr(self, k, None)
		return _unicode_decode("%s") % (d,)

	if sys.hexversion < 0x3000000:

		__unicode__ = __str__

		def __str__(self):
			return _unicode_encode(self.__unicode__())

class RepoConfigLoader(object):
	"""Loads and store config of several repositories, loaded from PORTDIR_OVERLAY or repos.conf"""

	@staticmethod
	def _add_repositories(portdir, portdir_overlay, prepos, ignored_map, ignored_location_map):
		"""Add overlays in PORTDIR_OVERLAY as repositories"""
		overlays = []
		if portdir:
			portdir = normalize_path(portdir)
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
				if os.path.isdir(ov):
					repo_opts = default_repo_opts.copy()
					repo_opts['location'] = ov
					repo = RepoConfig(None, repo_opts)
					# repos_conf_opts contains options from repos.conf
					repos_conf_opts = repos_conf.get(repo.name)
					if repos_conf_opts is not None:
						# Selectively copy only the attributes which
						# repos.conf is allowed to override.
						for k in ('aliases', 'eclass_overrides', 'masters', 'priority'):
							v = getattr(repos_conf_opts, k, None)
							if v is not None:
								setattr(repo, k, v)

					if repo.name in prepos:
						old_location = prepos[repo.name].location
						if old_location is not None and old_location != repo.location:
							ignored_map.setdefault(repo.name, []).append(old_location)
							ignored_location_map[old_location] = repo.name
							if old_location == portdir:
								portdir = repo.user_location

					if ov == portdir and portdir not in port_ov:
						repo.priority = -1000
					elif repo.priority is None:
						repo.priority = base_priority
						base_priority += 1

					prepos[repo.name] = repo
				else:
					if not portage._sync_disabled_warnings:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY (not a dir): '%s'\n") % ov, noiselevel=-1)

		return portdir

	@staticmethod
	def _parse(paths, prepos, ignored_map, ignored_location_map):
		"""Parse files in paths to load config"""
		parser = SafeConfigParser()

		# use read_file/readfp in order to control decoding of unicode
		try:
			# Python >=3.2
			read_file = parser.read_file
		except AttributeError:
			read_file = parser.readfp

		for p in paths:
			f = None
			try:
				f = io.open(_unicode_encode(p,
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace')
			except EnvironmentError:
				pass
			else:
				try:
					read_file(f)
				except ParsingError as e:
					writemsg(_unicode_decode(
						_("!!! Error while reading repo config file: %s\n")
						) % e, noiselevel=-1)
			finally:
				if f is not None:
					f.close()

		prepos['DEFAULT'] = RepoConfig("DEFAULT", parser.defaults())
		for sname in parser.sections():
			optdict = {}
			for oname in parser.options(sname):
				optdict[oname] = parser.get(sname, oname)

			repo = RepoConfig(sname, optdict)
			if repo.location and not os.path.exists(repo.location):
				writemsg(_("!!! Invalid repos.conf entry '%s'"
					" (not a dir): '%s'\n") % (sname, repo.location), noiselevel=-1)
				continue

			if repo.name in prepos:
				old_location = prepos[repo.name].location
				if old_location is not None and repo.location is not None and old_location != repo.location:
					ignored_map.setdefault(repo.name, []).append(old_location)
					ignored_location_map[old_location] = repo.name
				prepos[repo.name].update(repo)
			else:
				prepos[repo.name] = repo

	def __init__(self, paths, settings):
		"""Load config from files in paths"""

		prepos = {}
		location_map = {}
		treemap = {}
		ignored_map = {}
		ignored_location_map = {}

		portdir = settings.get('PORTDIR', '')
		portdir_overlay = settings.get('PORTDIR_OVERLAY', '')

		self._parse(paths, prepos, ignored_map, ignored_location_map)

		# If PORTDIR_OVERLAY contains a repo with the same repo_name as
		# PORTDIR, then PORTDIR is overridden.
		portdir = self._add_repositories(portdir, portdir_overlay, prepos,
			ignored_map, ignored_location_map)
		if portdir and portdir.strip():
			portdir = os.path.realpath(portdir)

		ignored_repos = tuple((repo_name, tuple(paths)) \
			for repo_name, paths in ignored_map.items())

		self.missing_repo_names = frozenset(repo.location
			for repo in prepos.values()
			if repo.location is not None and repo.missing_repo_name)

		#Take aliases into account.
		new_prepos = {}
		for repo_name, repo in prepos.items():
			names = set()
			names.add(repo_name)
			if repo.aliases:
				aliases = stack_lists([repo.aliases], incremental=True)
				names.update(aliases)

			for name in names:
				if name in new_prepos:
					writemsg_level(_("!!! Repository name or alias '%s', " + \
						"defined for repository '%s', overrides " + \
						"existing alias or repository.\n") % (name, repo_name), level=logging.WARNING, noiselevel=-1)
				new_prepos[name] = repo
		prepos = new_prepos

		for (name, r) in prepos.items():
			if r.location is not None:
				location_map[r.location] = name
				treemap[name] = r.location

		# filter duplicates from aliases, by only including
		# items where repo.name == key

		prepos_order = sorted(prepos.items(), key=lambda r:r[1].priority or 0)

		prepos_order = [repo.name for (key, repo) in prepos_order
			if repo.name == key and repo.location is not None]

		if prepos['DEFAULT'].main_repo is None or \
			prepos['DEFAULT'].main_repo not in prepos:
			#setting main_repo if it was not set in repos.conf
			if portdir in location_map:
				prepos['DEFAULT'].main_repo = location_map[portdir]
			elif portdir in ignored_location_map:
				prepos['DEFAULT'].main_repo = ignored_location_map[portdir]
			else:
				prepos['DEFAULT'].main_repo = None
				if not portage._sync_disabled_warnings:
					writemsg(_("!!! main-repo not set in DEFAULT and PORTDIR is empty.\n"), noiselevel=-1)

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
					repo.masters = self.mainRepo(),
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
						layout_filename = os.path.join(repo.user_location,
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

	def repoUserLocationList(self):
		"""Get a list of repositories location. Replaces PORTDIR_OVERLAY"""
		user_location_list = []
		for repo in self.prepos_order:
			if self.prepos[repo].location is not None:
				user_location_list.append(self.prepos[repo].user_location)
		return tuple(user_location_list)

	def mainRepoLocation(self):
		"""Returns the location of main repo"""
		main_repo = self.prepos['DEFAULT'].main_repo
		if main_repo is not None and main_repo in self.prepos:
			return self.prepos[main_repo].location
		else:
			return ''

	def mainRepo(self):
		"""Returns the main repo"""
		maid_repo = self.prepos['DEFAULT'].main_repo
		if maid_repo is None:
			return None
		return self.prepos[maid_repo]

	def _check_locations(self):
		"""Check if repositories location are correct and show a warning message if not"""
		for (name, r) in self.prepos.items():
			if name != 'DEFAULT':
				if r.location is None:
					writemsg(_("!!! Location not set for repository %s\n") % name, noiselevel=-1)
				else:
					if not os.path.isdir(r.location):
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

	def __getitem__(self, repo_name):
		return self.prepos[repo_name]

	def __iter__(self):
		for repo_name in self.prepos_order:
			yield self.prepos[repo_name]

def load_repository_config(settings):
	#~ repoconfigpaths = [os.path.join(settings.global_config_path, "repos.conf")]
	repoconfigpaths = []
	if settings.local_config:
		repoconfigpaths.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
			USER_CONFIG_PATH, "repos.conf"))
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

	data['allow-provide-virtual'] = \
		layout_data.get('allow-provide-virtuals', 'false').lower() == 'true'

	data['sign-commit'] = layout_data.get('sign-commits', 'false').lower() \
		== 'true'

	data['sign-manifest'] = layout_data.get('sign-manifests', 'true').lower() \
		== 'true'

	data['thin-manifest'] = layout_data.get('thin-manifests', 'false').lower() \
		== 'true'

	manifest_policy = layout_data.get('use-manifests', 'strict').lower()
	data['allow-missing-manifest'] = manifest_policy != 'strict'
	data['create-manifest'] = manifest_policy != 'false'
	data['disable-manifest'] = manifest_policy == 'false'

	# for compatibility w/ PMS, fallback to pms; but also check if the
	# cache exists or not.
	cache_formats = layout_data.get('cache-formats', '').lower().split()
	if not cache_formats:
		# Auto-detect cache formats, and prefer md5-cache if available.
		# After this behavior is deployed in stable portage, the default
		# egencache format can be changed to md5-dict.
		cache_formats = []
		if os.path.isdir(os.path.join(repo_location, 'metadata', 'md5-cache')):
			cache_formats.append('md5-dict')
		if os.path.isdir(os.path.join(repo_location, 'metadata', 'cache')):
			cache_formats.append('pms')
	data['cache-formats'] = tuple(cache_formats)

	manifest_hashes = layout_data.get('manifest-hashes')
	if manifest_hashes is not None:
		manifest_hashes = frozenset(manifest_hashes.upper().split())
		if MANIFEST2_REQUIRED_HASH not in manifest_hashes:
			repo_name = _get_repo_name(repo_location, cached=repo_name)
			warnings.warn((_("Repository named '%(repo_name)s' has a "
				"'manifest-hashes' setting that does not contain "
				"the '%(hash)s' hash which is required by this "
				"portage version. You will have to upgrade portage "
				"if you want to generate valid manifests for this "
				"repository: %(layout_filename)s") %
				{"repo_name": repo_name or 'unspecified',
				"hash":MANIFEST2_REQUIRED_HASH,
				"layout_filename":layout_filename}),
				DeprecationWarning)
		unsupported_hashes = manifest_hashes.difference(
			MANIFEST2_HASH_FUNCTIONS)
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

	return data, layout_errors
