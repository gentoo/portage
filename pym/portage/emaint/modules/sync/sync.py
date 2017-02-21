# Copyright 2014-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import os
import sys

import portage
portage._internal_caller = True
portage._sync_mode = True
from portage.localization import _
from portage.output import bold, red, create_color_func
from portage._global_updates import _global_updates
from portage.sync.controller import SyncManager
from portage.util import writemsg_level
from portage.util.digraph import digraph
from portage.util._async.AsyncScheduler import AsyncScheduler
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util._eventloop.EventLoop import EventLoop

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
		if emerge_config is None:
			# need a basic options instance
			actions, opts, _files = parse_opts([], silent=True)
			emerge_config = load_emerge_config(
				action='sync', args=_files, opts=opts)

			# Parse EMERGE_DEFAULT_OPTS, for settings like
			# --package-moves=n.
			cmdline = portage.util.shlex_split(
				emerge_config.target_config.settings.get(
				"EMERGE_DEFAULT_OPTS", ""))
			emerge_config.opts = parse_opts(cmdline, silent=True)[1]

			if hasattr(portage, 'settings'):
				# cleanly destroy global objects
				portage._reset_legacy_globals()
				# update redundant global variables, for consistency
				# and in order to conserve memory
				portage.settings = emerge_config.target_config.settings
				portage.db = emerge_config.trees
				portage.root = portage.db._target_eroot

		self.emerge_config = emerge_config
		if emerge_logging:
			_emerge.emergelog._disable = False
		self.xterm_titles = "notitles" not in \
			self.emerge_config.target_config.settings.features
		emergelog(self.xterm_titles, " === sync")


	def auto_sync(self, **kwargs):
		'''Sync auto-sync enabled repos'''
		options = kwargs.get('options', None)
		if options:
			return_messages = options.get('return-messages', False)
		else:
			return_messages = False
		success, selected, msgs = self._get_repos(True)
		if not success:
			if return_messages:
				msgs.append(red(" * ") + \
					"Errors were encountered while getting repos... returning")
				return (False, msgs)
			return (False, None)
		if not selected:
			if return_messages:
				msgs.append("Nothing to sync... returning")
				return (True, msgs)
			return (True, None)
		return self._sync(selected, return_messages, emaint_opts=options)


	def all_repos(self, **kwargs):
		'''Sync all repos defined in repos.conf'''
		options = kwargs.get('options', None)
		if options:
			return_messages = options.get('return-messages', False)
		else:
			return_messages = False
		success, selected, msgs = self._get_repos(auto_sync_only=False)
		if not success:
			if return_messages:
				msgs.append(red(" * ") + \
					"Errors were encountered while getting repos... returning")
				return (False, msgs)
			return (False, None)
		if not selected:
			if return_messages:
				msgs.append("Nothing to sync... returning")
				return (True, msgs)
			return (True, None)
		return self._sync(selected, return_messages, emaint_opts=options)


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
		success, available, msgs = self._get_repos(auto_sync_only=False)
		# Ignore errors from _get_repos(), we only want to know if the repo
		# exists.
		selected = self._match_repos(repos, available)
		if not selected:
			msgs.append(red(" * ") + "The specified repos are invalid or missing: %s" %
				(bold(", ".join(repos))) + "\n   ...returning")
			if return_messages:
				return (False, msgs)
			return (False, None)
		return self._sync(selected, return_messages, emaint_opts=options)


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
		msgs = []
		emerge_repos = []
		selected_repos = []
		if self.emerge_config.args:
			unknown_repo_names = []
			for repo_name in self.emerge_config.args:
				#print("_get_repos(): repo_name =", repo_name)
				try:
					repo = self.emerge_config.target_config.settings.repositories[repo_name]
				except KeyError:
					unknown_repo_names.append(repo_name)
				else:
					emerge_repos.append(repo)
			if unknown_repo_names:
				msgs.append(warn(" * ") + "Unknown repo(s): %s\n" %
					" ".join(unknown_repo_names));
				return (False, emerge_repos, msgs)
			selected_repos = emerge_repos
		else:
			selected_repos.extend(self.emerge_config.target_config.settings.repositories)

		valid_repos = []
		missing_sync_type = []
		for repo in selected_repos:
			if repo.sync_type is None:
				missing_sync_type.append(repo.name)
			else:
				valid_repos.append(repo)
		if missing_sync_type:
			msgs.append(warn(" * ") + "Missing sync-type for repo(s): %s" %
				" ".join(missing_sync_type) + "\n")
			return (False, valid_repos, msgs)

		if auto_sync_only:
			selected_repos = self._filter_auto(selected_repos)
		#print("_get_repos(), selected =", selected_repos)
		if emerge_repos:
			skipped_repos = set(emerge_repos) - set(selected_repos)
			if skipped_repos:
				msgs.append(warn(" * ") + "auto-sync is disabled for repo(s): %s" %
					" ".join(repo.name for repo in skipped_repos) + "\n")
				return (False, selected_repos, msgs)
		return (True, selected_repos, msgs)


	def _filter_auto(self, repos):
		selected = []
		for repo in repos:
			if repo.auto_sync in ['yes', 'true']:
				selected.append(repo)
		return selected


	def _sync(self, selected_repos, return_messages,
		emaint_opts=None):

		if emaint_opts is not None:
			for k, v in emaint_opts.items():
				if v is not None:
					k = "--" + k.replace("_", "-")
					self.emerge_config.opts[k] = v

		msgs = []
		# Portage needs to ensure a sane umask for the files it creates.
		os.umask(0o22)

		sync_manager = SyncManager(
			self.emerge_config.target_config.settings, emergelog)

		max_jobs = (self.emerge_config.opts.get('--jobs', 1)
			if 'parallel-fetch' in self.emerge_config.
			target_config.settings.features else 1)
		sync_scheduler = SyncScheduler(emerge_config=self.emerge_config,
			selected_repos=selected_repos, sync_manager=sync_manager,
			max_jobs=max_jobs,
			event_loop=global_event_loop() if portage._internal_caller else
				EventLoop(main=False))

		sync_scheduler.start()
		sync_scheduler.wait()
		retvals = sync_scheduler.retvals
		msgs.extend(sync_scheduler.msgs)
		returncode = True

		if retvals:
			msgs.extend(self.rmessage(retvals, 'sync'))
			for repo, retval in retvals:
				if retval != os.EX_OK:
					returncode = False
					break
		else:
			msgs.extend(self.rmessage([('None', os.EX_OK)], 'sync'))

		# run the post_sync_hook one last time for
		# run only at sync completion hooks
		if sync_scheduler.global_hooks_enabled:
			rcode = sync_manager.perform_post_sync_hook('')
			if rcode:
				msgs.extend(self.rmessage([('None', rcode)], 'post-sync'))
				if rcode != os.EX_OK:
					returncode = False

		# Reload the whole config.
		portage._sync_mode = False
		self._reload_config()
		self._do_pkg_moves()
		msgs.extend(self._check_updates())
		display_news_notification(self.emerge_config.target_config,
			self.emerge_config.opts)

		if return_messages:
			return (returncode, msgs)
		return (returncode, None)


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

		msgs = []
		if mybestpv != mypvs and "--quiet" not in self.emerge_config.opts:
			msgs.append('')
			msgs.append(warn(" * ")+bold("An update to portage is available.")+" It is _highly_ recommended")
			msgs.append(warn(" * ")+"that you update portage now, before any other packages are updated.")
			msgs.append('')
			msgs.append(warn(" * ")+"To update portage, run 'emerge --oneshot portage' now.")
			msgs.append('')
		return msgs


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


