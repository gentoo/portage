# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio
import json
import os
import tempfile
from types import SimpleNamespace

from _emerge._observability import (
    ObservabilityMonitor,
    build_snapshot,
    format_snapshots,
    missing_feature_hint,
    read_snapshots,
    status_dir,
)
from _emerge.PackageMerge import PackageMerge as _RealPackageMerge

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop


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


class PackageMerge(_RealPackageMerge):
    __slots__ = ()

    def __init__(self, build):
        self.merge = build


class _Settings(dict):
    """Minimal stand-in for portage config: dict plus a ``features`` set."""

    def __init__(self, features=(), **items):
        super().__init__(items)
        self.features = set(features)


class _FakeLoop:
    """Stand-in for the scheduler's event loop, with call_later run on demand."""

    def __init__(self):
        self.calls = []

    def call_later(self, delay, callback):
        entry = [delay, callback]
        self.calls.append(entry)
        return SimpleNamespace(cancel=lambda: self._cancel(entry))

    def _cancel(self, entry):
        if entry in self.calls:
            self.calls.remove(entry)

    def run_pending(self):
        pending, self.calls = self.calls, []
        for _delay, callback in pending:
            callback()


def _make_scheduler(features=("observability",), eprefix="", tasks=None, loop=None):
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
        _event_loop=loop if loop is not None else _FakeLoop(),
        _cgroup=None,
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

        self.assertEqual(snap["type"], "snapshot")
        self.assertEqual(snap["schema"], 1)
        self.assertEqual(snap["jobs"]["completed"], 1)
        self.assertEqual(snap["jobs"]["total"], 5)
        self.assertEqual(len(snap["tasks"]), 2)

        by_cpv = {t["cpv"]: t for t in snap["tasks"]}
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["phase"], "compile")
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["pid"], 4321)
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["kind"], "build")
        self.assertEqual(by_cpv["sys-apps/bar-3"]["kind"], "merge")

    def test_snapshot_includes_cgroup_resources(self):
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=7)
        sched = _make_scheduler(tasks=[build])

        class _Cg:
            def read_stats(self, cpv):
                return {"cpu_usec": 2_000_000, "mem_peak": 1234} if cpv else None

        sched._cgroup = _Cg()
        monitor = ObservabilityMonitor(sched)
        monitor.note_task_started(build)

        snap = build_snapshot(monitor)
        res = snap["tasks"][0]["resources"]
        self.assertEqual(res["cpu_usec"], 2_000_000)
        self.assertEqual(res["mem_peak"], 1234)

    def test_snapshot_marks_merge_wait(self):
        # A merge sitting in the merge-wait queue is reported as waiting, with
        # its phase surfaced as "merge-wait".
        waiting = PackageMerge(EbuildBuild(_Pkg("dev-libs/foo-1.2")))
        active = EbuildBuild(_Pkg("sys-apps/bar-3"))
        sched = _make_scheduler(tasks=[waiting, active])
        sched._merge_wait_queue = [waiting]
        monitor = ObservabilityMonitor(sched)
        monitor.note_task_started(waiting)
        monitor.note_task_started(active)

        snap = build_snapshot(monitor)
        by_cpv = {t["cpv"]: t for t in snap["tasks"]}
        self.assertTrue(by_cpv["dev-libs/foo-1.2"]["merge_wait"])
        self.assertEqual(by_cpv["dev-libs/foo-1.2"]["phase"], "merge-wait")
        self.assertFalse(by_cpv["sys-apps/bar-3"]["merge_wait"])

    def test_merge_wait_freezes_elapsed_at_build_done(self):
        waiting = PackageMerge(EbuildBuild(_Pkg("dev-libs/foo-1.2")))
        sched = _make_scheduler(tasks=[waiting])
        sched._merge_wait_queue = [waiting]
        monitor = ObservabilityMonitor(sched)
        monitor.note_task_started(waiting)
        # Build started 100s ago and finished building 40s ago: elapsed should
        # freeze at the 60s build duration, not the ~100s since it started.
        import time as _t

        now = _t.time()
        monitor._build_times["dev-libs/foo-1.2"] = [now - 100, now - 40]

        entry = build_snapshot(monitor)["tasks"][0]
        self.assertEqual(entry["start_time"], now - 100)
        self.assertAlmostEqual(entry["elapsed"], 60, delta=1)

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

    def test_client_disconnect_removes_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build])
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)

            async def exercise():
                monitor.update(force=True)
                for _ in range(100):
                    if monitor._server is not None:
                        break
                    await asyncio.sleep(0.01)
                self.assertIsNotNone(monitor._server)

                reader, writer = await asyncio.open_unix_connection(
                    monitor._socket_path
                )
                snap = json.loads(await reader.readline())
                self.assertEqual(snap["tasks"][0]["cpv"], "dev-libs/foo-1.2")
                self.assertEqual(len(monitor._writers), 1)

                writer.close()
                await writer.wait_closed()
                # The server side must forget the client on EOF alone, without
                # needing a broadcast to discover the write is going nowhere.
                for _ in range(100):
                    if not monitor._writers:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(monitor._writers, [])

            try:
                global_event_loop().run_until_complete(exercise())
            finally:
                monitor.close()

    def test_snapshot_is_republished_without_task_events(self):
        loop = _FakeLoop()
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build], loop=loop)
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            monitor.update(force=True)

            path = os.path.join(status_dir(tmp), f"emerge-{os.getpid()}.json")
            with open(path, encoding="utf_8") as f:
                first = json.load(f)

            self.assertEqual(len(loop.calls), 1)
            self.assertEqual(loop.calls[0][0], monitor._refresh_interval)
            loop.run_pending()

            with open(path, encoding="utf_8") as f:
                second = json.load(f)
            self.assertGreater(second["timestamp"], first["timestamp"])
            self.assertGreater(
                second["tasks"][0]["elapsed"], first["tasks"][0]["elapsed"]
            )
            # The republish rearms the timer for the one after it.
            self.assertEqual(len(loop.calls), 1)

            monitor.close()
            self.assertEqual(loop.calls, [])

    def test_timer_republish_does_not_suppress_the_next_task_event(self):
        loop = _FakeLoop()
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build], loop=loop)
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            monitor.update(force=True)

            # Age the last event-driven publish past the rate limit, so that
            # only the timer below can put the next event back under it.
            monitor._last_write -= monitor._min_write_latency * 2
            last_write = monitor._last_write
            loop.run_pending()
            self.assertEqual(monitor._last_write, last_write)

            path = os.path.join(status_dir(tmp), f"emerge-{os.getpid()}.json")
            with open(path, encoding="utf_8") as f:
                after_timer = json.load(f)

            monitor.update()
            with open(path, encoding="utf_8") as f:
                after_event = json.load(f)
            self.assertGreater(after_event["timestamp"], after_timer["timestamp"])

            monitor.close()

    def test_pending_refresh_is_dropped_when_publishing_fails(self):
        loop = _FakeLoop()
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build], loop=loop)
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            monitor.update(force=True)
            self.assertEqual(len(loop.calls), 1)

            # What a failed status file write leaves behind.  The timer armed
            # by the publish above is already pending at this point.
            monitor._status_path = None
            monitor.enabled = False

            loop.run_pending()
            self.assertEqual(loop.calls, [])

            monitor.close()

    def test_no_refresh_is_armed_once_the_loop_is_closed(self):
        loop = _FakeLoop()

        def call_later(delay, callback):
            raise RuntimeError("Event loop is closed")

        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build], loop=loop)
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            loop.call_later = call_later

            # The publish itself still has to go through.
            monitor.update(force=True)
            path = os.path.join(status_dir(tmp), f"emerge-{os.getpid()}.json")
            self.assertTrue(os.path.exists(path))
            self.assertIsNone(monitor._refresh_handle)

            monitor.close()

    def test_close_stops_further_publishing(self):
        loop = _FakeLoop()
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build], loop=loop)
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)
            monitor.update(force=True)

            path = os.path.join(status_dir(tmp), f"emerge-{os.getpid()}.json")
            monitor.close()
            self.assertFalse(os.path.exists(path))

            # A task event arriving after close() must not recreate the file
            # or re-arm the timer.
            monitor.update(force=True)
            self.assertFalse(os.path.exists(path))
            self.assertEqual(loop.calls, [])

    def test_hint_when_nothing_read_and_feature_absent(self):
        self.assertIn("observability", missing_feature_hint([], features=set()))

    def test_no_hint_when_nothing_read_but_feature_present(self):
        self.assertIsNone(missing_feature_hint([], features={"observability"}))

    def test_no_hint_when_something_was_read(self):
        # The feature is enabled for the emerge being observed, not for the
        # process observing it, so a readable snapshot is never held back.
        self.assertIsNone(missing_feature_hint([{"emerge_pid": 1}], features=set()))

    def test_stale_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            # Use an implausible PID that is not running.
            with open(os.path.join(d, "emerge-2147480000.json"), "w") as f:
                json.dump({"emerge_pid": 2147480000, "tasks": []}, f)
            self.assertEqual(read_snapshots(tmp), [])
