# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import gzip
import io
import sys
import tempfile

from _emerge.AsynchronousLock import AsynchronousLock
from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.EbuildProcess import EbuildProcess
from _emerge.CompositeTask import CompositeTask
from portage.package.ebuild.prepare_build_dirs import _prepare_workdir
from portage.util import writemsg

try:
	from portage.xml.metadata import MetaDataXML
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# http://bugs.python.org/issue14988
	MetaDataXML = None

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.elog:messages@elog_messages',
	'portage.package.ebuild.doebuild:_check_build_log,' + \
		'_post_phase_cmds,_post_phase_userpriv_perms,' + \
		'_post_src_install_soname_symlinks,' + \
		'_post_src_install_uid_fix,_postinst_bsdflags,' + \
		'_post_src_install_write_metadata,' + \
		'_preinst_bsdflags'
)
from portage import os
from portage import _encodings
from portage import _unicode_encode

class EbuildPhase(CompositeTask):

	__slots__ = ("actionmap", "phase", "settings") + \
		("_ebuild_lock",)

	# FEATURES displayed prior to setup phase
	_features_display = (
		"ccache", "compressdebug", "distcc", "distcc-pump", "fakeroot",
		"installsources", "keeptemp", "keepwork", "nostrip",
		"preserve-libs", "sandbox", "selinux", "sesandbox",
		"splitdebug", "suidctl", "test", "userpriv",
		"usersandbox"
	)

	# Locked phases
	_locked_phases = ("setup", "preinst", "postinst", "prerm", "postrm")

	def _start(self):

		need_builddir = self.phase not in EbuildProcess._phases_without_builddir

		if need_builddir:
			phase_completed_file = os.path.join(
				self.settings['PORTAGE_BUILDDIR'],
				".%sed" % self.phase.rstrip('e'))
			if not os.path.exists(phase_completed_file):
				# If the phase is really going to run then we want
				# to eliminate any stale elog messages that may
				# exist from a previous run.
				try:
					os.unlink(os.path.join(self.settings['T'],
						'logging', self.phase))
				except OSError:
					pass

		if self.phase in ('nofetch', 'pretend', 'setup'):

			use = self.settings.get('PORTAGE_BUILT_USE')
			if use is None:
				use = self.settings['PORTAGE_USE']

			maint_str = ""
			upstr_str = ""
			metadata_xml_path = os.path.join(os.path.dirname(self.settings['EBUILD']), "metadata.xml")
			if MetaDataXML is not None and os.path.isfile(metadata_xml_path):
				herds_path = os.path.join(self.settings['PORTDIR'],
					'metadata/herds.xml')
				try:
					metadata_xml = MetaDataXML(metadata_xml_path, herds_path)
					maint_str = metadata_xml.format_maintainer_string()
					upstr_str = metadata_xml.format_upstream_string()
				except SyntaxError:
					maint_str = "<invalid metadata.xml>"

			msg = []
			msg.append("Package:    %s" % self.settings.mycpv)
			if self.settings.get('PORTAGE_REPO_NAME'):
				msg.append("Repository: %s" % self.settings['PORTAGE_REPO_NAME'])
			if maint_str:
				msg.append("Maintainer: %s" % maint_str)
			if upstr_str:
				msg.append("Upstream:   %s" % upstr_str)

			msg.append("USE:        %s" % use)
			relevant_features = []
			enabled_features = self.settings.features
			for x in self._features_display:
				if x in enabled_features:
					relevant_features.append(x)
			if relevant_features:
				msg.append("FEATURES:   %s" % " ".join(relevant_features))

			# Force background=True for this header since it's intended
			# for the log and it doesn't necessarily need to be visible
			# elsewhere.
			self._elog('einfo', msg, background=True)

		if self.phase == 'package':
			if 'PORTAGE_BINPKG_TMPFILE' not in self.settings:
				self.settings['PORTAGE_BINPKG_TMPFILE'] = \
					os.path.join(self.settings['PKGDIR'],
					self.settings['CATEGORY'], self.settings['PF']) + '.tbz2'

		if self.phase in ("pretend", "prerm"):
			env_extractor = BinpkgEnvExtractor(background=self.background,
				scheduler=self.scheduler, settings=self.settings)
			if env_extractor.saved_env_exists():
				self._start_task(env_extractor, self._env_extractor_exit)
				return
			# If the environment.bz2 doesn't exist, then ebuild.sh will
			# source the ebuild as a fallback.

		self._start_lock()

	def _env_extractor_exit(self, env_extractor):
		if self._default_exit(env_extractor) != os.EX_OK:
			self.wait()
			return

		self._start_lock()

	def _start_lock(self):
		if (self.phase in self._locked_phases and
			"ebuild-locks" in self.settings.features):
			eroot = self.settings["EROOT"]
			lock_path = os.path.join(eroot, portage.VDB_PATH + "-ebuild")
			if os.access(os.path.dirname(lock_path), os.W_OK):
				self._ebuild_lock = AsynchronousLock(path=lock_path,
					scheduler=self.scheduler)
				self._start_task(self._ebuild_lock, self._lock_exit)
				return

		self._start_ebuild()

	def _lock_exit(self, ebuild_lock):
		if self._default_exit(ebuild_lock) != os.EX_OK:
			self.wait()
			return
		self._start_ebuild()

	def _start_ebuild(self):

		# Don't open the log file during the clean phase since the
		# open file can result in an nfs lock on $T/build.log which
		# prevents the clean phase from removing $T.
		logfile = None
		if self.phase not in ("clean", "cleanrm") and \
			self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
			logfile = self.settings.get("PORTAGE_LOG_FILE")

		fd_pipes = None
		if not self.background and self.phase == 'nofetch':
			# All the pkg_nofetch output goes to stderr since
			# it's considered to be an error message.
			fd_pipes = {1 : sys.stderr.fileno()}

		ebuild_process = EbuildProcess(actionmap=self.actionmap,
			background=self.background, fd_pipes=fd_pipes, logfile=logfile,
			phase=self.phase, scheduler=self.scheduler,
			settings=self.settings)

		self._start_task(ebuild_process, self._ebuild_exit)

	def _ebuild_exit(self, ebuild_process):

		if self._ebuild_lock is not None:
			self._ebuild_lock.unlock()
			self._ebuild_lock = None

		fail = False
		if self._default_exit(ebuild_process) != os.EX_OK:
			if self.phase == "test" and \
				"test-fail-continue" in self.settings.features:
				pass
			else:
				fail = True

		if not fail:
			self.returncode = None

		logfile = None
		if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
			logfile = self.settings.get("PORTAGE_LOG_FILE")

		if self.phase == "install":
			out = io.StringIO()
			_check_build_log(self.settings, out=out)
			msg = out.getvalue()
			self.scheduler.output(msg, log_path=logfile)

		if fail:
			self._die_hooks()
			return

		settings = self.settings
		_post_phase_userpriv_perms(settings)

		if self.phase == "unpack":
			# Bump WORKDIR timestamp, in case tar gave it a timestamp
			# that will interfere with distfiles / WORKDIR timestamp
			# comparisons as reported in bug #332217. Also, fix
			# ownership since tar can change that too.
			os.utime(settings["WORKDIR"], None)
			_prepare_workdir(settings)
		elif self.phase == "install":
			out = io.StringIO()
			_post_src_install_write_metadata(settings)
			_post_src_install_uid_fix(settings, out)
			msg = out.getvalue()
			if msg:
				self.scheduler.output(msg, log_path=logfile)
		elif self.phase == "preinst":
			_preinst_bsdflags(settings)
		elif self.phase == "postinst":
			_postinst_bsdflags(settings)

		post_phase_cmds = _post_phase_cmds.get(self.phase)
		if post_phase_cmds is not None:
			if logfile is not None and self.phase in ("install",):
				# Log to a temporary file, since the code we are running
				# reads PORTAGE_LOG_FILE for QA checks, and we want to
				# avoid annoying "gzip: unexpected end of file" messages
				# when FEATURES=compress-build-logs is enabled.
				fd, logfile = tempfile.mkstemp()
				os.close(fd)
			post_phase = MiscFunctionsProcess(background=self.background,
				commands=post_phase_cmds, logfile=logfile, phase=self.phase,
				scheduler=self.scheduler, settings=settings)
			self._start_task(post_phase, self._post_phase_exit)
			return

		# this point is not reachable if there was a failure and
		# we returned for die_hooks above, so returncode must
		# indicate success (especially if ebuild_process.returncode
		# is unsuccessful and test-fail-continue came into play)
		self.returncode = os.EX_OK
		self._current_task = None
		self.wait()

	def _post_phase_exit(self, post_phase):

		self._assert_current(post_phase)

		log_path = None
		if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
			log_path = self.settings.get("PORTAGE_LOG_FILE")

		if post_phase.logfile is not None and \
			post_phase.logfile != log_path:
			# We were logging to a temp file (see above), so append
			# temp file to main log and remove temp file.
			self._append_temp_log(post_phase.logfile, log_path)

		if self._final_exit(post_phase) != os.EX_OK:
			writemsg("!!! post %s failed; exiting.\n" % self.phase,
				noiselevel=-1)
			self._die_hooks()
			return

		if self.phase == "install":
			out = io.StringIO()
			_post_src_install_soname_symlinks(self.settings, out)
			msg = out.getvalue()
			if msg:
				self.scheduler.output(msg, log_path=log_path)

		self._current_task = None
		self.wait()
		return

	def _append_temp_log(self, temp_log, log_path):

		temp_file = open(_unicode_encode(temp_log,
			encoding=_encodings['fs'], errors='strict'), 'rb')

		log_file, log_file_real = self._open_log(log_path)

		for line in temp_file:
			log_file.write(line)

		temp_file.close()
		log_file.close()
		if log_file_real is not log_file:
			log_file_real.close()
		os.unlink(temp_log)

	def _open_log(self, log_path):

		f = open(_unicode_encode(log_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='ab')
		f_real = f

		if log_path.endswith('.gz'):
			f =  gzip.GzipFile(filename='', mode='ab', fileobj=f)

		return (f, f_real)

	def _die_hooks(self):
		self.returncode = None
		phase = 'die_hooks'
		die_hooks = MiscFunctionsProcess(background=self.background,
			commands=[phase], phase=phase,
			scheduler=self.scheduler, settings=self.settings)
		self._start_task(die_hooks, self._die_hooks_exit)

	def _die_hooks_exit(self, die_hooks):
		if self.phase != 'clean' and \
			'noclean' not in self.settings.features and \
			'fail-clean' in self.settings.features:
			self._default_exit(die_hooks)
			self._fail_clean()
			return
		self._final_exit(die_hooks)
		self.returncode = 1
		self.wait()

	def _fail_clean(self):
		self.returncode = None
		portage.elog.elog_process(self.settings.mycpv, self.settings)
		phase = "clean"
		clean_phase = EbuildPhase(background=self.background,
			phase=phase, scheduler=self.scheduler, settings=self.settings)
		self._start_task(clean_phase, self._fail_clean_exit)
		return

	def _fail_clean_exit(self, clean_phase):
		self._final_exit(clean_phase)
		self.returncode = 1
		self.wait()

	def _elog(self, elog_funcname, lines, background=None):
		if background is None:
			background = self.background
		out = io.StringIO()
		phase = self.phase
		elog_func = getattr(elog_messages, elog_funcname)
		global_havecolor = portage.output.havecolor
		try:
			portage.output.havecolor = \
				self.settings.get('NOCOLOR', 'false').lower() in ('no', 'false')
			for line in lines:
				elog_func(line, phase=phase, key=self.settings.mycpv, out=out)
		finally:
			portage.output.havecolor = global_havecolor
		msg = out.getvalue()
		if msg:
			log_path = None
			if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
				log_path = self.settings.get("PORTAGE_LOG_FILE")
			self.scheduler.output(msg, log_path=log_path,
				background=background)
