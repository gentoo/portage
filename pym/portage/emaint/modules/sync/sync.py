# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import os
import sys

import portage
from portage.localization import _
from portage.output import bold, create_color_func
from portage.sync import get_syncer
from portage._global_updates import _global_updates
from portage.util import writemsg_level

import _emerge
from _emerge.emergelog import emergelog


portage.proxy.lazyimport.lazyimport(globals(),
	'_emerge.actions:adjust_configs,load_emerge_config',
	'_emerge.chk_updated_cfg_files:chk_updated_cfg_files',
	'_emerge.main:parse_opts',
	'_emerge.post_emerge:display_news_notification',
)

warn = create_color_func("WARN")

if sys.hexversion >= 0x3000000:
	_basestring = str
else:
	_basestring = basestring


class SyncRepos(object):

	short_desc = "Check repos.conf settings and/or sync repositories"

	@staticmethod
	def name():
		return "sync"


	def can_progressbar(self, func):
		return False


	def __init__(self, emerge_config=None, emerge_logging=False):
		'''Class init function

		@param emerge_config: optional an emerge_config instance to use
		@param emerge_logging: boolean, defaults to False
		'''
		if emerge_config:
			self.emerge_config = emerge_config
		else:
			# need a basic options instance
			actions, opts, _files = parse_opts([], silent=True)
			self.emerge_config = load_emerge_config(
				action='sync', args=_files, trees=[], opts=opts)
		if emerge_logging:
			_emerge.emergelog._disable = False
		self.xterm_titles = "notitles" not in \
			self.emerge_config.target_config.settings.features
		emergelog(self.xterm_titles, " === sync")


	def auto_sync(self, **kwargs):
		'''Sync auto-sync enabled repos'''
		options = kwargs.get('options', None)
		selected = self._get_repos(True)
		if options.get('return-messages', False):
			return self.rmessage(self._sync(selected), 'sync')
		return self._sync(selected)


	def all_repos(self, **kwargs):
		'''Sync all repos defined in repos.conf'''
		selected = self._get_repos(auto_sync_only=False)
		options = kwargs.get('options', None)
		if options.get('return-messages', False):
			return self.rmessage(
				self._sync(selected),
				'sync')
		return self._sync(selected)


	def repo(self, **kwargs):
		'''Sync the specified repo'''
		options = kwargs.get('options', None)
		if options:
			repos = options.get('repo', '')
			return_messages = options.get('return-messages', False)
		else:
			return_messages = False
		if isinstance(repos, _basestring):
			repos = repos.split()
		available = self._get_repos(auto_sync_only=False)
		selected = self._match_repos(repos, available)
		if return_messages:
			return self.rmessage(self._sync(selected), 'sync')
		return self._sync(selected)


	@staticmethod
	def _match_repos(repos, available):
		'''Internal search, matches up the repo.name in repos

		@param repos: list, of repo names to match
		@param avalable: list of repo objects to search
		@return: list of repo objects that match
		'''
		selected = []
		for repo in available:
			if repo.name in repos:
				selected.append(repo)
		return selected


	def _get_repos(self, auto_sync_only=True):
		selected_repos = []
		unknown_repo_names = []
		missing_sync_type = []
		if self.emerge_config.args:
			for repo_name in self.emerge_config.args:
				print("_get_repos(): repo_name =", repo_name)
				try:
					repo = self.emerge_config.target_config.settings.repositories[repo_name]
				except KeyError:
					unknown_repo_names.append(repo_name)
				else:
					selected_repos.append(repo)
					if repo.sync_type is None:
						missing_sync_type.append(repo)

			if unknown_repo_names:
				writemsg_level("!!! %s\n" % _("Unknown repo(s): %s") %
					" ".join(unknown_repo_names),
					level=logging.ERROR, noiselevel=-1)

			if missing_sync_type:
				writemsg_level("!!! %s\n" %
					_("Missing sync-type for repo(s): %s") %
					" ".join(repo.name for repo in missing_sync_type),
					level=logging.ERROR, noiselevel=-1)

			if unknown_repo_names or missing_sync_type:
				print("missing or unknown repos... returning")
				return []

		else:
			selected_repos.extend(self.emerge_config.target_config.settings.repositories)
		#print("_get_repos(), selected =", selected_repos)
		if auto_sync_only:
			return self._filter_auto(selected_repos)
		return selected_repos


	def _filter_auto(self, repos):
		selected = []
		for repo in repos:
			if repo.auto_sync in ['yes', 'true']:
				selected.append(repo)
		return selected


	def _sync(self, selected_repos):
		if not selected_repos:
			print("_sync(), nothing to sync... returning")
			return [('None', os.EX_OK)]
		# Portage needs to ensure a sane umask for the files it creates.
		os.umask(0o22)
		portage._sync_mode = True

		sync_manager = get_syncer(self.emerge_config.target_config.settings, emergelog)
		retvals = []
		for repo in selected_repos:
			print("syncing repo:", repo.name)
			if repo.sync_type is not None:
				returncode = sync_manager.sync(self.emerge_config, repo)
				#if returncode != os.EX_OK:
				retvals.append((repo.name, returncode))

		# Reload the whole config.
		portage._sync_mode = False
		self._reload_config()
		self._do_pkg_moves()
		self._check_updates()
		display_news_notification(self.emerge_config.target_config,
			self.emerge_config.opts)
		if retvals:
			return retvals
		return [('None', os.EX_OK)]


	def _do_pkg_moves(self):
		if self.emerge_config.opts.get('--package-moves') != 'n' and \
			_global_updates(self.emerge_config.trees,
			self.emerge_config.target_config.mtimedb["updates"],
			quiet=("--quiet" in self.emerge_config.opts)):
			self.emerge_config.target_config.mtimedb.commit()
			# Reload the whole config.
			self._reload_config()


	def _check_updates(self):
		mybestpv = self.emerge_config.target_config.trees['porttree'].dbapi.xmatch(
			"bestmatch-visible", portage.const.PORTAGE_PACKAGE_ATOM)
		mypvs = portage.best(
			self.emerge_config.target_config.trees['vartree'].dbapi.match(
				portage.const.PORTAGE_PACKAGE_ATOM))

		chk_updated_cfg_files(self.emerge_config.target_config.root,
			portage.util.shlex_split(
				self.emerge_config.target_config.settings.get("CONFIG_PROTECT", "")))

		if mybestpv != mypvs and "--quiet" not in self.emerge_config.opts:
			print()
			print(warn(" * ")+bold("An update to portage is available.")+" It is _highly_ recommended")
			print(warn(" * ")+"that you update portage now, before any other packages are updated.")
			print()
			print(warn(" * ")+"To update portage, run 'emerge --oneshot portage' now.")
			print()


	def _reload_config(self):
		'''Reload the whole config from scratch.'''
		load_emerge_config(emerge_config=self.emerge_config)
		adjust_configs(self.emerge_config.opts, self.emerge_config.trees)


	def rmessage(self, rvals, action):
		'''Creates emaint style messages to return to the task handler'''
		messages = []
		for rval in rvals:
			messages.append("Action: %s for repo: %s, returned code = %s"
				% (action, rval[0], rval[1]))
		return messages
