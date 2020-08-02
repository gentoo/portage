# testStaticFileSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage.tests import TestCase, test_cps
from portage._sets.files import StaticFileSet

class StaticFileSetTestCase(TestCase):
	"""Simple Test Case for StaticFileSet"""

	def setUp(self):
		fd, self.testfile = tempfile.mkstemp(suffix=".testdata", prefix=self.__class__.__name__, text=True)
		f = os.fdopen(fd, 'w')
		f.write("\n".join(test_cps))
		f.close()

	def tearDown(self):
		os.unlink(self.testfile)

	def testSampleStaticFileSet(self):
		s = StaticFileSet(self.testfile)
		s.load()
		self.assertEqual(set(test_cps), s.getAtoms())
