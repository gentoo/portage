# test_PackageUseFile.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.env.config import PackageUseFile
from tempfile import mkstemp


class PackageUseFileTestCase(TestCase):

	cpv = 'sys-apps/portage'
	useflags = ['cdrom', 'far', 'boo', 'flag', 'blat']

	def testPackageUseFile(self):
		"""
		A simple test to ensure the load works properly
		"""
		self.BuildFile()
		try:
			f = PackageUseFile(self.fname)
			f.load()
			for cpv, use in f.items():
				self.assertEqual(cpv, self.cpv)
				[flag for flag in use if self.assertTrue(flag in self.useflags)]
		finally:
			self.NukeFile()

	def BuildFile(self):
		fd, self.fname = mkstemp()
		f = os.fdopen(fd, 'w')
		f.write("%s %s" % (self.cpv, ' '.join(self.useflags)))
		f.close()

	def NukeFile(self):
		os.unlink(self.fname)
