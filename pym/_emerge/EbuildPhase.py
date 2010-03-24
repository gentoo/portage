# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.EbuildProcess import EbuildProcess
from _emerge.CompositeTask import CompositeTask
from portage.package.ebuild.doebuild import _check_build_log, \
	_post_phase_cmds, _post_src_install_chost_fix, \
	_post_src_install_uid_fix
from portage.util import writemsg, writemsg_stdout
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import codecs

class EbuildPhase(CompositeTask):

	__slots__ = ("background", "pkg", "phase",
		"scheduler", "settings", "tree")

	def _start(self):

		ebuild_process = EbuildProcess(background=self.background,
			pkg=self.pkg, phase=self.phase, scheduler=self.scheduler,
			settings=self.settings, tree=self.tree)

		self._start_task(ebuild_process, self._ebuild_exit)

	def _ebuild_exit(self, ebuild_process):

		if self.phase == "install":
			out = portage.StringIO()
			log_path = self.settings.get("PORTAGE_LOG_FILE")
			log_file = None
			if log_path is not None:
				log_file = codecs.open(_unicode_encode(log_path,
					encoding=_encodings['fs'], errors='strict'),
					mode='a', encoding=_encodings['content'], errors='replace')
			try:
				_check_build_log(self.settings, out=out)
				msg = _unicode_decode(out.getvalue(),
					encoding=_encodings['content'], errors='replace')
				if msg:
					if not self.background:
						writemsg_stdout(msg, noiselevel=-1)
					if log_file is not None:
						log_file.write(msg)
			finally:
				if log_file is not None:
					log_file.close()

		if self._default_exit(ebuild_process) != os.EX_OK:
			self._die_hooks()
			return

		settings = self.settings

		if self.phase == "install":
			out = None
			log_path = self.settings.get("PORTAGE_LOG_FILE")
			log_file = None
			if self.background and log_path is not None:
				log_file = codecs.open(_unicode_encode(log_path,
					encoding=_encodings['fs'], errors='strict'),
					mode='a', encoding=_encodings['content'], errors='replace')
				out = log_file
			_post_src_install_chost_fix(settings)
			_post_src_install_uid_fix(settings, out=out)
			if log_file is not None:
				log_file.close()

		post_phase_cmds = _post_phase_cmds.get(self.phase)
		if post_phase_cmds is not None:
			post_phase = MiscFunctionsProcess(background=self.background,
				commands=post_phase_cmds, phase=self.phase, pkg=self.pkg,
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
			commands=[phase], phase=phase, pkg=self.pkg,
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
		portage.elog.elog_process(self.pkg.cpv, self.settings)
		phase = "clean"
		clean_phase = EbuildPhase(background=self.background,
			pkg=self.pkg, phase=phase,
			scheduler=self.scheduler, settings=self.settings,
			tree=self.tree)
		self._start_task(clean_phase, self._fail_clean_exit)
		return

	def _fail_clean_exit(self, clean_phase):
		self._final_exit(clean_phase)
		self.returncode = 1
		self.wait()
