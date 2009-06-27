# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SpawnProcess import SpawnProcess
# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage
class EbuildProcess(SpawnProcess):

	__slots__ = ("phase", "pkg", "settings", "tree")

	def _start(self):
		# Don't open the log file during the clean phase since the
		# open file can result in an nfs lock on $T/build.log which
		# prevents the clean phase from removing $T.
		if self.phase not in ("clean", "cleanrm"):
			self.logfile = self.settings.get("PORTAGE_LOG_FILE")
		SpawnProcess._start(self)

	def _pipe(self, fd_pipes):
		stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			portage._create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

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
		SpawnProcess._set_returncode(self, wait_retval)

		if self.phase not in ("clean", "cleanrm"):
			self.returncode = portage._doebuild_exit_status_check_and_log(
				self.settings, self.phase, self.returncode)

		if self.phase == "test" and self.returncode != os.EX_OK and \
			"test-fail-continue" in self.settings.features:
			self.returncode = os.EX_OK

		portage._post_phase_userpriv_perms(self.settings)

