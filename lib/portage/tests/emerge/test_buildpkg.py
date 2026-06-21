# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys

import portage
import os
from portage.const import (
    PORTAGE_PYM_PATH,
    USER_CONFIG_PATH,
)
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class BuildPkgTestCase(TestCase):
    def testBuildPkgEnabled(self):
        """
        Check that binary packages are built only when appropriate.
        """
        debug = False

        ebuilds = {
            "dev-libs/penv-1": {"EAPI": "8"},
            "dev-libs/arg-1": {"EAPI": "8"},
            "dev-libs/feature-1": {"EAPI": "8"},
        }

        user_config = {
            "package.env": ("dev-libs/penv buildpkg.conf",),
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config, debug=debug
        )

        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        trees = playground.trees
        bindb = trees[eroot]["bintree"].dbapi
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)
        env_dir = os.path.join(user_config_dir, "env")

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
            "--oneshot",
            "--verbose",
        )

        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")

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
            "PATH": settings.get("PATH"),
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
        }

        dirs = [
            playground.distdir,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
            env_dir,
        ]

        try:
            for d in dirs:
                ensure_dirs(d)

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            with open(os.path.join(env_dir, "buildpkg.conf"), "w") as f:
                print('FEATURES="buildpkg"', file=f)

            if debug:
                # The subprocess inherits both stdout and stderr, for
                # debugging purposes.
                stdout = None
            else:
                # The subprocess inherits stderr so that any warnings
                # triggered by python -Wd will be visible.
                stdout = subprocess.PIPE

            def run_emerge(args, myenv={}):
                proc = subprocess.Popen(
                    emerge_cmd + args,
                    env=dict(env, **myenv),
                    stdout=stdout,
                )

                if debug:
                    proc.wait()
                else:
                    output = proc.stdout.readlines()
                    proc.wait()
                    proc.stdout.close()
                    if proc.returncode != os.EX_OK:
                        for line in output:
                            sys.stderr.write(line.decode("utf-8", "replace"))

                self.assertEqual(
                    os.EX_OK,
                    proc.returncode,
                    f"{emerge_cmd} {args} failed with exit code {proc.returncode}",
                )

                # Repopulate the cache after building.
                bindb.bintree.populate()

            run_emerge(("--buildpkg-exclude=dev-libs/penv", "dev-libs/penv"))
            with self.assertRaises(KeyError):
                bindb.aux_get("dev-libs/penv-1", [])

            run_emerge(("dev-libs/penv", "dev-libs/arg"))
            self.assertEqual([], bindb.aux_get("dev-libs/penv-1", []))
            with self.assertRaises(KeyError):
                bindb.aux_get("dev-libs/arg-1", [])

            run_emerge(("--buildpkg", "dev-libs/arg"))
            self.assertEqual([], bindb.aux_get("dev-libs/arg-1", []))

            run_emerge(
                ("--buildpkg-exclude=dev-libs/feature", "dev-libs/feature"),
                {"FEATURES": "buildpkg"},
            )
            with self.assertRaises(KeyError):
                bindb.aux_get("dev-libs/feature-1", [])

            run_emerge(("dev-libs/feature",), {"FEATURES": "buildpkg"})
            self.assertEqual([], bindb.aux_get("dev-libs/feature-1", []))

        finally:
            playground.debug = False
            playground.cleanup()
