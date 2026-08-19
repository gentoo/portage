# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Observability support for a running emerge process.

When FEATURES="observability" is enabled, the Scheduler publishes a
machine-readable snapshot of its current state (which packages are
building/merging, in which phase, for how long) to a JSON status file
under PORTAGE_RUN_PATH (e.g. /run/portage/emerge-<pid>.json).  External
consumers can poll this file (see ``portageq jobs`` / ``emerge --status``).

A Unix-domain socket at /run/portage/emerge-<pid>.sock additionally streams
newline-delimited JSON snapshots: the current snapshot on connect, then one
line per update.

Every object carries a "type" field naming its kind ("snapshot" today).
Consumers must dispatch on it and ignore kinds they do not know, so that
other kinds can be added later without breaking them.

Everything here degrades silently: if the runtime directory is not
writable (e.g. unprivileged, no /run) emerge proceeds unaffected.
"""

import asyncio as _asyncio
import json
import os as _os
import time

import portage
import portage.exception
from portage import os
from portage.const import PORTAGE_RUN_PATH
from portage.util import atomic_ofstream, ensure_dirs, writemsg_level
from portage.util.futures import asyncio
from portage.util.human_readable import bytes_to_human

from _emerge.PackageMerge import PackageMerge as _PackageMerge

_SCHEMA_VERSION = 1


def _task_pkg(task):
    """Return the Package associated with a running task, or None."""
    pkg = getattr(task, "pkg", None)
    if pkg is not None:
        return pkg
    merge = getattr(task, "merge", None)
    if merge is not None:
        return getattr(merge, "pkg", None)
    return None


def _task_pid(task):
    """Return the live PID for task, or None."""
    seen = set()
    current = task
    for _ in range(16):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        pid = getattr(current, "pid", None)
        if pid:
            return pid
        current = getattr(current, "_current_task", None)
    return None


class _BuildTimes:
    """Timing and final resource usage for one package's build.

    Created when the build task starts and kept until the package's merge
    finishes, so that consumers see one continuous record across the
    build -> merge hand-off.
    """

    __slots__ = ("start", "finished", "resources")

    def __init__(self, start):
        self.start = start
        self.finished = None
        # Final cgroup counters, captured when the build finishes and
        # before the cgroup is destroyed.
        self.resources = None

    def elapsed(self, now):
        """Wall-clock duration of the build itself.

        Frozen once the build finishes, so that time spent waiting to merge
        does not inflate it.
        """
        if self.finished is not None:
            return self.finished - self.start
        return now - self.start


def build_snapshot(monitor):
    """Serialize the scheduler's current state into a plain dict."""
    scheduler = monitor._scheduler
    now = time.time()

    cgroup = getattr(scheduler, "_cgroup", None)
    merge_wait_ids = {id(t) for t in getattr(scheduler, "_merge_wait_queue", ())}

    tasks = []
    for task in scheduler._running_tasks.values():
        pkg = _task_pkg(task)
        if pkg is None:
            continue
        # PackageMerge installs an already-built package; everything else
        # represents an in-progress build/extract.
        cpv = str(pkg.cpv)
        kind = "merge" if isinstance(task, _PackageMerge) else "build"
        waiting = id(task) in merge_wait_ids

        # Prefer the build's own start/finish times (continuous across the
        # build -> merge hand-off) over the per-task start time.
        times = monitor._build_times.get(cpv)
        if times is not None:
            start, build_finished = times.start, times.finished
            frozen_res = times.resources
        else:
            start, build_finished = monitor._task_start.get(id(task)), None
            frozen_res = None

        # A package waiting to merge is done building: freeze its elapsed time at
        # build completion rather than letting the wait inflate it.
        if waiting and build_finished is not None and start is not None:
            elapsed = build_finished - start
        elif start is not None:
            elapsed = now - start
        else:
            elapsed = None

        entry = {
            "cpv": cpv,
            "category": pkg.category,
            "pf": pkg.pf,
            "root": pkg.root,
            "operation": getattr(pkg, "operation", None),
            "binary": bool(getattr(pkg, "built", False)),
            "kind": kind,
            "phase": "merge-wait" if waiting else monitor._phases.get(cpv),
            "merge_wait": waiting,
            "pid": _task_pid(task),
            "start_time": start,
            "elapsed": elapsed,
        }
        if frozen_res is not None:
            entry["resources"] = frozen_res
        elif cgroup is not None:
            res = cgroup.read_stats(str(pkg.cpv))
            if res:
                entry["resources"] = res
        tasks.append(entry)

    tasks.sort(key=lambda t: (t["start_time"] is None, t["start_time"] or 0))

    display = scheduler._status_display
    return {
        "type": "snapshot",
        "schema": _SCHEMA_VERSION,
        "emerge_pid": _os.getpid(),
        "timestamp": now,
        "jobs": {
            "running": scheduler._jobs,
            "max": scheduler._max_jobs,
            "completed": display.curval,
            "total": display.maxval,
            "failed": len(scheduler._failed_pkgs),
            "merge_wait": len(scheduler._merge_wait_queue),
            "merges_pending": len(scheduler._task_queues.merge),
        },
        "tasks": tasks,
    }


