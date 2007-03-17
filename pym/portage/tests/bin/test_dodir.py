# test_dodir.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dep_getcpv.py 6182 2007-03-06 07:35:22Z antarus $

from setup_env import *

class DoDir(BinTestCase):
	def testBasic(self):
		dodir("usr /usr")
		exists_in_D("/usr")
		dodir("/var/lib/moocow")
		exists_in_D("/var/lib/moocow")
