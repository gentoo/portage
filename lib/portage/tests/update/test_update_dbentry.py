# Copyright 2012-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function
import sys
import re
import textwrap

import portage
from portage import os
from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.dep import Atom
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.update import update_dbentry
from portage.util import ensure_dirs
from portage.versions import _pkg_str
from portage._global_updates import _do_global_updates
from portage.output import colorize


class UpdateDbentryTestCase(TestCase):
    def testUpdateDbentryTestCase(self):
        cases = (
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "1",
                "  dev-libs/A:0  ",
                "  dev-libs/B:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "1",
                "  >=dev-libs/A-1:0  ",
                "  >=dev-libs/B-1:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "2",
                "  dev-libs/A[foo]  ",
                "  dev-libs/B[foo]  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "5",
                "  dev-libs/A:0/1=[foo]  ",
                "  dev-libs/B:0/1=[foo]  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "5",
                "  dev-libs/A:0/1[foo]  ",
                "  dev-libs/B:0/1[foo]  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "5",
                "  dev-libs/A:0/0[foo]  ",
                "  dev-libs/B:0/0[foo]  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                "5",
                "  dev-libs/A:0=[foo]  ",
                "  dev-libs/B:0=[foo]  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "1",
                "  dev-libs/A:0  ",
                "  dev-libs/A:1  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "1",
                "  >=dev-libs/A-1:0  ",
                "  >=dev-libs/A-1:1  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "5",
                "  dev-libs/A:0/1=[foo]  ",
                "  dev-libs/A:1/1=[foo]  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "5",
                "  dev-libs/A:0/1[foo]  ",
                "  dev-libs/A:1/1[foo]  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "5",
                "  dev-libs/A:0/0[foo]  ",
                "  dev-libs/A:1/1[foo]  ",
            ),
            (
                ("slotmove", Atom("dev-libs/A"), "0", "1"),
                "5",
                "  dev-libs/A:0=[foo]  ",
                "  dev-libs/A:1=[foo]  ",
            ),
        )
        for update_cmd, eapi, input_str, output_str in cases:
            result = update_dbentry(update_cmd, input_str, eapi=eapi)
            self.assertEqual(result, output_str)

    def testUpdateDbentryBlockerTestCase(self):
        """
        Avoid creating self-blockers for bug #367215.
        """
        cases = (
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/B-1", eapi="1", slot="0"),
                "  !dev-libs/A  ",
                "  !dev-libs/A  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/C-1", eapi="1", slot="0"),
                "  !dev-libs/A  ",
                "  !dev-libs/B  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/B-1", eapi="1", slot="0"),
                "  !dev-libs/A:0  ",
                "  !dev-libs/A:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/C-1", eapi="1", slot="0"),
                "  !dev-libs/A:0  ",
                "  !dev-libs/B:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/C-1", eapi="1", slot="0"),
                "  !>=dev-libs/A-1:0  ",
                "  !>=dev-libs/B-1:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/B-1", eapi="1", slot="0"),
                "  !>=dev-libs/A-1:0  ",
                "  !>=dev-libs/A-1:0  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/C-1", eapi="1", slot="0"),
                "  !>=dev-libs/A-1  ",
                "  !>=dev-libs/B-1  ",
            ),
            (
                ("move", Atom("dev-libs/A"), Atom("dev-libs/B")),
                _pkg_str("dev-libs/B-1", eapi="1", slot="0"),
                "  !>=dev-libs/A-1  ",
                "  !>=dev-libs/A-1  ",
            ),
        )
        for update_cmd, parent, input_str, output_str in cases:
            result = update_dbentry(update_cmd, input_str, parent=parent)
            self.assertEqual(result, output_str)

    def testUpdateDbentryDbapiTestCase(self):

        ebuilds = {
            "dev-libs/A-2::dont_apply_updates": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
                "SLOT": "2",
            },
            "dev-libs/B-2::dont_apply_updates": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
                "SLOT": "2",
            },
        }

        installed = {
            "dev-libs/A-1::test_repo": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
                "SLOT": "2",
            },
            "dev-libs/B-1::test_repo": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
            },
            "dev-libs/M-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/N-1::test_repo": {
                "EAPI": "4",
            },
            "dev-libs/N-2::test_repo": {
                "EAPI": "4",
            },
        }

        binpkgs = {
            "dev-libs/A-1::test_repo": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
            },
            "dev-libs/A-2::dont_apply_updates": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
                "SLOT": "2",
            },
            "dev-libs/B-1::test_repo": {
                "RDEPEND": "dev-libs/M dev-libs/N dev-libs/P",
                "EAPI": "4",
            },
        }

        world = ["dev-libs/M", "dev-libs/N"]

        updates = textwrap.dedent(
            """
			move dev-libs/M dev-libs/M-moved
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
                    world=world,
                    user_config={
                        "make.conf": ('BINPKG_FORMAT="%s"' % binpkg_format,),
                    },
                )

                settings = playground.settings
                trees = playground.trees
                eroot = settings["EROOT"]
                test_repo_location = settings.repositories["test_repo"].location
                portdb = trees[eroot]["porttree"].dbapi
                vardb = trees[eroot]["vartree"].dbapi
                bindb = trees[eroot]["bintree"].dbapi
                setconfig = trees[eroot]["root_config"].setconfig
                selected_set = setconfig.getSets()["selected"]

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

                    # M -> M-moved
                    old_pattern = re.compile(r"\bdev-libs/M(\s|$)")
                    rdepend = vardb.aux_get("dev-libs/A-1", ["RDEPEND"])[0]
                    self.assertTrue(old_pattern.search(rdepend) is None)
                    self.assertTrue("dev-libs/M-moved" in rdepend)
                    rdepend = bindb.aux_get("dev-libs/A-1", ["RDEPEND"])[0]
                    self.assertTrue(old_pattern.search(rdepend) is None)
                    self.assertTrue("dev-libs/M-moved" in rdepend)
                    rdepend = vardb.aux_get("dev-libs/B-1", ["RDEPEND"])[0]
                    self.assertTrue(old_pattern.search(rdepend) is None)
                    self.assertTrue("dev-libs/M-moved" in rdepend)
                    rdepend = vardb.aux_get("dev-libs/B-1", ["RDEPEND"])[0]
                    self.assertTrue(old_pattern.search(rdepend) is None)
                    self.assertTrue("dev-libs/M-moved" in rdepend)

                    # dont_apply_updates
                    rdepend = vardb.aux_get("dev-libs/A-2", ["RDEPEND"])[0]
                    self.assertTrue("dev-libs/M" in rdepend)
                    self.assertTrue("dev-libs/M-moved" not in rdepend)
                    rdepend = bindb.aux_get("dev-libs/A-2", ["RDEPEND"])[0]
                    self.assertTrue("dev-libs/M" in rdepend)
                    self.assertTrue("dev-libs/M-moved" not in rdepend)

                    selected_set.load()
                    self.assertTrue("dev-libs/M" not in selected_set)
                    self.assertTrue("dev-libs/M-moved" in selected_set)

                finally:
                    playground.cleanup()
