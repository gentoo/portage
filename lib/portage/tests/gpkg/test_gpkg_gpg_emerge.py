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
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.gpg import GPG
from portage.process import find_binary
from portage.tests import TestCase, CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class test_gpkg_gpg_emerge_case(TestCase):
    def test_gpkg_require_signed_repo(self):
        debug = False
        gpg = None
        tmpdir = tempfile.mkdtemp()

        binhost_dir = os.path.join(tmpdir, "binhost-verifyme")
        other_binhost_dir = os.path.join(tmpdir, "binhost-dontverify-me")
        os.mkdir(f"{binhost_dir}-incoming")
        os.mkdir(f"{other_binhost_dir}-incoming")
        os.makedirs(os.path.join(binhost_dir, "app-misc", "hello"))
        os.makedirs(os.path.join(other_binhost_dir, "app-misc", "hello"))

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
                    "[test-other-binhost]",
                    f"sync-uri = file://{other_binhost_dir}",
                    f"location = {other_binhost_dir}-incoming",
                    "verify-signature = false",
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
                CommandStep(
                    returncode=os.EX_OK,
                    command=emerge_cmd
                    + (
                        "--oneshot",
                        "app-misc/hello",
                    ),
                ),
                # Move it to the 'external' binhost we'll fetch from
                FunctionStep(
                    function=lambda i: self.assertTrue(
                        shutil.move(
                            os.path.join(
                                eroot,
                                "pkgdir",
                                "app-misc",
                                "hello",
                                "hello-1-1.gpkg.tar",
                            ),
                            os.path.join(
                                binhost_dir, "app-misc", "hello", "hello-1-1.gpkg.tar"
                            ),
                        ),
                        f"step {i}",
                    )
                ),
                FunctionStep(
                    function=lambda i: self.assertTrue(
                        shutil.copy(
                            os.path.join(eroot, "pkgdir", "Packages"),
                            os.path.join(binhost_dir, "Packages"),
                        ),
                        f"step {i}",
                    ),
                ),
                # Cleanup the internal PKGDIR where it was
                # originally made, as it's now gone
                CommandStep(
                    returncode=os.EX_OK,
                    command=("emaint",)
                    + (
                        "binhost",
                        "--fix",
                    ),
                ),
                # Try to fetch it from the external binhost upon which
                # verification should fail because it was never signed.
                CommandStep(
                    returncode=not os.EX_OK,
                    command=emerge_cmd
                    + (
                        "--getbinpkgonly",
                        "--verbose",
                        "app-misc/hello",
                    ),
                ),
                # FEATURES="binpkg-ignore-signature" should take precedence
                # over binrepos.conf.
                CommandStep(
                    returncode=os.EX_OK,
                    env={"FEATURES": "binpkg-ignore-signature"},
                    command=emerge_cmd
                    + (
                        "--getbinpkgonly",
                        "--verbose",
                        "app-misc/hello",
                    ),
                ),
                #
                # Test with the other binhost now.
                #
                # Move it to the 'external' binhost we'll fetch from
                FunctionStep(
                    function=lambda i: self.assertTrue(
                        shutil.move(
                            os.path.join(
                                binhost_dir,
                                "app-misc",
                                "hello",
                                "hello-1-1.gpkg.tar",
                            ),
                            os.path.join(
                                other_binhost_dir,
                                "app-misc",
                                "hello",
                                "hello-1-1.gpkg.tar",
                            ),
                        ),
                        f"step {i}",
                    )
                ),
                FunctionStep(
                    function=lambda i: self.assertTrue(
                        shutil.copy(
                            os.path.join(binhost_dir, "Packages"),
                            os.path.join(other_binhost_dir, "Packages"),
                        ),
                        f"step {i}",
                    ),
                ),
                # Cleanup the internal PKGDIR where it was
                # originally made, as it's now gone
                CommandStep(
                    returncode=os.EX_OK,
                    command=("emaint",)
                    + (
                        "binhost",
                        "--fix",
                    ),
                ),
                # FEATURES="binpkg-request-signature" should take precedence
                # over binrepos.conf.
                CommandStep(
                    returncode=not os.EX_OK,
                    env={
                        "FEATURES": "binpkg-request-signature",
                        "PORTAGE_TRUST_HELPER": "true",
                    },
                    command=emerge_cmd
                    + (
                        "--getbinpkgonly",
                        "--verbose",
                        "app-misc/hello",
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
            if gpg is not None:
                gpg.stop()
            shutil.rmtree(tmpdir)
            playground.debug = False
            playground.cleanup()
