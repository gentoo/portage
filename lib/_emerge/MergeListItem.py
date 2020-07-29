# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.dep import _repo_separator
from portage.output import colorize

from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.Binpkg import Binpkg
from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildBuild import EbuildBuild
from _emerge.PackageUninstall import PackageUninstall

class MergeListItem(CompositeTask):

	"""
	TODO: For parallel scheduling, everything here needs asynchronous
	execution support (start, poll, and wait methods).
	"""

	__slots__ = ("args_set",
		"binpkg_opts", "build_opts", "config_pool", "emerge_opts",
		"find_blockers", "logger", "mtimedb", "pkg",
		"pkg_count", "pkg_to_replace", "prefetcher",
		"settings", "statusMessage", "world_atom") + \
		("_install_task",)

	def _start(self):

		pkg = self.pkg
		build_opts = self.build_opts

		if pkg.installed:
			# uninstall,  executed by self.merge()
			self.returncode = os.EX_OK
			self._async_wait()
			return

		args_set = self.args_set
		find_blockers = self.find_blockers
		logger = self.logger
		mtimedb = self.mtimedb
		pkg_count = self.pkg_count
		scheduler = self.scheduler
		settings = self.settings
		world_atom = self.world_atom
		ldpath_mtimes = mtimedb["ldpath"]

		action_desc = "Emerging"
		preposition = "for"
		pkg_color = "PKG_MERGE"
		if pkg.type_name == "binary":
			pkg_color = "PKG_BINARY_MERGE"
			action_desc += " binary"

		if build_opts.fetchonly:
			action_desc = "Fetching"

		msg = "%s (%s of %s) %s" % \
			(action_desc,
			colorize("MERGE_LIST_PROGRESS", str(pkg_count.curval)),
			colorize("MERGE_LIST_PROGRESS", str(pkg_count.maxval)),
			colorize(pkg_color, pkg.cpv + _repo_separator + pkg.repo))

		if pkg.root_config.settings["ROOT"] != "/":
			msg += " %s %s" % (preposition, pkg.root)

		if not build_opts.pretend:
			self.statusMessage(msg)
			logger.log(" >>> emerge (%s of %s) %s to %s" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg.root))

		if pkg.type_name == "ebuild":

			build = EbuildBuild(args_set=args_set,
				background=self.background,
				config_pool=self.config_pool,
				find_blockers=find_blockers,
				ldpath_mtimes=ldpath_mtimes, logger=logger,
				opts=build_opts, pkg=pkg, pkg_count=pkg_count,
				prefetcher=self.prefetcher, scheduler=scheduler,
				settings=settings, world_atom=world_atom)

			self._install_task = build
			self._start_task(build, self._default_final_exit)
			return

		if pkg.type_name == "binary":

			binpkg = Binpkg(background=self.background,
				find_blockers=find_blockers,
				ldpath_mtimes=ldpath_mtimes, logger=logger,
				opts=self.binpkg_opts, pkg=pkg, pkg_count=pkg_count,
				prefetcher=self.prefetcher, settings=settings,
				scheduler=scheduler, world_atom=world_atom)

			self._install_task = binpkg
			self._start_task(binpkg, self._default_final_exit)
			return

	def create_install_task(self):

		pkg = self.pkg
		build_opts = self.build_opts
		mtimedb = self.mtimedb
		scheduler = self.scheduler
		settings = self.settings
		world_atom = self.world_atom
		ldpath_mtimes = mtimedb["ldpath"]

		if pkg.installed:
			if not (build_opts.buildpkgonly or \
				build_opts.fetchonly or build_opts.pretend):

				task = PackageUninstall(background=self.background,
					ldpath_mtimes=ldpath_mtimes, opts=self.emerge_opts,
					pkg=pkg, scheduler=scheduler, settings=settings,
					world_atom=world_atom)

			else:
				task = AsynchronousTask()

		elif build_opts.fetchonly or \
			build_opts.buildpkgonly:
			task = AsynchronousTask()
		else:
			task = self._install_task.create_install_task()

		return task
