# test_PackageUseFile.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_PackageUseFile.py 6182 2007-03-06 07:35:22Z antarus $

from portage.tests import TestCase
from portage.env.config import PackageUseFile

class PackageUseFileTestCase(TestCase):

	fname = 'package.use'
	cpv = 'sys-apps/portage'
	useflags = ['cdrom', 'far', 'boo', 'flag', 'blat']
	
	def testPackageUseLoad(self):
		"""
		A simple test to ensure the load works properly
		"""
		self.BuildFile()
		try:
			f = PackageUseFile(self.fname)
			f.load(recursive=False)
			for cpv, use in f.iteritems():
				self.assertEqual( cpv, self.cpv )
				[flag for flag in use if self.assertTrue(flag in self.useflags)]
		finally:
			self.NukeFile()

	def BuildFile(self):
		f = open(self.fname, 'wb')
		f.write("%s %s" % (self.cpv, ' '.join(self.useflags)))
	
	def NukeFile(self):
		import os
		os.unlink(self.fname)
