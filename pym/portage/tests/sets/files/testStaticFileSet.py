# testStaticFileSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: testShell.py 7363 2007-07-22 23:21:14Z zmedico $

from portage.tests import TestCase, test_cps
from portage.sets.files import StaticFileSet
from portage.env.loaders import TestTextLoader
from portage.env.config import ConfigLoaderKlass

class StaticFileSetTestCase(TestCase):
	"""Simple Test Case for StaicFileSet"""

	def setUp(self):
		pass

	def tearDown(self):
		pass

	def testSampleStaticFileSet(self):
		d = {}
		for item in test_cps:
			d[item] = None
		loader = TestTextLoader(validator=None)
		loader.setData(d)
		data = ConfigLoaderKlass(loader)
		s = StaticFileSet('test', '/dev/null', data=data)
		s.load()
		self.assertEqual(set(test_cps), s.getAtoms())

