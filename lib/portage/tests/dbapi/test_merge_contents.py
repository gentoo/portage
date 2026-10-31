# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage import config
from portage.dbapi.vartree import dblink
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class MergeContentsTestCase(TestCase):
    """
    dblink._merge_contents() sets the umask to 0 while merging. It must
    restore the umask and discard the partial CONTENTS file if merging
    fails.
    """

    def setUp(self):
        self.playground = ResolverPlayground(ebuilds={"dev-libs/foo-1": {}})
        settings = self.playground.settings
        self.settings = config(clone=settings)
        self.vartree = self.playground.trees[settings["EROOT"]]["vartree"]
        self.srcroot = os.path.join(self.playground.eroot, "image")
        os.makedirs(self.srcroot)

    def tearDown(self):
        self.playground.cleanup()

    def merge_contents(self, mergeme):
        link = dblink(
            "dev-libs",
            "foo-1",
            settings=self.settings,
            vartree=self.vartree,
            treetype="vartree",
        )
        os.makedirs(link.dbtmpdir)
        link.mergeme = mergeme

        self.dbtmpdir = link.dbtmpdir

        umask = os.umask(0o022)
        try:
            return link._merge_contents(self.srcroot, self.playground.eroot, {})
        finally:
            self.assertEqual(os.umask(umask), 0o022)

    def testFailure(self):
        self.assertEqual(self.merge_contents(lambda *args: 1), 1)
        self.assertEqual(os.listdir(self.dbtmpdir), [])

    def testException(self):
        def mergeme(*args):
            raise OSError("merge failed")

        with self.assertRaises(OSError):
            self.merge_contents(mergeme)
        self.assertEqual(os.listdir(self.dbtmpdir), [])

    def testSuccess(self):
        self.assertEqual(self.merge_contents(lambda *args: os.EX_OK), os.EX_OK)
        self.assertEqual(os.listdir(self.dbtmpdir), ["CONTENTS"])
