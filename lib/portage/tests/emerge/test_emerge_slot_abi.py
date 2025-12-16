# Copyright 2012-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import shlex
import subprocess
import sys

import portage
from portage import os
from portage.const import BASH_BINARY, PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase, CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class SlotAbiEmergeTestCase(TestCase):
    def testSlotAbiEmerge(self):
        debug = False

        ebuilds = {
            "dev-libs/glib-1.2.10": {"SLOT": "1"},
            "dev-libs/glib-2.30.2": {"EAPI": "5", "SLOT": "2/2.30"},
            "dev-libs/glib-2.32.3": {"EAPI": "5", "SLOT": "2/2.32"},
            "dev-libs/dbus-glib-0.98": {
                "EAPI": "5",
                "DEPEND": "dev-libs/glib:2=",
                "RDEPEND": "dev-libs/glib:2=",
            },
        }
        installed = {
            "dev-libs/glib-1.2.10": {"EAPI": "5", "SLOT": "1"},
            "dev-libs/glib-2.30.2": {"EAPI": "5", "SLOT": "2/2.30"},
            "dev-libs/dbus-glib-0.98": {
                "EAPI": "5",
                "DEPEND": "dev-libs/glib:2/2.30=",
                "RDEPEND": "dev-libs/glib:2/2.30=",
            },
        }

        world = ["dev-libs/glib:1", "dev-libs/dbus-glib"]

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world, debug=debug
        )
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        trees = playground.trees
        portdb = trees[eroot]["porttree"].dbapi
        vardb = trees[eroot]["vartree"].dbapi
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)
        package_mask_path = os.path.join(user_config_dir, "package.mask")

        portage_python = portage._python_interpreter
        ebuild_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "ebuild"),
        )
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        test_ebuild = portdb.findname("dev-libs/dbus-glib-0.98")
        self.assertFalse(test_ebuild is None)

        test_commands = (
            CommandStep(
                returncode=os.EX_OK,
                command=emerge_cmd
                + (
                    "--oneshot",
                    "dev-libs/glib",
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    "dev-libs/glib:2/2.32="
                    in vardb.aux_get("dev-libs/dbus-glib-0.98", ["RDEPEND"])[0],
                    f"step {i}",
                )
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=(BASH_BINARY,)
                + (
                    "-c",
                    "echo %s >> %s"
                    % tuple(
                        map(
                            shlex.quote,
                            (
                                ">=dev-libs/glib-2.32",
                                package_mask_path,
                            ),
                        )
                    ),
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emerge_cmd
                + (
                    "--oneshot",
                    "dev-libs/glib",
                ),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    "dev-libs/glib:2/2.30="
                    in vardb.aux_get("dev-libs/dbus-glib-0.98", ["RDEPEND"])[0],
                    f"step {i}",
                )
            ),
        )

        distdir = playground.distdir
        pkgdir = playground.pkgdir
        fake_bin = os.path.join(eprefix, "bin")
        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
        profile_path = settings.profile_path

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
        }

        if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
            env["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
                "__PORTAGE_TEST_HARDLINK_LOCKS"
            ]

        dirs = [distdir, fake_bin, portage_tmpdir, user_config_dir, var_cache_edb]
        true_symlinks = ["chown", "chgrp"]
        true_binary = find_binary("true")
        self.assertEqual(true_binary is None, False, "true command not found")
        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(true_binary, os.path.join(fake_bin, x))
            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")
            # non-empty system set keeps --depclean quiet
            with open(os.path.join(profile_path, "packages"), "w") as f:
                f.write("*dev-libs/token-system-pkg")

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
            playground.cleanup()
