# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class NoreplaceEmergeTestCase(TestCase):
    def testNoreplaceAlreadyInstalled(self):
        ebuilds = {
            "dev-libs/A-1": {"KEYWORDS": "x86"},
        }
        installed = {
            "dev-libs/A-1": {"KEYWORDS": "x86"},
        }

        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        settings = playground.settings
        eprefix = settings["EPREFIX"]

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        fake_bin = os.path.join(eprefix, "bin")
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")

        path = settings.get("PATH")
        if not path or not path.strip():
            path = ""
        else:
            path = ":" + path
        path = fake_bin + path

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is None or pythonpath.split(":")[0] != PORTAGE_PYM_PATH:
            pythonpath = PORTAGE_PYM_PATH + (":" + pythonpath if pythonpath else "")

        env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "PATH": path,
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
        }

        if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
            env["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
                "__PORTAGE_TEST_HARDLINK_LOCKS"
            ]

        true_binary = find_binary("true")
        self.assertIsNotNone(true_binary, "true command not found")

        try:
            ensure_dirs(fake_bin)
            ensure_dirs(var_cache_edb)
            for x in ("chown", "chgrp"):
                os.symlink(true_binary, os.path.join(fake_bin, x))
            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            proc = subprocess.Popen(
                emerge_cmd + ("--noreplace", "--verbose", "dev-libs/A"),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate()

            self.assertEqual(
                proc.returncode,
                os.EX_OK,
                f"emerge --noreplace --verbose crashed:\n{stderr.decode()}",
            )
        finally:
            playground.cleanup()
