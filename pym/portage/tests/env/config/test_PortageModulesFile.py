import os

from portage.tests import TestCase
from portage.env.config import PortageModulesFile
from tempfile import mkstemp
from itertools import izip

class PortageModulesFileTestCase(TestCase):

	keys = ['foo.bar','baz','bob','extra_key']
	modules = ['spanky','zmedico','antarus','ricer']

	def setUp(self):
		self.items = {}
		for k,v in izip(self.keys, self.modules):
			self.items[k] = v

	def testPortageModulesFile(self):
		self.BuildFile()
		f = PortageModulesFile(self.fname)
		for k in f.keys():
			self.assertEqual( f[k], self.items[k] )
		self.NukeFile()

	def BuildFile(self):
		fd, self.fname = mkstemp()
		f = os.fdopen(fd, 'wb')
		for k,v in self.items.iteritems():
			f.write('%s=%s\n' % (k,v))
		f.close()

	def NukeFile(self):
		import os
		os.unlink(self.fname)
