# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import tempfile

from portage.tests import TestCase
from portage.util.cgroup import (
    CgroupManager,
    _migrate_procs,
    _usable_anchor,
    cleanup_stale,
    read_stats,
    sanitize_name,
)


class CgroupTestCase(TestCase):
    def test_sanitize_name(self):
        self.assertEqual(sanitize_name("dev-libs/foo-1.2"), "dev-libs_foo-1.2")
        self.assertEqual(sanitize_name("cat/pkg-1.2_p3-r2"), "cat_pkg-1.2_p3-r2")
        # No path separators survive.
        self.assertNotIn("/", sanitize_name("a/b/c-1"))

    def test_read_stats_parses_controllers(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "cpu.stat"), "w") as f:
                f.write("usage_usec 12345678\nuser_usec 9000000\nsystem_usec 3000000\n")
            with open(os.path.join(d, "memory.current"), "w") as f:
                f.write("536870912\n")
            with open(os.path.join(d, "memory.peak"), "w") as f:
                f.write("805306368\n")
            with open(os.path.join(d, "io.stat"), "w") as f:
                f.write(
                    "8:0 rbytes=1048576 wbytes=2097152 rios=10 wios=20\n"
                    "259:0 rbytes=4194304 wbytes=0 rios=5 wios=0\n"
                )
            stats = read_stats(d)

        self.assertEqual(stats["cpu_usec"], 12345678)
        self.assertEqual(stats["mem_current"], 536870912)
        self.assertEqual(stats["mem_peak"], 805306368)
        # io.stat is summed across devices.
        self.assertEqual(stats["io_read_bytes"], 1048576 + 4194304)
        self.assertEqual(stats["io_write_bytes"], 2097152)

    def test_read_stats_missing_dir(self):
        self.assertIsNone(read_stats("/nonexistent/cgroup/leaf"))

    def test_read_stats_ignores_nonnumeric_memory(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "memory.current"), "w") as f:
                f.write("max\n")
            self.assertNotIn("mem_current", read_stats(d))

    def test_manager_read_destroy_disabled(self):
        # With setup() not run (or unavailable), the manager is a no-op.
        mgr = CgroupManager("/sys/fs/cgroup/portage")
        self.assertFalse(mgr.enabled)
        self.assertIsNone(mgr.read_stats("dev-libs/foo-1.2"))
        mgr.destroy("dev-libs/foo-1.2")  # must not raise

    def test_manager_reads_and_destroys_by_cpv(self):
        with tempfile.TemporaryDirectory() as root:
            mgr = CgroupManager(root)
            mgr.enabled = True  # bypass real cgroupfs detection for the test
            os.makedirs(mgr.emerge_root, exist_ok=True)
            leaf = mgr._leaf_path("dev-libs/foo-1.2")
            os.mkdir(leaf)
            with open(os.path.join(leaf, "memory.peak"), "w") as f:
                f.write("1024\n")
            self.assertEqual(mgr.read_stats("dev-libs/foo-1.2")["mem_peak"], 1024)

            # A real cgroup rmdir succeeds despite interface files; a plain
            # directory does not, so clear it first to model the empty leaf.
            os.unlink(os.path.join(leaf, "memory.peak"))
            mgr.destroy("dev-libs/foo-1.2")
            self.assertFalse(os.path.exists(leaf))

    def test_usable_anchor(self):
        with tempfile.TemporaryDirectory() as d:
            # No cgroup.subtree_control at all (not a cgroup, or unreadable).
            self.assertFalse(_usable_anchor(d))

            control = os.path.join(d, "cgroup.subtree_control")
            # A systemd .scope enables nothing for its children; a user slice
            # typically enables cpu and memory but not io.
            for content in ("", "cpu memory pids"):
                with open(control, "w") as fh:
                    fh.write(f"{content}\n")
                self.assertFalse(_usable_anchor(d))

            with open(control, "w") as fh:
                fh.write("cpu io memory pids\n")
            self.assertTrue(_usable_anchor(d))

    def test_usable_anchor_delegated(self):
        with tempfile.TemporaryDirectory() as d:
            try:
                os.setxattr(d, "user.delegate", b"1")
            except OSError:
                self.skipTest("filesystem does not support user extended attributes")
            with open(os.path.join(d, "cgroup.subtree_control"), "w") as fh:
                fh.write("\n")

            # Delegation only helps if the controllers are there to enable.
            with open(os.path.join(d, "cgroup.controllers"), "w") as fh:
                fh.write("cpu memory pids\n")
            self.assertFalse(_usable_anchor(d))

            # A cgroup delegated to us with everything available: emerge may
            # enable the controllers itself, so anchor there.
            with open(os.path.join(d, "cgroup.controllers"), "w") as fh:
                fh.write("cpu io memory pids\n")
            self.assertTrue(_usable_anchor(d))

            os.removexattr(d, "user.delegate")
            self.assertFalse(_usable_anchor(d))

    def test_migrate_procs(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src")
            dest = os.path.join(src, "init.scope")
            os.mkdir(src)

            # Nothing to move: no cgroup.procs, then an empty one.
            self.assertFalse(_migrate_procs(src, dest))
            procs = os.path.join(src, "cgroup.procs")
            with open(procs, "w") as fh:
                fh.write("")
            self.assertFalse(_migrate_procs(src, dest))
            self.assertFalse(os.path.exists(dest))

            with open(procs, "w") as fh:
                fh.write("11\n22\n33\n")
            self.assertTrue(_migrate_procs(src, dest))
            # cgroup.procs takes one pid per write(), so each is written
            # separately; on a plain file only the last one survives.
            with open(os.path.join(dest, "cgroup.procs")) as fh:
                self.assertEqual(fh.read(), "33")

    def test_cleanup_stale_reaps_only_dead_emerges(self):
        with tempfile.TemporaryDirectory() as root:
            # A very large pid is guaranteed to be above pid_max, so it can
            # never be alive.
            stale = os.path.join(root, "emerge-99999999")
            live = os.path.join(root, f"emerge-{os.getpid()}")
            # A bare leaf, as doebuild creates when there is no Scheduler.
            orphan = os.path.join(root, "dev-libs_bar-2.0")
            for path in (stale, live, orphan):
                os.mkdir(path)
            # Leaves of the dead emerge go away with it.
            os.mkdir(os.path.join(stale, "dev-libs_foo-1.2"))
            # An occupied leaf refuses rmdir, standing in for the EBUSY the
            # kernel returns while a cgroup still holds processes.
            busy = os.path.join(root, "dev-libs_baz-3.0")
            os.mkdir(busy)
            with open(os.path.join(busy, "cgroup.procs"), "w") as fh:
                fh.write("1234\n")

            cleanup_stale(root)

            self.assertFalse(os.path.exists(stale))
            self.assertTrue(os.path.isdir(live))
            self.assertFalse(os.path.exists(orphan))
            self.assertTrue(os.path.isdir(busy))

    def test_close_removes_untracked_leaves(self):
        with tempfile.TemporaryDirectory() as root:
            mgr = CgroupManager(root)
            mgr.enabled = True  # bypass real cgroupfs detection for the test
            os.makedirs(mgr.emerge_root, exist_ok=True)
            # A build aborted before its leaf was destroyed.
            os.mkdir(mgr._leaf_path("dev-libs/foo-1.2"))

            mgr.close()

            self.assertFalse(os.path.exists(mgr.emerge_root))
            self.assertFalse(os.path.exists(root))
            self.assertFalse(mgr.enabled)
            mgr.close()  # idempotent; must not raise
            os.mkdir(root)  # TemporaryDirectory cleanup needs it back
