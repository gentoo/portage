# test_PackageMaskFile.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_PackageMaskFile.py 6182 2007-03-06 07:35:22Z antarus $

from portage.env.config import PackageMaskFile
from portage.tests import TestCase

class PackageMaskFileTestCase(TestCase):

	fname = 'package.mask'
	atoms = ['sys-apps/portage','dev-util/diffball','not@va1id@t0m']
	
	def testPackageMaskLoad(self):
		self.BuildFile()
		try:
			f = PackageMaskFile(self.fname)
			f.load(recursive=False)
			[atom for atom in f.iterkeys() if self.assertTrue(atom in self.atoms)]
		finally:
			self.NukeFile()
	
	def BuildFile(self):
		f = open(self.fname, 'wb')
		f.write("\n".join(self.atoms))
		f.close()
	
	def NukeFile(self):
		import os
		os.unlink(self.fname)
