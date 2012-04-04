# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildPhase import EbuildPhase
from _emerge.TaskSequence import TaskSequence
from _emerge.CompositeTask import CompositeTask
import portage
from portage import os
from portage.eapi import eapi_has_src_prepare_and_src_configure, \
	eapi_exports_replace_vars
from portage.package.ebuild.doebuild import _prepare_fake_distdir

class EbuildExecuter(CompositeTask):

	__slots__ = ("pkg", "settings")

	_phases = ("prepare", "configure", "compile", "test", "install")

	_live_eclasses = frozenset([
		"bzr",
		"cvs",
		"darcs",
		"git",
		"git-2",
		"mercurial",
		"subversion",
		"tla",
	])

	def _start(self):
		pkg = self.pkg
		scheduler = self.scheduler
		settings = self.settings
		cleanup = 0
		portage.prepare_build_dirs(pkg.root, settings, cleanup)

		alist = settings.configdict["pkg"].get("A", "").split()
		_prepare_fake_distdir(settings, alist)

		if eapi_exports_replace_vars(settings['EAPI']):
			vardb = pkg.root_config.trees['vartree'].dbapi
			settings["REPLACING_VERSIONS"] = " ".join(
				set(portage.versions.cpv_getversion(match) \
					for match in vardb.match(pkg.slot_atom) + \
					vardb.match('='+pkg.cpv)))

		setup_phase = EbuildPhase(background=self.background,
			phase="setup", scheduler=scheduler,
			settings=settings)

		setup_phase.addExitListener(self._setup_exit)
		self._task_queued(setup_phase)
		self.scheduler.scheduleSetup(setup_phase)

	def _setup_exit(self, setup_phase):

		if self._default_exit(setup_phase) != os.EX_OK:
			self.wait()
			return

		unpack_phase = EbuildPhase(background=self.background,
			phase="unpack", scheduler=self.scheduler,
			settings=self.settings)

		if self._live_eclasses.intersection(self.pkg.inherited):
			# Serialize $DISTDIR access for live ebuilds since
			# otherwise they can interfere with eachother.

			unpack_phase.addExitListener(self._unpack_exit)
			self._task_queued(unpack_phase)
			self.scheduler.scheduleUnpack(unpack_phase)

		else:
			self._start_task(unpack_phase, self._unpack_exit)

	def _unpack_exit(self, unpack_phase):

		if self._default_exit(unpack_phase) != os.EX_OK:
			self.wait()
			return

		ebuild_phases = TaskSequence(scheduler=self.scheduler)

		pkg = self.pkg
		phases = self._phases
		eapi = pkg.metadata["EAPI"]
		if not eapi_has_src_prepare_and_src_configure(eapi):
			# skip src_prepare and src_configure
			phases = phases[2:]

		for phase in phases:
			ebuild_phases.add(EbuildPhase(background=self.background,
				phase=phase, scheduler=self.scheduler,
				settings=self.settings))

		self._start_task(ebuild_phases, self._default_final_exit)

