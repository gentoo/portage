from _emerge.EbuildPhase import EbuildPhase
from _emerge.TaskSequence import TaskSequence
from _emerge.CompositeTask import CompositeTask
# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage
class EbuildExecuter(CompositeTask):

	__slots__ = ("pkg", "scheduler", "settings") + ("_tree",)

	_phases = ("prepare", "configure", "compile", "test", "install")

	_live_eclasses = frozenset([
		"bzr",
		"cvs",
		"darcs",
		"git",
		"mercurial",
		"subversion"
	])

	def _start(self):
		self._tree = "porttree"
		pkg = self.pkg
		phase = "clean"
		clean_phase = EbuildPhase(background=self.background, pkg=pkg, phase=phase,
			scheduler=self.scheduler, settings=self.settings, tree=self._tree)
		self._start_task(clean_phase, self._clean_phase_exit)

	def _clean_phase_exit(self, clean_phase):

		if self._default_exit(clean_phase) != os.EX_OK:
			self.wait()
			return

		pkg = self.pkg
		scheduler = self.scheduler
		settings = self.settings
		cleanup = 1

		# This initializes PORTAGE_LOG_FILE.
		portage.prepare_build_dirs(pkg.root, settings, cleanup)

		setup_phase = EbuildPhase(background=self.background,
			pkg=pkg, phase="setup", scheduler=scheduler,
			settings=settings, tree=self._tree)

		setup_phase.addExitListener(self._setup_exit)
		self._current_task = setup_phase
		self.scheduler.scheduleSetup(setup_phase)

	def _setup_exit(self, setup_phase):

		if self._default_exit(setup_phase) != os.EX_OK:
			self.wait()
			return

		unpack_phase = EbuildPhase(background=self.background,
			pkg=self.pkg, phase="unpack", scheduler=self.scheduler,
			settings=self.settings, tree=self._tree)

		if self._live_eclasses.intersection(self.pkg.inherited):
			# Serialize $DISTDIR access for live ebuilds since
			# otherwise they can interfere with eachother.

			unpack_phase.addExitListener(self._unpack_exit)
			self._current_task = unpack_phase
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
		if eapi in ("0", "1"):
			# skip src_prepare and src_configure
			phases = phases[2:]

		for phase in phases:
			ebuild_phases.add(EbuildPhase(background=self.background,
				pkg=self.pkg, phase=phase, scheduler=self.scheduler,
				settings=self.settings, tree=self._tree))

		self._start_task(ebuild_phases, self._default_final_exit)

