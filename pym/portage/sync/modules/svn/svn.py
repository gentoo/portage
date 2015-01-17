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


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		return os.path.exists(os.path.join(self.repo.location, '.svn'))


	def new(self, **kwargs):
		if kwargs:
			self._kwargs(kwargs)
		#initial checkout
		svn_root = self.repo.sync_uri
		exitcode = portage.process.spawn_bash(
			"cd %s; exec svn co %s ." %
			(portage._shell_quote(self.repo.location),
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

		exitcode, d = self._svn_upgrade()
		if exitcode != os.EX_OK:
			return (exitcode, False)

		#svn update
		exitcode = portage.process.spawn_bash(
			"cd %s; exec svn update" % \
			(portage._shell_quote(self.repo.location),),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! svn update error; exiting."
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
		return (exitcode, False)


	def _svn_upgrade(self):
		"""
		Internal function which performs an svn upgrade on the repo

		@return: tuple of return code (0=success), whether the cache
			needs to be updated
		@rtype: (int, bool)
		"""
		exitcode = portage.process.spawn_bash(
			"cd %s; exec svn upgrade" %
			(portage._shell_quote(self.repo.location),),
			**portage._native_kwargs(self.spawn_kwargs))
		if exitcode != os.EX_OK:
			msg = "!!! svn upgrade error; exiting."
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
		return (exitcode, False)
