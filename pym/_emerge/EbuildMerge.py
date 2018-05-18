# Copyright 1999-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import functools

from _emerge.CompositeTask import CompositeTask
from portage import os
from portage.dbapi._MergeProcess import MergeProcess
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture

class EbuildMerge(CompositeTask):

	__slots__ = ("exit_hook", "find_blockers", "logger", "ldpath_mtimes",
		"pkg", "pkg_count", "pkg_path", "postinst_failure", "pretend",
		"settings", "tree", "world_atom")

	def _start(self):
		root_config = self.pkg.root_config
		settings = self.settings
		mycat = settings["CATEGORY"]
		mypkg = settings["PF"]
		pkgloc = settings["D"]
		infloc = os.path.join(settings["PORTAGE_BUILDDIR"], "build-info")
		myebuild = settings["EBUILD"]
		mydbapi = root_config.trees[self.tree].dbapi
		vartree = root_config.trees["vartree"]
		background = (settings.get('PORTAGE_BACKGROUND') == '1')
		logfile = settings.get('PORTAGE_LOG_FILE')

		merge_task = MergeProcess(
			mycat=mycat, mypkg=mypkg, settings=settings,
			treetype=self.tree, vartree=vartree, scheduler=self.scheduler,
			background=background, blockers=self.find_blockers, pkgloc=pkgloc,
			infloc=infloc, myebuild=myebuild, mydbapi=mydbapi,
			prev_mtimes=self.ldpath_mtimes, logfile=logfile)

		self._start_task(merge_task, self._merge_exit)

	def _merge_exit(self, merge_task):
		if self._final_exit(merge_task) != os.EX_OK:
			self._start_exit_hook(self.returncode)
			return

		self.postinst_failure = merge_task.postinst_failure
		pkg = self.pkg
		self.world_atom(pkg)
		pkg_count = self.pkg_count
		pkg_path = self.pkg_path
		logger = self.logger
		if "noclean" not in self.settings.features:
			short_msg = "emerge: (%s of %s) %s Clean Post" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			logger.log((" === (%s of %s) " + \
				"Post-Build Cleaning (%s::%s)") % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path),
				short_msg=short_msg)
		logger.log(" ::: completed emerge (%s of %s) %s to %s" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg.root))

		self._start_exit_hook(self.returncode)

	def _start_exit_hook(self, returncode):
		"""
		Start the exit hook, and set returncode after it completes.
		"""
		# The returncode will be set after exit hook is complete.
		self.returncode = None
		self._start_task(
			AsyncTaskFuture(future=self.exit_hook(self)),
			functools.partial(self._exit_hook_exit, returncode))

	def _exit_hook_exit(self, returncode, task):
		self._assert_current(task)
		self.returncode = returncode
		self._async_wait()
