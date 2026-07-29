# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import time

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class MergeUseVdbTestCase(TestCase):
    def testMergeUseVdb(self):
        """
        Verify that FEATURES="merge-use-vdb" uses the VDB hashes and avoids replacing
        files on the live filesystem if the new file's hash matches the VDB hash.
        """

        debug = False

        content_A_1 = """
S="${WORKDIR}"
src_install() {
    insinto /usr/lib/A
    echo original_content > "${T}"/foo
    doins "${T}"/foo
}
"""

        ebuilds = {
            "dev-libs/A-1": {
                "EAPI": "5",
                "IUSE": "+flag",
                "KEYWORDS": "x86",
                "LICENSE": "GPL-2",
                "MISC_CONTENT": content_A_1,
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

        foo_path = os.path.join(eroot, "usr", "lib", "A", "foo")

        def modify_file(path, spoof_mtime=None):
            with open(path, "w", encoding="utf-8") as f:
                f.write("modified_content_at_%d\n" % time.time())
            if spoof_mtime is not None:
                os.utime(path, (spoof_mtime, spoof_mtime))

        def verify_file_content(path, expected):
            with open(path, encoding="utf-8") as f:
                content = f.read().strip()
                self.assertEqual(content, expected)

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
        }

        if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
            env["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
                "__PORTAGE_TEST_HARDLINK_LOCKS"
            ]

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

            if debug:
                stdout = None
            else:
                stdout = subprocess.PIPE

            def run_cmd(args, extra_env=None):
                local_env = env.copy()
                if extra_env:
                    local_env.update(extra_env)

                proc = subprocess.Popen(args, env=local_env, stdout=stdout)
                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != os.EX_OK:
                        import sys

                        for line in output:
                            sys.stderr.write(line.decode("utf-8", "replace"))

                self.assertEqual(os.EX_OK, proc.returncode, f"cmd failed: {args}")

            # Install package normally
            run_cmd(emerge_cmd + ("-1", "=dev-libs/A-1"))
            verify_file_content(foo_path, "original_content")

            # Record original mtime
            original_mtime = os.stat(foo_path).st_mtime

            # Modify the installed file (changes mtime naturally)
            modify_file(foo_path)

            with open(foo_path, encoding="utf-8") as f:
                modified_content = f.read().strip()

            # Re-install with feature disabled (default behavior)
            # The manual modification should be replaced by original content
            run_cmd(emerge_cmd + ("-1", "=dev-libs/A-1"))
            verify_file_content(foo_path, "original_content")

            # Modify the installed file again, but don't spoof mtime
            modify_file(foo_path)

            # Re-install with feature enabled. Even though feature is
            # enabled, mtime differs, so it falls back to reading file
            # and overwrites it.
            run_cmd(emerge_cmd + ("-1", "=dev-libs/A-1"), {"FEATURES": "merge-use-vdb"})
            verify_file_content(foo_path, "original_content")

            # Record original mtime again
            original_mtime = os.stat(foo_path).st_mtime

            # Modify the installed file and spoof mtime to match original
            modify_file(foo_path, spoof_mtime=original_mtime)
            with open(foo_path, encoding="utf-8") as f:
                modified_content = f.read().strip()

            # Re-install with feature enabled. The manual modification
            # should be preserved because both mtime AND VDB hash
            # match
            run_cmd(emerge_cmd + ("-1", "=dev-libs/A-1"), {"FEATURES": "merge-use-vdb"})
            verify_file_content(foo_path, modified_content)

        finally:
            playground.cleanup()
