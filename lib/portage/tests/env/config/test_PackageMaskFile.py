# test_PackageMaskFile.py -- Portage Unit Testing Functionality
# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.env.config import PackageMaskFile
from portage.tests import TestCase, test_cps
from tempfile import mkstemp

class PackageMaskFileTestCase(TestCase):

	def testPackageMaskFile(self):
		self.BuildFile()
		try:
			f = PackageMaskFile(self.fname)
			f.load()
			for atom in f:
				self.assertTrue(atom in test_cps)
		finally:
			self.NukeFile()

	def BuildFile(self):
		fd, self.fname = mkstemp()
		f = os.fdopen(fd, 'w')
		f.write("\n".join(test_cps))
		f.close()

	def NukeFile(self):
		os.unlink(self.fname)
