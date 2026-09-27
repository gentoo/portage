# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shutil

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util._dyn_libs.LinkageMapELF import LinkageMapELF


class LinkageMapUpdateTestCase(TestCase):
    """
    LinkageMapELF.rebuild() drops removed packages in place, and the result
    must match a full rebuild.
    """

    # cpv -> NEEDED.ELF.2 lines, as arch;path;soname;runpath;needed;category
    needed = {
        "dev-libs/A-1": ("X86_64;/usr/lib64/libA.so.1;libA.so.1;;libc.so.6;x86_64",),
        "dev-libs/B-1": (
            "X86_64;/usr/lib64/libB.so.1;libB.so.1;;libA.so.1,libc.so.6;x86_64",
        ),
        "app-misc/C-1": (
            "X86_64;/usr/bin/c;;;libA.so.1,libB.so.1,libc.so.6;x86_64",
            "X86_64;/usr/lib64/libC.so.1;libC.so.1;;libc.so.6;x86_64",
        ),
    }

    def setUp(self):
        installed = {
            cpv: {"EAPI": "8", "COUNTER": str(i + 1)}
            for i, cpv in enumerate(self.needed)
        }
        self.playground = ResolverPlayground(installed=installed)
        self.eroot = self.playground.eroot
        self.vardb = self.playground.trees[self.eroot]["vartree"].dbapi
        for cpv, lines in self.needed.items():
            path = os.path.join(self.vardb.getpath(cpv), "NEEDED.ELF.2")
            with open(path, "w") as f:
                f.write("".join(f"{line}\n" for line in lines))
            self.vardb._bump_mtime(cpv)

    def tearDown(self):
        self.playground.cleanup()

    @staticmethod
    def _snapshot(linkmap):
        libs = {
            arch: {
                soname: (frozenset(node.providers), frozenset(node.consumers))
                for soname, node in sonames.items()
            }
            for arch, sonames in linkmap._libs.items()
        }
        props = {
            key: (
                p.arch,
                p.needed,
                p.runpaths,
                p.soname,
                frozenset(p.alt_paths),
                p.owner,
            )
            for key, p in linkmap._obj_properties.items()
        }
        return libs, props, dict(linkmap._obj_key_cache)

    def _counting_linkmap(self):
        linkmap = LinkageMapELF(self.vardb)
        linkmap.full_rebuilds = 0
        clear_cache = linkmap._clear_cache

        def counting_clear_cache():
            linkmap.full_rebuilds += 1
            clear_cache()

        linkmap._clear_cache = counting_clear_cache
        return linkmap

    def _remove(self, cpv):
        shutil.rmtree(self.vardb.getpath(cpv))
        self.vardb._bump_mtime(cpv)

    def test_removal_matches_full_rebuild(self):
        linkmap = self._counting_linkmap()
        linkmap.rebuild()
        self.assertIsNotNone(linkmap._indexed_pkgs)

        for cpv in ("dev-libs/B-1", "dev-libs/A-1"):
            self._remove(cpv)
            linkmap.rebuild()
            expected = LinkageMapELF(self.vardb)
            expected.rebuild()
            self.assertEqual(self._snapshot(linkmap), self._snapshot(expected))

        self.assertEqual(linkmap.getOwners("/usr/bin/c"), ("app-misc/C-1",))
        self.assertEqual(linkmap.getSoname("/usr/lib64/libC.so.1"), "libC.so.1")
        self.assertEqual(linkmap.full_rebuilds, 1)

    def test_invalidate_rebuilds_on_query(self):
        linkmap = self._counting_linkmap()
        linkmap.rebuild()
        self._remove("dev-libs/A-1")
        linkmap._invalidate()
        with self.assertRaises(KeyError):
            linkmap.getOwners("/usr/lib64/libA.so.1")
        expected = LinkageMapELF(self.vardb)
        expected.rebuild()
        self.assertEqual(self._snapshot(linkmap), self._snapshot(expected))
        self.assertEqual(linkmap.full_rebuilds, 1)

    def test_library_path_change_forces_full_rebuild(self):
        linkmap = self._counting_linkmap()
        linkmap.rebuild()
        self._remove("dev-libs/B-1")
        os.makedirs(os.path.join(self.eroot, "etc"), exist_ok=True)
        with open(os.path.join(self.eroot, "etc", "ld.so.conf"), "a") as f:
            f.write("/opt/new/lib64\n")
        linkmap.rebuild()
        self.assertEqual(linkmap.full_rebuilds, 2)

    def test_arguments_disable_update(self):
        linkmap = self._counting_linkmap()
        linkmap.rebuild(exclude_pkgs=["dev-libs/B-1"])
        self.assertIsNone(linkmap._indexed_pkgs)
        linkmap.rebuild()
        self.assertEqual(linkmap.full_rebuilds, 2)
