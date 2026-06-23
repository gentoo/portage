# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import time

from portage.tests import CommandStep, FunctionStep
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.tests.emaint.EmaintTestCase import EmaintTestCase


class EmainBinhostTestCase(EmaintTestCase):
    def testCompressedIndex(self):
        user_config = {"make.conf": ('FEATURES="-compress-index"',)}

        binpkgs = {
            "app-misc/A-1": {
                "EAPI": "8",
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
        steps = (
            FunctionStep(
                function=lambda i: self.assertTrue(
                    os.path.exists(bintree._pkgindex_file), f"step {i}"
                ),
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
