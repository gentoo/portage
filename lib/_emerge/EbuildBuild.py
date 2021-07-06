# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import io

import _emerge.emergelog
from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.EbuildExecuter import EbuildExecuter
from _emerge.EbuildPhase import EbuildPhase
from _emerge.EbuildBinpkg import EbuildBinpkg
from _emerge.EbuildFetcher import EbuildFetcher
from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildMerge import EbuildMerge
from _emerge.EbuildFetchonly import EbuildFetchonly
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.TaskSequence import TaskSequence

import portage
from portage import _encodings, _unicode_encode, os
from portage.package.ebuild.digestcheck import digestcheck
from portage.package.ebuild.doebuild import _check_temp_dir
from portage.package.ebuild._spawn_nofetch import SpawnNofetchWithoutBuilddir
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util.path import first_existing


class EbuildBuild(CompositeTask):

	__slots__ = ("args_set", "config_pool", "find_blockers",
		"ldpath_mtimes", "logger", "opts", "pkg", "pkg_count",
		"prefetcher", "settings", "world_atom") + \
		("_build_dir", "_buildpkg", "_ebuild_path", "_issyspkg", "_tree")

	def _start(self):
		if not self.opts.fetchonly:
			rval = _check_temp_dir(self.settings)
			if rval != os.EX_OK:
				self.returncode = rval
				self._current_task = None
				self._async_wait()
				return

		# First get the SRC_URI metadata (it's not cached in self.pkg.metadata
		# because some packages have an extremely large SRC_URI value).
		self._start_task(
			AsyncTaskFuture(
				future=self.pkg.root_config.trees["porttree"].dbapi.\
				async_aux_get(self.pkg.cpv, ["SRC_URI"], myrepo=self.pkg.repo,
				loop=self.scheduler)),
			self._start_with_metadata)

	def _start_with_metadata(self, aux_get_task):
		self._assert_current(aux_get_task)
		if aux_get_task.cancelled:
			self._default_final_exit(aux_get_task)
			return

		pkg = self.pkg
		settings = self.settings
		root_config = pkg.root_config
		tree = "porttree"
		self._tree = tree
		portdb = root_config.trees[tree].dbapi
		settings.setcpv(pkg)
		settings.configdict["pkg"]["SRC_URI"], = aux_get_task.future.result()
		settings.configdict["pkg"]["EMERGE_FROM"] = "ebuild"
		if self.opts.buildpkgonly:
			settings.configdict["pkg"]["MERGE_TYPE"] = "buildonly"
		else:
			settings.configdict["pkg"]["MERGE_TYPE"] = "source"
		ebuild_path = portdb.findname(pkg.cpv, myrepo=pkg.repo)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % pkg.cpv)
		self._ebuild_path = ebuild_path
		portage.doebuild_environment(ebuild_path, 'setup',
			settings=self.settings, db=portdb)

		# Check the manifest here since with --keep-going mode it's
		# currently possible to get this far with a broken manifest.
		if not self._check_manifest():
			self.returncode = 1
			self._current_task = None
			self._async_wait()
			return

		prefetcher = self.prefetcher
		if prefetcher is None:
			pass
		elif prefetcher.isAlive() and \
			prefetcher.poll() is None:

			if not self.background:
				fetch_log = os.path.join(
					_emerge.emergelog._emerge_log_dir, 'emerge-fetch.log')
				msg = (
					'Fetching files in the background.',
					'To view fetch progress, run in another terminal:',
					'tail -f %s' % fetch_log,
				)
				out = portage.output.EOutput()
				for l in msg:
					out.einfo(l)

			self._current_task = prefetcher
			prefetcher.addExitListener(self._prefetch_exit)
			return

		self._prefetch_exit(prefetcher)

	def _check_manifest(self):
		success = True

		settings = self.settings
		if 'strict' in settings.features and \
			'digest' not in settings.features:
			settings['O'] = os.path.dirname(self._ebuild_path)
			quiet_setting = settings.get('PORTAGE_QUIET')
			settings['PORTAGE_QUIET'] = '1'
			try:
				success = digestcheck([], settings, strict=True)
			finally:
				if quiet_setting:
					settings['PORTAGE_QUIET'] = quiet_setting
				else:
					del settings['PORTAGE_QUIET']

		return success

	def _prefetch_exit(self, prefetcher):

		if self._was_cancelled():
			self.wait()
			return

		opts = self.opts
		pkg = self.pkg
		settings = self.settings

		if opts.fetchonly:
			if opts.pretend:
				fetcher = EbuildFetchonly(
					fetch_all=opts.fetch_all_uri,
					pkg=pkg, pretend=opts.pretend,
					settings=settings)
				retval = fetcher.execute()
				if retval == os.EX_OK:
					self._current_task = None
					self.returncode = os.EX_OK
					self._async_wait()
				else:
					# For pretend mode, the convention it to execute
					# pkg_nofetch and return a successful exitcode.
					self._start_task(SpawnNofetchWithoutBuilddir(
						background=self.background,
						portdb=self.pkg.root_config.trees[self._tree].dbapi,
						ebuild_path=self._ebuild_path,
						scheduler=self.scheduler,
						settings=self.settings),
						self._default_final_exit)
				return

			quiet_setting = settings.get("PORTAGE_QUIET", False)
			fetch_log = None
			logwrite_access = False
			if quiet_setting:
				fetch_log = os.path.join(
					_emerge.emergelog._emerge_log_dir, "emerge-fetch.log"
				)
				logwrite_access = os.access(first_existing(fetch_log), os.W_OK)

			fetcher = EbuildFetcher(
				config_pool=self.config_pool,
				ebuild_path=self._ebuild_path,
				fetchall=self.opts.fetch_all_uri,
				fetchonly=self.opts.fetchonly,
				background=quiet_setting if logwrite_access else False,
				logfile=fetch_log if logwrite_access else None,
				pkg=self.pkg,
				scheduler=self.scheduler,
			)

			if fetch_log and logwrite_access:
				fetcher.addExitListener(self._fetchonly_exit)
				self._task_queued(fetcher)
				self.scheduler.fetch.schedule(fetcher, force_queue=True)
			else:
				self._start_task(fetcher, self._fetchonly_exit)
			return

		self._build_dir = EbuildBuildDir(
			scheduler=self.scheduler, settings=settings)
		self._start_task(
			AsyncTaskFuture(future=self._build_dir.async_lock()),
			self._start_pre_clean)

	def _start_pre_clean(self, lock_task):
		self._assert_current(lock_task)
		if lock_task.cancelled:
			self._default_final_exit(lock_task)
			return

		lock_task.future.result()
		# Cleaning needs to happen before fetch, since the build dir
		# is used for log handling.
		msg = " === (%s of %s) Cleaning (%s::%s)" % \
			(self.pkg_count.curval, self.pkg_count.maxval,
			self.pkg.cpv, self._ebuild_path)
		short_msg = "emerge: (%s of %s) %s Clean" % \
			(self.pkg_count.curval, self.pkg_count.maxval, self.pkg.cpv)
		self.logger.log(msg, short_msg=short_msg)

		pre_clean_phase = EbuildPhase(background=self.background,
			phase='clean', scheduler=self.scheduler, settings=self.settings)
		self._start_task(pre_clean_phase, self._pre_clean_exit)

	def _fetchonly_exit(self, fetcher):
		self._final_exit(fetcher)
		if self.returncode != os.EX_OK:
			self.returncode = None
			portdb = self.pkg.root_config.trees[self._tree].dbapi
			self._start_task(SpawnNofetchWithoutBuilddir(
				background=self.background,
				portdb=portdb,
				ebuild_path=self._ebuild_path,
				scheduler=self.scheduler,
				settings=self.settings),
				self._nofetch_without_builddir_exit)
			return

		self.wait()

	def _nofetch_without_builddir_exit(self, nofetch):
		self._final_exit(nofetch)
		self.returncode = 1
		self.wait()

	def _pre_clean_exit(self, pre_clean_phase):
		if self._default_exit(pre_clean_phase) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		# for log handling
		portage.prepare_build_dirs(self.pkg.root, self.settings, 1)

		fetcher = EbuildFetcher(config_pool=self.config_pool,
			ebuild_path=self._ebuild_path,
			fetchall=self.opts.fetch_all_uri,
			fetchonly=self.opts.fetchonly,
			background=self.background,
			logfile=self.settings.get('PORTAGE_LOG_FILE'),
			pkg=self.pkg, scheduler=self.scheduler)

		self._start_task(AsyncTaskFuture(
			future=fetcher.async_already_fetched(self.settings)),
			functools.partial(self._start_fetch, fetcher))

	def _start_fetch(self, fetcher, already_fetched_task):
		self._assert_current(already_fetched_task)
		if already_fetched_task.cancelled:
			self._default_final_exit(already_fetched_task)
			return

		try:
			already_fetched = already_fetched_task.future.result()
		except portage.exception.InvalidDependString as e:
			msg_lines = []
			msg = "Fetch failed for '%s' due to invalid SRC_URI: %s" % \
				(self.pkg.cpv, e)
			msg_lines.append(msg)
			fetcher._eerror(msg_lines)
			portage.elog.elog_process(self.pkg.cpv, self.settings)
			self._async_unlock_builddir(returncode=1)
			return

		if already_fetched:
			# This case is optimized to skip the fetch queue.
			fetcher = None
			self._fetch_exit(fetcher)
			return

		# Allow the Scheduler's fetch queue to control the
		# number of concurrent fetchers.
		fetcher.addExitListener(self._fetch_exit)
		self._task_queued(fetcher)
		self.scheduler.fetch.schedule(fetcher)

	def _fetch_exit(self, fetcher):

		if fetcher is not None and \
			self._default_exit(fetcher) != os.EX_OK:
			self._fetch_failed()
			return

		# discard successful fetch log
		self._build_dir.clean_log()
		pkg = self.pkg
		logger = self.logger
		opts = self.opts
		pkg_count = self.pkg_count
		scheduler = self.scheduler
		settings = self.settings
		features = settings.features
		ebuild_path = self._ebuild_path
		system_set = pkg.root_config.sets["system"]

		#buildsyspkg: Check if we need to _force_ binary package creation
		self._issyspkg = "buildsyspkg" in features and \
				system_set.findAtomForPackage(pkg) and \
				"buildpkg" not in features and \
				opts.buildpkg != 'n'

		if ("buildpkg" in features or self._issyspkg) \
			and not self.opts.buildpkg_exclude.findAtomForPackage(pkg):

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

	def _fetch_failed(self):
		# We only call the pkg_nofetch phase if either RESTRICT=fetch
		# is set or the package has explicitly overridden the default
		# pkg_nofetch implementation. This allows specialized messages
		# to be displayed for problematic packages even though they do
		# not set RESTRICT=fetch (bug #336499).

		if 'fetch' not in self.pkg.restrict and \
			'nofetch' not in self.pkg.defined_phases:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		self.returncode = None
		nofetch_phase = EbuildPhase(background=self.background,
			phase='nofetch', scheduler=self.scheduler, settings=self.settings)
		self._start_task(nofetch_phase, self._nofetch_exit)

	def _nofetch_exit(self, nofetch_phase):
		self._final_exit(nofetch_phase)
		self._async_unlock_builddir(returncode=1)

	def _async_unlock_builddir(self, returncode=None):
		"""
		Release the lock asynchronously, and if a returncode parameter
		is given then set self.returncode and notify exit listeners.
		"""
		if returncode is not None:
			# The returncode will be set after unlock is complete.
			self.returncode = None
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		self._start_task(
			AsyncTaskFuture(future=self._build_dir.async_unlock()),
			functools.partial(self._unlock_builddir_exit, returncode=returncode))

	def _unlock_builddir_exit(self, unlock_task, returncode=None):
		self._assert_current(unlock_task)
		if unlock_task.cancelled and returncode is not None:
			self._default_final_exit(unlock_task)
			return

		# Normally, async_unlock should not raise an exception here.
		unlock_task.future.cancelled() or unlock_task.future.result()
		if returncode is not None:
			self.returncode = returncode
			self._async_wait()

	def _build_exit(self, build):
		if self._default_exit(build) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		buildpkg = self._buildpkg

		if not buildpkg:
			self._final_exit(build)
			self.wait()
			return

		if self._issyspkg:
			msg = ">>> This is a system package, " + \
				"let's pack a rescue tarball.\n"
			self.scheduler.output(msg,
				log_path=self.settings.get("PORTAGE_LOG_FILE"))

		binpkg_tasks = TaskSequence()
		requested_binpkg_formats = self.settings.get("PORTAGE_BINPKG_FORMAT", "tar").split()
		for pkg_fmt in portage.const.SUPPORTED_BINPKG_FORMATS:
			if pkg_fmt in requested_binpkg_formats:
				if pkg_fmt == "rpm":
					binpkg_tasks.add(EbuildPhase(background=self.background,
						phase="rpm", scheduler=self.scheduler,
						settings=self.settings))
				else:
					task = EbuildBinpkg(
						background=self.background,
						pkg=self.pkg, scheduler=self.scheduler,
						settings=self.settings)
					binpkg_tasks.add(task)
					# Guarantee that _record_binpkg_info is called
					# immediately after EbuildBinpkg. Note that
					# task.addExitListener does not provide the
					# necessary guarantee (see bug 578204).
					binpkg_tasks.add(self._RecordBinpkgInfo(
						ebuild_binpkg=task, ebuild_build=self))

		if binpkg_tasks:
			self._start_task(binpkg_tasks, self._buildpkg_exit)
			return

		self._final_exit(build)
		self.wait()

	class _RecordBinpkgInfo(AsynchronousTask):
		"""
		This class wraps the EbuildBuild _record_binpkg_info method
		with an AsynchronousTask interface, so that it can be
		scheduled as a member of a TaskSequence.
		"""

		__slots__ = ('ebuild_binpkg', 'ebuild_build',)

		def _start(self):
			self.ebuild_build._record_binpkg_info(self.ebuild_binpkg)
			AsynchronousTask._start(self)

	def _buildpkg_exit(self, packager):
		"""
		Released build dir lock when there is a failure or
		when in buildpkgonly mode. Otherwise, the lock will
		be released when merge() is called.
		"""

		if self._default_exit(packager) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		if self.opts.buildpkgonly:
			phase = 'success_hooks'
			success_hooks = MiscFunctionsProcess(
				background=self.background,
				commands=[phase], phase=phase,
				scheduler=self.scheduler, settings=self.settings)
			self._start_task(success_hooks,
				self._buildpkgonly_success_hook_exit)
			return

		# Continue holding the builddir lock until
		# after the package has been installed.
		self._current_task = None
		self.returncode = packager.returncode
		self.wait()

	def _record_binpkg_info(self, task):
		if task.returncode != os.EX_OK:
			return

		# Save info about the created binary package, so that
		# identifying information can be passed to the install
		# task, to be recorded in the installed package database.
		pkg = task.get_binpkg_info()
		infoloc = os.path.join(self.settings["PORTAGE_BUILDDIR"],
			"build-info")
		info = {
			"BINPKGMD5": "%s\n" % pkg._metadata["MD5"],
		}
		if pkg.build_id is not None:
			info["BUILD_ID"] = "%s\n" % pkg.build_id
		for k, v in info.items():
			with io.open(_unicode_encode(os.path.join(infoloc, k),
				encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['repo.content'],
				errors='strict') as f:
				f.write(v)

	def _buildpkgonly_success_hook_exit(self, success_hooks):
		self._default_exit(success_hooks)
		self.returncode = None
		# Need to call "clean" phase for buildpkgonly mode
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		phase = 'clean'
		clean_phase = EbuildPhase(background=self.background,
			phase=phase, scheduler=self.scheduler, settings=self.settings)
		self._start_task(clean_phase, self._clean_exit)

	def _clean_exit(self, clean_phase):
		if self._final_exit(clean_phase) != os.EX_OK or \
			self.opts.buildpkgonly:
			self._async_unlock_builddir(returncode=self.returncode)
		else:
			self.wait()

	def create_install_task(self):
		"""
		Install the package and then clean up and release locks.
		Only call this after the build has completed successfully
		and neither fetchonly nor buildpkgonly mode are enabled.
		"""

		ldpath_mtimes = self.ldpath_mtimes
		logger = self.logger
		pkg = self.pkg
		pkg_count = self.pkg_count
		settings = self.settings
		world_atom = self.world_atom
		ebuild_path = self._ebuild_path
		tree = self._tree

		task = EbuildMerge(exit_hook=self._install_exit,
			find_blockers=self.find_blockers,
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

		return task

	def _install_exit(self, task):
		"""
		@returns: Future, result is the returncode from an
			EbuildBuildDir.async_unlock() task
		"""
		self._async_unlock_builddir()
		if self._current_task is None:
			result = self.scheduler.create_future()
			self.scheduler.call_soon(result.set_result, os.EX_OK)
		else:
			result = self._current_task.async_wait()
		return result
