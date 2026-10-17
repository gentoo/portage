# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage import config
from portage.dbapi.vartree import dblink
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

CONTENTS = "obj /usr/bin/foo d41d8cd98f00b204e9800998ecf8427e 0\n"
EXECUTABLE = "X86_64;/usr/bin/foo;;;libc.so.6;x86_64\n"
LIBRARY = "X86_64;/usr/lib64/libfoo.so.1;libfoo.so.1;;libc.so.6;x86_64\n"


class MayPreserveLibsTestCase(TestCase):
    """
    dblink._may_preserve_libs() decides whether treewalk needs the linkmap
    rebuild that _find_libs_to_preserve() depends on.
    """

    def setUp(self):
        installed = {
            "dev-libs/empty-1": {"EAPI": "8"},
            "dev-libs/noelf-1": {"EAPI": "8"},
            "dev-libs/exe-1": {"EAPI": "8"},
            "dev-libs/lib-1": {"EAPI": "8"},
            "dev-libs/plib-1": {"EAPI": "8"},
        }
        ebuilds = {cpv[:-1] + "2": metadata for cpv, metadata in installed.items()}
        self.playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        settings = self.playground.settings
        self.vartree = self.playground.trees[settings["EROOT"]]["vartree"]
        vardb = self.vartree.dbapi

        for cpv, contents, needed in (
            ("dev-libs/noelf-1", CONTENTS, None),
            ("dev-libs/exe-1", CONTENTS, EXECUTABLE),
            ("dev-libs/lib-1", CONTENTS, EXECUTABLE + LIBRARY),
            ("dev-libs/plib-1", CONTENTS, EXECUTABLE),
        ):
            with open(vardb.getpath(cpv, filename="CONTENTS"), "w") as f:
                f.write(contents)
            if needed is not None:
                with open(vardb.getpath(cpv, filename="NEEDED.ELF.2"), "w") as f:
                    f.write(needed)

        # plib-1 lists no soname, but owns a library it preserved. The
        # registry drops entries whose files do not exist.
        lib = os.path.join(settings["EROOT"], "usr", "lib64", "libplib.so.1")
        os.makedirs(os.path.dirname(lib))
        open(lib, "w").close()
        registry = vardb._plib_registry
        registry.lock()
        try:
            registry.load()
            registry.register("dev-libs/plib-1", "0", "1", [lib])
            registry.store()
        finally:
            registry.unlock()

        self.settings = config(clone=settings)
        self.settings.features.add("preserve-libs")

    def tearDown(self):
        self.playground.cleanup()

    def may_preserve_libs(self, pn, replaced=True):
        new = dblink(
            "dev-libs",
            f"{pn}-2",
            settings=self.settings,
            vartree=self.vartree,
            treetype="vartree",
        )
        if replaced:
            new._installed_instance = dblink(
                "dev-libs",
                f"{pn}-1",
                settings=self.settings,
                vartree=self.vartree,
                treetype="vartree",
            )
        return new._may_preserve_libs()

    def testNoReplacedInstance(self):
        self.assertFalse(self.may_preserve_libs("lib", replaced=False))

    def testReplacedInstanceOwnsNoFiles(self):
        self.assertFalse(self.may_preserve_libs("empty"))

    def testNoNeeded(self):
        self.assertFalse(self.may_preserve_libs("noelf"))

    def testNoSoname(self):
        self.assertFalse(self.may_preserve_libs("exe"))

    def testSoname(self):
        self.assertTrue(self.may_preserve_libs("lib"))

    def testPreservedLibs(self):
        self.assertTrue(self.may_preserve_libs("plib"))

    def testPreserveLibsDisabled(self):
        self.settings.features.discard("preserve-libs")
        self.assertFalse(self.may_preserve_libs("lib"))
