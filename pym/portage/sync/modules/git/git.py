# Copyright 2005-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging

import portage
from portage import os
from portage.util import writemsg_level
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from .timestamps import git_sync_timestamps


class GitSync(object):
	'''Git sync class'''

	short_desc = "Perform sync operations on git based repositories"

	@staticmethod
	def name():
		return "GitSync"


	def can_progressbar(self, func):
		return False


	def __init__(self):
		self.settings = None
		self.has_git = True
		if portage.process.find_binary("git") is None:
			msg = ["Command not found: git",
			"Type \"emerge %s\" to enable git support." % portage.const.GIT_PACKAGE_ATOM]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			self.has_git = False


	def sync(self, **kwargs):
		''' Update existing git repository, and ignore the syncuri. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		git directly.
		'''
		if kwargs:
			options = kwargs.get('options', {})
			emerge_config = options.get('emerge_config', None)
			logger = options.get('logger', None)
			repo = options.get('repo', None)
			portdb = options.get('portdb', None)
			spawn_kwargs = options.get('spawn_kwargs', None)
			xterm_titles = options.get('xterm_titles', False)

		if not self.has_git:
			return repo.location, 1, False

		msg = ">>> Starting git pull in %s..." % repo.location
		logger(xterm_titles, msg )
		writemsg_level(msg + "\n")
		exitcode = portage.process.spawn_bash("cd %s ; git pull" % \
			(portage._shell_quote(repo.location),),
			**portage._native_kwargs(spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s." % repo.location
			logger(xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return exitcode
		msg = ">>> Git pull in %s successful" % repo.location
		logger(xterm_titles, msg)
		writemsg_level(msg + "\n")
		return self.post_sync(portdb, repo.location, emerge_config)


	def post_sync(self, portdb, location, emerge_config):
		'''repo.sync_type == "git":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		'''
		# avoid circular import for now
		from _emerge.actions import load_emerge_config, adjust_configs
		# Reload the whole config from scratch.
		settings, trees, mtimedb = load_emerge_config(emerge_config=emerge_config)
		adjust_configs(emerge_config.opts, emerge_config.trees)
		portdb = trees[settings['EROOT']]['porttree'].dbapi
		updatecache_flg = False
		exitcode = git_sync_timestamps(portdb, location)
		if exitcode == os.EX_OK:
			updatecache_flg = True
		return (exitcode, updatecache_flg)

