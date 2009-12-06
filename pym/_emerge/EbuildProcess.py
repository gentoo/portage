# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
from portage import os

class EbuildProcess(AbstractEbuildProcess):

	__slots__ = ('tree',)

	def _start(self):
		# Don't open the log file during the clean phase since the
		# open file can result in an nfs lock on $T/build.log which
		# prevents the clean phase from removing $T.
		if self.phase not in ("clean", "cleanrm"):
			self.logfile = self.settings.get("PORTAGE_LOG_FILE")
		AbstractEbuildProcess._start(self)

	def _spawn(self, args, **kwargs):

		root_config = self.pkg.root_config
		tree = self.tree
		mydbapi = root_config.trees[tree].dbapi
		settings = self.settings
		ebuild_path = settings["EBUILD"]
		debug = settings.get("PORTAGE_DEBUG") == "1"

		rval = portage.doebuild(ebuild_path, self.phase,
			root_config.root, settings, debug,
			mydbapi=mydbapi, tree=tree, **kwargs)

		return rval

	def _set_returncode(self, wait_retval):
		AbstractEbuildProcess._set_returncode(self, wait_retval)

		if self.phase not in ("clean", "cleanrm"):
			self.returncode = portage._doebuild_exit_status_check_and_log(
				self.settings, self.phase, self.returncode)

		if self.phase == "test" and self.returncode != os.EX_OK and \
			"test-fail-continue" in self.settings.features:
			self.returncode = os.EX_OK

		portage._post_phase_userpriv_perms(self.settings)