def status_dir(eprefix=""):
    """Directory where running emerge processes publish status files."""
    if eprefix:
        return os.path.join(eprefix, PORTAGE_RUN_PATH.lstrip(os.sep))
    return PORTAGE_RUN_PATH


def read_snapshots(eprefix=""):
    """Read all live emerge status files; return a list of snapshot dicts."""
    import glob
    import socket

    snapshots = []

    # Try reading from sockets first to trigger a fresh snapshot
    for path in sorted(glob.glob(os.path.join(status_dir(eprefix), "emerge-*.sock"))):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(path)
                with s.makefile("r", encoding="utf_8") as f:
                    line = f.readline()
                    if line:
                        snapshot = json.loads(line)
                        pid = snapshot.get("emerge_pid")
                        if isinstance(pid, int) and pid > 0 and _pid_alive(pid):
                            snapshots.append(snapshot)
        except (OSError, ValueError, socket.timeout, json.JSONDecodeError):
            pass

    # Fall back to json files, e.g., in case we run into the socket timeout above.
    for path in sorted(glob.glob(os.path.join(status_dir(eprefix), "emerge-*.json"))):
        try:
            with open(path, encoding="utf_8") as f:
                snapshot = json.load(f)
        except (OSError, ValueError):
            continue
        pid = snapshot.get("emerge_pid")
        if not isinstance(pid, int) or pid <= 0 or not _pid_alive(pid):
            continue
        # If we successfully read a live snapshot for this PID via the socket,
        # skip the JSON fallback to avoid duplicating the same process in the output.
        # Note: the socket connect above triggers an update() server-side which rewrites
        # the JSON status file. So by the time this loop runs, the JSON is fresh too
        # and either would do, but the socket snapshot is the one we know is current.
        if not any(s.get("emerge_pid") == pid for s in snapshots):
            snapshots.append(snapshot)

    return snapshots


def _pid_alive(pid):
    if pid <= 0:
        return False
    try:
        _os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _format_cpu(val, task):
    cpu_s = val / 1e6
    elapsed = task.get("elapsed")
    if elapsed is not None and elapsed > 0:
        parallelism = cpu_s / elapsed
        return f"{cpu_s:.2f}s ({parallelism:.2f}x)"
    return f"{cpu_s:.2f}s"


_RESOURCE_FIELDS = (
    ("cpu_usec", "CPU", _format_cpu),
    ("mem_current", "Mem", lambda v, t: bytes_to_human(v)),
    ("mem_peak", "MaxMem", lambda v, t: bytes_to_human(v)),
    ("mem_swap_current", "Swap", lambda v, t: bytes_to_human(v)),
    ("mem_swap_peak", "MaxSwap", lambda v, t: bytes_to_human(v)),
    ("mem_zswap_current", "ZSwap", lambda v, t: bytes_to_human(v)),
    ("io_read_bytes", "I/O R", lambda v, t: bytes_to_human(v)),
    ("io_write_bytes", "I/O W", lambda v, t: bytes_to_human(v)),
)


