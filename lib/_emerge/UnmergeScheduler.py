# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import os

import portage
from portage.output import colorize
from portage.util._async.AsyncScheduler import AsyncScheduler

from _emerge.Package import Package
from _emerge.PackageUninstall import PackageUninstall


class UnmergeScheduler(AsyncScheduler):
    """
    Unmerge packages in parallel. A package is unmerged only after the
    packages that must be unmerged before it, which are given by deps as
    a mapping from each cpv to the cpvs that it waits for. A dependency on
    a package that is not being unmerged is followed through to the
    packages that it waits for in turn.

    After a failure, no more unmerges are started, and the running ones
    are allowed to finish. The failures attribute then lists (cpv,
    returncode, log_path) tuples, and the remaining attribute lists the
    cpvs that were never started.
    """

    _loadavg_latency = 30

    def __init__(
        self,
        root_config,
        opts,
        settings,
        cpvs,
        deps,
        ldpath_mtimes,
        world_atom,
        writemsg_level=portage.util.writemsg_level,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._background = True
        self._root_config = root_config
        self._opts = opts
        self._settings = settings
        self._ldpath_mtimes = ldpath_mtimes
        self._world_atom = world_atom
        self._writemsg_level = writemsg_level

        selected = set(cpvs)
        expanded = {}

        # deps must not have cycles.
        def prerequisites(cpv):
            if cpv not in expanded:
                result = set()
                for dep in deps.get(cpv, ()):
                    if dep in selected:
                        result.add(dep)
                    else:
                        result.update(prerequisites(dep))
                expanded[cpv] = result
            return expanded[cpv]

        self._waiting = {cpv: set(prerequisites(cpv)) for cpv in cpvs}
        self._waiters = collections.defaultdict(list)
        for cpv, prereqs in self._waiting.items():
            for prereq in prereqs:
                self._waiters[prereq].append(cpv)
        self._ready = collections.deque(cpv for cpv in cpvs if not self._waiting[cpv])
        self._tasks = {}
        self._count = 0
        self._total = len(cpvs)
        self.failures = []

    @property
    def remaining(self):
        started = set(self._tasks.values())
        return [cpv for cpv in self._waiting if cpv not in started]

    def _keep_scheduling(self):
        return bool(self._ready) and not self.failures and not self._terminated.is_set()

    def _next_task(self):
        cpv = self._ready.popleft()
        self._count += 1
        self._writemsg_level(
            ">>> Unmerging ({} of {}) {}...\n".format(
                colorize("MERGE_LIST_PROGRESS", str(self._count)),
                colorize("MERGE_LIST_PROGRESS", str(self._total)),
                cpv,
            ),
            noiselevel=-1,
        )

        vardb = self._root_config.trees["vartree"].dbapi
        pkg = Package(
            built=True,
            cpv=cpv,
            installed=True,
            metadata=zip(
                Package.metadata_keys, vardb.aux_get(cpv, Package.metadata_keys)
            ),
            operation="uninstall",
            root_config=self._root_config,
            type_name="installed",
        )
        task = PackageUninstall(
            background=True,
            ldpath_mtimes=self._ldpath_mtimes,
            opts=self._opts,
            pkg=pkg,
            settings=portage.config(clone=self._settings),
            skip_display=True,
            world_atom=self._world_atom,
        )
        self._tasks[task] = cpv
        return task

    def _task_exit(self, task):
        cpv = self._tasks[task]
        vardb = self._root_config.trees["vartree"].dbapi
        if vardb._linkmap is not None:
            # Like portage.unmerge(), mark the map stale for the
            # subprocesses spawned from now on.
            vardb._linkmap._invalidate()

        if task.returncode == os.EX_OK:
            for waiter in self._waiters.pop(cpv, ()):
                prereqs = self._waiting[waiter]
                prereqs.discard(cpv)
                if not prereqs:
                    self._ready.append(waiter)
        else:
            self.failures.append(
                (cpv, task.returncode, task.settings.get("PORTAGE_LOG_FILE"))
            )
        super()._task_exit(task)


def _symlink_deps(vardb, cpvs, deps):
    """
    Return deps with each package that owns a symlink to a directory also
    waiting for the other packages with files beneath it, unless they
    already wait for it. Unmerged together, the owner can keep the symlink
    for the other's files while the other leaves it to the owner.
    """
    contents = {cpv: vardb._dblink(cpv).getcontents() for cpv in cpvs}
    link_owners = collections.defaultdict(set)
    for cpv, files in contents.items():
        for path, data in files.items():
            if data[0] == "sym" and os.path.isdir(path):
                link_owners[path].add(cpv)
    if not link_owners:
        return deps

    # The owners of the symlinks at or above each directory.
    dir_owners = {}

    def owners_above(path):
        if path not in dir_owners:
            parent = os.path.dirname(path)
            owners = set() if parent == path else owners_above(parent)
            if path in link_owners:
                owners = owners | link_owners[path]
            dir_owners[path] = owners
        return dir_owners[path]

    deps = {cpv: set(prereqs) for cpv, prereqs in deps.items()}

    def waits_for(cpv, target):
        stack = [cpv]
        seen = set()
        while stack:
            cpv = stack.pop()
            if cpv == target:
                return True
            if cpv not in seen:
                seen.add(cpv)
                stack.extend(deps.get(cpv, ()))
        return False

    for cpv in cpvs:
        owners = set()
        for parent in {os.path.dirname(path) for path in contents[cpv]}:
            owners.update(owners_above(parent))
        owners.discard(cpv)
        for owner in sorted(owners):
            if not waits_for(cpv, owner):
                deps.setdefault(owner, set()).add(cpv)
    return deps
