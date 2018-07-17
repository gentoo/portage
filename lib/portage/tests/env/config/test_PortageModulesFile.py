# Copyright 2006-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.tests import TestCase
from portage.env.config import PortageModulesFile
from tempfile import mkstemp

class PortageModulesFileTestCase(TestCase):

	keys = ['foo.bar', 'baz', 'bob', 'extra_key']
	invalid_keys = ['', ""]
	modules = ['spanky', 'zmedico', 'antarus', 'ricer', '5', '6']

	def setUp(self):
		self.items = {}
		for k, v in zip(self.keys + self.invalid_keys, self.modules):
			self.items[k] = v

	def testPortageModulesFile(self):
		self.BuildFile()
		f = PortageModulesFile(self.fname)
		f.load()
		for k in self.keys:
			self.assertEqual(f[k], self.items[k])
		for ik in self.invalid_keys:
			self.assertEqual(False, ik in f)
		self.NukeFile()

	def BuildFile(self):
		fd, self.fname = mkstemp()
		f = os.fdopen(fd, 'w')
		for k, v in self.items.items():
			f.write('%s=%s\n' % (k, v))
		f.close()

	def NukeFile(self):
		os.unlink(self.fname)
