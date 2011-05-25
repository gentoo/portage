# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import portage
from portage import os
from portage.dbapi._MergeProcess import MergeProcess
from portage.exception import UnsupportedAPIException
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.emergelog import emergelog
from _emerge.CompositeTask import CompositeTask
from _emerge.unmerge import _unmerge_display

class PackageUninstall(CompositeTask):
	"""
	Uninstall a package asynchronously in a subprocess. When
	both parallel-install and ebuild-locks FEATURES are enabled,
	it is essential for the ebuild-locks code to execute in a
	subprocess, since the portage.locks module does not behave
	as desired if we try to lock the same file multiple times
	concurrently from the same process for ebuild-locks phases
	such as pkg_setup, pkg_prerm, and pkg_postrm.
	"""

	__slots__ = ("world_atom", "ldpath_mtimes", "opts",
			"pkg", "settings", "_builddir_lock")

	def _start(self):

		vardb = self.pkg.root_config.trees["vartree"].dbapi
		dbdir = vardb.getpath(self.pkg.cpv)
		if not os.path.exists(dbdir):
			# Apparently the package got uninstalled
			# already, so we can safely return early.
			self.returncode = os.EX_OK
			self.wait()
			return

		self.settings.setcpv(self.pkg)
		cat, pf = portage.catsplit(self.pkg.cpv)
		myebuildpath = os.path.join(dbdir, pf + ".ebuild")

		try:
			portage.doebuild_environment(myebuildpath, "prerm",
				settings=self.settings, db=vardb)
		except UnsupportedAPIException:
			# This is safe to ignore since this function is
			# guaranteed to set PORTAGE_BUILDDIR even though
			# it raises UnsupportedAPIException. The error
			# will be logged when it prevents the pkg_prerm
			# and pkg_postrm phases from executing.
			pass

		self._builddir_lock = EbuildBuildDir(
			scheduler=self.scheduler, settings=self.settings)
		self._builddir_lock.lock()

		portage.prepare_build_dirs(
			settings=self.settings, cleanup=True)

		# Output only gets logged if it comes after prepare_build_dirs()
		# which initializes PORTAGE_LOG_FILE.
		retval, pkgmap = _unmerge_display(self.pkg.root_config,
			self.opts, "unmerge", [self.pkg.cpv], clean_delay=0,
			writemsg_level=self._writemsg_level)

		if retval != os.EX_OK:
			self._builddir_lock.unlock()
			self.returncode = retval
			self.wait()
			return

		self._writemsg_level(">>> Unmerging %s...\n" % (self.pkg.cpv,),
			noiselevel=-1)
		self._emergelog("=== Unmerging... (%s)" % (self.pkg.cpv,))

		unmerge_task = MergeProcess(
			mycat=cat, mypkg=pf, settings=self.settings,
			treetype="vartree", vartree=self.pkg.root_config.trees["vartree"],
			scheduler=self.scheduler, background=self.background,
			mydbapi=self.pkg.root_config.trees["vartree"].dbapi,
			prev_mtimes=self.ldpath_mtimes,
			logfile=self.settings.get("PORTAGE_LOG_FILE"), unmerge=True)

		self._start_task(unmerge_task, self._unmerge_exit)

	def _unmerge_exit(self, unmerge_task):
		if self._final_exit(unmerge_task) != os.EX_OK:
			self._emergelog(" !!! unmerge FAILURE: %s" % (self.pkg.cpv,))
		else:
			self._emergelog(" >>> unmerge success: %s" % (self.pkg.cpv,))
			self.world_atom(self.pkg)
		self._builddir_lock.unlock()
		self.wait()

	def _emergelog(self, msg):
		emergelog("notitles" not in self.settings.features, msg)

	def _writemsg_level(self, msg, level=0, noiselevel=0):

		log_path = self.settings.get("PORTAGE_LOG_FILE")
		background = self.background

		if log_path is None:
			if not (background and level < logging.WARNING):
				portage.util.writemsg_level(msg,
					level=level, noiselevel=noiselevel)
		else:
			self.scheduler.output(msg, log_path=log_path,
				level=level, noiselevel=noiselevel)
