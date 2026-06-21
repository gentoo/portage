# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import json
import os
import tempfile
from types import SimpleNamespace

from portage.tests import TestCase

from _emerge._observability import (
    ObservabilityMonitor,
    build_snapshot,
    format_snapshots,
    read_snapshots,
    status_dir,
)


class _Pkg:
    def __init__(self, cpv, built=False, operation="merge"):
        self.cpv = cpv
        self.category, self.pf = cpv.split("/", 1)
        self.root = "/"
        self.built = built
        self.operation = operation


class EbuildBuild:
    def __init__(self, pkg, pid=None):
        self.pkg = pkg
        self.pid = pid


class PackageMerge:
    def __init__(self, build):
        self.merge = build
        self.pkg = build.pkg


class _Settings(dict):
    """Minimal stand-in for portage config: dict plus a ``features`` set."""

    def __init__(self, features=(), **items):
        super().__init__(items)
        self.features = set(features)


def _make_scheduler(features=("observability",), eprefix="", tasks=None):
    tasks = tasks or []
    running = {id(t): t for t in tasks}
    return SimpleNamespace(
        settings=_Settings(features=features, EPREFIX=eprefix),
        _running_tasks=running,
        _jobs=sum(1 for t in tasks if isinstance(t, EbuildBuild)),
        _max_jobs=4,
        _failed_pkgs=[],
        _merge_wait_queue=[],
        _task_queues=SimpleNamespace(merge=[]),
        _status_display=SimpleNamespace(curval=1, maxval=5),
        _event_loop=None,
    )


class ObservabilitySnapshotTestCase(TestCase):
    def test_status_dir_default_is_absolute(self):
        self.assertTrue(status_dir("").startswith("/"))
        self.assertEqual(status_dir("/p"), "/p/run/portage")

    def test_build_snapshot_structure(self):
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=4321)
        merge = PackageMerge(EbuildBuild(_Pkg("sys-apps/bar-3")))
        sched = _make_scheduler(tasks=[build, merge])
        monitor = ObservabilityMonitor(sched)
        monitor.note_task_started(build)
        monitor.note_task_started(merge)
        monitor.note_phase("dev-libs/foo-1.2", "compile")

        snap = build_snapshot(monitor)

        self.assertEqual(snap["schema"], 1)
        self.assertEqual(snap["jobs"]["completed"], 1)
        self.assertEqual(snap["jobs"]["total"], 5)
        self.assertEqual(len(snap["tasks"]), 2)

        by_cpv = {t["cpv"]: t for t in snap["tasks"]}
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["phase"], "compile")
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["pid"], 4321)
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["kind"], "build")
        self.assertEqual(by_cpv["sys-apps/bar-3"]["kind"], "merge")

    def test_disabled_when_feature_absent(self):
        sched = _make_scheduler(features=(), tasks=[])
        monitor = ObservabilityMonitor(sched)
        self.assertFalse(monitor.enabled)
        # All hooks must be safe no-ops.
        monitor.note_task_started(object())
        monitor.note_phase("a/b-1", "compile")
        monitor.update(force=True)
        monitor.close()

    def test_write_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build])
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            monitor.note_phase("dev-libs/foo-1.2", "install")
            monitor.update(force=True)

            path = os.path.join(status_dir(tmp), f"emerge-{os.getpid()}.json")
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf_8") as f:
                snap = json.load(f)
            self.assertEqual(snap["tasks"][0]["cpv"], "dev-libs/foo-1.2")

            # read_snapshots finds it (our own PID is alive).
            found = read_snapshots(tmp)
            self.assertEqual(len(found), 1)
            self.assertIn("dev-libs/foo-1.2", format_snapshots(found))

            monitor.close()
            self.assertFalse(os.path.exists(path))

    def test_stale_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            # Use an implausible PID that is not running.
            with open(os.path.join(d, "emerge-2147480000.json"), "w") as f:
                json.dump({"emerge_pid": 2147480000, "tasks": []}, f)
            self.assertEqual(read_snapshots(tmp), [])
