# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""cgroup v2 resource accounting for package builds (monitor-only).

When FEATURES="cgroup" is enabled and emerge runs as root on a cgroup v2
system, each source build gets its own leaf cgroup under
PORTAGE_CGROUP_ROOT/emerge-<pid>/. The build's process tree is placed in
that cgroup, so the kernel accounts its CPU time, peak memory, and I/O.
These are read back for live observability snapshots and a per-build
summary; no limits are imposed.

On systems with CONFIG_FAIR_GROUP_SCHED the per-build cgroup hierarchy also
improves scheduling fairness: the kernel distributes CPU time evenly across
build slots rather than proportionally to thread count, which improves system
responsiveness during parallel emerges.

When running under a cgroup v2 manager that has already placed this process
in a cgroup from which every controller we need can reach our leaves, the
hierarchy is anchored under that cgroup rather than directly under the
cgroup v2 root, keeping the manager's view of the hierarchy consistent.
In practice that means a unit started with systemd's Delegate=yes, where
all controllers are handed to us. An interactive emerge is not such a case:
it runs inside a .scope that is delegated nothing and typically lacks io
anyway, so anchoring there would leave the leaves without controllers and
we fall back to the cgroup v2 root, where they are all available.

Degrades to a no-op when not root or cgroup v2 is unavailable.
"""

from __future__ import annotations

import atexit
import logging
import os
import re

from portage.util import writemsg_level

_CGROUPFS = "/sys/fs/cgroup"

# Controllers enabled on each cgroup level so leaves expose the matching
# interface files (cpu.stat, memory.peak, io.stat).
_CONTROLLERS = ("cpu", "io", "memory")

# cgroup names must not contain '/'; collapse anything unusual.
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._+-]")

# Per-emerge cgroup directory names, as created by CgroupManager.
_EMERGE_DIR_RE = re.compile(r"^emerge-([0-9]+)$")


def sanitize_name(cpv: str) -> str:
    """Turn a cpv ("cat/pkg-1.2") into a single safe cgroup directory name."""
    return _SANITIZE_RE.sub("_", cpv)


def _warn(msg: str) -> None:
    writemsg_level(f"!!! cgroup: {msg}\n", level=logging.WARNING, noiselevel=-1)


def _info(msg: str) -> None:
    writemsg_level(f"cgroup: {msg}\n", level=logging.INFO)


def _debug(msg: str) -> None:
    writemsg_level(f"cgroup: {msg}\n", level=logging.DEBUG, noiselevel=2)


def _read_controllers(path: str) -> set[str]:
    try:
        with open(os.path.join(path, "cgroup.controllers"), encoding="ascii") as fh:
            return set(fh.read().split())
    except OSError:
        return set()


def _read_subtree_control(path: str) -> set[str]:
    try:
        with open(os.path.join(path, "cgroup.subtree_control"), encoding="ascii") as fh:
            return set(fh.read().split())
    except OSError:
        return set()


def _is_delegated(path: str) -> bool:
    """True if a cgroup manager marked path as delegated to its owner.

    systemd sets this extended attribute on the cgroup of a unit configured
    with Delegate= (trusted.delegate before systemd 250, user.delegate
    since), which is our signal that the subtree is ours to rearrange.
    """
    for attr in ("user.delegate", "trusted.delegate"):
        try:
            if os.getxattr(path, attr) not in (b"", b"0"):
                return True
        except OSError:
            continue
    return False


def _usable_anchor(path: str) -> bool:
    """True if our leaves below path can be given every controller we need.

    Either the manager already enabled them for path's children, or it
    delegated path to us, in which case we may enable them ourselves (see
    _prepare_anchor()).
    """
    wanted = set(_CONTROLLERS)
    if wanted.issubset(_read_subtree_control(path)):
        return True
    return _is_delegated(path) and wanted.issubset(_read_controllers(path))


def _detect_portage_root() -> str:
    """Return the path under which to anchor the portage cgroup hierarchy.

    Usually /sys/fs/cgroup/portage.  If a cgroup v2 manager has already
    placed this process in a cgroup from which all of _CONTROLLERS can be
    given to our leaves, nest under that cgroup instead so the manager
    stays aware of our hierarchy.  A cgroup that cannot is no use to us:
    its children, and so our leaves, would expose no controller interface
    files, leaving nothing but core accounting to read.
    """
    try:
        with open("/proc/self/cgroup", encoding="ascii") as f:
            for line in f:
                if not line.startswith("0::"):
                    continue
                path = line.strip().split("::", 1)[1]
                # We may be running below an init.scope of our own making;
                # anchor at the delegated cgroup itself, not one level down.
                path = path.removesuffix("/init.scope")
                if path and path != "/":
                    current = _CGROUPFS + path
                    if _usable_anchor(current):
                        return os.path.join(current, "portage")
    except OSError:
        pass
    return os.path.join(_CGROUPFS, "portage")


DEFAULT_CGROUP_ROOT = _detect_portage_root()


def available(root: str = DEFAULT_CGROUP_ROOT) -> bool:
    """True if running as root on a cgroup v2 system."""
    if os.geteuid() != 0:
        return False
    return os.path.exists(os.path.join(_CGROUPFS, "cgroup.controllers"))


def _enable_subtree_control(path: str, warn: bool = True) -> None:
    """Enable known controllers for children of path (idempotent).

    A controller that the parent did not delegate to us cannot be enabled,
    and its accounting is silently missing from every leaf below, so warn
    rather than quietly reporting a subset.
    """
    controllers = _read_controllers(path)
    missing = [c for c in _CONTROLLERS if c not in controllers]
    if missing and warn:
        _warn(
            f"{path}: controllers not delegated by parent: {' '.join(missing)}; "
            "their accounting will be unavailable"
        )
    wanted = [c for c in _CONTROLLERS if c in controllers]
    if wanted:
        try:
            with open(
                os.path.join(path, "cgroup.subtree_control"), "w", encoding="ascii"
            ) as fh:
                fh.write(" ".join(f"+{c}" for c in wanted))
        except OSError as e:
            if warn:
                _warn(f"cannot enable controllers on {path}: {e}")
            else:
                _debug(f"cannot enable controllers on {path}: {e}")


def _migrate_procs(src: str, dest: str) -> bool:
    """Move every process in the src cgroup into dest, which is created.

    cgroup.procs takes a single pid per write(), and a pid read from src may
    be gone by the time we write it, so migrate one at a time and treat an
    individual failure as nothing worse than a process left behind.
    """
    try:
        with open(os.path.join(src, "cgroup.procs"), encoding="ascii") as fh:
            pids = fh.read().split()
    except OSError as e:
        _debug(f"cannot read processes of {src}: {e}")
        return False
    if not pids:
        return False
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        _debug(f"cannot create {dest}: {e}")
        return False

    procs = os.path.join(dest, "cgroup.procs")
    moved = 0
    for pid in pids:
        try:
            with open(procs, "w", encoding="ascii") as fh:
                fh.write(pid)
        except OSError as e:
            _debug(f"cannot move pid {pid} into {dest}: {e}")
        else:
            moved += 1
    _debug(f"moved {moved} of {len(pids)} processes into {dest}")
    return moved > 0


def _prepare_anchor(root: str) -> None:
    """Make the parent of root able to give controllers to our hierarchy.

    A cgroup that holds processes may not enable anything in
    cgroup.subtree_control (cgroup v2's "no internal processes" rule), and
    that is precisely the cgroup systemd hands a service started with
    Delegate=yes: emerge itself sits in its root.  Move those processes
    into a leaf named init.scope -- the same trick, under the same name,
    that systemd uses at the root of the hierarchy -- so that controllers
    can be enabled for our own children.

    Only a cgroup delegated to us is rearranged this way.  The cgroup v2
    root is exempt from the rule and needs no such treatment; any other
    cgroup belongs to whoever manages it, not to us.
    """
    parent = os.path.dirname(root)
    wanted = set(_CONTROLLERS) & _read_controllers(parent)
    if not wanted or wanted.issubset(_read_subtree_control(parent)):
        return
    _enable_subtree_control(parent, warn=False)
    if wanted.issubset(_read_subtree_control(parent)):
        return
    if not _is_delegated(parent):
        return
    if _migrate_procs(parent, os.path.join(parent, "init.scope")):
        _enable_subtree_control(parent, warn=False)


def ensure_base(root: str = DEFAULT_CGROUP_ROOT) -> bool:
    """Create the base cgroup and enable controllers (idempotent)."""
    if not available(root):
        return False
    _prepare_anchor(root)
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as e:
        _warn(f"cannot create base cgroup {root}: {e}")
        return False
    _enable_subtree_control(root)
    return True


def leaf_path(root: str, cpv: str) -> str:
    return os.path.join(root, sanitize_name(cpv))


def ensure_leaf(root: str, cpv: str) -> str | None:
    """Ensure the per-build leaf cgroup exists; return its path or None."""
    if not ensure_base(root):
        return None
    path = leaf_path(root, cpv)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        _warn(f"cannot create cgroup {path}: {e}")
        return None
    return path


def _kill(path: str) -> None:
    """Kill every process in the cgroup at path and its descendants."""
    kill_file = os.path.join(path, "cgroup.kill")
    # cgroup.kill needs kernel >= 5.14, and is absent once the cgroup is
    # gone; either way there is nothing more we can do here.
    if not os.path.exists(kill_file):
        return
    try:
        with open(kill_file, "w", encoding="ascii") as fh:
            fh.write("1")
    except OSError:
        pass


def remove_tree(path: str) -> None:
    """Kill and remove the cgroup at path along with all its descendants.

    Removal is best effort: a cgroup that still holds processes (for example
    a kernel thread, or a process we are not permitted to kill) cannot be
    removed, and is left behind rather than treated as an error.
    """
    _kill(path)
    try:
        entries = os.listdir(path)
    except OSError:
        return
    for name in entries:
        child = os.path.join(path, name)
        if os.path.isdir(child):
            remove_tree(child)
    try:
        os.rmdir(path)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        # EPERM: the pid exists but belongs to someone else.
        return True
    return True


def cleanup_stale(root: str) -> None:
    """Remove cgroups left behind by builds that are no longer running.

    cgroup v2 offers no way to have the kernel release a cgroup when its
    creator exits, so an emerge killed with SIGKILL (or a machine that lost
    power mid-build) leaves its hierarchy behind. Reap those here, taking
    care not to disturb cgroups of concurrently running emerges.

    Two shapes accumulate under root: emerge-<pid> hierarchies, reaped once
    that pid is gone, and bare per-cpv leaves created by doebuild for builds
    that ran without a Scheduler (`ebuild` on the command line), which have
    nobody to destroy them. The latter are only rmdir'ed, which the kernel
    refuses while the cgroup still holds processes, so a concurrent build is
    left alone. Removing the leaf of a build that is merely between phases
    is harmless: the next spawn recreates it.
    """
    try:
        entries = os.listdir(root)
    except OSError:
        return
    for name in entries:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        match = _EMERGE_DIR_RE.match(name)
        if match is None:
            try:
                os.rmdir(path)
            except OSError:
                pass
        elif not _pid_alive(int(match.group(1))):
            remove_tree(path)


def _read_int(path: str) -> int | None:
    try:
        with open(path, encoding="ascii") as fh:
            value = fh.read().strip()
    except OSError:
        return None
    try:
        return int(value)  # memory.* may read "max"; treat non-numeric as absent
    except ValueError:
        return None


def _read_keyed(path: str) -> dict[str, int]:
    """Parse a flat 'key value key value' cgroup stat file (e.g. cpu.stat)."""
    out: dict[str, int] = {}
    try:
        with open(path, encoding="ascii") as fh:
            tokens = fh.read().split()
    except OSError:
        return out
    for i in range(0, len(tokens) - 1, 2):
        try:
            out[tokens[i]] = int(tokens[i + 1])
        except ValueError:
            pass
    return out


def read_stats(path: str) -> dict | None:
    """Read accounting from a leaf cgroup path. None if the cgroup is gone.

    Keys (any may be absent depending on kernel/controllers):
      cpu_usec          - total CPU time (microseconds)
      mem_current       - current memory (bytes)
      mem_peak          - peak memory (bytes; kernel >= 5.19)
      mem_swap_current  - current swap usage (bytes)
      mem_swap_peak     - peak swap usage (bytes; kernel >= 6.5)
      mem_zswap_current - current zswap usage (bytes)
      io_read_bytes     - bytes read across all devices
      io_write_bytes    - bytes written across all devices
    """
    if not os.path.isdir(path):
        return None

    stats: dict = {}

    cpu = _read_keyed(os.path.join(path, "cpu.stat"))
    if "usage_usec" in cpu:
        stats["cpu_usec"] = cpu["usage_usec"]

    cur = _read_int(os.path.join(path, "memory.current"))
    if cur is not None:
        stats["mem_current"] = cur
    peak = _read_int(os.path.join(path, "memory.peak"))
    if peak is not None:
        stats["mem_peak"] = peak
    swap_cur = _read_int(os.path.join(path, "memory.swap.current"))
    if swap_cur is not None:
        stats["mem_swap_current"] = swap_cur
    swap_peak = _read_int(os.path.join(path, "memory.swap.peak"))
    if swap_peak is not None:
        stats["mem_swap_peak"] = swap_peak
    zswap_cur = _read_int(os.path.join(path, "memory.zswap.current"))
    if zswap_cur is not None:
        stats["mem_zswap_current"] = zswap_cur

    rbytes = wbytes = 0
    have_io = False
    try:
        with open(os.path.join(path, "io.stat"), encoding="ascii") as fh:
            for line in fh:
                fields = dict(
                    tok.split("=", 1) for tok in line.split()[1:] if "=" in tok
                )
                if "rbytes" in fields or "wbytes" in fields:
                    have_io = True
                try:
                    rbytes += int(fields.get("rbytes", 0))
                    wbytes += int(fields.get("wbytes", 0))
                except ValueError:
                    pass
    except OSError:
        pass
    if have_io:
        stats["io_read_bytes"] = rbytes
        stats["io_write_bytes"] = wbytes

    return stats


class CgroupManager:
    """Per-emerge handle: read and destroy build leaves by cpv.

    Creates a two-level hierarchy: root/emerge-<pid>/<cpv>.  The emerge-level
    cgroup isolates each invocation's accounting so stale cgroups from a
    previous (failed) run of the same package cannot pollute the new build's
    stats.  emerge_root is exposed so callers can pass it to child processes
    via settings.
    """

    def __init__(self, root: str = DEFAULT_CGROUP_ROOT, verbose: bool = False) -> None:
        self.root = root
        self.emerge_root = os.path.join(root, f"emerge-{os.getpid()}")
        self.enabled = False
        self.verbose = verbose
        self._seen: set[str] = set()

    def setup(self) -> bool:
        """Initialize the base and per-emerge cgroups. Sets self.enabled."""
        if not ensure_base(self.root):
            return False
        if self.verbose:
            _info(f"using {self.root}")
        cleanup_stale(self.root)
        try:
            os.makedirs(self.emerge_root, exist_ok=True)
        except OSError as e:
            _warn(f"cannot create emerge cgroup {self.emerge_root}: {e}")
            return False
        _enable_subtree_control(self.emerge_root)
        self.enabled = True
        # close() is called from Scheduler.merge(), but that is skipped if
        # we exit via an unhandled exception or a signal handler.
        atexit.register(self.close)
        return True

    def _leaf_path(self, cpv: str) -> str:
        return leaf_path(self.emerge_root, cpv)

    def read_stats(self, cpv: str) -> dict | None:
        if not self.enabled:
            return None
        self._seen.add(cpv)
        return read_stats(self._leaf_path(cpv))

    def destroy(self, cpv: str) -> None:
        self._seen.discard(cpv)
        remove_tree(self._leaf_path(cpv))

    def close(self) -> None:
        if not self.enabled:
            return
        self.enabled = False
        self._seen.clear()
        # Removes leaves of builds that were aborted before _cgroup_finish()
        # got a chance to destroy them, along with emerge_root itself.
        remove_tree(self.emerge_root)
        # Only succeeds if no other emerge is using the hierarchy.
        try:
            os.rmdir(self.root)
        except OSError:
            pass
