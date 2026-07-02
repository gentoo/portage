# Copyright 1999-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildPhase import EbuildPhase
from _emerge.TaskSequence import TaskSequence
from _emerge.CompositeTask import CompositeTask
import os
import portage

from portage.eapi import (
    eapi_has_src_prepare_and_src_configure,
    eapi_exports_replace_vars,
)


class EbuildExecuter(CompositeTask):
    __slots__ = ("pkg", "settings")

    _phases = ("prepare", "configure", "compile", "test", "install")

    # src_* phases whose default (EAPI-provided) implementations are no-ops
    # for a package with no source to act on. src_install is intentionally
    # excluded: it creates ${D} and drives the install-time QA checks, so it
    # always runs. Excluding src_install also sidesteps declarative variables
    # such as DOCS, which can reference FILESDIR (present even for sourceless
    # packages) and thus may do real work in the default src_install body.
    _skippable_src_phases = frozenset(
        ("unpack", "prepare", "configure", "compile", "test")
    )

    def _can_skip_source_phases(self):
        """
        Return True if unpack and the src_prepare/configure/compile/test
        phases would only run no-op default bodies and can be skipped
        entirely (avoiding one ebuild.sh subprocess spawn per phase).

        This holds when the package has no source to unpack (empty SRC_URI,
        hence empty ${A}, hence nothing for the default phase bodies to
        configure/compile/install) and defines none of those phases itself.
        Empty/virtual packages (DEFINED_PHASES=-) are the motivating case.
        """
        settings = self.settings
        # The ebuild command's manual mode relies on running each phase.
        if "noauto" in settings.features:
            return False
        # Live ebuilds fetch their source in src_unpack regardless of
        # SRC_URI, so never skip unpack for them.
        if "live" in settings.get("PROPERTIES", "").split():
            return False

        metadata = self.pkg._metadata
        if metadata.get("SRC_URI", "").strip():
            return False
        defined_phases = frozenset(metadata.get("DEFINED_PHASES", "").split())
        if defined_phases.intersection(self._skippable_src_phases):
            return False

        # pkg_setup (which has run by now) records whether PATCHES is set;
        # the default src_prepare would apply it, so don't skip in that case.
        if os.path.exists(os.path.join(settings["PORTAGE_BUILDDIR"], ".src_patches")):
            return False

        return True

    def _start(self):
        pkg = self.pkg
        scheduler = self.scheduler
        settings = self.settings
        cleanup = 0
        portage.prepare_build_dirs(pkg.root, settings, cleanup)

        if eapi_exports_replace_vars(settings["EAPI"]):
            vardb = pkg.root_config.trees["vartree"].dbapi
            settings["REPLACING_VERSIONS"] = " ".join(
                {
                    portage.versions.cpv_getversion(match)
                    for match in vardb.match(pkg.slot_atom) + vardb.match("=" + pkg.cpv)
                }
            )

        setup_phase = EbuildPhase(
            background=self.background,
            phase="setup",
            scheduler=scheduler,
            settings=settings,
        )

        setup_phase.addExitListener(self._setup_exit)
        self._task_queued(setup_phase)
        self.scheduler.scheduleSetup(setup_phase)

    def _setup_exit(self, setup_phase):
        if self._default_exit(setup_phase) != os.EX_OK:
            self.wait()
            return

        if self._can_skip_source_phases():
            # No source and no ebuild-defined src_* phases: unpack and
            # src_prepare/configure/compile/test would only run no-op
            # default bodies. Skip straight to src_install (which creates
            # ${D} and runs the install QA checks). WORKDIR was already
            # created by prepare_build_dirs(), so src_install can cd into
            # it as usual.
            self._start_phases(("install",))
            return

        unpack_phase = EbuildPhase(
            background=self.background,
            phase="unpack",
            scheduler=self.scheduler,
            settings=self.settings,
        )

        if "live" in self.settings.get("PROPERTIES", "").split():
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

        phases = self._phases
        eapi = self.pkg.eapi
        if not eapi_has_src_prepare_and_src_configure(eapi):
            # skip src_prepare and src_configure
            phases = phases[2:]

        self._start_phases(phases)

    def _start_phases(self, phases):
        ebuild_phases = TaskSequence(scheduler=self.scheduler)

        for phase in phases:
            ebuild_phases.add(
                EbuildPhase(
                    background=self.background,
                    phase=phase,
                    scheduler=self.scheduler,
                    settings=self.settings,
                )
            )

        self._start_task(ebuild_phases, self._default_final_exit)
