# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.dep import ExtendedAtomDict
from portage.tests import TestCase


class TestExtendedAtomDict(TestCase):
    def testExtendedAtomDict(self):
        d = ExtendedAtomDict(dict)
        d["*/*"] = {"test1": "x"}
        d["dev-libs/*"] = {"test2": "y"}
        d.setdefault("sys-apps/portage", {})["test3"] = "z"
        self.assertEqual(d.get("dev-libs/A"), {"test1": "x", "test2": "y"})
        self.assertEqual(d.get("sys-apps/portage"), {"test1": "x", "test3": "z"})
        self.assertEqual(d["dev-libs/*"], {"test2": "y"})
        self.assertEqual(d["sys-apps/portage"], {"test1": "x", "test3": "z"})

    def testExtendedAtomDictGetMiss(self):
        d = ExtendedAtomDict(set)
        d.setdefault("sys-apps/portage", set()).add("a")
        self.assertEqual(d.get("sys-apps/portage"), {"a"})
        self.assertIsNone(d.get("dev-libs/A"))
        self.assertEqual(d.get("dev-libs/A", "default"), "default")
        self.assertIsNone(d.get("dev-libs/*"))
        self.assertIsNone(d.get(None))

        d["dev-libs/*"] = {"b"}
        self.assertEqual(d.get("dev-libs/A"), {"b"})
        self.assertEqual(d.get("sys-apps/portage"), {"a"})
        self.assertIsNone(d.get("app-misc/A"))
        self.assertEqual(d.get("app-misc/A", "default"), "default")
