# test_isvalidatom.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import ExtendedAtomDict

class TestExtendedAtomDict(TestCase):

	def testExtendedAtomDict(self):
		d = ExtendedAtomDict(dict)
		d["*/*"] = { "test1": "x" }
		d["dev-libs/*"] = { "test2": "y" }
		d.setdefault("sys-apps/portage", {})["test3"] = "z"
		self.assertEqual(d.get("dev-libs/A"), { "test1": "x", "test2": "y" })
		self.assertEqual(d.get("sys-apps/portage"), { "test1": "x", "test3": "z" })
		self.assertEqual(d["dev-libs/*"], { "test2": "y" })
		self.assertEqual(d["sys-apps/portage"], {'test1': 'x', 'test3': 'z'})
