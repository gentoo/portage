# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import glob
import os
import shutil
import subprocess
import sys
import textwrap

import portage
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage.util._dyn_libs.PreservedLibsRegistry import PreservedLibsRegistry

FOO = textwrap.dedent("""
    S="${WORKDIR}"

    src_compile() {
        echo 'int foo(void) { return 0; }' > foo.c || die
        gcc -shared -fPIC -Wl,-soname,libfoo.so.%(v)s -o libfoo.so.%(v)s foo.c || die
    }

    src_install() {
        dolib.so libfoo.so.%(v)s
        dosym libfoo.so.%(v)s /usr/$(get_libdir)/libfoo.so
    }
    """)

NOLIB = textwrap.dedent("""
    S="${WORKDIR}"

    src_install() {
        insinto /usr/share/foo
        newins - data <<< data
    }
    """)

CONSUMER = textwrap.dedent("""
    S="${WORKDIR}"

    src_compile() {
        echo 'int foo(void); int main(void) { return foo(); }' > main.c || die
        gcc -o consumer main.c -L"${ESYSROOT}/usr/$(get_libdir)" \\
            -Wl,-rpath,"${EPREFIX}/usr/$(get_libdir)" -lfoo || die
    }

    src_install() {
        dobin consumer
    }
    """)


class PreserveLibsTestCase(TestCase):
    def setUp(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("needs ELF")
        for tool in ("gcc", "scanelf"):
            if shutil.which(tool) is None:
                self.skipTest(f"needs {tool}")

        ebuilds = {
            "dev-libs/foo-1": {"EAPI": "8", "MISC_CONTENT": FOO % {"v": 1}},
            "dev-libs/foo-2": {"EAPI": "8", "MISC_CONTENT": FOO % {"v": 2}},
            "dev-libs/foo-3": {"EAPI": "8", "MISC_CONTENT": NOLIB},
            "dev-libs/foo-4": {"EAPI": "8", "MISC_CONTENT": NOLIB},
            "app-misc/consumer-1": {
                "EAPI": "8",
                "DEPEND": "dev-libs/foo",
                "RDEPEND": "dev-libs/foo",
                "MISC_CONTENT": CONSUMER,
            },
        }

        self.playground = ResolverPlayground(ebuilds=ebuilds)
        settings = self.playground.settings
        self.eprefix = eprefix = settings["EPREFIX"]

        # The linkmap runs scanelf from EPREFIX for preserved libraries.
        ensure_dirs(os.path.join(eprefix, "usr", "bin"))
        os.symlink(
            shutil.which("scanelf"), os.path.join(eprefix, "usr", "bin", "scanelf")
        )

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is None or pythonpath.split(":")[0] != PORTAGE_PYM_PATH:
            pythonpath = PORTAGE_PYM_PATH + (":" + pythonpath if pythonpath else "")

        self.env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "FEATURES": "preserve-libs -sandbox -usersandbox",
            "PATH": settings.get("PATH"),
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
            "PORTAGE_PYTHON": portage._python_interpreter,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", "1"),
            "PYTHONPATH": pythonpath,
        }

        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        for d in (
            self.playground.distdir,
            os.path.join(eprefix, "var", "tmp", "portage"),
            var_cache_edb,
        ):
            ensure_dirs(d)
        with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
            f.write(b"100")

        self.registry = PreservedLibsRegistry(
            settings["ROOT"],
            os.path.join(eprefix, "var", "lib", "portage", "preserved_libs_registry"),
        )

        self.emerge("=dev-libs/foo-1", "app-misc/consumer")
        (self.lib,) = glob.glob(os.path.join(eprefix, "usr", "lib*", "libfoo.so.1"))

    def tearDown(self):
        self.playground.cleanup()

    def emerge(self, *args):
        proc = subprocess.run(
            (
                portage._python_interpreter,
                "-b",
                "-Wd",
                os.path.join(str(self.bindir), "emerge"),
                "--oneshot",
            )
            + args,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, os.EX_OK, proc.stdout)

    def preserved_libs(self):
        self.registry.load()
        return self.registry.getPreservedLibs()

    def testPreserveAndPrune(self):
        """
        A library that is still consumed is preserved when its package is
        upgraded to a new soname, and removed once nothing consumes it.
        """
        self.emerge("=dev-libs/foo-2")
        self.assertTrue(os.path.exists(self.lib))
        self.assertEqual(self.preserved_libs(), {"dev-libs/foo-2": [self.lib]})

        self.emerge("app-misc/consumer")
        self.assertFalse(os.path.exists(self.lib))
        self.assertEqual(self.preserved_libs(), {})

    def testPreservedLibCarriedOver(self):
        """
        A preserved library stays preserved when the package that owns it is
        replaced again, even if that package no longer provides a library.
        """
        self.emerge("=dev-libs/foo-3")
        self.assertEqual(self.preserved_libs(), {"dev-libs/foo-3": [self.lib]})

        self.emerge("=dev-libs/foo-4")
        self.assertTrue(os.path.exists(self.lib))
        self.assertEqual(self.preserved_libs(), {"dev-libs/foo-4": [self.lib]})
