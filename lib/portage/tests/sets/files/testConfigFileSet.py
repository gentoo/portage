# testConfigFileSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage.tests import TestCase, test_cps
from portage._sets.files import ConfigFileSet

class ConfigFileSetTestCase(TestCase):
	"""Simple Test Case for ConfigFileSet"""

	def setUp(self):
		fd, self.testfile = tempfile.mkstemp(suffix=".testdata", prefix=self.__class__.__name__, text=True)
		f = os.fdopen(fd, 'w')
		for i in range(0, len(test_cps)):
			atom = test_cps[i]
			if i % 2 == 0:
				f.write(atom + ' abc def\n')
			else:
				f.write(atom + '\n')
		f.close()

	def tearDown(self):
		os.unlink(self.testfile)

	def testConfigStaticFileSet(self):
		s = ConfigFileSet(self.testfile)
		s.load()
		self.assertEqual(set(test_cps), s.getAtoms())
