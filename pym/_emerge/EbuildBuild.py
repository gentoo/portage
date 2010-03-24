# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildExecuter import EbuildExecuter
from _emerge.EbuildPhase import EbuildPhase
from _emerge.EbuildBinpkg import EbuildBinpkg
from _emerge.EbuildFetcher import EbuildFetcher
from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildMerge import EbuildMerge
from _emerge.EbuildFetchonly import EbuildFetchonly
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from portage.util import writemsg
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
import codecs
from portage.output import colorize
class EbuildBuild(CompositeTask):

	__slots__ = ("args_set", "config_pool", "find_blockers",
		"ldpath_mtimes", "logger", "opts", "pkg", "pkg_count",
		"prefetcher", "settings", "world_atom") + \
		("_build_dir", "_buildpkg", "_ebuild_path", "_issyspkg", "_tree")

	def _start(self):

		logger = self.logger
		opts = self.opts
		pkg = self.pkg
		settings = self.settings
		world_atom = self.world_atom
		root_config = pkg.root_config
		tree = "porttree"
		self._tree = tree
		portdb = root_config.trees[tree].dbapi
		settings.setcpv(pkg)
		settings.configdict["pkg"]["EMERGE_FROM"] = pkg.type_name
		ebuild_path = portdb.findname(pkg.cpv)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % pkg.cpv)
		self._ebuild_path = ebuild_path

		prefetcher = self.prefetcher
		if prefetcher is None:
			pass
		elif not prefetcher.isAlive():
			prefetcher.cancel()
		elif prefetcher.poll() is None:

			waiting_msg = "Fetching files " + \
				"in the background. " + \
				"To view fetch progress, run `tail -f " + \
				"/var/log/emerge-fetch.log` in another " + \
				"terminal."
			msg_prefix = colorize("GOOD", " * ")
			from textwrap import wrap
			waiting_msg = "".join("%s%s\n" % (msg_prefix, line) \
				for line in wrap(waiting_msg, 65))
			if not self.background:
				writemsg(waiting_msg, noiselevel=-1)

			self._current_task = prefetcher
			prefetcher.addExitListener(self._prefetch_exit)
			return

		self._prefetch_exit(prefetcher)

	def _prefetch_exit(self, prefetcher):

		opts = self.opts
		pkg = self.pkg
		settings = self.settings

		if opts.fetchonly:
				fetcher = EbuildFetchonly(
					fetch_all=opts.fetch_all_uri,
					pkg=pkg, pretend=opts.pretend,
					settings=settings)
				retval = fetcher.execute()
				self.returncode = retval
				self.wait()
				return

		fetcher = EbuildFetcher(config_pool=self.config_pool,
			fetchall=opts.fetch_all_uri,
			fetchonly=opts.fetchonly,
			background=self.background,
			pkg=pkg, scheduler=self.scheduler)

		self._start_task(fetcher, self._fetch_exit)

	def _fetch_exit(self, fetcher):
		opts = self.opts
		pkg = self.pkg

		fetch_failed = False
		if opts.fetchonly:
			fetch_failed = self._final_exit(fetcher) != os.EX_OK
		else:
			fetch_failed = self._default_exit(fetcher) != os.EX_OK

		if fetch_failed and fetcher.logfile is not None and \
			os.path.exists(fetcher.logfile):
			self.settings["PORTAGE_LOG_FILE"] = fetcher.logfile

		if fetch_failed or opts.fetchonly:
			self.wait()
			return

		logger = self.logger
		opts = self.opts
		pkg_count = self.pkg_count
		scheduler = self.scheduler
		settings = self.settings
		features = settings.features
		ebuild_path = self._ebuild_path
		system_set = pkg.root_config.sets["system"]

		self._build_dir = EbuildBuildDir(pkg=pkg, settings=settings)
		self._build_dir.lock()

		# Cleaning is triggered before the setup
		# phase, in portage.doebuild().
		msg = " === (%s of %s) Cleaning (%s::%s)" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
		short_msg = "emerge: (%s of %s) %s Clean" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv)
		logger.log(msg, short_msg=short_msg)

		#buildsyspkg: Check if we need to _force_ binary package creation
		self._issyspkg = "buildsyspkg" in features and \
				system_set.findAtomForPackage(pkg) and \
				not opts.buildpkg

		if opts.buildpkg or self._issyspkg:

			self._buildpkg = True

			msg = " === (%s of %s) Compiling/Packaging (%s::%s)" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
			short_msg = "emerge: (%s of %s) %s Compile" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			logger.log(msg, short_msg=short_msg)

		else:
			msg = " === (%s of %s) Compiling/Merging (%s::%s)" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, ebuild_path)
			short_msg = "emerge: (%s of %s) %s Compile" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			logger.log(msg, short_msg=short_msg)

		build = EbuildExecuter(background=self.background, pkg=pkg,
			scheduler=scheduler, settings=settings)
		self._start_task(build, self._build_exit)

	def _unlock_builddir(self):
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		self._build_dir.unlock()

	def _build_exit(self, build):
		if self._default_exit(build) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		opts = self.opts
		buildpkg = self._buildpkg

		if not buildpkg:
			self._final_exit(build)
			self.wait()
			return

		if self._issyspkg:
			msg = ">>> This is a system package, " + \
				"let's pack a rescue tarball.\n"

			log_path = self.settings.get("PORTAGE_LOG_FILE")
			if log_path is not None:
				log_file = codecs.open(_unicode_encode(log_path,
					encoding=_encodings['fs'], errors='strict'),
					mode='a', encoding=_encodings['content'], errors='replace')
				try:
					log_file.write(msg)
				finally:
					log_file.close()

			if not self.background:
				portage.writemsg_stdout(msg, noiselevel=-1)

		packager = EbuildBinpkg(background=self.background, pkg=self.pkg,
			scheduler=self.scheduler, settings=self.settings)

		self._start_task(packager, self._buildpkg_exit)

	def _buildpkg_exit(self, packager):
		"""
		Released build dir lock when there is a failure or
		when in buildpkgonly mode. Otherwise, the lock will
		be released when merge() is called.
		"""

		if self._default_exit(packager) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		if self.opts.buildpkgonly:
			phase = 'success_hooks'
			success_hooks = MiscFunctionsProcess(
				background=self.background,
				commands=[phase], phase=phase, pkg=self.pkg,
				scheduler=self.scheduler, settings=self.settings)
			self._start_task(success_hooks,
				self._buildpkgonly_success_hook_exit)
			return

		# Continue holding the builddir lock until
		# after the package has been installed.
		self._current_task = None
		self.returncode = packager.returncode
		self.wait()

	def _buildpkgonly_success_hook_exit(self, success_hooks):
		self._default_exit(success_hooks)
		self.returncode = None
		# Need to call "clean" phase for buildpkgonly mode
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		phase = 'clean'
		clean_phase = EbuildPhase(background=self.background,
			pkg=self.pkg, phase=phase,
			scheduler=self.scheduler, settings=self.settings,
			tree=self._tree)
		self._start_task(clean_phase, self._clean_exit)

	def _clean_exit(self, clean_phase):
		if self._final_exit(clean_phase) != os.EX_OK or \
			self.opts.buildpkgonly:
			self._unlock_builddir()
		self.wait()

	def install(self):
		"""
		Install the package and then clean up and release locks.
		Only call this after the build has completed successfully
		and neither fetchonly nor buildpkgonly mode are enabled.
		"""

		find_blockers = self.find_blockers
		ldpath_mtimes = self.ldpath_mtimes
		logger = self.logger
		pkg = self.pkg
		pkg_count = self.pkg_count
		settings = self.settings
		world_atom = self.world_atom
		ebuild_path = self._ebuild_path
		tree = self._tree

		merge = EbuildMerge(find_blockers=self.find_blockers,
			ldpath_mtimes=ldpath_mtimes, logger=logger, pkg=pkg,
			pkg_count=pkg_count, pkg_path=ebuild_path,
			scheduler=self.scheduler,
			settings=settings, tree=tree, world_atom=world_atom)

		msg = " === (%s of %s) Merging (%s::%s)" % \
			(pkg_count.curval, pkg_count.maxval,
			pkg.cpv, ebuild_path)
		short_msg = "emerge: (%s of %s) %s Merge" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv)
		logger.log(msg, short_msg=short_msg)

		try:
			rval = merge.execute()
		finally:
			self._unlock_builddir()

		return rval