def format_snapshots(snapshots):
    """Render snapshots as a human-readable table."""
    if not snapshots:
        return "No emerge processes are currently running.\n"

    lines = []
    for snapshot in snapshots:
        jobs = snapshot.get("jobs", {})
        lines.append(
            "emerge[{pid}]: {running} running, {completed}/{total} done, "
            "{failed} failed".format(
                pid=snapshot.get("emerge_pid", "?"),
                running=jobs.get("running", 0),
                completed=jobs.get("completed", 0),
                total=jobs.get("total", 0),
                failed=jobs.get("failed", 0),
            )
        )
        for task in snapshot.get("tasks", []):
            elapsed = task.get("elapsed")
            elapsed_str = f"{max(0, int(elapsed))}s" if elapsed is not None else "-"
            phase = task.get("phase") or task.get("kind") or "-"
            line = f"  {task.get('cpv', '?'):<45} {phase:<10} {elapsed_str:>7}"

            resources = task.get("resources")
            if resources:
                res_strs = []
                for field, label, formatter in _RESOURCE_FIELDS:
                    val = resources.get(field)
                    if val is not None:
                        res_strs.append(f"{label}: {formatter(val, task)}")

                if res_strs:
                    line += f"  [{', '.join(res_strs)}]"

            lines.append(line)
    return "\n".join(lines) + "\n"


NOT_ENABLED_HINT = (
    "Nothing to report. Note that emerge only publishes status when it is "
    'started with FEATURES="observability"; see make.conf(5).\n'
)


def missing_feature_hint(snapshots, features=None):
    """Return a hint about FEATURES="observability", or None.

    There is only something to say when nothing was read, since the
    feature applies to the emerge being observed rather than to the one
    observing it.

    `features` defaults to this configuration's FEATURES, looked up only
    when it is needed, since loading the config is not cheap.
    """
    if snapshots:
        return None
    if features is None:
        settings = getattr(portage, "settings", None)
        features = settings.features if settings is not None else frozenset()
    if "observability" in features:
        return None
    return NOT_ENABLED_HINT


