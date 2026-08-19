# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio
import json
import os
import socket
import tempfile
import threading
import time
from types import SimpleNamespace

from _emerge import _observability
from _emerge._observability import (
    ObservabilityMonitor,
    _BuildTimes,
    average_parallelism,
    build_snapshot,
    format_snapshots,
    missing_feature_hint,
    read_snapshots,
    status_dir,
)
from _emerge.PackageMerge import PackageMerge as _RealPackageMerge
from _emerge.Scheduler import Scheduler

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


class _FakeStatusSocket:
    """Stand-in for a running emerge's status socket.

    Serves one canned line per connection, optionally after a delay, so
    that both the happy path and the timeout fallback can be exercised.
    """

    def __init__(self, path, payload, delay=0.0):
        self._payload = payload
        self._delay = delay
        self._stop = False
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(0.1)
        self._sock.bind(path)
        self._sock.listen(4)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _addr = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with conn:
                if self._delay:
                    time.sleep(self._delay)
                try:
                    conn.sendall(json.dumps(self._payload).encode("utf_8") + b"\n")
                except OSError:
                    pass

    def close(self):
        self._stop = True
        self._thread.join(timeout=10)
        self._sock.close()


def _write_status_file(directory, pid, payload):
    with open(
        os.path.join(directory, f"emerge-{pid}.json"), "w", encoding="utf_8"
    ) as f:
        json.dump(payload, f)


def _snapshot(pid, cpv):
    return {"type": "snapshot", "schema": 1, "emerge_pid": pid, "tasks": [{"cpv": cpv}]}


