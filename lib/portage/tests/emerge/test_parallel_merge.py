# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
from unittest import mock

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.dbapi.vartree import _parse_merge_jobs
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class ParseMergeJobsTestCase(TestCase):
    def testParseMergeJobs(self):
        with mock.patch("portage.util.cpuinfo.get_cpu_count", return_value=12):
            for value, makeopts, expected in (
                (None, "-j4", 1),
                ("", "-j4", 1),
                (" ", "-j4", 1),
                ("1", "-j4", 1),
                ("4", None, 4),
                (" 4 ", None, 4),
                ("auto", "-j4", 4),
                ("auto", "-l8 -j 6", 6),
                ("auto", "-l8", 12),
                ("auto", "", 12),
                ("auto", None, 12),
                ("auto", "-j0", 12),
                ("0", None, None),
                ("-3", None, None),
                ("foo", None, None),
                ("Auto", None, None),
            ):
                with self.subTest(value=value, makeopts=makeopts):
                    self.assertEqual(_parse_merge_jobs(value, makeopts), expected)

        with mock.patch("portage.util.cpuinfo.get_cpu_count", return_value=None):
            self.assertEqual(_parse_merge_jobs("auto", None), 1)


class ParallelMergeTestCase(TestCase):
    def testParallelMerge(self):
        """
        Verify that PORTAGE_MERGE_JOBS > 1 correctly and safely merges
        directories, regular files, hardlinks, symlinks, and config-protected files.
        """
        debug = False

        content_pkg_1 = """
S="${WORKDIR}"
src_install() {
    # Deep directory hierarchy
    keepdir /usr/share/doc/testpkg/nested/sub

    # Regular files
    echo "content_file_1" > "${T}"/file1
    echo "content_file_2" > "${T}"/file2
    insinto /usr/share/doc/testpkg
    doins "${T}"/file1
    insinto /usr/share/doc/testpkg/nested
    doins "${T}"/file2

    # Hardlink pair
    echo "hardlink_content" > "${T}"/hl_source
    insinto /usr/lib/testpkg
    doins "${T}"/hl_source
    # create hardlink in image dir
    ln "${ED}"/usr/lib/testpkg/hl_source "${ED}"/usr/lib/testpkg/hl_target

    # Symlinks
    dosym hl_source /usr/lib/testpkg/hl_symlink
    dosym ../../share/doc/testpkg /usr/lib/testpkg/doc_dir_symlink
    # A chain of symlinks, whose merge is deferred until its target is
    # merged, as well as a dangling and circular symlinks, which are merged
    # in the final pass.
    dosym chain_b /usr/lib/testpkg/chain_a
    dosym chain_c /usr/lib/testpkg/chain_b
    dosym hl_source /usr/lib/testpkg/chain_c
    dosym nonexistent /usr/lib/testpkg/dangling
    dosym loop_b /usr/lib/testpkg/loop_a
    dosym loop_a /usr/lib/testpkg/loop_b

    # Config-protected file
    dodir /etc
    echo "config_content_v1" > "${T}"/test.conf
    insinto /etc
    doins "${T}"/test.conf

    # Batch test files (small files)
    for i in $(seq 1 50); do
        echo "batch_test_${i}" > "${T}"/small_${i}.txt
    done
    insinto /usr/share/batchtest
    doins "${T}"/small_*.txt
}
"""

        ebuilds = {
            "app-misc/testpkg-1": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "LICENSE": "GPL-2",
                "MISC_CONTENT": content_pkg_1,
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=debug)
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        distdir = playground.distdir
        fake_bin = os.path.join(eprefix, "bin")
        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")

        path = settings.get("PATH")
        if path is not None and not path.strip():
            path = None
        if path is None:
            path = ""
        else:
            path = ":" + path
        path = fake_bin + path

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is not None and pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
            pass
        else:
            if pythonpath is None:
                pythonpath = ""
            else:
                pythonpath = ":" + pythonpath
            pythonpath = PORTAGE_PYM_PATH + pythonpath

        env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "CLEAN_DELAY": "0",
            "DISTDIR": distdir,
            "EMERGE_DEFAULT_OPTS": "-v",
            "EMERGE_WARNING_DELAY": "0",
            "PATH": path,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PORTAGE_TMPDIR": portage_tmpdir,
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", "1"),
            "PYTHONPATH": pythonpath,
            "__PORTAGE_TEST_PATH_OVERRIDE": fake_bin,
            "PORTAGE_MERGE_JOBS": "4",
        }

        dirs = [distdir, fake_bin, portage_tmpdir, var_cache_edb]
        true_symlinks = ["prepstrip", "scanelf"]
        true_binary = find_binary("true")
        self.assertEqual(true_binary is None, False, "true command not found")

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(true_binary, os.path.join(fake_bin, x))
            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            def run_cmd(args, extra_env=None):
                local_env = env.copy()
                if extra_env:
                    local_env.update(extra_env)

                proc = subprocess.Popen(
                    args,
                    env=local_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                output = proc.stdout.readlines()
                proc.wait()
                proc.stdout.close()
                if proc.returncode != os.EX_OK:
                    import sys

                    for line in output:
                        sys.stderr.write(line.decode("utf-8", "replace"))

                self.assertEqual(os.EX_OK, proc.returncode, f"cmd failed: {args}")
                return [line.decode("utf-8", "replace") for line in output]

            # Merge package with 4 threads
            merge_out = run_cmd(emerge_cmd + ("-1", "=app-misc/testpkg-1"))
            self.assertTrue(
                any(
                    "Merged package contents in" in line and "4 jobs" in line
                    for line in merge_out
                ),
                f"Expected merge timing summary in output, got: {''.join(merge_out)}",
            )

            # 1. Verify directory creation
            nested_sub_dir = os.path.join(
                eroot, "usr", "share", "doc", "testpkg", "nested", "sub"
            )
            self.assertTrue(os.path.isdir(nested_sub_dir))

            # 2. Verify regular files
            file1_path = os.path.join(eroot, "usr", "share", "doc", "testpkg", "file1")
            file2_path = os.path.join(
                eroot, "usr", "share", "doc", "testpkg", "nested", "file2"
            )
            self.assertTrue(os.path.isfile(file1_path))
            self.assertTrue(os.path.isfile(file2_path))
            with open(file1_path, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "content_file_1")
            with open(file2_path, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "content_file_2")

            # 2b. Verify batched small files
            for i in range(1, 51):
                p = os.path.join(eroot, "usr", "share", "batchtest", f"small_{i}.txt")
                self.assertTrue(os.path.isfile(p), f"Missing batched file: {p}")
                with open(p, encoding="utf-8") as f:
                    self.assertEqual(f.read().strip(), f"batch_test_{i}")

            # 3. Verify hardlinks
            hl_source = os.path.join(eroot, "usr", "lib", "testpkg", "hl_source")
            hl_target = os.path.join(eroot, "usr", "lib", "testpkg", "hl_target")
            self.assertTrue(os.path.isfile(hl_source))
            self.assertTrue(os.path.isfile(hl_target))
            st_source = os.stat(hl_source)
            st_target = os.stat(hl_target)
            self.assertEqual(
                (st_source.st_dev, st_source.st_ino),
                (st_target.st_dev, st_target.st_ino),
                "Hardlinks do not point to the same inode!",
            )

            # 4. Verify symlinks
            sym_file = os.path.join(eroot, "usr", "lib", "testpkg", "hl_symlink")
            sym_dir = os.path.join(eroot, "usr", "lib", "testpkg", "doc_dir_symlink")
            self.assertTrue(os.path.islink(sym_file))
            self.assertEqual(os.readlink(sym_file), "hl_source")
            self.assertTrue(os.path.islink(sym_dir))
            self.assertTrue(os.path.isdir(sym_dir))
            for name, target in (
                ("chain_a", "chain_b"),
                ("chain_b", "chain_c"),
                ("chain_c", "hl_source"),
                ("dangling", "nonexistent"),
                ("loop_a", "loop_b"),
                ("loop_b", "loop_a"),
            ):
                link = os.path.join(eroot, "usr", "lib", "testpkg", name)
                self.assertEqual(os.readlink(link), target)
            self.assertTrue(
                os.path.isfile(os.path.join(eroot, "usr", "lib", "testpkg", "chain_a"))
            )

            # 5. Verify config file
            conf_file = os.path.join(eroot, "etc", "test.conf")
            self.assertTrue(os.path.isfile(conf_file))
            with open(conf_file, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "config_content_v1")

            # 6. Verify CONTENTS file recording in var/db/pkg
            contents_file = os.path.join(
                eroot, "var", "db", "pkg", "app-misc", "testpkg-1", "CONTENTS"
            )

            def read_contents():
                contents_map = {}
                with open(contents_file, encoding="utf-8") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            contents_map[parts[1]] = parts[0]
                return contents_map

            self.assertTrue(os.path.isfile(contents_file))
            contents_map = read_contents()

            # Only the contents of EPREFIX are merged, not the directories
            # leading to it.
            for path in contents_map:
                self.assertTrue(
                    path.startswith(eprefix + os.sep),
                    f"CONTENTS entry outside of EPREFIX: {path}",
                )

            self.assertEqual(
                contents_map.get(os.path.join(eprefix, "usr/share/doc/testpkg/file1")),
                "obj",
            )
            self.assertEqual(
                contents_map.get(os.path.join(eprefix, "usr/lib/testpkg/hl_source")),
                "obj",
            )
            self.assertEqual(
                contents_map.get(os.path.join(eprefix, "usr/lib/testpkg/hl_target")),
                "obj",
            )
            self.assertEqual(
                contents_map.get(os.path.join(eprefix, "usr/lib/testpkg/hl_symlink")),
                "sym",
            )
            for name in (
                "doc_dir_symlink",
                "chain_a",
                "chain_b",
                "chain_c",
                "dangling",
                "loop_a",
                "loop_b",
            ):
                self.assertEqual(
                    contents_map.get(os.path.join(eprefix, "usr/lib/testpkg", name)),
                    "sym",
                )
            self.assertEqual(
                contents_map.get(
                    os.path.join(eprefix, "usr/share/doc/testpkg/nested/sub")
                ),
                "dir",
            )
            self.assertEqual(
                contents_map.get(os.path.join(eprefix, "etc/test.conf")),
                "obj",
            )

            # Re-merge package to verify config-protect handling (confmem),
            # vdb hash reuse, and that contents are preserved on re-merge.
            merge_out_2 = run_cmd(emerge_cmd + ("-1", "=app-misc/testpkg-1"))
            self.assertTrue(
                any(
                    "Merged package contents in" in line and "4 jobs" in line
                    for line in merge_out_2
                ),
                f"Expected merge timing summary in re-merge output, got: {''.join(merge_out_2)}",
            )
            contents_map_2 = read_contents()
            self.assertEqual(
                contents_map_2.get(os.path.join(eprefix, "etc/test.conf")),
                "obj",
            )

            # PORTAGE_MERGE_JOBS=auto uses the -j value of MAKEOPTS.
            merge_out_auto = run_cmd(
                emerge_cmd + ("-1", "=app-misc/testpkg-1"),
                extra_env={"PORTAGE_MERGE_JOBS": "auto", "MAKEOPTS": "-j3"},
            )
            self.assertTrue(
                any(
                    "Merged package contents in" in line and "(3 jobs)" in line
                    for line in merge_out_auto
                ),
                f"Expected merge timing summary with 3 jobs, got: {''.join(merge_out_auto)}",
            )
            self.assertEqual(read_contents(), contents_map_2)

            # PORTAGE_MERGE_JOBS=1 merges sequentially, and still reports the
            # duration of the merge.
            merge_out_seq = run_cmd(
                emerge_cmd + ("-1", "=app-misc/testpkg-1"),
                extra_env={"PORTAGE_MERGE_JOBS": "1"},
            )
            self.assertTrue(
                any(
                    "Merged package contents in" in line and "(1 job)" in line
                    for line in merge_out_seq
                ),
                f"Expected merge timing summary with 1 job, got: {''.join(merge_out_seq)}",
            )
            self.assertEqual(read_contents(), contents_map_2)

            # Without PORTAGE_MERGE_JOBS, the merge is sequential and does not
            # report its duration.
            merge_out_default = run_cmd(
                emerge_cmd + ("-1", "=app-misc/testpkg-1"),
                extra_env={"PORTAGE_MERGE_JOBS": ""},
            )
            self.assertFalse(
                any("Merged package contents in" in line for line in merge_out_default),
                f"Did not expect merge timing summary without PORTAGE_MERGE_JOBS, got: {''.join(merge_out_default)}",
            )

            # The sequential merge records the same CONTENTS entries.
            self.assertEqual(read_contents(), contents_map_2)

        finally:
            playground.cleanup()
