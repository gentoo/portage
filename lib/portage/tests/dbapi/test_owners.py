# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shutil

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class OwnersTestCase(TestCase):
    """
    Exercise vardbapi._owners against hand-written CONTENTS.
    """

    installed = {
        "dev-libs/A-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/B-1": {"EAPI": "7", "SLOT": "0"},
        "dev-libs/C-1": {"EAPI": "7", "SLOT": "0"},
    }

    # cpv -> the paths, relative to EROOT, that it owns.
    contents = {
        "dev-libs/A-1": ("usr/lib/libA.so", "usr/bin/tool"),
        "dev-libs/B-1": ("usr/lib/libB.so", "usr/bin/tool"),
        # C records its library under the other spelling of usr/lib.
        "dev-libs/C-1": ("usr/target/libC.so",),
    }

    user_config = {}

    def setUp(self):
        self.playground = ResolverPlayground(
            installed=self.installed, user_config=self.user_config
        )
        eroot = self.playground.eroot
        self.vardb = self.playground.trees[eroot]["vartree"].dbapi

        # usr/lib is a symlink to usr/target, so the two are one directory
        # recorded under two spellings, like the cross-toolchain
        # /usr/${CHOST}/lib symlinks.
        os.makedirs(self._abs("usr/target"), exist_ok=True)
        os.makedirs(self._abs("usr/bin"), exist_ok=True)
        if not os.path.exists(self._abs("usr/lib")):
            os.symlink("target", self._abs("usr/lib"))

        for cpv, paths in self.contents.items():
            self._write_contents(cpv, paths)

    def tearDown(self):
        self.playground.cleanup()

    def _abs(self, path):
        return os.path.join(self.playground.eroot, path)

    def _write_contents(self, cpv, paths):
        contents = {}
        for path in paths:
            abs_path = self._abs(path)
            with open(abs_path, "w") as f:
                f.write(cpv)
            mtime = str(int(os.lstat(abs_path).st_mtime))
            contents[abs_path] = ("obj", mtime, 32 * "0")
        self.vardb.writeContentsToContentsFile(self.vardb._dblink(cpv), contents)

    def _owners(self, *paths):
        """
        Return the {cpv: {path relative to EROOT, ...}} the given query
        yields, and assert that no (owner, path) pair is reported twice.
        """
        results = list(self.vardb._owners.iter_owners(list(paths)))
        self.assertEqual(len(results), len({(o.mycpv, p) for o, p in results}))
        owners = {}
        for owner, path in results:
            owners.setdefault(owner.mycpv, set()).add(path)
        return owners

    def test_exact_path(self):
        self.assertEqual(
            self._owners(self._abs("usr/lib/libA.so")),
            {"dev-libs/A-1": {"usr/lib/libA.so"}},
        )

    def test_unowned_path(self):
        self.assertEqual(self._owners(self._abs("usr/lib/libZ.so")), {})

    def test_nonexistent_path(self):
        self.assertEqual(self._owners(self._abs("no/such/dir/no-such-file")), {})

    def test_trailing_separator(self):
        self.assertEqual(
            self._owners(self._abs("usr/lib/libA.so") + os.sep),
            {"dev-libs/A-1": {"usr/lib/libA.so"}},
        )

    def test_path_shared_by_two_packages(self):
        self.assertEqual(
            self._owners(self._abs("usr/bin/tool")),
            {"dev-libs/A-1": {"usr/bin/tool"}, "dev-libs/B-1": {"usr/bin/tool"}},
        )

    def test_basename(self):
        self.assertEqual(self._owners("libB.so"), {"dev-libs/B-1": {"usr/lib/libB.so"}})

    def test_basename_shared_by_two_packages(self):
        self.assertEqual(
            self._owners("tool"),
            {"dev-libs/A-1": {"usr/bin/tool"}, "dev-libs/B-1": {"usr/bin/tool"}},
        )

    def test_batched_query(self):
        self.assertEqual(
            self._owners(
                self._abs("usr/lib/libA.so"), "libB.so", self._abs("usr/lib/libZ.so")
            ),
            {"dev-libs/A-1": {"usr/lib/libA.so"}, "dev-libs/B-1": {"usr/lib/libB.so"}},
        )

    def test_symlinked_parent_directory(self):
        # C recorded usr/target/libC.so; asking through usr/lib has to find it
        # by matching the parent directory's inode.
        self.assertEqual(
            self._owners(self._abs("usr/lib/libC.so")),
            {"dev-libs/C-1": {"usr/target/libC.so"}},
        )

    def test_symlinked_parent_directory_other_way(self):
        # ... and the same in reverse, for a file recorded under usr/lib.
        self.assertEqual(
            self._owners(self._abs("usr/target/libA.so")),
            {"dev-libs/A-1": {"usr/lib/libA.so"}},
        )

    def test_recreated_parent_directory(self):
        libC = self._abs("usr/lib/libC.so")
        self.assertEqual(self._owners(libC), {"dev-libs/C-1": {"usr/target/libC.so"}})
        # usr/target is removed and recreated, with a new inode, by a merge
        # of another package.
        shutil.rmtree(self._abs("usr/target"))
        os.makedirs(self._abs("usr/target"))
        self._write_contents("dev-libs/B-1", ("usr/target/libB.so", "usr/bin/tool"))
        self.assertEqual(self._owners(libC), {"dev-libs/C-1": {"usr/target/libC.so"}})

    def test_index_follows_rewritten_package(self):
        self.assertEqual(
            self._owners(self._abs("usr/bin/tool")),
            {"dev-libs/A-1": {"usr/bin/tool"}, "dev-libs/B-1": {"usr/bin/tool"}},
        )
        self.vardb.removeFromContents("dev-libs/B-1", [self._abs("usr/bin/tool")])
        self.assertEqual(
            self._owners(self._abs("usr/bin/tool")),
            {"dev-libs/A-1": {"usr/bin/tool"}},
        )
        # B's other file is still indexed.
        self.assertEqual(self._owners("libB.so"), {"dev-libs/B-1": {"usr/lib/libB.so"}})

    def test_index_follows_removed_package(self):
        self.assertEqual(self._owners("libB.so"), {"dev-libs/B-1": {"usr/lib/libB.so"}})
        shutil.rmtree(self.vardb.getpath("dev-libs/B-1"))
        self.vardb._clear_cache()
        self.assertEqual(self._owners("libB.so"), {})
        self.assertEqual(
            self._owners(self._abs("usr/bin/tool")), {"dev-libs/A-1": {"usr/bin/tool"}}
        )

    def test_index_follows_new_file(self):
        self.assertEqual(self._owners("libD.so"), {})
        self._write_contents("dev-libs/C-1", ("usr/target/libC.so", "usr/lib/libD.so"))
        self.assertEqual(self._owners("libD.so"), {"dev-libs/C-1": {"usr/lib/libD.so"}})

    def test_get_owners(self):
        owners = self.vardb._owners.get_owners([self._abs("usr/bin/tool"), "libA.so"])
        self.assertEqual(
            {link.mycpv: files for link, files in owners.items()},
            {
                "dev-libs/A-1": {"usr/bin/tool", "usr/lib/libA.so"},
                "dev-libs/B-1": {"usr/bin/tool"},
            },
        )


class CaseInsensitiveOwnersTestCase(OwnersTestCase):
    user_config = {"make.conf": ('FEATURES="case-insensitive-fs"',)}

    contents = dict(OwnersTestCase.contents)
    # E and F record one path with different spellings.
    contents["dev-libs/E-1"] = ("usr/lib/LibE.so",)
    contents["dev-libs/F-1"] = ("usr/lib/LIBE.so",)

    installed = dict(OwnersTestCase.installed)
    installed["dev-libs/E-1"] = {"EAPI": "7", "SLOT": "0"}
    installed["dev-libs/F-1"] = {"EAPI": "7", "SLOT": "0"}

    def test_reports_recorded_spelling(self):
        expected = {
            "dev-libs/E-1": {"usr/lib/LibE.so"},
            "dev-libs/F-1": {"usr/lib/LIBE.so"},
        }
        self.assertEqual(self._owners(self._abs("usr/lib/libe.so")), expected)
        self.assertEqual(self._owners("LIBE.SO"), expected)
