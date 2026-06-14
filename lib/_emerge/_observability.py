# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Observability support for a running emerge process.

When FEATURES="observability" is enabled, the Scheduler publishes a
machine-readable snapshot of its current state (which packages are
building/merging, in which phase, for how long) to a JSON status file
under PORTAGE_RUN_PATH (e.g. /run/portage/emerge-<pid>.json).  External
consumers can poll this file (see ``portageq jobs`` / ``emerge --status``).

Everything here degrades silently: if the runtime directory is not
writable (e.g. unprivileged, no /run) emerge proceeds unaffected.
"""

import json
import os as _os
import time

import portage
import portage.exception
from portage import os
from portage.const import PORTAGE_RUN_PATH
from portage.util import atomic_ofstream, ensure_dirs, writemsg_level

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


def build_snapshot(monitor):
    """Serialize the scheduler's current state into a plain dict."""
    scheduler = monitor._scheduler
    now = time.time()

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
            start, build_finished = times[0], times[1]
        else:
            start, build_finished = monitor._task_start.get(id(task)), None

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
        tasks.append(entry)

    tasks.sort(key=lambda t: (t["start_time"] is None, t["start_time"] or 0))

    display = scheduler._status_display
    return {
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

    snapshots = []
    for path in sorted(glob.glob(os.path.join(status_dir(eprefix), "emerge-*.json"))):
        try:
            with open(path, encoding="utf_8") as f:
                snapshot = json.load(f)
        except (OSError, ValueError):
            continue
        pid = snapshot.get("emerge_pid")
        if not isinstance(pid, int) or pid <= 0 or not _pid_alive(pid):
            continue
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
            lines.append(f"  {task.get('cpv', '?'):<45} {phase:<10} {elapsed_str:>7}")
    return "\n".join(lines) + "\n"


class ObservabilityMonitor:
    """Owns the status file for one Scheduler.

    All public methods are no-ops when the feature is disabled, so the
    Scheduler can call them unconditionally.
    """

    # Don't rewrite the status file more often than this (seconds), to
    # bound IO when many short phases churn.  Mirrors JobStatusDisplay's
    # rate-limiting intent.
    _min_write_latency = 1.0

    def __init__(self, scheduler):
        self._scheduler = scheduler
        settings = scheduler.settings

        self.enabled = "observability" in settings.features

        # id(task) -> epoch start time; str(cpv) -> current phase name.
        self._task_start = {}
        self._phases = {}
        # str(cpv) -> [build_start, build_finished or None]
        self._build_times = {}

        self._status_path = None
        self._last_write = 0

        if not self.enabled:
            return

        run_dir = status_dir(settings.get("EPREFIX", ""))
        pid = _os.getpid()
        self._run_dir = run_dir
        self._status_path = os.path.join(run_dir, f"emerge-{pid}.json")

    def note_task_started(self, task):
        if not self.enabled:
            return
        now = time.time()
        self._task_start[id(task)] = now
        if not isinstance(task, _PackageMerge):
            pkg = _task_pkg(task)
            if pkg is not None:
                self._build_times[str(pkg.cpv)] = [now, None]

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
                times[1] = time.time()

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

        self._write_status_file(snapshot)

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

    def close(self):
        if self._status_path:
            try:
                _os.unlink(self._status_path)
            except OSError:
                pass
