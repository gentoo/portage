# Copyright 1999-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

import _emerge.emergelog
from _emerge.EbuildPhase import EbuildPhase
from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
from _emerge.EbuildMerge import EbuildMerge
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.SpawnProcess import SpawnProcess
from portage.eapi import eapi_exports_replace_vars
from portage.util import ensure_dirs
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util.futures.compat_coroutine import coroutine
import portage
from portage import os
from portage import shutil
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import io
import logging

class Binpkg(CompositeTask):

	__slots__ = ("find_blockers",
		"ldpath_mtimes", "logger", "opts",
		"pkg", "pkg_count", "prefetcher", "settings", "world_atom") + \
		("_bintree", "_build_dir", "_build_prefix",
		"_ebuild_path", "_fetched_pkg",
		"_image_dir", "_infloc", "_pkg_path", "_tree", "_verify")

	def _writemsg_level(self, msg, level=0, noiselevel=0):
		self.scheduler.output(msg, level=level, noiselevel=noiselevel,
			log_path=self.settings.get("PORTAGE_LOG_FILE"))

	def _start(self):

		pkg = self.pkg
		settings = self.settings
		settings.setcpv(pkg)
		self._tree = "bintree"
		self._bintree = self.pkg.root_config.trees[self._tree]
		self._verify = not self.opts.pretend

		# Use realpath like doebuild_environment() does, since we assert
		# that this path is literally identical to PORTAGE_BUILDDIR.
		dir_path = os.path.join(os.path.realpath(settings["PORTAGE_TMPDIR"]),
			"portage", pkg.category, pkg.pf)
		self._image_dir = os.path.join(dir_path, "image")
		self._infloc = os.path.join(dir_path, "build-info")
		self._ebuild_path = os.path.join(self._infloc, pkg.pf + ".ebuild")
		settings["EBUILD"] = self._ebuild_path
		portage.doebuild_environment(self._ebuild_path, 'setup',
			settings=self.settings, db=self._bintree.dbapi)
		if dir_path != self.settings['PORTAGE_BUILDDIR']:
			raise AssertionError("'%s' != '%s'" % \
				(dir_path, self.settings['PORTAGE_BUILDDIR']))
		self._build_dir = EbuildBuildDir(
			scheduler=self.scheduler, settings=settings)
		settings.configdict["pkg"]["EMERGE_FROM"] = "binary"
		settings.configdict["pkg"]["MERGE_TYPE"] = "binary"

		if eapi_exports_replace_vars(settings["EAPI"]):
			vardb = self.pkg.root_config.trees["vartree"].dbapi
			settings["REPLACING_VERSIONS"] = " ".join(
				set(portage.versions.cpv_getversion(x) \
					for x in vardb.match(self.pkg.slot_atom) + \
					vardb.match('='+self.pkg.cpv)))

		# The prefetcher has already completed or it
		# could be running now. If it's running now,
		# wait for it to complete since it holds
		# a lock on the file being fetched. The
		# portage.locks functions are only designed
		# to work between separate processes. Since
		# the lock is held by the current process,
		# use the scheduler and fetcher methods to
		# synchronize with the fetcher.
		prefetcher = self.prefetcher
		if prefetcher is None:
			pass
		elif prefetcher.isAlive() and \
			prefetcher.poll() is None:

			if not self.background:
				fetch_log = os.path.join(
					_emerge.emergelog._emerge_log_dir, 'emerge-fetch.log')
				msg = (
					'Fetching in the background:',
					prefetcher.pkg_path,
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

	def _prefetch_exit(self, prefetcher):

		if self._was_cancelled():
			self.wait()
			return

		if not (self.opts.pretend or self.opts.fetchonly):
			self._start_task(
				AsyncTaskFuture(future=self._build_dir.async_lock()),
				self._start_fetcher)
		else:
			self._start_fetcher()

	def _start_fetcher(self, lock_task=None):
		if lock_task is not None:
			self._assert_current(lock_task)
			if lock_task.cancelled:
				self._default_final_exit(lock_task)
				return

			lock_task.future.result()
			# Initialize PORTAGE_LOG_FILE (clean_log won't work without it).
			portage.prepare_build_dirs(self.settings["ROOT"], self.settings, 1)
			# If necessary, discard old log so that we don't
			# append to it.
			self._build_dir.clean_log()

		pkg = self.pkg
		pkg_count = self.pkg_count
		fetcher = None

		if self.opts.getbinpkg and self._bintree.isremote(pkg.cpv):

			fetcher = BinpkgFetcher(background=self.background,
				logfile=self.settings.get("PORTAGE_LOG_FILE"), pkg=self.pkg,
				pretend=self.opts.pretend, scheduler=self.scheduler)

			msg = " --- (%s of %s) Fetching Binary (%s::%s)" %\
				(pkg_count.curval, pkg_count.maxval, pkg.cpv,
					fetcher.pkg_path)
			short_msg = "emerge: (%s of %s) %s Fetch" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			self.logger.log(msg, short_msg=short_msg)

			# Allow the Scheduler's fetch queue to control the
			# number of concurrent fetchers.
			fetcher.addExitListener(self._fetcher_exit)
			self._task_queued(fetcher)
			self.scheduler.fetch.schedule(fetcher)
			return

		self._fetcher_exit(fetcher)

	def _fetcher_exit(self, fetcher):

		# The fetcher only has a returncode when
		# --getbinpkg is enabled.
		if fetcher is not None:
			self._fetched_pkg = fetcher.pkg_path
			if self._default_exit(fetcher) != os.EX_OK:
				self._async_unlock_builddir(returncode=self.returncode)
				return

		if self.opts.pretend:
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		verifier = None
		if self._verify:
			if self._fetched_pkg:
				path = self._fetched_pkg
			else:
				path = self.pkg.root_config.trees["bintree"].getname(
					self.pkg.cpv)
			logfile = self.settings.get("PORTAGE_LOG_FILE")
			verifier = BinpkgVerifier(background=self.background,
				logfile=logfile, pkg=self.pkg, scheduler=self.scheduler,
				_pkg_path=path)
			self._start_task(verifier, self._verifier_exit)
			return

		self._verifier_exit(verifier)

	def _verifier_exit(self, verifier):
		if verifier is not None and \
			self._default_exit(verifier) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		logger = self.logger
		pkg = self.pkg
		pkg_count = self.pkg_count

		if self._fetched_pkg:
			pkg_path = self._bintree.getname(
				self._bintree.inject(pkg.cpv,
				filename=self._fetched_pkg),
				allocate_new=False)
		else:
			pkg_path = self.pkg.root_config.trees["bintree"].getname(
				self.pkg.cpv)

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		if pkg_path is not None:
			self.settings["PORTAGE_BINPKG_FILE"] = pkg_path
		self._pkg_path = pkg_path

		logfile = self.settings.get("PORTAGE_LOG_FILE")
		if logfile is not None and os.path.isfile(logfile):
			# Remove fetch log after successful fetch.
			try:
				os.unlink(logfile)
			except OSError:
				pass

		if self.opts.fetchonly:
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		msg = " === (%s of %s) Merging Binary (%s::%s)" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path)
		short_msg = "emerge: (%s of %s) %s Merge Binary" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv)
		logger.log(msg, short_msg=short_msg)

		phase = "clean"
		settings = self.settings
		ebuild_phase = EbuildPhase(background=self.background,
			phase=phase, scheduler=self.scheduler,
			settings=settings)

		self._start_task(ebuild_phase, self._clean_exit)

	def _clean_exit(self, clean_phase):
		if self._default_exit(clean_phase) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		self._start_task(
			AsyncTaskFuture(future=self._unpack_metadata(loop=self.scheduler)),
			self._unpack_metadata_exit)

	@coroutine
	def _unpack_metadata(self, loop=None):

		dir_path = self.settings['PORTAGE_BUILDDIR']

		infloc = self._infloc
		pkg = self.pkg
		pkg_path = self._pkg_path

		dir_mode = 0o755
		for mydir in (dir_path, self._image_dir, infloc):
			portage.util.ensure_dirs(mydir, uid=portage.data.portage_uid,
				gid=portage.data.portage_gid, mode=dir_mode)

		# This initializes PORTAGE_LOG_FILE.
		portage.prepare_build_dirs(self.settings["ROOT"], self.settings, 1)
		self._writemsg_level(">>> Extracting info\n")

		yield self._bintree.dbapi.unpack_metadata(self.settings, infloc, loop=self.scheduler)
		check_missing_metadata = ("CATEGORY", "PF")
		for k, v in zip(check_missing_metadata,
			self._bintree.dbapi.aux_get(self.pkg.cpv, check_missing_metadata)):
			if v:
				continue
			elif k == "CATEGORY":
				v = pkg.category
			elif k == "PF":
				v = pkg.pf
			else:
				continue

			f = io.open(_unicode_encode(os.path.join(infloc, k),
				encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['content'],
				errors='backslashreplace')
			try:
				f.write(_unicode_decode(v + "\n"))
			finally:
				f.close()

		# Store the md5sum in the vdb.
		if pkg_path is not None:
			md5sum, = self._bintree.dbapi.aux_get(self.pkg.cpv, ['MD5'])
			if not md5sum:
				md5sum = portage.checksum.perform_md5(pkg_path)
			with io.open(_unicode_encode(os.path.join(infloc, 'BINPKGMD5'),
				encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['content'], errors='strict') as f:
				f.write(_unicode_decode('{}\n'.format(md5sum)))

		env_extractor = BinpkgEnvExtractor(background=self.background,
			scheduler=self.scheduler, settings=self.settings)
		env_extractor.start()
		yield env_extractor.async_wait()
		if env_extractor.returncode != os.EX_OK:
			raise portage.exception.PortageException('failed to extract environment for {}'.format(self.pkg.cpv))

	def _unpack_metadata_exit(self, unpack_metadata):
		if self._default_exit(unpack_metadata) != os.EX_OK:
			unpack_metadata.future.result()
			self._async_unlock_builddir(returncode=self.returncode)
			return

		setup_phase = EbuildPhase(background=self.background,
			phase="setup", scheduler=self.scheduler,
			settings=self.settings)

		setup_phase.addExitListener(self._setup_exit)
		self._task_queued(setup_phase)
		self.scheduler.scheduleSetup(setup_phase)

	def _setup_exit(self, setup_phase):
		if self._default_exit(setup_phase) != os.EX_OK:
			self._async_unlock_builddir(returncode=self.returncode)
			return

		self._writemsg_level(">>> Extracting %s\n" % self.pkg.cpv)
		self._start_task(
			AsyncTaskFuture(future=self._bintree.dbapi.unpack_contents(
				self.settings,
				self._image_dir, loop=self.scheduler)),
			self._unpack_contents_exit)

	def _unpack_contents_exit(self, unpack_contents):
		if self._default_exit(unpack_contents) != os.EX_OK:
			unpack_contents.future.result()
			self._writemsg_level("!!! Error Extracting '%s'\n" % \
				self._pkg_path, noiselevel=-1, level=logging.ERROR)
			self._async_unlock_builddir(returncode=self.returncode)
			return

		try:
			with io.open(_unicode_encode(os.path.join(self._infloc, "EPREFIX"),
				encoding=_encodings['fs'], errors='strict'), mode='r',
				encoding=_encodings['repo.content'], errors='replace') as f:
				self._build_prefix = f.read().rstrip('\n')
		except IOError:
			self._build_prefix = ""

		if self._build_prefix == self.settings["EPREFIX"]:
			ensure_dirs(self.settings["ED"])
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		env = self.settings.environ()
		env["PYTHONPATH"] = self.settings["PORTAGE_PYTHONPATH"]
		chpathtool = SpawnProcess(
			args=[portage._python_interpreter,
			os.path.join(self.settings["PORTAGE_BIN_PATH"], "chpathtool.py"),
			self.settings["D"], self._build_prefix, self.settings["EPREFIX"]],
			background=self.background, env=env,
			scheduler=self.scheduler,
			logfile=self.settings.get('PORTAGE_LOG_FILE'))
		self._writemsg_level(">>> Adjusting Prefix to %s\n" % self.settings["EPREFIX"])
		self._start_task(chpathtool, self._chpathtool_exit)

	def _chpathtool_exit(self, chpathtool):
		if self._final_exit(chpathtool) != os.EX_OK:
			self._writemsg_level("!!! Error Adjusting Prefix to %s\n" %
				(self.settings["EPREFIX"],),
				noiselevel=-1, level=logging.ERROR)
			self._async_unlock_builddir(returncode=self.returncode)
			return

		# We want to install in "our" prefix, not the binary one
		with io.open(_unicode_encode(os.path.join(self._infloc, "EPREFIX"),
			encoding=_encodings['fs'], errors='strict'), mode='w',
			encoding=_encodings['repo.content'], errors='strict') as f:
			f.write(self.settings["EPREFIX"] + "\n")

		# Move the files to the correct location for merge.
		image_tmp_dir = os.path.join(
			self.settings["PORTAGE_BUILDDIR"], "image_tmp")
		build_d = os.path.join(self.settings["D"],
			self._build_prefix.lstrip(os.sep)).rstrip(os.sep)
		if not os.path.isdir(build_d):
			# Assume this is a virtual package or something.
			shutil.rmtree(self._image_dir)
			ensure_dirs(self.settings["ED"])
		else:
			os.rename(build_d, image_tmp_dir)
			if build_d != self._image_dir:
				shutil.rmtree(self._image_dir)
			ensure_dirs(os.path.dirname(self.settings["ED"].rstrip(os.sep)))
			os.rename(image_tmp_dir, self.settings["ED"])

		self.wait()

	def _async_unlock_builddir(self, returncode=None):
		"""
		Release the lock asynchronously, and if a returncode parameter
		is given then set self.returncode and notify exit listeners.
		"""
		if self.opts.pretend or self.opts.fetchonly:
			if returncode is not None:
				self.returncode = returncode
				self._async_wait()
			return
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

	def create_install_task(self):
		task = EbuildMerge(exit_hook=self._install_exit,
			find_blockers=self.find_blockers,
			ldpath_mtimes=self.ldpath_mtimes, logger=self.logger,
			pkg=self.pkg, pkg_count=self.pkg_count,
			pkg_path=self._pkg_path, scheduler=self.scheduler,
			settings=self.settings, tree=self._tree,
			world_atom=self.world_atom)
		return task

	def _install_exit(self, task):
		"""
		@returns: Future, result is the returncode from an
			EbuildBuildDir.async_unlock() task
		"""
		self.settings.pop("PORTAGE_BINPKG_FILE", None)
		if task.returncode == os.EX_OK and \
			'binpkg-logs' not in self.settings.features and \
			self.settings.get("PORTAGE_LOG_FILE"):
			try:
				os.unlink(self.settings["PORTAGE_LOG_FILE"])
			except OSError:
				pass
		self._async_unlock_builddir()
		if self._current_task is None:
			result = self.scheduler.create_future()
			self.scheduler.call_soon(result.set_result, os.EX_OK)
		else:
			result = self._current_task.async_wait()
		return result
