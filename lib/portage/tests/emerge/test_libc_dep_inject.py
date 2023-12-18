# Copyright 2016-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys
import textwrap

import portage
from portage import os
from portage import _unicode_decode
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.util import ensure_dirs

from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class LibcDepInjectEmergeTestCase(TestCase):
    def testLibcDepInjection(self):
        """
        Test whether the implicit libc dependency injection (bug #913628)
        is correctly added for only ebuilds installing an ELF binary.

        Based on BlockerFileCollisionEmergeTestCase.
        """
        debug = False

        install_elf = textwrap.dedent(
            """
        S="${WORKDIR}"

        src_install() {
            insinto /usr/bin
            # We need an ELF binary for the injection to trigger, so
            # use ${BASH} given we know it must be around for running ebuilds.
            cp "${BASH}" "${ED}"/usr/bin/${PN} || die
        }
        """
        )

        ebuilds = {
            "sys-libs/glibc-2.38": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "virtual/libc-1": {
                "EAPI": "8",
                "RDEPEND": "sys-libs/glibc",
            },
            "dev-libs/A-1": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "dev-libs/B-1": {
                "EAPI": "8",
            },
            "dev-libs/C-1": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "dev-libs/D-1": {
                "EAPI": "8",
            },
            "dev-libs/E-1": {
                "EAPI": "8",
                "RDEPEND": ">=dev-libs/D-1",
                "MISC_CONTENT": install_elf,
            },
        }

        world = ("dev-libs/A",)

        playground = ResolverPlayground(ebuilds=ebuilds, world=world, debug=debug)
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        test_commands = (
            # If we install a package with an ELF but no libc provider is installed,
            # make sure we don't inject anything (we don't want to have some bare RDEPEND with
            # literally "[]").
            emerge_cmd
            + (
                "--oneshot",
                "dev-libs/C",
            ),
            (
                lambda: not portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "dev-libs", "C-1", "RDEPEND"
                    )
                ),
            ),
            # (We need sys-libs/glibc pulled in and virtual/libc installed)
            emerge_cmd
            + (
                "--oneshot",
                "virtual/libc",
            ),
            # A package NOT installing an ELF binary shouldn't have an injected libc dep
            # Let's check the virtual/libc one as we already have to merge it to pull in
            # sys-libs/glibc, but we'll do a better check after too.
            (
                lambda: ">=sys-libs/glibc-2.38\n"
                not in portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "virtual", "libc-1", "RDEPEND"
                    )
                ),
            ),
            # A package NOT installing an ELF binary shouldn't have an injected libc dep
            emerge_cmd
            + (
                "--oneshot",
                "dev-libs/B",
            ),
            (
                lambda: not portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "dev-libs", "B-1", "RDEPEND"
                    )
                ),
            ),
            # A package installing an ELF binary should have an injected libc dep
            emerge_cmd
            + (
                "--oneshot",
                "dev-libs/A",
            ),
            (lambda: os.path.exists(os.path.join(eroot, "usr/bin/A")),),
            (
                lambda: ">=sys-libs/glibc-2.38\n"
                in portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "dev-libs", "A-1", "RDEPEND"
                    )
                ),
            ),
            # Install glibc again because earlier, no libc was installed, so the injection
            # wouldn't have fired even if the "are we libc?" check was broken.
            emerge_cmd
            + (
                "--oneshot",
                "sys-libs/glibc",
            ),
            # We don't want the libc (sys-libs/glibc is the provider here) to have an injected dep on itself
            (
                lambda: ">=sys-libs/glibc-2.38\n"
                not in portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "sys-libs", "glibc-2.38", "RDEPEND"
                    )
                ),
            ),
            # Make sure we append to, not clobber, RDEPEND
            emerge_cmd
            + (
                "--oneshot",
                "dev-libs/E",
            ),
            (
                lambda: [">=dev-libs/D-1 >=sys-libs/glibc-2.38\n"]
                == portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "dev-libs", "E-1", "RDEPEND"
                    )
                ),
            ),
        )

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
            "FEATURES": "-qa-unresolved-soname-deps -preserve-libs -merge-sync",
        }

        dirs = [
            playground.distdir,
            fake_bin,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
        ]

        true_symlinks = ["chown", "chgrp"]

        # We don't want to make pax-utils a hard-requirement for tests,
        # so if it's not found, skip the test rather than FAIL it.
        needed_binaries = {
            "true": (find_binary("true"), True),
            "scanelf": (find_binary("scanelf"), False),
            "find": (find_binary("find"), True),
        }

        for name, (path, mandatory) in needed_binaries.items():
            found = path is not None

            if not found:
                if mandatory:
                    self.assertIsNotNone(path, f"command {name} not found")
                else:
                    self.skipTest(f"{name} not found")

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(needed_binaries["true"][0], os.path.join(fake_bin, x))

            # We need scanelf, find for the ELF parts (creating NEEDED)
            os.symlink(needed_binaries["scanelf"][0], os.path.join(fake_bin, "scanelf"))
            os.symlink(needed_binaries["find"][0], os.path.join(fake_bin, "find"))

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")
            with open(os.path.join(profile_path, "packages"), "w") as f:
                f.write("*virtual/libc")

            if debug:
                # The subprocess inherits both stdout and stderr, for
                # debugging purposes.
                stdout = None
            else:
                # The subprocess inherits stderr so that any warnings
                # triggered by python -Wd will be visible.
                stdout = subprocess.PIPE

            for i, args in enumerate(test_commands):
                if hasattr(args[0], "__call__"):
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

                self.assertEqual(
                    os.EX_OK, proc.returncode, f"emerge failed with args {args}"
                )

            # Check that dev-libs/A doesn't get re-emerged via --changed-deps
            # after injecting the libc dep. We want to suppress the injected
            # dep in the changed-deps comparisons.
            k = ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--changed-deps": True,
                    "--deep": True,
                    "--update": True,
                    "--verbose": True,
                },
                success=True,
                mergelist=[],
            )
            playground.run_TestCase(k)
            self.assertEqual(k.test_success, True, k.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()

    def testBinpkgLibcDepInjection(self):
        """
        Test whether the implicit libc dependency injection (bug #913628)
        correctly forces an upgrade to a newer glibc before merging a binpkg
        built against it.

        Based on BlockerFileCollisionEmergeTestCase.
        """
        debug = False

        install_elf = textwrap.dedent(
            """
        S="${WORKDIR}"

        src_install() {
            insinto /usr/bin
            # We need an ELF binary for the injection to trigger, so
            # use ${BASH} given we know it must be around for running ebuilds.
            cp "${BASH}" "${ED}"/usr/bin/${PN} || die
        }
        """
        )

        ebuilds = {
            "sys-libs/glibc-2.37": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "sys-libs/glibc-2.38": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "virtual/libc-1": {
                "EAPI": "8",
                "RDEPEND": "sys-libs/glibc",
            },
            "dev-libs/A-1": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
            "dev-libs/B-1": {
                "EAPI": "8",
            },
            "dev-libs/C-1": {
                "EAPI": "8",
                "MISC_CONTENT": install_elf,
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds, debug=debug)
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
        )

        test_commands = (
            # (We need sys-libs/glibc pulled in and virtual/libc installed)
            emerge_cmd
            + (
                "--oneshot",
                "virtual/libc",
            ),
            # A package installing an ELF binary should have an injected libc dep
            emerge_cmd
            + (
                "--oneshot",
                "dev-libs/A",
            ),
            (lambda: os.path.exists(os.path.join(eroot, "usr/bin/A")),),
            (
                lambda: ">=sys-libs/glibc-2.38\n"
                in portage.util.grablines(
                    os.path.join(
                        eprefix, "var", "db", "pkg", "dev-libs", "A-1", "RDEPEND"
                    )
                ),
            ),
            # Downgrade glibc to a version (2.37) older than the version
            # that dev-libs/A's binpkg was built against (2.38). Below,
            # we check that it pulls in a newer glibc via a ResolverPlayground
            # testcase.
            emerge_cmd
            + (
                "--oneshot",
                "--nodeps",
                "<sys-libs/glibc-2.38",
            ),
        )

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

        # We don't want to make pax-utils a hard-requirement for tests,
        # so if it's not found, skip the test rather than FAIL it.
        needed_binaries = {
            "true": (find_binary("true"), True),
            "scanelf": (find_binary("scanelf"), False),
            "find": (find_binary("find"), True),
        }

        for name, (path, mandatory) in needed_binaries.items():
            found = path is not None

            if not found:
                if mandatory:
                    self.assertIsNotNone(path, f"command {name} not found")
                else:
                    self.skipTest(f"{name} not found")

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(needed_binaries["true"][0], os.path.join(fake_bin, x))

            # We need scanelf, find for the ELF parts (creating NEEDED)
            os.symlink(needed_binaries["scanelf"][0], os.path.join(fake_bin, "scanelf"))
            os.symlink(needed_binaries["find"][0], os.path.join(fake_bin, "find"))

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")
            with open(os.path.join(profile_path, "packages"), "w") as f:
                f.write("*virtual/libc")

            if debug:
                # The subprocess inherits both stdout and stderr, for
                # debugging purposes.
                stdout = None
            else:
                # The subprocess inherits stderr so that any warnings
                # triggered by python -Wd will be visible.
                stdout = subprocess.PIPE

            for i, args in enumerate(test_commands):
                if hasattr(args[0], "__call__"):
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

                self.assertEqual(
                    os.EX_OK, proc.returncode, f"emerge failed with args {args}"
                )

            # Now check that glibc gets upgraded to the right version
            # for the binpkg first after we downgraded it earlier, before
            # merging the dev-libs/A binpkg which needs 2.38.
            k = ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={
                    "--usepkgonly": True,
                    "--verbose": True,
                },
                success=True,
                mergelist=["[binary]sys-libs/glibc-2.38-1", "[binary]dev-libs/A-1-1"],
            )
            playground.run_TestCase(k)
            self.assertEqual(k.test_success, True, k.fail_msg)

        finally:
            playground.debug = False
            playground.cleanup()
