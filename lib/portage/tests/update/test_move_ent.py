# Copyright 2012-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
import textwrap
import pytest
import portage
from portage import os
from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage._global_updates import _do_global_updates
from portage.output import colorize


class MoveEntTestCase(TestCase):
    def testMoveEnt(self):
        ebuilds = {
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        installed = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        binpkgs = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        updates = textwrap.dedent(
            """
			move dev-libs/A dev-libs/A-moved
		"""
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
                    with open(os.path.join(updates_dir, "1Q-2010"), "w") as f:
                        f.write(updates)

                    # Create an empty updates directory, so that this
                    # repo doesn't inherit updates from the main repo.
                    ensure_dirs(
                        os.path.join(
                            portdb.getRepositoryPath("dont_apply_updates"),
                            "profiles",
                            "updates",
                        )
                    )

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
                    self.assertRaises(KeyError, vardb.aux_get, "dev-libs/A-1", ["EAPI"])
                    vardb.aux_get("dev-libs/A-moved-1", ["EAPI"])
                    # The original package should still exist because a binary
                    # package move is a copy on write operation.
                    bindb.aux_get("dev-libs/A-1", ["EAPI"])
                    bindb.aux_get("dev-libs/A-moved-1", ["EAPI"])

                    # dont_apply_updates
                    self.assertRaises(
                        KeyError, vardb.aux_get, "dev-libs/A-moved-2", ["EAPI"]
                    )
                    vardb.aux_get("dev-libs/A-2", ["EAPI"])
                    self.assertRaises(
                        KeyError, bindb.aux_get, "dev-libs/A-moved-2", ["EAPI"]
                    )
                    bindb.aux_get("dev-libs/A-2", ["EAPI"])

                finally:
                    playground.cleanup()

    def testMoveEntWithSignature(self):
        ebuilds = {
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        installed = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        binpkgs = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        updates = textwrap.dedent(
            """
			move dev-libs/A dev-libs/A-moved
		"""
        )

        for binpkg_format in ("gpkg",):
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                playground = ResolverPlayground(
                    binpkgs=binpkgs,
                    ebuilds=ebuilds,
                    installed=installed,
                    user_config={
                        "make.conf": (f'BINPKG_FORMAT="{binpkg_format}"',),
                    },
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
                    with open(os.path.join(updates_dir, "1Q-2010"), "w") as f:
                        f.write(updates)

                    # Create an empty updates directory, so that this
                    # repo doesn't inherit updates from the main repo.
                    ensure_dirs(
                        os.path.join(
                            portdb.getRepositoryPath("dont_apply_updates"),
                            "profiles",
                            "updates",
                        )
                    )

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
                    self.assertRaises(KeyError, vardb.aux_get, "dev-libs/A-1", ["EAPI"])
                    vardb.aux_get("dev-libs/A-moved-1", ["EAPI"])
                    # The original package should still exist because a binary
                    # package move is a copy on write operation.
                    bindb.aux_get("dev-libs/A-1", ["EAPI"])
                    print(bindb.aux_get("dev-libs/A-1", "PF"))
                    self.assertRaises(
                        KeyError, bindb.aux_get, "dev-libs/A-moved-1", ["EAPI"]
                    )

                    # dont_apply_updates
                    self.assertRaises(
                        KeyError, vardb.aux_get, "dev-libs/A-moved-2", ["EAPI"]
                    )
                    vardb.aux_get("dev-libs/A-2", ["EAPI"])
                    self.assertRaises(
                        KeyError, bindb.aux_get, "dev-libs/A-moved-2", ["EAPI"]
                    )
                    bindb.aux_get("dev-libs/A-2", ["EAPI"])

                finally:
                    playground.cleanup()

    # Ignore "The loop argument is deprecated" since this argument is conditionally
    # added to asyncio.Lock as needed for compatibility with python 3.9.
    @pytest.mark.filterwarnings("ignore:The loop argument is deprecated")
    @pytest.mark.filterwarnings("error")
    def testMoveEntWithCorruptIndex(self):
        """
        Test handling of the Packages index being stale (bug #920828)
        and gpkg's binpkg-multi-instance handling.

        We expect a UserWarning to be thrown if the gpkg structure is broken,
        so we promote that to an error.
        """
        ebuilds = {
            "dev-libs/A-moved-1::test_repo": {
                "EAPI": "4",
                "SLOT": "2",
            },
            "dev-libs/B-1::test_repo": {"EAPI": "4", "RDEPEND": "dev-libs/A-moved"},
        }

        installed = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/B-1::test_repo": {"EAPI": "4", "RDEPEND": "dev-libs/A"},
        }

        binpkgs = {
            "dev-libs/A-1::test_repo": {
                "EAPI": "4",
                "BUILD_ID": "1",
            },
            "dev-libs/B-1::test_repo": {
                "EAPI": "4",
                "BUILD_ID": "1",
                "RDEPEND": "dev-libs/A",
            },
        }

        updates = textwrap.dedent(
            """
			move dev-libs/A dev-libs/A-moved
		"""
        )

        for binpkg_format in ("gpkg",):
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
                            f'FEATURES="binpkg-multi-instance pkgdir-index-trusted"',
                        ),
                    },
                    debug=False,
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
                    with open(os.path.join(updates_dir, "1Q-2010"), "w") as f:
                        f.write(updates)

                    # Make the Packages index out-of-date
                    os.remove(
                        os.path.join(
                            bindb.bintree.pkgdir, "dev-libs", "A", "A-1-1.gpkg.tar"
                        )
                    )

                    global_noiselimit = portage.util.noiselimit
                    portage.util.noiselimit = -2
                    try:
                        _do_global_updates(trees, {})
                    finally:
                        portage.util.noiselimit = global_noiselimit
                finally:
                    playground.cleanup()