def _set_build_times(monitor, cpv, start, finished=None, resources=None):
    """Install a synthetic build timing record for cpv on monitor."""
    times = _BuildTimes(start)
    times.finished = finished
    times.resources = resources
    monitor._build_times[cpv] = times
    return times


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
        now = time.time()
        _set_build_times(monitor, "dev-libs/foo-1.2", now - 100, now - 40)

        entry = build_snapshot(monitor)["tasks"][0]
        self.assertEqual(entry["start_time"], now - 100)
        self.assertAlmostEqual(entry["elapsed"], 60, delta=1)

    def test_resources_frozen_at_build_completion(self):
        # The cgroup is destroyed once the build is over, so the counters
        # captured at completion are the only ones left to report.
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        sched = _make_scheduler(tasks=[build])
        live = {"cpu_usec": 4_000_000, "mem_peak": 4096}
        sched._cgroup = SimpleNamespace(read_stats=lambda cpv: dict(live))
        monitor = ObservabilityMonitor(sched)
        monitor.note_task_started(build)
        monitor.note_task_finished(build)
        cpv = "dev-libs/foo-1.2"
        monitor.note_build_resources(cpv, sched._cgroup.read_stats(cpv))

        # A later read of the cgroup must not leak into the snapshot.
        live["cpu_usec"] = 9_000_000
        merge = PackageMerge(build)
        sched._running_tasks = {id(merge): merge}
        monitor.note_task_started(merge)

        entry = build_snapshot(monitor)["tasks"][0]
        self.assertEqual(entry["resources"]["cpu_usec"], 4_000_000)

    def test_transient_counters_are_not_frozen(self):
        # memory.current and friends describe a cgroup that no longer
        # exists once the build is done; the peaks and totals do not.
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        monitor = ObservabilityMonitor(_make_scheduler(tasks=[build]))
        monitor.note_task_started(build)
        monitor.note_task_finished(build)
        monitor.note_build_resources(
            "dev-libs/foo-1.2",
            {
                "cpu_usec": 1_000_000,
                "mem_current": 111,
                "mem_peak": 222,
                "mem_swap_current": 333,
                "mem_swap_peak": 444,
                "mem_zswap_current": 555,
                "io_read_bytes": 0,
                "io_write_bytes": 666,
            },
        )

        frozen = monitor._build_times["dev-libs/foo-1.2"].resources
        self.assertEqual(
            sorted(frozen),
            [
                "cpu_usec",
                "io_read_bytes",
                "io_write_bytes",
                "mem_peak",
                "mem_swap_peak",
            ],
        )

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

    def test_parallelism_is_frozen_through_merge_wait_and_merge(self):
        # cpu_usec stops advancing when the build ends, so the parallelism
        # derived from it must be divided by the build's own duration and
        # not by a wall clock that keeps running through the merge.
        for merge_wait in (True, False):
            with self.subTest(merge_wait=merge_wait):
                merge = PackageMerge(EbuildBuild(_Pkg("dev-libs/foo-1.2")))
                sched = _make_scheduler(tasks=[merge])
                if merge_wait:
                    sched._merge_wait_queue = [merge]
                monitor = ObservabilityMonitor(sched)
                monitor.note_task_started(merge)
                # 40s of building earning 800s of CPU, finished 60s ago.
                now = time.time()
                _set_build_times(
                    monitor,
                    "dev-libs/foo-1.2",
                    now - 100,
                    now - 60,
                    {"cpu_usec": 800_000_000},
                )

                entry = build_snapshot(monitor)["tasks"][0]
                self.assertAlmostEqual(entry["build_elapsed"], 40, delta=1)
                self.assertIn("(20.0", format_snapshots([build_snapshot(monitor)]))

    def test_format_snapshots_renders_resources(self):
        snap = {
            "emerge_pid": 4242,
            "jobs": {"running": 1, "completed": 0, "total": 1, "failed": 0},
            "tasks": [
                {
                    "cpv": "dev-libs/foo-1.2",
                    "phase": "compile",
                    "elapsed": 30.0,
                    "build_elapsed": 30.0,
                    "resources": {
                        "cpu_usec": 60_000_000,
                        "mem_current": 1024,
                        "mem_peak": 2048,
                        "io_read_bytes": 0,
                        "io_write_bytes": 4096,
                    },
                }
            ],
        }
        line = format_snapshots([snap]).splitlines()[1]
        self.assertIn(
            "[CPU: 60.00s (2.00x), Mem: 1.00 KiB, MaxMem: 2.00 KiB, "
            "I/O R: 0.00 B, I/O W: 4.00 KiB]",
            line,
        )

    def test_zero_valued_resources_are_still_reported(self):
        # Zero bytes of I/O is a fact about the build, not a missing value.
        snap = {
            "emerge_pid": 1,
            "jobs": {"running": 1, "completed": 0, "total": 1, "failed": 0},
            "tasks": [
                {
                    "cpv": "dev-libs/foo-1.2",
                    "phase": "compile",
                    "elapsed": 1.0,
                    "resources": {"io_read_bytes": 0, "io_write_bytes": 0},
                }
            ],
        }
        self.assertIn("I/O R: 0.00 B, I/O W: 0.00 B", format_snapshots([snap]))

    def test_average_parallelism_without_a_usable_duration(self):
        for elapsed in (None, 0, -1):
            with self.subTest(elapsed=elapsed):
                self.assertIsNone(average_parallelism(1_000_000, elapsed))

    def test_build_timing_is_recorded_while_disabled(self):
        # FEATURES="cgroup" reports build parallelism from this timing and
        # does not imply FEATURES="observability".
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        sched = _make_scheduler(features=(), tasks=[build])
        monitor = ObservabilityMonitor(sched)
        self.assertFalse(monitor.enabled)

        monitor.note_task_started(build)
        monitor._build_times["dev-libs/foo-1.2"].start = time.time() - 40
        self.assertAlmostEqual(monitor.build_elapsed("dev-libs/foo-1.2"), 40, delta=1)

        monitor.note_task_finished(build)
        frozen = monitor.build_elapsed("dev-libs/foo-1.2")
        self.assertAlmostEqual(frozen, 40, delta=1)
        self.assertIsNone(monitor.build_elapsed("no-such/pkg-1"))
        # Nothing that only the published snapshot needs is kept.
        self.assertEqual(monitor._task_start, {})

    def test_forget_build_drops_the_record(self):
        # A build that produces no merge task -- it failed, or emerge was
        # interrupted -- would otherwise keep its record for the rest of
        # the run, since only the merge drops it.
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        monitor = ObservabilityMonitor(_make_scheduler(tasks=[build]))
        monitor.note_task_started(build)
        monitor.note_phase("dev-libs/foo-1.2", "compile")
        monitor.note_task_finished(build)
        # Still there: a merge would go on reporting the build's duration.
        self.assertIn("dev-libs/foo-1.2", monitor._build_times)

        monitor.forget_build(build)
        self.assertEqual(monitor._build_times, {})
        self.assertEqual(monitor._phases, {})
        self.assertIsNone(monitor.build_elapsed("dev-libs/foo-1.2"))

    def test_socket_wins_over_the_status_file(self):
        # The socket answer is built when we ask; the file is only as fresh
        # as the last publish. The same emerge must appear once, not twice.
        pid = os.getpid()
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            _write_status_file(d, pid, _snapshot(pid, "stale/pkg-1"))
            server = _FakeStatusSocket(
                os.path.join(d, f"emerge-{pid}.sock"), _snapshot(pid, "fresh/pkg-1")
            )
            try:
                found = read_snapshots(tmp)
            finally:
                server.close()

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["tasks"][0]["cpv"], "fresh/pkg-1")

    def test_status_file_used_when_the_socket_times_out(self):
        # An emerge whose main loop is busy never answers; its status file
        # is still readable and is what we fall back to.
        pid = os.getpid()
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            _write_status_file(d, pid, _snapshot(pid, "from/file-1"))
            server = _FakeStatusSocket(
                os.path.join(d, f"emerge-{pid}.sock"),
                _snapshot(pid, "from/socket-1"),
                delay=0.5,
            )
            timeout = _observability._SOCKET_TIMEOUT
            _observability._SOCKET_TIMEOUT = 0.05
            try:
                found = read_snapshots(tmp)
            finally:
                _observability._SOCKET_TIMEOUT = timeout
                server.close()

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["tasks"][0]["cpv"], "from/file-1")

    def test_socket_pid_must_match_the_name_it_is_published_under(self):
        # A socket left behind by an emerge that was killed is answered by
        # whatever inherits its pid. _pid_alive() cannot tell the
        # difference, but the pid in the name can.
        pid = os.getpid()
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            server = _FakeStatusSocket(
                os.path.join(d, f"emerge-{pid}.sock"),
                _snapshot(os.getppid(), "impostor/pkg-1"),
            )
            try:
                self.assertEqual(read_snapshots(tmp), [])
            finally:
                server.close()

    def test_status_file_pid_must_match_the_name_it_is_published_under(self):
        pid = os.getpid()
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            _write_status_file(d, pid, _snapshot(os.getppid(), "impostor/pkg-1"))
            self.assertEqual(read_snapshots(tmp), [])

    def test_snapshots_are_ordered_by_pid(self):
        # Which transport answered for which emerge must not reorder the
        # result: one comes from a socket here and the other from a file.
        pids = sorted({os.getpid(), os.getppid()})
        if len(pids) < 2:
            self.skipTest("need two distinct live pids")
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            _write_status_file(d, pids[1], _snapshot(pids[1], "second/pkg-1"))
            server = _FakeStatusSocket(
                os.path.join(d, f"emerge-{pids[0]}.sock"),
                _snapshot(pids[0], "first/pkg-1"),
            )
            try:
                found = read_snapshots(tmp)
            finally:
                server.close()

            self.assertEqual([s["emerge_pid"] for s in found], pids)

    def test_unreadable_socket_does_not_hide_the_status_file(self):
        # No listener on the socket path at all: connect fails immediately.
        pid = os.getpid()
        with tempfile.TemporaryDirectory() as tmp:
            d = status_dir(tmp)
            os.makedirs(d)
            _write_status_file(d, pid, _snapshot(pid, "from/file-1"))
            with open(os.path.join(d, f"emerge-{pid}.sock"), "w"):
                pass
            found = read_snapshots(tmp)

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["tasks"][0]["cpv"], "from/file-1")

    def test_read_snapshots_over_a_real_server_socket(self):
        # End to end over the wire the monitor actually serves: the
        # snapshot read is the one the connect itself caused to be
        # published, not the one in the status file.
        with tempfile.TemporaryDirectory() as tmp:
            build = EbuildBuild(_Pkg("dev-libs/foo-1.2"), pid=99)
            sched = _make_scheduler(eprefix=tmp, tasks=[build])
            sched._cgroup = SimpleNamespace(
                read_stats=lambda cpv: {"cpu_usec": 2_000_000, "mem_peak": 4096}
            )
            monitor = ObservabilityMonitor(sched)
            monitor.note_task_started(build)

            async def exercise():
                monitor.update(force=True)
                for _ in range(100):
                    if monitor._server is not None:
                        break
                    await asyncio.sleep(0.01)
                self.assertIsNotNone(monitor._server)

                # Only in the status file at this point, and the rate limit
                # would keep an unforced publish from picking it up.
                later = EbuildBuild(_Pkg("sys-apps/bar-3"), pid=100)
                sched._running_tasks[id(later)] = later
                monitor.note_task_started(later)
                monitor._last_write = time.time()

                # read_snapshots() blocks, so it cannot run on this loop.
                return await asyncio.get_event_loop().run_in_executor(
                    None, read_snapshots, tmp
                )

            try:
                found = global_event_loop().run_until_complete(exercise())
            finally:
                monitor.close()

            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["emerge_pid"], os.getpid())
            self.assertEqual(
                sorted(t["cpv"] for t in found[0]["tasks"]),
                ["dev-libs/foo-1.2", "sys-apps/bar-3"],
            )
            rendered = format_snapshots(found)
            self.assertIn("CPU: 2.00s", rendered)
            self.assertIn("MaxMem: 4.00 KiB", rendered)

    def test_connect_publishes_a_current_snapshot(self):
        # Rate limiting bounds IO from bursty task events; it must not hand
        # a connecting client the state as it was up to a second ago.
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

                # A second task appears, with no event to publish it, and
                # the rate limit would suppress an unforced update.
                later = EbuildBuild(_Pkg("sys-apps/bar-3"), pid=100)
                sched._running_tasks[id(later)] = later
                monitor.note_task_started(later)
                monitor._last_write = time.time()

                reader, writer = await asyncio.open_unix_connection(
                    monitor._socket_path
                )
                try:
                    snap = json.loads(await reader.readline())
                finally:
                    writer.close()
                    await writer.wait_closed()

                self.assertEqual(
                    sorted(t["cpv"] for t in snap["tasks"]),
                    ["dev-libs/foo-1.2", "sys-apps/bar-3"],
                )
                # The status file is rewritten too, which is what makes it
                # safe for read_snapshots() to fall back to it.
                with open(monitor._status_path, encoding="utf_8") as f:
                    self.assertEqual(len(json.load(f)["tasks"]), 2)

            try:
                global_event_loop().run_until_complete(exercise())
            finally:
                monitor.close()

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


