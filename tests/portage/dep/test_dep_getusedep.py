# test_dep_getusedeps.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dep_getslot.py 5794 2007-01-27 18:16:08Z antarus $

from unittest import TestCase
from portage.dep import dep_getusedeps

class DepGetUseDeps(TestCase):
	""" A simple testcase for dep_getusedeps
	"""

	def testDepGetUseDeps(self):

		useflags = [ '', 'foo', '-bar', ['baz','bar'], ['baz','-bar'] ]
		cpvs = [ "sys-apps/portage" ]
		slots = [ None, "0","1","linux-sources-2.5.7","randomstring" ]
		versions = [ None, "2.1.1", "2.1.1-r2"]
		for mycpv in cpvs:
			for version in versions:
				for slot in slots:
					for use in useflags:
						cpv = mycpv[:]
						if version:
							cpv += version
						if slot:
							cpv += ":" + slot
						if isinstance( use, list ):
							for u in use:
								cpv = cpv + "[" + u + "]"
							self.assertEqual( dep_getusedeps(
								cpv ), use )
						else:
							if len(use):
								self.assertEqual( dep_getusedeps(
									cpv + "[" + use + "]" ), [use] )
							else:
								self.assertEqual( dep_getusedeps(
									cpv + "[" + use + "]" ), [] )