class SyncScheduler(AsyncScheduler):
	'''
	Sync repos in parallel, but don't sync a given repo until all
	of its masters have synced.
	'''
	def __init__(self, **kwargs):
		'''
		@param emerge_config: an emerge_config instance
		@param selected_repos: list of RepoConfig instances
		@param sync_manager: a SyncManger instance
		'''
		self._emerge_config = kwargs.pop('emerge_config')
		self._selected_repos = kwargs.pop('selected_repos')
		self._sync_manager = kwargs.pop('sync_manager')
		AsyncScheduler.__init__(self, **kwargs)
		self._init_graph()
		self.retvals = []
		self.msgs = []

	def _init_graph(self):
		'''
		Graph relationships between repos and their masters.
		'''
		self._sync_graph = digraph()
		self._leaf_nodes = []
		self._repo_map = {}
		self._running_repos = set()
		selected_repo_names = frozenset(repo.name
			for repo in self._selected_repos)
		for repo in self._selected_repos:
			self._repo_map[repo.name] = repo
			self._sync_graph.add(repo.name, None)
			for master in repo.masters:
				if master.name in selected_repo_names:
					self._repo_map[master.name] = master
					self._sync_graph.add(master.name, repo.name)
		self._complete_graph = self._sync_graph.copy()
		self._hooks_repos = set()
		self._update_leaf_nodes()

	def _task_exit(self, task):
		'''
		Remove the task from the graph, in order to expose
		more leaf nodes.
		'''
		self._running_tasks.discard(task)
		# Set hooks_enabled = True by default, in order to ensure
		# that hooks will be called in a backward-compatible manner
		# even if all sync tasks have failed.
		hooks_enabled = True
		returncode = task.returncode
		if task.returncode == os.EX_OK:
			returncode, message, updatecache_flg, hooks_enabled = task.result
			if message:
				self.msgs.append(message)
		repo = task.kwargs['repo'].name
		self._running_repos.remove(repo)
		self.retvals.append((repo, returncode))
		self._sync_graph.remove(repo)
		self._update_leaf_nodes()
		if hooks_enabled:
			self._hooks_repos.add(repo)
		super(SyncScheduler, self)._task_exit(self)

	def _master_hooks(self, repo_name):
		"""
		@param repo_name: a repo name
		@type repo_name: str
		@return: True if hooks would have been executed for any master
			repositories of the given repo, False otherwise
		@rtype: bool
		"""
		traversed_nodes = set()
		node_stack = [repo_name]
		while node_stack:
			node = node_stack.pop()
			if node in self._hooks_repos:
				return True
			if node not in traversed_nodes:
				traversed_nodes.add(node)
				node_stack.extend(self._complete_graph.child_nodes(node))
		return False

	@property
	def global_hooks_enabled(self):
		"""
		@return: True if repo.postsync.d hooks would have been executed
			for any repositories.
		@rtype: bool
		"""
		return bool(self._hooks_repos)

	def _update_leaf_nodes(self):
		'''
		Populate self._leaf_nodes with current leaves from
		self._sync_graph. If a circular master relationship
		is discovered, choose a random node to break the cycle.
		'''
		if self._sync_graph and not self._leaf_nodes:
			self._leaf_nodes = [obj for obj in
				self._sync_graph.leaf_nodes()
				if obj not in self._running_repos]

			if not (self._leaf_nodes or self._running_repos):
				# If there is a circular master relationship,
				# choose a random node to break the cycle.
				self._leaf_nodes = [next(iter(self._sync_graph))]

	def _next_task(self):
		'''
		Return a task for the next available leaf node.
		'''
		if not self._sync_graph:
			raise StopIteration()
		# If self._sync_graph is non-empty, then self._leaf_nodes
		# is guaranteed to be non-empty, since otherwise
		# _can_add_job would have returned False and prevented
		# _next_task from being immediately called.
		node = self._leaf_nodes.pop()
		self._running_repos.add(node)
		self._update_leaf_nodes()

		return self._sync_manager.sync_async(
			emerge_config=self._emerge_config,
			repo=self._repo_map[node],
			master_hooks=self._master_hooks(node))

	def _can_add_job(self):
		'''
		Returns False if there are no leaf nodes available.
		'''
		if not AsyncScheduler._can_add_job(self):
			return False
		return bool(self._leaf_nodes) and not self._terminated.is_set()

	def _keep_scheduling(self):
		'''
		Schedule as long as the graph is non-empty, and we haven't
		been terminated.
		'''
		return bool(self._sync_graph) and not self._terminated.is_set()
