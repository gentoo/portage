# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import errno

import portage
from portage import os
from portage.util import writemsg_level
from portage.sync.syncbase import SyncBase


class CVSSync(SyncBase):
	'''CVS sync module'''

	short_desc = "Perform sync operations on CVS repositories"

	@staticmethod
	def name():
		return "CVSSync"


	def __init__(self):
		SyncBase.__init__(self, "cvs", portage.const.CVS_PACKAGE_ATOM)


	def new(self, **kwargs):
		if kwargs:
			self._kwargs(kwargs)
		#initial checkout
		msg = ">>> Starting initial cvs checkout with %s..." % self.repo.sync_uri
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
		cvs_root = self.repo.sync_uri
		if portage.process.spawn_bash(
			"cd %s; exec cvs -z0 -d %s co -P -d %s %s" %
			(portage._shell_quote(os.path.dirname(self.repo.location)), portage._shell_quote(cvs_root),
				portage._shell_quote(os.path.basename(self.repo.location)),
				portage._shell_quote(self.repo.sync_cvs_repo)),
				**portage._native_kwargs(self.spawn_kwargs)) != os.EX_OK:
			msg = "!!! cvs checkout error; exiting."
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
			return (1, False)
		return (0, False)


	def _sync(self):
		"""
		Internal function to sync an existing CVS repository

		@return: tuple of return code (0=success), whether the cache
			needs to be updated
		@rtype: (int, bool)
		"""

		cvs_root = self.repo.sync_uri

		if cvs_root.startswith("cvs://"):
			cvs_root = cvs_root[6:]
			#cvs update
			msg = ">>> Starting cvs update with %s..." % self.repo.sync_uri
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n")
			exitcode = portage.process.spawn_bash(
				"cd %s; exec cvs -z0 -q update -dP" % \
				(portage._shell_quote(self.repo.location),),
				**portage._native_kwargs(self.spawn_kwargs))
			if exitcode != os.EX_OK:
				msg = "!!! cvs update error; exiting."
				self.logger(self.xterm_titles, msg)
				writemsg_level(msg + "\n", noiselevel=-1, level=logging.ERROR)
		return (exitcode, False)
