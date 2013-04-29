# test_isjustname.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import isjustname

class IsJustName(TestCase):

	def testIsJustName(self):

		cats = ("", "sys-apps/", "foo/", "virtual/")
		pkgs = ("portage", "paludis", "pkgcore", "notARealPkg")
		vers = ("", "-2.0-r3", "-1.0_pre2", "-3.1b")

		for pkg in pkgs:
			for cat in cats:
				for ver in vers:
					if len(ver):
						self.assertFalse(isjustname(cat + pkg + ver),
						msg="isjustname(%s) is True!" % (cat + pkg + ver))
					else:
						self.assertTrue(isjustname(cat + pkg + ver),
						msg="isjustname(%s) is False!" % (cat + pkg + ver))
