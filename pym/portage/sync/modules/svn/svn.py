# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import errno

import portage
from portage import os
from portage.util import writemsg_level
from portage.sync.syncbase import SyncBase


class SVNSync(SyncBase):
	'''SVN sync module'''

	short_desc = "Perform sync operations on SVN repositories"

	@staticmethod
	def name():
		return "SVNSync"


	def __init__(self):
		SyncBase.__init__(self, "svn", "dev-vcs/subversion")


	def new(self, **kwargs):
		if kwargs:
			self._kwargs(kwargs)
		#initial checkout
		msg = ">>> Starting initial svn checkout with %s..." % self.repo.sync_uri
		self.logger(self.xterm_titles, msg)
		writemsg_level(msg + "\n")
		try:
			os.rmdir(self.repo.location)
		except OSError as e:
			if e.errno != errno.ENOENT:
				msg = "!!! existing '%s' directory; exiting." % self.repo.location
				self.logger(self.xterm_titles, msg)
				writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
				return (1, False)
			del e
		svn_root = self.repo.sync_uri
		exitcode =  portage.process.spawn_bash(
			"cd %s; exec svn %s" %
			(portage._shell_quote(os.path.dirname(self.repo.location)),
			portage._shell_quote(svn_root)),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! svn checkout error; exiting."
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
		return (exitcode, False)


	def _sync(self):
		"""
		Internal function to sync an existing SVN repository

		@return: tuple of return code (0=success), whether the cache
			needs to be updated
		@rtype: (int, bool)
		"""

		svn_root = self.repo.sync_uri

		if svn_root.startswith("svn://"):
			svn_root = svn_root[6:]
			#svn update
			msg = ">>> Starting svn update with %s..." % self.repo.sync_uri
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n")
			exitcode = portage.process.spawn_bash(
				"cd %s; exec svn update" % \
				(portage._shell_quote(self.repo.location),),
				**portage._native_kwargs(self.spawn_kwargs))
			if exitcode != os.EX_OK:
				msg = "!!! svn update error; exiting."
				self.logger(self.xterm_titles, msg)
				writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
		return (exitcode, False)
