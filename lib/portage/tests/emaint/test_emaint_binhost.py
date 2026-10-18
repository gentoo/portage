# Copyright 2025-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import filecmp
import os
import shutil
import time

from portage.tests import CommandStep, FunctionStep
from portage.tests.emaint.EmaintTestCase import EmaintTestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class EmainBinhostTestCase(EmaintTestCase):
    def testCompressedIndex(self):
        user_config = {"make.conf": ('FEATURES="-compress-index"',)}

        binpkgs = {
            "app-misc/A-1": {
                "EAPI": "8",
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "DEPEND": "app-misc/B",
                "RDEPEND": "app-misc/C",
            },
            "app-text/A-1": {
                "EAPI": "8",
                "BUILD_ID": "1",
                "BUILD_TIME": "1",
                "DEPEND": "app-misc/B",
                "RDEPEND": "app-misc/C",
            },
        }

        playground = ResolverPlayground(
            binpkgs=binpkgs,
            user_config=user_config,
            debug=False,
        )

        def current_time(offset=0):
            t = time.time() + offset
            return (t, t)

        emaint = self.cmds["emaint"]
        bintree = playground.trees[playground.settings["EROOT"]]["bintree"]

        def cmp_files(f1, f2):
            # filecmp.cmp caches results by (path, stat signature), where the
            # signature only includes second-precision mtimes, so a cached
            # outcome of an earlier comparison could be wrongly reused here.
            # Compare the contents directly, bypassing the cache.
            return filecmp._do_cmp(f1, f2)

        steps = (
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(bintree._pkgindex_file), f"step {i}"
                ),
            ),
            # Creating a fresh index then regenerating it should yield
            # the same result.
            FunctionStep(
                function=lambda i: os.unlink(bintree._pkgindex_file),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("binhost", "--fix"),
            ),
            FunctionStep(
                function=lambda i: shutil.copyfile(
                    bintree._pkgindex_file, f"{bintree._pkgindex_file}.bak"
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("binhost", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    cmp_files(bintree._pkgindex_file, f"{bintree._pkgindex_file}.bak")
                )
            ),
            # Make sure it differs if we bump the mtime on a binpkg.
            FunctionStep(
                function=lambda i: os.utime(
                    bintree.getname("app-misc/A-1"),
                    current_time(offset=1),
                ),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("binhost", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    cmp_files(bintree._pkgindex_file, f"{bintree._pkgindex_file}.bak")
                )
            ),
            FunctionStep(
                function=lambda i: os.unlink(f"{bintree._pkgindex_file}.bak"),
            ),
            # The compressed index should not exist yet because compress-index is disabled in make.conf.
            FunctionStep(
                function=lambda i: self.assertFalse(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                )
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--check"),
            ),
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                ),
            ),
            FunctionStep(
                function=lambda i: os.unlink(bintree._pkgindex_file + ".gz"),
            ),
            # It should report an error for a missing Packages.gz here.
            CommandStep(
                returncode=1,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--check"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--check"),
            ),
            # Bump the timestamp of Packages so that Packages.gz becomes stale.
            FunctionStep(
                function=lambda i: os.utime(
                    bintree._pkgindex_file, current_time(offset=2)
                ),
            ),
            # It should report an error for stale Packages.gz here.
            CommandStep(
                returncode=1,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--check"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "compress-index"},
                command=emaint + ("binhost", "--check"),
            ),
            # It should delete the unwanted Packages.gz here when compress-index is disabled.
            CommandStep(
                returncode=os.EX_OK,
                env={"FEATURES": "-compress-index"},
                command=emaint + ("binhost", "--fix"),
            ),
            FunctionStep(
                function=lambda i: self.assertFalse(
                    os.path.exists(bintree._pkgindex_file + ".gz"), f"step {i}"
                )
            ),
        )

        self.runEmaintTest(steps, playground)

    def testSameBasenameInDifferentDirs(self):
        """Test for bug #978985.

        The same basename can legitimately occur in different directories.
        When the corresponding packages also happen to have the same SIZE and
        mtime, the index can match a file against a package from a different
        directory unless the directory is taken into account. Ask emaint to
        regenerate the index twice, so that the second run reuses the index
        written by the first, and check that every package keeps the path that
        actually belongs to it.
        """
        user_config = {"make.conf": ('BINPKG_FORMAT="xpak"',)}

        metadata = {
            "EAPI": "8",
            "BUILD_ID": "1",
            "BUILD_TIME": "1",
            "CHOST": "x86_64-pc-linux-gnu",
            "USER_PATCHES": "0",
        }

        # The same PF in two categories produces packages whose file name only
        # differs by the directory they live in.
        binpkgs = {
            "cat1/foo-1": dict(metadata),
            "cat2/foo-1": dict(metadata),
        }

        playground = ResolverPlayground(
            binpkgs=binpkgs,
            user_config=user_config,
            debug=False,
        )

        emaint = self.cmds["emaint"]
        pkgdir = playground.settings["PKGDIR"]
        bintree = playground.trees[playground.settings["EROOT"]]["bintree"]

        def make_packages_match_index_by_timestamp(step):
            # Give both packages the same mtime, so that they can only be told
            # apart by their directory.
            mtime = int(time.time()) - 1000
            for category in ("cat1", "cat2"):
                path = bintree.getname(f"{category}/foo-1")
                os.utime(path, (mtime, mtime))

        def assert_paths_not_confused(step):
            bintree.populate(force_reindex=False)
            self.assertEqual(
                sorted(bintree.dbapi.cpv_all()),
                sorted(["cat1/foo-1", "cat2/foo-1"]),
                f"step {step}",
            )
            for category in ("cat1", "cat2"):
                cpv = f"{category}/foo-1"
                self.assertEqual(
                    bintree.getname(cpv),
                    os.path.join(pkgdir, category, "foo", "foo-1-1.xpak"),
                    f"step {step}: wrong path indexed for {cpv}",
                )

        steps = (
            FunctionStep(function=make_packages_match_index_by_timestamp),
            # The first run writes the index, the second one reindexes against
            # it, which is where the basename index is consulted.
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("binhost", "--fix"),
            ),
            CommandStep(
                returncode=os.EX_OK,
                command=emaint + ("binhost", "--fix"),
            ),
            FunctionStep(function=assert_paths_not_confused),
        )

        self.runEmaintTest(steps, playground)
