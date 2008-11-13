# testStaticFileSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: testShell.py 7363 2007-07-22 23:21:14Z zmedico $

import tempfile, os

from portage.tests import TestCase, test_cps
from portage._sets.files import StaticFileSet
from portage.env.loaders import TestTextLoader
from portage.env.config import ConfigLoaderKlass

class StaticFileSetTestCase(TestCase):
	"""Simple Test Case for StaticFileSet"""

	def setUp(self):
		fd, self.testfile = tempfile.mkstemp(suffix=".testdata", prefix=self.__class__.__name__, text=True)
		os.write(fd, "\n".join(test_cps))
		os.close(fd)

	def tearDown(self):
		os.unlink(self.testfile)

	def testSampleStaticFileSet(self):
		s = StaticFileSet(self.testfile)
		s.load()
		self.assertEqual(set(test_cps), s.getAtoms())

