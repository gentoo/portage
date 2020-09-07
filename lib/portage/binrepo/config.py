# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from collections import OrderedDict
from collections.abc import Mapping
from hashlib import md5

from portage.localization import _
from portage.util import _recursive_file_list, writemsg
from portage.util.configparser import (SafeConfigParser, ConfigParserError,
	read_configs)


class BinRepoConfig:
	__slots__ = (
		'name',
		'name_fallback',
		'fetchcommand',
		'priority',
		'resumecommand',
		'sync_uri',
	)
	def __init__(self, opts):
		"""
		Create a BinRepoConfig with options in opts.
		"""
		for k in self.__slots__:
			setattr(self, k, opts.get(k.replace('_', '-')))

	def info_string(self):
		"""
		Returns a formatted string containing informations about the repository.
		Used by emerge --info.
		"""
		indent = " " * 4
		repo_msg = []
		repo_msg.append(self.name or self.name_fallback)
		if self.priority is not None:
			repo_msg.append(indent + "priority: " + str(self.priority))
		repo_msg.append(indent + "sync-uri: " + self.sync_uri)
		repo_msg.append("")
		return "\n".join(repo_msg)


class BinRepoConfigLoader(Mapping):
	def __init__(self, paths, settings):
		"""Load config from files in paths"""

		# Defaults for value interpolation.
		parser_defaults = {
			"EPREFIX" : settings["EPREFIX"],
			"EROOT" : settings["EROOT"],
			"PORTAGE_CONFIGROOT" : settings["PORTAGE_CONFIGROOT"],
			"ROOT" : settings["ROOT"],
		}

		try:
			parser = self._parse(paths, parser_defaults)
		except ConfigParserError as e:
			writemsg(
				_("!!! Error while reading binrepo config file: %s\n") % e,
				noiselevel=-1)
			parser = SafeConfigParser(defaults=parser_defaults)

		repos = []
		sync_uris = []
		for section_name in parser.sections():
			repo_data = dict(parser[section_name].items())
			repo_data['name'] = section_name
			repo = BinRepoConfig(repo_data)
			if repo.sync_uri is None:
				writemsg(_("!!! Missing sync-uri setting for binrepo %s\n") % (repo.name,), noiselevel=-1)
				continue

			sync_uri = self._normalize_uri(repo.sync_uri)
			sync_uris.append(sync_uri)
			repo.sync_uri = sync_uri
			if repo.priority is not None:
				try:
					repo.priority = int(repo.priority)
				except ValueError:
					repo.priority = None
			repos.append(repo)

		sync_uris = set(sync_uris)
		current_priority = 0
		for sync_uri in reversed(settings.get("PORTAGE_BINHOST", "").split()):
			sync_uri = self._normalize_uri(sync_uri)
			if sync_uri not in sync_uris:
				current_priority += 1
				sync_uris.add(sync_uri)
				repos.append(BinRepoConfig({
					'name-fallback': self._digest_uri(sync_uri),
					'name': None,
					'priority': current_priority,
					'sync-uri': sync_uri,
				}))

		self._data = OrderedDict((repo.name or repo.name_fallback, repo) for repo in
			sorted(repos, key=lambda repo: (repo.priority or 0, repo.name or repo.name_fallback)))

	@staticmethod
	def _digest_uri(uri):
		return md5(uri.encode('utf_8')).hexdigest()

	@staticmethod
	def _normalize_uri(uri):
		return uri.rstrip('/')

	@staticmethod
	def _parse(paths, defaults):
		parser = SafeConfigParser(defaults=defaults)
		recursive_paths = []
		for p in paths:
			if isinstance(p, str):
				recursive_paths.extend(_recursive_file_list(p))
			else:
				recursive_paths.append(p)

		read_configs(parser, recursive_paths)
		return parser

	def __iter__(self):
		return iter(self._data)

	def __contains__(self, key):
		return key in self._data

	def __getitem__(self, key):
		return self._data[key]

	def __len__(self):
		return len(self._data)
