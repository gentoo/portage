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
from portage.sync.syncbase import SyncBase


class GitSync(SyncBase):
	'''Git sync class'''

	short_desc = "Perform sync operations on git based repositories"

	@staticmethod
	def name():
		return "GitSync"


	def __init__(self):
		SyncBase.__init__(self, "git", portage.const.GIT_PACKAGE_ATOM)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		if kwargs:
			self._kwargs(kwargs)
		elif not self.repo:
			return False

		if not os.path.exists(self.repo.location):
			return False
		exitcode = portage.process.spawn_bash("cd %s ; git rev-parse" %\
			(portage._shell_quote(self.repo.location),),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode == 128:
			return False
		return True


	def new(self, **kwargs):
		'''Do the initial clone of the repository'''
		if kwargs:
			self._kwargs(kwargs)
		emerge_config = self.options.get('emerge_config', None)
		portdb = self.options.get('portdb', None)
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(self.xterm_titles,
					'Created new directory %s' % self.repo.location)
		except IOError:
			return (1, False)
		msg = ">>> Cloning git repository from upstream into %s..." % self.repo.location
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		sync_uri = self.repo.sync_uri
		if sync_uri.startswith("file://"):
			sync_uri = sync_uri[6:]
		exitcode = portage.process.spawn_bash("cd %s ; %s clone %s ." % \
			(portage._shell_quote(self.repo.location),
			self.bin_command,
			portage._shell_quote(sync_uri)),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! git clone error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		msg = ">>> Git clone successful"
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		return (os.EX_OK, True)


	def _sync(self):
		''' Update existing git repository, and ignore the syncuri. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		git directly.
		'''
		# No kwargs call here; this is internal, so it should have been
		# called by something which set the internal variables
		emerge_config = self.options.get('emerge_config', None)
		portdb = self.options.get('portdb', None)

		msg = ">>> Starting git pull in %s..." % self.repo.location
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		exitcode = portage.process.spawn_bash("cd %s ; git pull" % \
			(portage._shell_quote(self.repo.location),),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		msg = ">>> Git pull successful: %s" % self.repo.location
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		return (os.EX_OK, True)
