# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
	from configparser import SafeConfigParser
except ImportError:
	from ConfigParser import SafeConfigParser
from portage import os
from portage.const import USER_CONFIG_PATH, GLOBAL_CONFIG_PATH, REPO_NAME_LOC
from portage.util import normalize_path, writemsg, shlex_split
from portage.localization import _
from portage import _unicode_encode
from portage import _encodings

import codecs

class RepoConfig(object):
	"""Stores config of one repository"""
	__slots__ = ['aliases', 'eclass_overrides', 'location', 'masters', 'main_repo',
		'missing_repo_name', 'name', 'priority', 'sync']
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

		masters = repo_opts.get('masters')
		if masters is not None:
			masters = tuple(masters.split())
		self.masters = masters

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

		self.missing_repo_name = False

		location = repo_opts.get('location')
		if location is not None:
			location = normalize_path(location)
			if os.path.isdir(location):
				repo_name = self._get_repo_name(location)
				if repo_name:
					name = repo_name
		self.name = name
		self.location = location

	def update(self, new_repo):
		"""Update repository with options in another RepoConfig"""
		if new_repo.aliases is not None:
			self.aliases = new_repo.aliases
		if new_repo.eclass_overrides is not None:
			self.eclass_overrides = new_repo.eclass_overrides
		if new_repo.masters is not None:
			self.masters = new_repo.masters
		if new_repo.name is not None:
			self.name = new_repo.name
		if new_repo.location is not None:
			self.location = new_repo.location
		if new_repo.priority is not None:
			self.priority = new_repo.priority
		if new_repo.sync is not None:
			self.sync = new_repo.sync

	def _get_repo_name(self, repo_path):
		"""Read repo_name from repo_path"""
		repo_name_path = os.path.join(repo_path, REPO_NAME_LOC)
		try:
			return codecs.open(
				_unicode_encode(repo_name_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace').readline().strip()
		except EnvironmentError:
			self.missing_repo_name = True
			return "x-" + os.path.basename(repo_path)

class RepoConfigLoader(object):
	"""Loads and store config of several repositories, loaded from PORTDIR_OVERLAY or repos.conf"""
	def __init__(self, paths, settings):
		"""Load config from files in paths"""
		def parse(paths, prepos, ignored_map, ignored_location_map):
			"""Parse files in paths to load config"""
			parser = SafeConfigParser()
			try:
				parser.read(paths)
			except SafeConfigParser.Error as e:
				writemsg(_("!!! Error while reading repo config file: %s\n") % e, noiselevel=-1)
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

		def add_overlays(portdir, portdir_overlay, prepos, ignored_map, ignored_location_map):
			"""Add overlays in PORTDIR_OVERLAY as repositories"""
			overlays = []
			port_ov = [normalize_path(i) for i in shlex_split(portdir_overlay)]
			overlays.extend(port_ov)
			if portdir:
				portdir = normalize_path(portdir)
				overlays.append(portdir)
			if overlays:
				#overlay priority is negative because we want them to be looked before any other repo
				base_priority = -1
				for ov in overlays:
					if os.path.isdir(ov):
						repo = RepoConfig(None, {'location' : ov})

						if repo.name in prepos:
							old_location = prepos[repo.name].location
							if old_location is not None and old_location != repo.location:
								ignored_map.setdefault(repo.name, []).append(old_location)
								ignored_location_map[old_location] = repo.name
							prepos[repo.name].update(repo)
						else:
							if ov == portdir and portdir not in port_ov:
								repo.priority = 1000
							else:
								repo.priority = base_priority
								base_priority -= 1
							prepos[repo.name] = repo
					else:
						writemsg(_("!!! Invalid PORTDIR_OVERLAY"
							" (not a dir): '%s'\n") % ov, noiselevel=-1)
		def repo_priority(r):
			"""
			Key funtion for comparing repositories by priority.
			None is equal priority zero.
			"""
			x = prepos[r].priority
			if x is None:
				return 0
			return x

		prepos = {}
		location_map = {}
		treemap = {}
		ignored_map = {}
		ignored_location_map = {}

		portdir = settings.get('PORTDIR', '')
		portdir_overlay = settings.get('PORTDIR_OVERLAY', '')
		add_overlays(portdir, portdir_overlay, prepos, ignored_map, ignored_location_map)
		parse(paths, prepos, ignored_map, ignored_location_map)
		ignored_repos = tuple((repo_name, tuple(paths)) \
			for repo_name, paths in ignored_map.items())

		self.missing_repo_names = frozenset(repo.location for repo in prepos.values() if repo.missing_repo_name)

		for (name, r) in prepos.items():
			if r.location is not None:
				location_map[r.location] = name
				treemap[name] = r.location

		prepos_order = [repo.name for repo in prepos.values() if repo.location is not None]
		prepos_order.sort(key=repo_priority, reverse=True)

		if portdir:
			portdir_repo = prepos[location_map[portdir]]
			portdir_sync = settings.get('SYNC', '')
			#if SYNC variable is set and not overwritten by repos.conf
			if portdir_sync and not portdir_repo.sync:
				portdir_repo.sync = portdir_sync

		if prepos['DEFAULT'].main_repo is None:
			#setting main_repo if it was not set in repos.conf
			if portdir in location_map:
				prepos['DEFAULT'].main_repo = location_map[portdir]
			elif portdir in ignored_location_map:
				prepos['DEFAULT'].main_repo = ignored_location_map[portdir]
			else:
				writemsg(_("!!! main-repo not set in DEFAULT and PORTDIR is empty. \n"), noiselevel=-1)

		self.prepos = prepos
		self.prepos_order = prepos_order
		self.ignored_repos = ignored_repos
		self.location_map = location_map
		self.treemap = treemap
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
		else:
			return ''

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

def load_repository_config(settings):
	#~ repoconfigpaths = [os.path.join(settings.global_config_path, "repos.conf")]
	#~ repoconfigpaths.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		#~ USER_CONFIG_PATH, "repos.conf"))
	repoconfigpaths = []
	return RepoConfigLoader(repoconfigpaths, settings)
