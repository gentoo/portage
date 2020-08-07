# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
import logging
import grp
import pwd
import warnings

from collections import OrderedDict

import portage
from portage import os
from portage.progress import ProgressBar
#from portage.emaint.defaults import DEFAULT_OPTIONS
from portage.util import writemsg, writemsg_level
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.package.ebuild.doebuild import _check_temp_dir
from portage.metadata import action_metadata
from portage.util._async.AsyncFunction import AsyncFunction
from portage import _unicode_decode
from portage import util
from _emerge.CompositeTask import CompositeTask


class TaskHandler:
	"""Handles the running of the tasks it is given
	"""

	def __init__(self, show_progress_bar=True, verbose=True, callback=None):
		self.show_progress_bar = show_progress_bar
		self.verbose = verbose
		self.callback = callback
		self.isatty = os.environ.get('TERM') != 'dumb' and sys.stdout.isatty()
		self.progress_bar = ProgressBar(self.isatty, title="Portage-Sync", max_desc_length=27)


	def run_tasks(self, tasks, func, status=None, verbose=True, options=None):
		"""Runs the module tasks"""
		# Ensure we have a task and function
		assert tasks
		assert func
		for task in tasks:
			inst = task()
			show_progress = self.show_progress_bar and self.isatty
			# check if the function is capable of progressbar
			# and possibly override it off
			if show_progress and hasattr(inst, 'can_progressbar'):
				show_progress = inst.can_progressbar(func)
			if show_progress:
				self.progress_bar.reset()
				self.progress_bar.set_label(func + " " + inst.name())
				onProgress = self.progress_bar.start()
			else:
				onProgress = None
			kwargs = {
				'onProgress': onProgress,
				# pass in a copy of the options so a module can not pollute or change
				# them for other tasks if there is more to do.
				'options': options.copy()
				}
			result = getattr(inst, func)(**kwargs)
			if show_progress:
				# make sure the final progress is displayed
				self.progress_bar.display()
				print()
				self.progress_bar.stop()
			if self.callback:
				self.callback(result)


def print_results(results):
	if results:
		print()
		print("\n".join(results))
		print("\n")


