# test_dodir.py -- Portage Unit Testing Functionality
# Copyright 2007-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests.bin.setup_env import BinTestCase, dodir, exists_in_D

class DoDir(BinTestCase):
	def testDoDir(self):
		self.init()
		try:
			dodir("usr /usr")
			exists_in_D("/usr")
			dodir("boot")
			exists_in_D("/boot")
			dodir("/var/lib/moocow")
			exists_in_D("/var/lib/moocow")
		finally:
			self.cleanup()
