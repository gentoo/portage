# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from types import SimpleNamespace

from _emerge.Scheduler import Scheduler
from portage.tests import TestCase


class _Phase:
    def __init__(self, runs_code):
        self.runs_code = runs_code
        self.started = False

    def _phase_runs_code(self):
        return self.runs_code

    def start(self):
        self.started = True


class ScheduleSetupTestCase(TestCase):
    """
    Scheduler._schedule_setup queues a setup phase only if it runs ebuild
    code.
    """

    def _schedule(self, phase, parallel_install):
        queued = {"merge": [], "ebuild_locks": []}
        scheduler = SimpleNamespace(
            _task_queues=SimpleNamespace(
                merge=SimpleNamespace(
                    max_jobs=4 if parallel_install else 1,
                    add=queued["merge"].append,
                ),
                ebuild_locks=SimpleNamespace(add=queued["ebuild_locks"].append),
            ),
            settings=SimpleNamespace(features={"ebuild-locks"}),
            _schedule=lambda: None,
        )
        Scheduler._schedule_setup(scheduler, phase)
        return queued

    def test_runs_code(self):
        for parallel_install, queue in ((True, "ebuild_locks"), (False, "merge")):
            phase = _Phase(True)
            queued = self._schedule(phase, parallel_install)
            self.assertEqual(queued[queue], [phase])
            self.assertFalse(phase.started)

    def test_runs_no_code(self):
        for parallel_install in (True, False):
            phase = _Phase(False)
            queued = self._schedule(phase, parallel_install)
            self.assertEqual(queued, {"merge": [], "ebuild_locks": []})
            self.assertTrue(phase.started)