class SchedulerCgroupLogTestCase(TestCase):
    def _cgroup_finish(self, features, stats):
        """Run Scheduler._cgroup_finish() and return what it logged."""
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        build.settings = _Settings()
        monitor = ObservabilityMonitor(_make_scheduler(features=features))
        monitor.note_task_started(build)
        # 40s of wall clock for the build.
        monitor._build_times["dev-libs/foo-1.2"].start = time.time() - 40
        monitor.note_task_finished(build)

        messages = []
        sched = Scheduler.__new__(Scheduler)
        sched._observability = monitor
        sched._cgroup = SimpleNamespace(
            read_stats=lambda cpv: stats, destroy=lambda cpv: None
        )
        sched._sched_iface = SimpleNamespace(
            output=lambda msg, log_path=None: messages.append(msg)
        )
        sched._logger = SimpleNamespace(log=lambda msg: None)
        sched._cgroup_finish(build)
        return "".join(messages)

    def test_final_counters_reach_the_monitor(self):
        # _cgroup_finish() is the last reader before the cgroup is
        # destroyed, so what it read is what the merge has to report.
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        build.settings = _Settings()
        monitor = ObservabilityMonitor(_make_scheduler())
        monitor.note_task_started(build)
        monitor.note_task_finished(build)

        sched = Scheduler.__new__(Scheduler)
        sched._observability = monitor
        sched._cgroup = SimpleNamespace(
            read_stats=lambda cpv: {"cpu_usec": 5_000_000},
            destroy=lambda cpv: None,
        )
        sched._sched_iface = SimpleNamespace(output=lambda msg, log_path=None: None)
        sched._logger = SimpleNamespace(log=lambda msg: None)
        sched._cgroup_finish(build)

        self.assertEqual(
            monitor._build_times["dev-libs/foo-1.2"].resources,
            {"cpu_usec": 5_000_000},
        )

    def test_build_duration_comes_from_the_monitor(self):
        # The log line divides CPU time by the build's wall clock, which
        # only the monitor knows.
        msg = self._cgroup_finish(("observability",), {"cpu_usec": 800_000_000})
        self.assertIn("CPU: 800.00s (20.00x)", msg)

    def test_parallelism_without_the_observability_feature(self):
        # FEATURES="cgroup" does not imply FEATURES="observability", and
        # used to lose the parallelism suffix with no hint as to why.
        msg = self._cgroup_finish((), {"cpu_usec": 800_000_000})
        self.assertIn("CPU: 800.00s (20.00x)", msg)

    def test_summary_matches_the_status_rendering(self):
        # One renderer drives both, so the log line and the "emerge
        # --status" bracket cannot drift apart.
        stats = {
            "cpu_usec": 800_000_000,
            "mem_peak": 4096,
            "io_read_bytes": 0,
            "io_write_bytes": 8192,
        }
        msg = self._cgroup_finish((), stats)
        self.assertIn(
            "=== Resource usage for dev-libs/foo-1.2 "
            "[CPU: 800.00s (20.00x), MaxMem: 4.00 KiB, "
            "I/O R: 0.00 B, I/O W: 8.00 KiB]",
            msg,
        )

    def test_transient_counters_are_left_out_of_the_summary(self):
        # The build is over and its cgroup is about to be destroyed, so
        # what it happens to be using right now is not worth logging.
        msg = self._cgroup_finish(
            (),
            {"cpu_usec": 800_000_000, "mem_current": 1024, "mem_peak": 4096},
        )
        self.assertIn("MaxMem: 4.00 KiB", msg)
        self.assertNotIn("Mem: 1.00 KiB", msg)

    def test_no_parallelism_without_a_build_duration(self):
        build = EbuildBuild(_Pkg("dev-libs/foo-1.2"))
        build.settings = _Settings()
        messages = []
        sched = Scheduler.__new__(Scheduler)
        sched._observability = ObservabilityMonitor(_make_scheduler(features=()))
        sched._cgroup = SimpleNamespace(
            read_stats=lambda cpv: {"cpu_usec": 800_000_000},
            destroy=lambda cpv: None,
        )
        sched._sched_iface = SimpleNamespace(
            output=lambda msg, log_path=None: messages.append(msg)
        )
        sched._logger = SimpleNamespace(log=lambda msg: None)
        sched._cgroup_finish(build)

        self.assertIn("CPU: 800.00s", "".join(messages))
        self.assertNotIn("x)", "".join(messages))
