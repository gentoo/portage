# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildPhase import EbuildPhase
from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.BinpkgExtractorAsync import BinpkgExtractorAsync
from _emerge.CompositeTask import CompositeTask
from _emerge.BinpkgVerifier import BinpkgVerifier
from _emerge.EbuildMerge import EbuildMerge
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.SpawnProcess import SpawnProcess
from portage.eapi import eapi_exports_replace_vars
from portage.util import ensure_dirs, writemsg
import portage
from portage import os
from portage import shutil
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import io
import logging
import textwrap
from portage.output import colorize

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

			waiting_msg = ("Fetching '%s' " + \
				"in the background. " + \
				"To view fetch progress, run `tail -f %s" + \
				"/var/log/emerge-fetch.log` in another " + \
				"terminal.") % (prefetcher.pkg_path, settings["EPREFIX"])
			msg_prefix = colorize("GOOD", " * ")
			waiting_msg = "".join("%s%s\n" % (msg_prefix, line) \
				for line in textwrap.wrap(waiting_msg, 65))
			if not self.background:
				writemsg(waiting_msg, noiselevel=-1)

			self._current_task = prefetcher
			prefetcher.addExitListener(self._prefetch_exit)
			return

		self._prefetch_exit(prefetcher)

	def _prefetch_exit(self, prefetcher):

		if self._was_cancelled():
			self.wait()
			return

		pkg = self.pkg
		pkg_count = self.pkg_count
		if not (self.opts.pretend or self.opts.fetchonly):
			self._build_dir.lock()
			# Initialize PORTAGE_LOG_FILE (clean_log won't work without it).
			portage.prepare_build_dirs(self.settings["ROOT"], self.settings, 1)
			# If necessary, discard old log so that we don't
			# append to it.
			self._build_dir.clean_log()
		fetcher = BinpkgFetcher(background=self.background,
			logfile=self.settings.get("PORTAGE_LOG_FILE"), pkg=self.pkg,
			pretend=self.opts.pretend, scheduler=self.scheduler)
		pkg_path = fetcher.pkg_path
		self._pkg_path = pkg_path
		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		self.settings["PORTAGE_BINPKG_FILE"] = pkg_path

		if self.opts.getbinpkg and self._bintree.isremote(pkg.cpv):

			msg = " --- (%s of %s) Fetching Binary (%s::%s)" %\
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path)
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
		if fetcher.returncode is not None:
			self._fetched_pkg = True
			if self._default_exit(fetcher) != os.EX_OK:
				self._unlock_builddir()
				self.wait()
				return

		if self.opts.pretend:
			self._current_task = None
			self.returncode = os.EX_OK
			self.wait()
			return

		verifier = None
		if self._verify:
			logfile = self.settings.get("PORTAGE_LOG_FILE")
			verifier = BinpkgVerifier(background=self.background,
				logfile=logfile, pkg=self.pkg, scheduler=self.scheduler)
			self._start_task(verifier, self._verifier_exit)
			return

		self._verifier_exit(verifier)

	def _verifier_exit(self, verifier):
		if verifier is not None and \
			self._default_exit(verifier) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		logger = self.logger
		pkg = self.pkg
		pkg_count = self.pkg_count
		pkg_path = self._pkg_path

		if self._fetched_pkg:
			self._bintree.inject(pkg.cpv, filename=pkg_path)

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
			self._unlock_builddir()
			self.wait()
			return

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

		pkg_xpak = portage.xpak.tbz2(self._pkg_path)
		check_missing_metadata = ("CATEGORY", "PF")
		missing_metadata = set()
		for k in check_missing_metadata:
			v = pkg_xpak.getfile(_unicode_encode(k,
				encoding=_encodings['repo.content']))
			if not v:
				missing_metadata.add(k)

		pkg_xpak.unpackinfo(infloc)
		for k in missing_metadata:
			if k == "CATEGORY":
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
		f = io.open(_unicode_encode(os.path.join(infloc, 'BINPKGMD5'),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['content'], errors='strict')
		try:
			f.write(_unicode_decode(
				str(portage.checksum.perform_md5(pkg_path)) + "\n"))
		finally:
			f.close()

		env_extractor = BinpkgEnvExtractor(background=self.background,
			scheduler=self.scheduler, settings=self.settings)

		self._start_task(env_extractor, self._env_extractor_exit)

	def _env_extractor_exit(self, env_extractor):
		if self._default_exit(env_extractor) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		setup_phase = EbuildPhase(background=self.background,
			phase="setup", scheduler=self.scheduler,
			settings=self.settings)

		setup_phase.addExitListener(self._setup_exit)
		self._task_queued(setup_phase)
		self.scheduler.scheduleSetup(setup_phase)

	def _setup_exit(self, setup_phase):
		if self._default_exit(setup_phase) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		extractor = BinpkgExtractorAsync(background=self.background,
			env=self.settings.environ(),
			image_dir=self._image_dir,
			pkg=self.pkg, pkg_path=self._pkg_path,
			logfile=self.settings.get("PORTAGE_LOG_FILE"),
			scheduler=self.scheduler)
		self._writemsg_level(">>> Extracting %s\n" % self.pkg.cpv)
		self._start_task(extractor, self._extractor_exit)

	def _extractor_exit(self, extractor):
		if self._default_exit(extractor) != os.EX_OK:
			self._unlock_builddir()
			self._writemsg_level("!!! Error Extracting '%s'\n" % \
				self._pkg_path, noiselevel=-1, level=logging.ERROR)
			self.wait()
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

		chpathtool = SpawnProcess(
			args=[portage._python_interpreter,
			os.path.join(self.settings["PORTAGE_BIN_PATH"], "chpathtool.py"),
			self.settings["D"], self._build_prefix, self.settings["EPREFIX"]],
			background=self.background, env=self.settings.environ(), 
			scheduler=self.scheduler,
			logfile=self.settings.get('PORTAGE_LOG_FILE'))
		self._writemsg_level(">>> Adjusting Prefix to %s\n" % self.settings["EPREFIX"])
		self._start_task(chpathtool, self._chpathtool_exit)

	def _chpathtool_exit(self, chpathtool):
		if self._final_exit(chpathtool) != os.EX_OK:
			self._unlock_builddir()
			self._writemsg_level("!!! Error Adjusting Prefix to %s" %
				(self.settings["EPREFIX"],),
				noiselevel=-1, level=logging.ERROR)
			self.wait()
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
			self._build_prefix.lstrip(os.sep))
		if not os.path.isdir(build_d):
			# Assume this is a virtual package or something.
			shutil.rmtree(self._image_dir)
			ensure_dirs(self.settings["ED"])
		else:
			os.rename(build_d, image_tmp_dir)
			shutil.rmtree(self._image_dir)
			ensure_dirs(os.path.dirname(self.settings["ED"].rstrip(os.sep)))
			os.rename(image_tmp_dir, self.settings["ED"])

		self.wait()

	def _unlock_builddir(self):
		if self.opts.pretend or self.opts.fetchonly:
			return
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		self._build_dir.unlock()

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
		self.settings.pop("PORTAGE_BINPKG_FILE", None)
		self._unlock_builddir()
		if task.returncode == os.EX_OK and \
			'binpkg-logs' not in self.settings.features and \
			self.settings.get("PORTAGE_LOG_FILE"):
			try:
				os.unlink(self.settings["PORTAGE_LOG_FILE"])
			except OSError:
				pass
