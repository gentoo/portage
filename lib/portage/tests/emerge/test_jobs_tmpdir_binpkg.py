# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

INSUFFICIENT = "has insufficient free space"


class JobsTmpdirBinpkgTestCase(TestCase):
    def testBinpkgsIgnoreTmpdirRequirement(self):
        """
        --jobs-tmpdir-require-free-gb limits source builds only.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8"},
            "dev-libs/B-1": {"EAPI": "8"},
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            settings = playground.settings
            eprefix = settings["EPREFIX"]

            emerge_cmd = (
                portage._python_interpreter,
                "-b",
                "-Wd",
                os.path.join(str(self.bindir), "emerge"),
            )

            pythonpath = os.environ.get("PYTHONPATH")
            if pythonpath is not None and not pythonpath.strip():
                pythonpath = None
            if pythonpath is None or pythonpath.split(":")[0] != PORTAGE_PYM_PATH:
                pythonpath = PORTAGE_PYM_PATH + (":" + pythonpath if pythonpath else "")

            env = {
                "PORTAGE_OVERRIDE_EPREFIX": eprefix,
                "PATH": settings.get("PATH"),
                "PORTAGE_INST_GID": str(os.getgid()),
                "PORTAGE_INST_UID": str(os.getuid()),
                "PORTAGE_PYTHON": portage._python_interpreter,
                "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
                "PYTHONDONTWRITEBYTECODE": os.environ.get(
                    "PYTHONDONTWRITEBYTECODE", "1"
                ),
                "PYTHONPATH": pythonpath,
            }

            var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
            for d in (
                playground.distdir,
                os.path.join(eprefix, "var", "tmp", "portage"),
                var_cache_edb,
            ):
                ensure_dirs(d)
            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            def emerge(*args):
                proc = subprocess.run(
                    emerge_cmd + args + ("dev-libs/A", "dev-libs/B"),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(proc.returncode, os.EX_OK, proc.stdout)
                return proc.stdout

            emerge("--oneshot", "--buildpkg", "--jobs-tmpdir-require-free-gb=0")

            # No PORTAGE_TMPDIR has this much room, so the check fails
            # whenever it is applied.
            out = emerge(
                "--oneshot",
                "--emptytree",
                "--jobs=2",
                "--jobs-tmpdir-require-free-gb=1000000000",
            )
            self.assertIn(INSUFFICIENT, out)

            out = emerge(
                "--oneshot",
                "--emptytree",
                "--usepkgonly",
                "--jobs=2",
                "--jobs-tmpdir-require-free-gb=1000000000",
            )
            self.assertNotIn(INSUFFICIENT, out)
        finally:
            playground.cleanup()
