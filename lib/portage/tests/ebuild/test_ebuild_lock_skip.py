# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

import portage
from _emerge.EbuildPhase import EbuildPhase
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class _Phase(EbuildPhase):
    """Record what _start_lock starts instead of running it."""

    __slots__ = ("started",)

    def _start_task(self, task, exit_handler):
        self.started.append(task)

    def _start_ebuild(self):
        self.started.append(None)


class EbuildLockSkipTestCase(TestCase):
    def setUp(self):
        self.playground = ResolverPlayground()

    def tearDown(self):
        self.playground.cleanup()

    def _abs(self, path):
        return os.path.join(self.playground.eroot, path)

    def _write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def _phase(self, phase, defined_phases):
        settings = portage.config(clone=self.playground.settings)
        settings.features.add("ebuild-locks")
        settings.mycpv = "dev-libs/A-1-r2"
        # Point the hook files at the playground, not at the host.
        settings["PORTAGE_BASHRC"] = self._abs("bashrc")
        settings["PM_EBUILD_HOOK_DIR"] = self._abs("hooks")
        settings["T"] = self._abs("temp")
        settings.configdict["pkg"]["DEFINED_PHASES"] = defined_phases
        return _Phase(phase=phase, settings=settings, started=[])

    def assertLocks(self, phase, expected):
        phase._start_lock()
        # Exactly one task starts: the lock, or the ebuild (recorded as
        # None) if no lock was taken.
        self.assertEqual(phase._ebuild_lock is not None, expected)
        self.assertEqual(phase.started, [phase._ebuild_lock])

    def test_phase_defined(self):
        self.assertLocks(self._phase("postinst", "install postinst"), True)

    def test_phase_not_defined(self):
        self.assertLocks(self._phase("postinst", "compile install"), False)
        self.assertLocks(self._phase("preinst", "-"), False)

    def test_no_defined_phases(self):
        self.assertLocks(self._phase("postinst", ""), True)

    def test_hook_mentioning_the_phase(self):
        # test_unmerge_phase_skip covers which hook files count.
        self._write(self._abs("bashrc"), "post_pkg_preinst() { :; }\n")
        self.assertLocks(self._phase("preinst", "install"), True)
        self.assertLocks(self._phase("postinst", "install"), False)

    def test_hook_in_saved_environment(self):
        # A hook function from the build host of a binary package.
        self._write(self._abs("temp/environment"), "post_pkg_postinst () \n{ :; }\n")
        self.assertLocks(self._phase("postinst", "-"), True)
        self.assertLocks(self._phase("preinst", "-"), False)
