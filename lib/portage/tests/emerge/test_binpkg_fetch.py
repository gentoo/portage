# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import shutil
import subprocess
import sys
import tempfile

import portage
from portage import os
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.process import find_binary
from portage.tests import TestCase, CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class BinpkgFetchtestCase(TestCase):
    def testLocalFilePkgSyncUpdate(self):
        """
        Check handling of local file:// sync-uri and unnecessary BUILD_ID
        increments (bug #921208).
        """
        debug = False

        ebuilds = {
            "dev-libs/A-1::local": {
                "EAPI": "7",
                "SLOT": "0",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=debug)
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        trees = playground.trees
        bindb = trees[eroot]["bintree"].dbapi
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        tmppkgdir = tempfile.TemporaryDirectory()
        tmppkgdir_suffix = os.path.join(tmppkgdir.name, "binpkg")

        test_commands = (
            # Create a trivial binpkg first.
            CommandStep(
                returncode=os.EX_OK,
                command=emerge_cmd
                + ("--oneshot", "--verbose", "--buildpkg", "dev-libs/A"),
            ),
            # Copy to a new PKGDIR which we'll use as PORTAGE_BINHOST
            # then delete the old PKGDIR.
            FunctionStep(
                function=lambda _: shutil.copytree(
                    bindb.bintree.pkgdir, tmppkgdir_suffix
                )
                or True,
            ),
            FunctionStep(
                function=lambda _: os.unlink(
                    os.path.join(
                        bindb.bintree.pkgdir, "dev-libs", "A", "A-1-1.gpkg.tar"
                    )
                )
                or True,
            ),
            # This should succeed if we've correctly saved it as A-1-1.gpkg.tar, not
            # A-1-2.gpkg.tar, and then also try to unpack the right filename.
            CommandStep(
                returncode=os.EX_OK,
                command=emerge_cmd
                + ("--oneshot", "--verbose", "--getbinpkgonly", "dev-libs/A"),
            ),
            # Check whether the downloaded binpkg in PKGDIR has the correct
            # filename (-1) or an unnecessarily-incremented one (-2).
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(
                        os.path.join(
                            bindb.bintree.pkgdir, "dev-libs", "A", "A-1-1.gpkg.tar"
                        )
                    ),
                    f"step {i}",
                )
            ),
        )

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
            "PATH": path,
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "FEATURES": "-pkgdir-index-trusted",
        }

        dirs = [
            playground.distdir,
            fake_bin,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
        ]

        true_symlinks = ["chown", "chgrp"]

        needed_binaries = {
            "true": (find_binary("true"), True),
        }

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(needed_binaries["true"][0], os.path.join(fake_bin, x))

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            if debug:
                # The subprocess inherits both stdout and stderr, for
                # debugging purposes.
                stdout = None
            else:
                # The subprocess inherits stderr so that any warnings
                # triggered by python -Wd will be visible.
                stdout = subprocess.PIPE

            for i, step in enumerate(test_commands):
                if isinstance(step, FunctionStep):
                    try:
                        step.function(i)
                    except Exception as e:
                        if isinstance(e, AssertionError) and f"step {i}" in str(e):
                            raise
                        raise AssertionError(
                            f"step {i} raised {e.__class__.__name__}"
                        ) from e
                    continue

                env["PORTAGE_BINHOST"] = f"file:///{tmppkgdir_suffix}"
                proc = subprocess.Popen(
                    step.command,
                    env=dict(env.items(), **(step.env or {})),
                    cwd=step.cwd,
                    stdout=stdout,
                )

                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != step.returncode:
                        for line in output:
                            sys.stderr.write(portage._unicode_decode(line))

                self.assertEqual(
                    step.returncode,
                    proc.returncode,
                    f"{step.command} (step {i}) failed with exit code {proc.returncode}",
                )
        finally:
            playground.debug = False
            playground.cleanup()
            tmppkgdir.cleanup()
