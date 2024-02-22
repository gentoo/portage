# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import shutil
import subprocess
import sys
import tempfile

import portage
from portage import _unicode_decode, os
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.process import find_binary
from portage.tests import TestCase
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
            emerge_cmd
            + (
                "--oneshot",
                "--verbose",
                "--buildpkg",
                "dev-libs/A",
            ),
            # Copy to a new PKGDIR which we'll use as PORTAGE_BINHOST then delete the old PKGDIR.
            (
                (
                    lambda: shutil.copytree(bindb.bintree.pkgdir, tmppkgdir_suffix)
                    or True,
                )
            ),
            (
                (
                    lambda: os.unlink(
                        os.path.join(
                            bindb.bintree.pkgdir, "dev-libs", "A", "A-1-1.gpkg.tar"
                        )
                    )
                    or True,
                )
            ),
        )
        test_commands_nonfatal = (
            # This should succeed if we've correctly saved it as A-1-1.gpkg.tar, not
            # A-1-2.gpkg.tar, and then also try to unpack the right filename, but
            # we defer checking the exit code to get a better error if the binpkg
            # was downloaded with the wrong filename.
            emerge_cmd
            + (
                "--oneshot",
                "--verbose",
                "--getbinpkgonly",
                "dev-libs/A",
            ),
        )
        test_commands_final = (
            # Check whether the downloaded binpkg in PKGDIR has the correct
            # filename (-1) or an unnecessarily-incremented one (-2).
            (
                lambda: os.path.exists(
                    os.path.join(
                        bindb.bintree.pkgdir, "dev-libs", "A", "A-1-1.gpkg.tar"
                    )
                ),
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

        def run_commands(test_commands, require_success=True):
            all_successful = True

            for i, args in enumerate(test_commands):
                if hasattr(args[0], "__call__"):
                    if require_success:
                        self.assertTrue(args[0](), f"callable at index {i} failed")
                    continue

                if isinstance(args[0], dict):
                    local_env = env.copy()
                    local_env.update(args[0])
                    args = args[1:]
                else:
                    local_env = env

                local_env["PORTAGE_BINHOST"] = f"file:///{tmppkgdir_suffix}"
                proc = subprocess.Popen(args, env=local_env, stdout=stdout)

                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != os.EX_OK:
                        for line in output:
                            sys.stderr.write(_unicode_decode(line))

                if all_successful and proc.returncode != os.EX_OK:
                    all_successful = False

                if require_success:
                    self.assertEqual(
                        os.EX_OK, proc.returncode, f"emerge failed with args {args}"
                    )

            return all_successful

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

            run_commands(test_commands)
            deferred_success = run_commands(test_commands_nonfatal, False)
            run_commands(test_commands_final)

            # Check the return value of test_commands_nonfatal later on so
            # we can get a better error message from test_commands_final
            # if possible.
            self.assertTrue(deferred_success, f"{test_commands_nonfatal} failed")
        finally:
            playground.debug = False
            playground.cleanup()
            tmppkgdir.cleanup()
