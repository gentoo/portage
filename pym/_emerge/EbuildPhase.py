# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.EbuildProcess import EbuildProcess
from _emerge.CompositeTask import CompositeTask
from portage.util import writemsg
try:
	import portage
except ImportError:
	from os import path as osp
	import sys
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
import codecs
import os
class EbuildPhase(CompositeTask):

	__slots__ = ("background", "pkg", "phase",
		"scheduler", "settings", "tree")

	_post_phase_cmds = portage._post_phase_cmds

	def _start(self):

		ebuild_process = EbuildProcess(background=self.background,
			pkg=self.pkg, phase=self.phase, scheduler=self.scheduler,
			settings=self.settings, tree=self.tree)

		self._start_task(ebuild_process, self._ebuild_exit)

	def _ebuild_exit(self, ebuild_process):

		if self.phase == "install":
			out = None
			log_path = self.settings.get("PORTAGE_LOG_FILE")
			log_file = None
			if self.background and log_path is not None:
				log_file = codecs.open(log_path, mode='a',
					encoding='utf_8', errors='replace')
				out = log_file
			try:
				portage._check_build_log(self.settings, out=out)
			finally:
				if log_file is not None:
					log_file.close()

		if self._default_exit(ebuild_process) != os.EX_OK:
			self.wait()
			return

		settings = self.settings

		if self.phase == "install":
			portage._post_src_install_chost_fix(settings)
			portage._post_src_install_uid_fix(settings)

		post_phase_cmds = self._post_phase_cmds.get(self.phase)
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
		self._current_task = None
		self.wait()
		return

