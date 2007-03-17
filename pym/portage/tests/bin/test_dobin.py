# test_dobin.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dep_getcpv.py 6182 2007-03-06 07:35:22Z antarus $

from setup_env import *

class DoBin(BinTestCase):
	def testBasic(self):
		dobin("does-not-exist", 1)
		xexists_in_D("does-not-exist")
		xexists_in_D("/bin/does-not-exist")
		xexists_in_D("/usr/bin/does-not-exist")