class ObservabilityMonitor:
    """Owns the status file and streaming socket for one Scheduler.

    All public methods are no-ops when the feature is disabled, so the
    Scheduler can call them unconditionally.
    """

    # Don't rewrite the status file more often than this (seconds), to
    # bound IO when many short phases churn.  Mirrors JobStatusDisplay's
    # rate-limiting intent.
    _min_write_latency = 1.0

    # Republish this often (seconds) even when no task event occurs, so that
    # the live gauges (elapsed time, cgroup counters, task PIDs) keep moving
    # through a phase that runs for hours.
    _refresh_interval = 2.0

    def __init__(self, scheduler):
        self._scheduler = scheduler
        settings = scheduler.settings

        self.enabled = "observability" in settings.features

        # id(task) -> epoch start time; str(cpv) -> current phase name.
        self._task_start = {}
        self._phases = {}
        # str(cpv) -> _BuildTimes
        self._build_times = {}

        self._status_path = None
        self._socket_path = None
        self._server = None
        self._writers = []
        self._server_started = False
        self._last_write = 0
        self._last_snapshot = None
        self._refresh_handle = None

        if not self.enabled:
            return

        run_dir = status_dir(settings.get("EPREFIX", ""))
        pid = _os.getpid()
        self._run_dir = run_dir
        self._status_path = os.path.join(run_dir, f"emerge-{pid}.json")
        self._socket_path = os.path.join(run_dir, f"emerge-{pid}.sock")

    def note_task_started(self, task):
        if not self.enabled:
            return
        now = time.time()
        self._task_start[id(task)] = now
        if not isinstance(task, _PackageMerge):
            pkg = _task_pkg(task)
            if pkg is not None:
                self._build_times[str(pkg.cpv)] = _BuildTimes(now)

    def note_task_finished(self, task):
        if not self.enabled:
            return
        self._task_start.pop(id(task), None)
        pkg = _task_pkg(task)
        if pkg is None:
            return
        cpv = str(pkg.cpv)
        if isinstance(task, _PackageMerge):
            self._phases.pop(cpv, None)
            self._build_times.pop(cpv, None)
        else:
            times = self._build_times.get(cpv)
            if times is not None:
                times.finished = time.time()
                cgroup = getattr(self._scheduler, "_cgroup", None)
                if cgroup is not None:
                    times.resources = cgroup.read_stats(cpv) or None

    def build_elapsed(self, cpv):
        """Wall-clock duration of the build of cpv, or None if unknown.

        Frozen once the build finishes, so callers reporting on a package
        that has moved on to merging still see the build's own duration.
        """
        times = self._build_times.get(str(cpv))
        if times is None:
            return None
        return times.elapsed(time.time())

    def note_phase(self, cpv, phase):
        if not self.enabled:
            return
        self._phases[str(cpv)] = phase
        self.update()

    def update(self, force=False):
        """Recompute the snapshot and publish it (rate-limited)."""
        if not self.enabled:
            return
        now = time.time()
        if not force and (now - self._last_write) < self._min_write_latency:
            return
        self._last_write = now
        self._publish()

    def _publish(self):
        try:
            snapshot = build_snapshot(self)
        except Exception as e:
            writemsg_level(
                f"!!! observability: failed to build snapshot: {e}\n",
                level=30,
                noiselevel=-1,
            )
            self.enabled = False
            return

        self._last_snapshot = snapshot
        self._write_status_file(snapshot)
        self._ensure_server()
        self._broadcast(snapshot)
        self._schedule_refresh()

    def _schedule_refresh(self):
        if not self.enabled or self._refresh_handle is not None:
            return
        try:
            self._refresh_handle = self._scheduler._event_loop.call_later(
                self._refresh_interval, self._refresh
            )
        except RuntimeError:
            # The loop is closed (shutdown in progress), so there will be no
            # further refreshes. Task events still publish.
            self._refresh_handle = None

    def _refresh(self):
        self._refresh_handle = None
        # A publish that fails disables the monitor, but the handle armed by
        # the previous one is still pending at that point.
        if not self.enabled:
            return
        # Publish without advancing _last_write: the rate limit is there for
        # bursty task events, not for this timer.
        self._publish()

    def _write_status_file(self, snapshot):
        try:
            ensure_dirs(self._run_dir, mode=0o755)
            f = atomic_ofstream(self._status_path, mode="w", encoding="utf_8")
            json.dump(snapshot, f, sort_keys=True)
            f.write("\n")
            f.close()
        except (OSError, portage.exception.PortageException) as e:
            # Typically EACCES/EROFS for unprivileged emerge or no /run.
            writemsg_level(
                f"!!! observability: cannot write {self._status_path}: {e}\n",
                level=30,
                noiselevel=-1,
            )
            self._status_path = None
            self.enabled = False

    def _ensure_server(self):
        if self._server_started:
            return
        self._server_started = True
        try:
            ensure_dirs(self._run_dir, mode=0o755)
            try:
                _os.unlink(self._socket_path)
            except FileNotFoundError:
                pass
            coro = _asyncio.start_unix_server(self._client_connected, self._socket_path)
            future = asyncio.ensure_future(coro)
            future.add_done_callback(self._server_ready)
        except Exception as e:
            writemsg_level(
                f"!!! observability: socket setup failed: {e}\n",
                level=30,
                noiselevel=-1,
            )

    def _server_ready(self, future):
        try:
            self._server = future.result()
            try:
                _os.chmod(self._socket_path, 0o600)
            except OSError:
                pass
        except Exception as e:
            writemsg_level(
                f"!!! observability: socket server failed: {e}\n",
                level=30,
                noiselevel=-1,
            )

    async def _client_connected(self, reader, writer):
        self.update()
        if self._last_snapshot is not None:
            data = (json.dumps(self._last_snapshot, sort_keys=True) + "\n").encode(
                "utf_8"
            )
            if not self._send(writer, data):
                return
        self._writers.append(writer)
        try:
            # Clients are not expected to send anything; this waits for the
            # peer to go away.  Without it a disconnected client is never
            # forgotten: asyncio's stream protocol keeps the transport open
            # after EOF, to permit half-close, so nothing else notices.
            # A client that shuts down only its write side is therefore
            # treated as gone: read the stream without half-closing.
            while await reader.read(4096):
                pass
        except OSError:
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            writer.close()

    def _broadcast(self, snapshot):
        if not self._writers:
            return
        data = (json.dumps(snapshot, sort_keys=True) + "\n").encode("utf_8")
        for writer in list(self._writers):
            if not self._send(writer, data):
                self._writers.remove(writer)

    @staticmethod
    def _send(writer, data):
        try:
            writer.write(data)
            return True
        except Exception:
            try:
                writer.close()
            except Exception:
                pass
            return False

    def close(self):
        # Nothing may publish after this: a later update() would re-arm the
        # timer and recreate the status file unlinked below.
        self.enabled = False
        if self._refresh_handle is not None:
            self._refresh_handle.cancel()
            self._refresh_handle = None
        for writer in self._writers:
            try:
                writer.close()
            except Exception:
                pass
        self._writers = []
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        for path in (self._status_path, self._socket_path):
            if path:
                try:
                    _os.unlink(path)
                except OSError:
                    pass
