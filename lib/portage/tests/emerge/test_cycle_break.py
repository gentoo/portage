# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import sys

import portage
import portage.util.mtimedb
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs


class CycleBreakEmergeTestCase(TestCase):
    def _ebuilds(self, freetype_install=""):
        return {
            "media-libs/freetype-1": {
                "EAPI": "8",
                "IUSE": "+harfbuzz",
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "RDEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "MISC_CONTENT": 'S="${WORKDIR}"\n' + freetype_install,
            },
            "media-libs/harfbuzz-1": {
                "EAPI": "8",
                "DEPEND": "media-libs/freetype",
                "RDEPEND": "media-libs/freetype",
                # Record the USE configuration of the freetype that was
                # installed when this package was built.
                "MISC_CONTENT": (
                    'S="${WORKDIR}"\n'
                    "src_install() {\n"
                    "\tinsinto /usr/share/${PN}\n"
                    "\tif has_version 'media-libs/freetype[harfbuzz]' ; then\n"
                    '\t\techo harfbuzz > "${T}"/freetype-use.txt\n'
                    "\telse\n"
                    '\t\techo -harfbuzz > "${T}"/freetype-use.txt\n'
                    "\tfi\n"
                    '\tdoins "${T}"/freetype-use.txt\n'
                    "}\n"
                ),
            },
        }

    def _emerge(self, playground, *args):
        """
        Run emerge --cycle-break=y in the playground and return its exit
        code and combined output.
        """
        settings = playground.settings
        eprefix = settings["EPREFIX"]
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
            "--cycle-break=y",
        )

        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
        fake_bin = os.path.join(eprefix, "bin")

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

        dirs = [
            playground.distdir,
            fake_bin,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
        ]
        true_symlinks = ["chown", "chgrp"]
        true_binary = find_binary("true")
        self.assertEqual(true_binary is None, False, "true command not found")

        for d in dirs:
            ensure_dirs(d)
        for x in true_symlinks:
            if not os.path.lexists(os.path.join(fake_bin, x)):
                os.symlink(true_binary, os.path.join(fake_bin, x))

        with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
            f.write(b"100")

        proc = subprocess.Popen(
            emerge_cmd + args,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = proc.stdout.read().decode("utf-8", "replace")
        proc.wait()
        proc.stdout.close()
        return proc.returncode, output

    def testCycleBreak(self):
        """
        Merge a cycle with --cycle-break=y and check that the first
        build uses the reduced USE configuration and that the second
        one uses the requested configuration.
        """
        playground = ResolverPlayground(ebuilds=self._ebuilds())
        eroot = playground.settings["EROOT"]
        vardb = playground.trees[eroot]["vartree"].dbapi

        try:
            returncode, output = self._emerge(playground, "media-libs/harfbuzz")
            if returncode != os.EX_OK:
                sys.stderr.write(output)
            self.assertEqual(
                os.EX_OK, returncode, f"emerge failed with exit code {returncode}"
            )

            # Both packages are installed, and freetype ended up with
            # the requested USE configuration.
            self.assertTrue(vardb.cpv_exists("media-libs/harfbuzz-1"))
            self.assertTrue(vardb.cpv_exists("media-libs/freetype-1"))
            (use,) = vardb.aux_get("media-libs/freetype-1", ["USE"])
            self.assertIn("harfbuzz", use.split())

            # harfbuzz was built against the temporary freetype, which
            # was built with USE=-harfbuzz.
            use_file = os.path.join(
                eroot, "usr", "share", "harfbuzz", "freetype-use.txt"
            )
            with open(use_file) as f:
                self.assertEqual(f.read().split(), ["-harfbuzz"])
        finally:
            playground.cleanup()

    def testWorldFileAndResume(self):
        """
        The transient build of a requested package does not add it to the
        world file, so a failed final build leaves it out. The resume list
        keeps only the final build.
        """
        ebuilds = self._ebuilds(
            freetype_install="src_install() {\n\tuse harfbuzz && die\n}\n"
        )
        playground = ResolverPlayground(ebuilds=ebuilds)
        eroot = playground.settings["EROOT"]
        try:
            returncode, output = self._emerge(
                playground, "media-libs/freetype", "media-libs/harfbuzz"
            )
            self.assertNotEqual(os.EX_OK, returncode, output)
            world_file = os.path.join(eroot, portage.const.WORLD_FILE)
            with open(world_file) as f:
                self.assertEqual(f.read().split(), ["media-libs/harfbuzz"])

            # The resume list forgets the transient build once it is
            # merged.
            mtimedb = portage.util.mtimedb.MtimeDB(
                os.path.join(eroot, portage.const.CACHE_PATH, "mtimedb")
            )
            self.assertEqual(
                mtimedb["resume"]["mergelist"],
                [["ebuild", eroot, "media-libs/freetype-1", "merge"]],
            )
            self.assertEqual(mtimedb["resume"]["cycle_break"], [])
        finally:
            playground.cleanup()

    def testKeepGoing(self):
        """
        With --keep-going, the cycle is still merged in order after an
        unrelated failure.
        """
        ebuilds = self._ebuilds()
        ebuilds["app-misc/broken-1"] = {
            "EAPI": "8",
            "MISC_CONTENT": 'S="${WORKDIR}"\nsrc_install() {\n\tdie\n}\n',
        }
        playground = ResolverPlayground(ebuilds=ebuilds)
        eroot = playground.settings["EROOT"]
        vardb = playground.trees[eroot]["vartree"].dbapi
        try:
            returncode, output = self._emerge(
                playground, "--keep-going", "app-misc/broken", "media-libs/harfbuzz"
            )
            self.assertNotEqual(os.EX_OK, returncode, output)
            self.assertFalse(vardb.cpv_exists("app-misc/broken-1"))
            self.assertTrue(vardb.cpv_exists("media-libs/harfbuzz-1"), output)
            (use,) = vardb.aux_get("media-libs/freetype-1", ["USE"])
            self.assertIn("harfbuzz", use.split())
            use_file = os.path.join(
                eroot, "usr", "share", "harfbuzz", "freetype-use.txt"
            )
            with open(use_file) as f:
                self.assertEqual(f.read().split(), ["-harfbuzz"])
        finally:
            playground.cleanup()

    def testTransientBuildFails(self):
        """
        With --keep-going, a failed transient build drops the final
        build and everything that needed the transient one.
        """
        ebuilds = self._ebuilds(
            freetype_install="src_install() {\n\tuse harfbuzz || die\n}\n"
        )
        playground = ResolverPlayground(ebuilds=ebuilds)
        eroot = playground.settings["EROOT"]
        vardb = playground.trees[eroot]["vartree"].dbapi
        try:
            returncode, output = self._emerge(
                playground, "--keep-going", "media-libs/harfbuzz"
            )
            self.assertNotEqual(os.EX_OK, returncode, output)
            self.assertFalse(vardb.cpv_exists("media-libs/freetype-1"))
            self.assertFalse(vardb.cpv_exists("media-libs/harfbuzz-1"))
            self.assertNotIn("Traceback", output)
            self.assertIn("media-libs/harfbuzz-1 dropped", output)
        finally:
            playground.cleanup()

    def testResumeSkipfirst(self):
        """
        Skipping a failed transient build with --resume --skipfirst also
        skips the final build, and drops what needed the transient one.
        """
        ebuilds = self._ebuilds(
            freetype_install="src_install() {\n\tuse harfbuzz || die\n}\n"
        )
        playground = ResolverPlayground(ebuilds=ebuilds)
        eroot = playground.settings["EROOT"]
        vardb = playground.trees[eroot]["vartree"].dbapi
        try:
            returncode, output = self._emerge(playground, "media-libs/harfbuzz")
            self.assertNotEqual(os.EX_OK, returncode, output)
            returncode, output = self._emerge(playground, "--resume", "--skipfirst")
            self.assertNotIn("circular dependencies", output)
            self.assertIn("dropped due to", output)
            self.assertFalse(vardb.cpv_exists("media-libs/freetype-1"))
            self.assertFalse(vardb.cpv_exists("media-libs/harfbuzz-1"))
        finally:
            playground.cleanup()