class SyncManager:
	'''Main sync control module'''

	def __init__(self, settings, logger):
		self.settings = settings
		self.logger = logger
		# Similar to emerge, sync needs a default umask so that created
		# files have sane permissions.
		os.umask(0o22)

		self.module_controller = portage.sync.module_controller
		self.module_names = self.module_controller.module_names
		self.hooks = {}
		for _dir in ["repo.postsync.d", "postsync.d"]:
			postsync_dir = os.path.join(self.settings["PORTAGE_CONFIGROOT"],
				portage.USER_CONFIG_PATH, _dir)
			hooks = OrderedDict()
			for filepath in util._recursive_file_list(postsync_dir):
				name = filepath.split(postsync_dir)[1].lstrip(os.sep)
				if os.access(filepath, os.X_OK):
					hooks[filepath] = name
				else:
					writemsg_level(" %s %s hook: '%s' is not executable\n"
						% (warn("*"), _dir, _unicode_decode(name),),
						level=logging.WARN, noiselevel=2)
			self.hooks[_dir] = hooks

	def __getattr__(self, name):
		if name == 'async':
			warnings.warn("portage.sync.controller.SyncManager.async "
				"has been renamed to sync_async",
				DeprecationWarning, stacklevel=2)
			return self.sync_async
		raise AttributeError(name)

	def get_module_descriptions(self, mod):
		desc = self.module_controller.get_func_descriptions(mod)
		if desc:
			return desc
		return []

	def sync_async(self, emerge_config=None, repo=None, master_hooks=True):
		self.emerge_config = emerge_config
		self.settings, self.trees, self.mtimedb = emerge_config
		self.xterm_titles = "notitles" not in self.settings.features
		self.portdb = self.trees[self.settings['EROOT']]['porttree'].dbapi
		return SyncRepo(sync_task=AsyncFunction(target=self.sync,
			kwargs=dict(emerge_config=emerge_config, repo=repo,
			master_hooks=master_hooks)),
			sync_callback=self._sync_callback)

	def sync(self, emerge_config=None, repo=None, master_hooks=True):
		self.callback = None
		self.repo = repo
		self.exitcode = 1
		self.updatecache_flg = False
		hooks_enabled = master_hooks or not repo.sync_hooks_only_on_change
		if repo.sync_type in self.module_names:
			tasks = [self.module_controller.get_class(repo.sync_type)]
		else:
			msg = "\n%s: Sync module '%s' is not an installed/known type'\n" \
				% (bad("ERROR"), repo.sync_type)
			return self.exitcode, msg, self.updatecache_flg, hooks_enabled

		rval = self.pre_sync(repo)
		if rval != os.EX_OK:
			return rval, None, self.updatecache_flg, hooks_enabled

		# need to pass the kwargs dict to the modules
		# so they are available if needed.
		task_opts = {
			'emerge_config': emerge_config,
			'logger': self.logger,
			'portdb': self.portdb,
			'repo': repo,
			'settings': self.settings,
			'spawn_kwargs': self.spawn_kwargs,
			'usersync_uid': self.usersync_uid,
			'xterm_titles': self.xterm_titles,
			}
		func = 'sync'
		status = None
		taskmaster = TaskHandler(callback=self.do_callback)
		taskmaster.run_tasks(tasks, func, status, options=task_opts)

		if (master_hooks or self.updatecache_flg or
			not repo.sync_hooks_only_on_change):
			hooks_enabled = True
			self.perform_post_sync_hook(
				repo.name, repo.sync_uri, repo.location)

		return self.exitcode, None, self.updatecache_flg, hooks_enabled


	def do_callback(self, result):
		#print("result:", result, "callback()", self.callback)
		exitcode, updatecache_flg = result
		self.exitcode = exitcode
		self.updatecache_flg = updatecache_flg
		if exitcode == 0:
			msg = "=== Sync completed for %s" % self.repo.name
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n")
		if self.callback:
			self.callback(exitcode, updatecache_flg)


	def perform_post_sync_hook(self, reponame, dosyncuri='', repolocation=''):
		succeeded = os.EX_OK
		if reponame:
			_hooks = self.hooks["repo.postsync.d"]
		else:
			_hooks = self.hooks["postsync.d"]
		for filepath in _hooks:
			writemsg_level("Spawning post_sync hook: %s\n"
				% (_unicode_decode(_hooks[filepath])),
				level=logging.ERROR, noiselevel=4)
			if reponame:
				retval = portage.process.spawn(
					[filepath, reponame, dosyncuri, repolocation],
					env=self.settings.environ())
			else:
				retval = portage.process.spawn([filepath],
					env=self.settings.environ())
			if retval != os.EX_OK:
				writemsg_level(" %s Spawn failed for: %s, %s\n" % (bad("*"),
					_unicode_decode(_hooks[filepath]), filepath),
					level=logging.ERROR, noiselevel=-1)
				succeeded = retval
		return succeeded


	def pre_sync(self, repo):
		msg = ">>> Syncing repository '%s' into '%s'..." \
			% (repo.name, repo.location)
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		try:
			st = os.stat(repo.location)
		except OSError:
			st = None

		self.usersync_uid = None
		spawn_kwargs = {}
		# Redirect command stderr to stdout, in order to prevent
		# spurious cron job emails (bug 566132).
		spawn_kwargs["fd_pipes"] = {
			0: portage._get_stdin().fileno(),
			1: sys.__stdout__.fileno(),
			2: sys.__stdout__.fileno()
		}
		spawn_kwargs["env"] = self.settings.environ()
		if repo.sync_user is not None:
			def get_sync_user_data(sync_user):
				user = None
				group = None
				home = None
				logname = None

				spl = sync_user.split(':', 1)
				if spl[0]:
					username = spl[0]
					try:
						try:
							pw = pwd.getpwnam(username)
						except KeyError:
							pw = pwd.getpwuid(int(username))
					except (ValueError, KeyError):
						writemsg("!!! User '%s' invalid or does not exist\n"
								% username, noiselevel=-1)
						return (logname, user, group, home)
					user = pw.pw_uid
					group = pw.pw_gid
					home = pw.pw_dir
					logname = pw.pw_name

				if len(spl) > 1:
					groupname = spl[1]
					try:
						try:
							gp = grp.getgrnam(groupname)
						except KeyError:
							pw = grp.getgrgid(int(groupname))
					except (ValueError, KeyError):
						writemsg("!!! Group '%s' invalid or does not exist\n"
								% groupname, noiselevel=-1)
						return (logname, user, group, home)

					group = gp.gr_gid

				return (logname, user, group, home)

			# user or user:group
			(logname, uid, gid, home) = get_sync_user_data(
				repo.sync_user)
			if uid is not None:
				spawn_kwargs["uid"] = uid
				self.usersync_uid = uid
			if gid is not None:
				spawn_kwargs["gid"] = gid
				spawn_kwargs["groups"] = [gid]
			if home is not None:
				spawn_kwargs["env"]["HOME"] = home
			if logname is not None:
				spawn_kwargs["env"]["LOGNAME"] = logname

		if st is None:
			perms = {'mode': 0o755}
			# respect sync-user if set
			if 'umask' in spawn_kwargs:
				perms['mode'] &= ~spawn_kwargs['umask']
			if 'uid' in spawn_kwargs:
				perms['uid'] = spawn_kwargs['uid']
			if 'gid' in spawn_kwargs:
				perms['gid'] = spawn_kwargs['gid']

			portage.util.ensure_dirs(repo.location, **perms)
			st = os.stat(repo.location)

		if (repo.sync_user is None and
			'usersync' in self.settings.features and
			portage.data.secpass >= 2 and
			(st.st_uid != os.getuid() and st.st_mode & 0o700 or
			st.st_gid != os.getgid() and st.st_mode & 0o070)):
			try:
				pw = pwd.getpwuid(st.st_uid)
			except KeyError:
				pass
			else:
				# Drop privileges when syncing, in order to match
				# existing uid/gid settings.
				self.usersync_uid = st.st_uid
				spawn_kwargs["uid"]    = st.st_uid
				spawn_kwargs["gid"]    = st.st_gid
				spawn_kwargs["groups"] = [st.st_gid]
				spawn_kwargs["env"]["HOME"] = pw.pw_dir
				spawn_kwargs["env"]["LOGNAME"] = pw.pw_name
				umask = 0o002
				if not st.st_mode & 0o020:
					umask = umask | 0o020
				spawn_kwargs["umask"] = umask
		# override the defaults when sync_umask is set
		if repo.sync_umask is not None:
			spawn_kwargs["umask"] = int(repo.sync_umask, 8)
		spawn_kwargs.setdefault("umask", 0o022)
		self.spawn_kwargs = spawn_kwargs

		if self.usersync_uid is not None:
			# PORTAGE_TMPDIR is used below, so validate it and
			# bail out if necessary.
			rval = _check_temp_dir(self.settings)
			if rval != os.EX_OK:
				return rval

		os.umask(0o022)
		return os.EX_OK

	def _sync_callback(self, proc):
		"""
		This is called in the parent process, serially, for each of the
		sync jobs when they complete. Some cache backends such as sqlite
		may require that cache access be performed serially in the
		parent process like this.
		"""
		repo = proc.kwargs['repo']
		exitcode = proc.returncode
		updatecache_flg = False
		if proc.returncode == os.EX_OK:
			exitcode, message, updatecache_flg, hooks_enabled = proc.result

		if updatecache_flg and "metadata-transfer" not in self.settings.features:
			updatecache_flg = False

		if updatecache_flg and \
			os.path.exists(os.path.join(
			repo.location, 'metadata', 'md5-cache')):

			# Only update cache for repo.location since that's
			# the only one that's been synced here.
			action_metadata(self.settings, self.portdb, self.emerge_config.opts,
				porttrees=[repo.location])


class SyncRepo(CompositeTask):
	"""
	Encapsulates a sync operation and the callback which executes afterwards,
	so both can be considered as a single composite task. This is useful
	since we don't want to consider a particular repo's sync operation as
	complete until after the callback has executed (bug 562264).

	The kwargs and result properties expose attributes that are accessed
	by SyncScheduler.
	"""

	__slots__ = ('sync_task', 'sync_callback')

	@property
	def kwargs(self):
		return self.sync_task.kwargs

	@property
	def result(self):
		return self.sync_task.result

	def _start(self):
		self._start_task(self.sync_task, self._sync_task_exit)

	def _sync_task_exit(self, sync_task):
		self._current_task = None
		self.returncode = sync_task.returncode
		self.sync_callback(self.sync_task)
		self._async_wait()
