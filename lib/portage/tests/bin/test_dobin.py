# test_dobin.py -- Portage Unit Testing Functionality
# Copyright 2007-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests.bin.setup_env import BinTestCase, dobin, xexists_in_D

class DoBin(BinTestCase):
	def testDoBin(self):
		self.init()
		try:
			dobin("does-not-exist", 1)
			xexists_in_D("does-not-exist")
			xexists_in_D("/bin/does-not-exist")
			xexists_in_D("/usr/bin/does-not-exist")
		finally:
			self.cleanup()
