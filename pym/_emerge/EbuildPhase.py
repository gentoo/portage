# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.EbuildProcess import EbuildProcess
from _emerge.CompositeTask import CompositeTask
from portage.util import writemsg, writemsg_stdout
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_check_build_log,' + \
		'_post_phase_cmds,_post_phase_userpriv_perms,' + \
		'_post_src_install_chost_fix,' + \
		'_post_src_install_uid_fix'
)
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import codecs

class EbuildPhase(CompositeTask):

	__slots__ = ("actionmap", "phase", "settings")

	def _start(self):

		if self.phase == 'prerm':
			env_extractor = BinpkgEnvExtractor(background=self.background,
				scheduler=self.scheduler, settings=self.settings)
			if env_extractor.saved_env_exists():
				self._start_task(env_extractor, self._env_extractor_exit)
				return
			# If the environment.bz2 doesn't exist, then ebuild.sh will
			# source the ebuild as a fallback.

		self._start_ebuild()

	def _env_extractor_exit(self, env_extractor):
		if self._default_exit(env_extractor) != os.EX_OK:
			self._unlock_builddir()
			self.wait()
			return

		self._start_ebuild()

	def _start_ebuild(self):

		# Don't open the log file during the clean phase since the
		# open file can result in an nfs lock on $T/build.log which
		# prevents the clean phase from removing $T.
		logfile = self.settings.get("PORTAGE_LOG_FILE")
		if self.phase in ("clean", "cleanrm"):
			logfile = None

		ebuild_process = EbuildProcess(actionmap=self.actionmap,
			background=self.background, logfile=logfile,
			phase=self.phase, scheduler=self.scheduler,
			settings=self.settings)

		self._start_task(ebuild_process, self._ebuild_exit)

	def _ebuild_exit(self, ebuild_process):

		fail = False
		if self._default_exit(ebuild_process) != os.EX_OK:
			if self.phase == "test" and \
				"test-fail-continue" in self.settings.features:
				pass
			else:
				fail = True

		if not fail:
			self.returncode = None

		if self.phase == "install":
			out = portage.StringIO()
			_check_build_log(self.settings, out=out)
			msg = _unicode_decode(out.getvalue(),
				encoding=_encodings['content'], errors='replace')
			self.scheduler.output(msg,
				log_path=self.settings.get("PORTAGE_LOG_FILE"))

		if fail:
			self._die_hooks()
			return

		settings = self.settings
		_post_phase_userpriv_perms(settings)

		if self.phase == "install":
			out = portage.StringIO()
			_post_src_install_chost_fix(settings)
			_post_src_install_uid_fix(settings, out)
			msg = _unicode_decode(out.getvalue(),
				encoding=_encodings['content'], errors='replace')
			if msg:
				self.scheduler.output(msg,
					log_path=self.settings.get("PORTAGE_LOG_FILE"))

		post_phase_cmds = _post_phase_cmds.get(self.phase)
		if post_phase_cmds is not None:
			post_phase = MiscFunctionsProcess(background=self.background,
				commands=post_phase_cmds, phase=self.phase,
				scheduler=self.scheduler, settings=settings)
			self._start_task(post_phase, self._post_phase_exit)
			return

		self.returncode = ebuild_process.returncode
		self._current_task = None
		self.wait()

	def _post_phase_exit(self, post_phase):
		if self._final_exit(post_phase) != os.EX_OK:
			writemsg("!!! post %s failed; exiting.\n" % self.phase,
				noiselevel=-1)
			self._die_hooks()
			return
		self._current_task = None
		self.wait()
		return

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
