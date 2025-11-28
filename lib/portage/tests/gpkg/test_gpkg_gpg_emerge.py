# Copyright 2022-2025 Gentoo Authors
# Similar to test_gpkg_gpg.py but
# with full emerge calls to test how we control signature verification.

import portage
import shutil
import sys
import tempfile
import subprocess

from portage import os
from portage import shutil
from portage import _unicode_decode
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.gpg import GPG
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class test_gpkg_gpg_emerge_case(TestCase):
    def test_gpkg_require_signed_repo(self):
        def run_commands(test_commands, require_success=True, invert=False):
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

                if invert:
                    self.assertNotEqual(
                        os.EX_OK,
                        proc.returncode,
                        f"emerge succeeded unexpectedly with args {args}",
                    )
                elif require_success:
                    self.assertEqual(
                        os.EX_OK, proc.returncode, f"emerge failed with args {args}"
                    )

            return all_successful

        debug = True
        gpg = None
        tmpdir = tempfile.mkdtemp()
        binhost_dir = os.path.join(tmpdir, "binhost-verifyme")
        os.mkdir(f"{binhost_dir}-incoming")
        os.makedirs(os.path.join(binhost_dir, "app-misc", "hello"))

        playground = ResolverPlayground(
            user_config={
                "make.conf": (
                    'FEATURES="${FEATURES} buildpkg -binpkg-signing -binpkg-index-trusted"',
                    'BINPKG_FORMAT="gpkg"',
                    'BINPKG_COMPRESS="none"',
                ),
                "binrepos.conf": (
                    "[test-binhost]",
                    f"sync-uri = file://{binhost_dir}",
                    f"location = {binhost_dir}-incoming",
                    "verify-signature = true",
                ),
            },
            ebuilds={
                "app-misc/hello-1": {
                    "EAPI": 8,
                }
            },
        )

        try:
            settings = playground.settings
            gpg = GPG(settings)
            gpg.unlock()

            portage_python = portage._python_interpreter
            emerge_cmd = (
                portage_python,
                "-b",
                "-Wd",
                os.path.join(str(self.bindir), "emerge"),
            )

            settings = playground.settings
            eprefix = settings["EPREFIX"]
            eroot = settings["EROOT"]
            var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
            user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

            test_commands = (
                # Create a binpkg. This step should succeed because
                # we aren't requiring just-created local binpkgs
                # to be signed.
                emerge_cmd
                + (
                    "--oneshot",
                    "app-misc/hello",
                ),
                # Move it to the 'external' binhost we'll fetch from
                (
                    lambda: shutil.move(
                        os.path.join(
                            eroot, "pkgdir", "app-misc", "hello", "hello-1-1.gpkg.tar"
                        ),
                        os.path.join(
                            binhost_dir, "app-misc", "hello", "hello-1-1.gpkg.tar"
                        ),
                    ),
                ),
                (
                    lambda: shutil.copy(
                        os.path.join(eroot, "pkgdir", "Packages"),
                        os.path.join(binhost_dir, "Packages"),
                    ),
                ),
                # Cleanup the internal PKGDIR where it was
                # originally made, as it's now gone
                (
                    "emaint",
                    "binhost",
                    "--fix",
                ),
            )

            test_commands_fail = (
                # Try to fetch it from the external binhost upon which
                # verification should fail because it was never signed.
                emerge_cmd
                + (
                    "--getbinpkgonly",
                    "--verbose",
                    "app-misc/hello",
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
                "PYTHONDONTWRITEBYTECODE": os.environ.get(
                    "PYTHONDONTWRITEBYTECODE", ""
                ),
                "PYTHONPATH": pythonpath,
                "PORTAGE_INST_GID": str(os.getgid()),
                "PORTAGE_INST_UID": str(os.getuid()),
                "FEATURES": "buildpkg",
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
            # We need these to fail
            run_commands(test_commands_fail, invert=True)
        finally:
            if gpg is not None:
                gpg.stop()
            shutil.rmtree(tmpdir)
            playground.debug = False
            playground.cleanup()
