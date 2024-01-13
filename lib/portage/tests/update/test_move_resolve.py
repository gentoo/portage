# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
import textwrap
import pytest
import portage
from portage import os
from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.util import ensure_dirs
from portage._global_updates import _do_global_updates
from portage.output import colorize


class MoveResolveTestCase(TestCase):
    def testMoveResolve(self):
        ebuilds = {
            "dev-build/make-4.4::test_repo": {
                "EAPI": "4",
            },
        }

        installed = {
            "sys-devel/make-4.4::test_repo": {
                "EAPI": "4",
            },
        }

        binpkgs = {
            "sys-devel/make-4.4::test_repo": {
                "EAPI": "4",
            },
        }

        updates = textwrap.dedent(
            """
			move sys-devel/make dev-build/make
		    """
        )

        test_cases = (
            # Make sure we didn't break general resolution of CATEGORY/PN. Check with binpkgs.
            ResolverPlaygroundTestCase(
                ["sys-devel/make"],
                options={
                    "--usepkgonly": True,
                },
                success=True,
                mergelist=["[binary]dev-build/make-4.4"],
            ),
            # Make sure we didn't break general resolution of CATEGORY/PN. Check without binpkgs.
            ResolverPlaygroundTestCase(
                ["sys-devel/make"],
                options={},
                success=True,
                mergelist=["dev-build/make-4.4"],
            ),
            # Make sure we didn't change behaviour of just PN. Check without binpkgs.
            ResolverPlaygroundTestCase(
                ["make"], options={}, success=True, mergelist=["dev-build/make-4.4"]
            ),
            # This doesn't exist (dev-util != dev-build), so it should fail. Check with binpkgs.
            ResolverPlaygroundTestCase(
                ["dev-util/make"],
                options={
                    "--usepkgonly": True,
                },
                success=False,
            ),
            # This doesn't exist (dev-util != dev-build), so it should fail. Check without binpkgs.
            ResolverPlaygroundTestCase(
                ["dev-util/make"],
                options={},
                success=False,
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                playground = ResolverPlayground(
                    binpkgs=binpkgs,
                    ebuilds=ebuilds,
                    installed=installed,
                    user_config={
                        "make.conf": (
                            f'BINPKG_FORMAT="{binpkg_format}"',
                            'FEATURES="-binpkg-signing"',
                        ),
                    },
                    debug=True,
                )

                settings = playground.settings
                trees = playground.trees
                eroot = settings["EROOT"]
                test_repo_location = settings.repositories["test_repo"].location
                portdb = trees[eroot]["porttree"].dbapi
                vardb = trees[eroot]["vartree"].dbapi
                bindb = trees[eroot]["bintree"].dbapi

                updates_dir = os.path.join(test_repo_location, "profiles", "updates")

                try:
                    ensure_dirs(updates_dir)
                    with open(os.path.join(updates_dir, "1Q-2024"), "w") as f:
                        f.write(updates)

                    global_noiselimit = portage.util.noiselimit
                    portage.util.noiselimit = -2
                    try:
                        _do_global_updates(trees, {})
                    finally:
                        portage.util.noiselimit = global_noiselimit

                    # Workaround for cache validation not working
                    # correctly when filesystem has timestamp precision
                    # of 1 second.
                    vardb._clear_cache()

                    # A -> A-moved
                    self.assertRaises(
                        KeyError, vardb.aux_get, "sys-devel/make-4.4", ["EAPI"]
                    )
                    vardb.aux_get("dev-build/make-4.4", ["EAPI"])
                    # The original package should still exist because a binary
                    # package move is a copy on write operation.
                    bindb.aux_get("sys-devel/make-4.4", ["EAPI"])
                    bindb.aux_get("dev-build/make-4.4", ["EAPI"])

                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()
