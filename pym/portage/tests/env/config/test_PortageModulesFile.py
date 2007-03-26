import os

from portage.tests import TestCase
from portage.env.config import PortageModulesFile
from tempfile import mkstemp

class PortageModulesFileTestCase(TestCase):

	keys = ['foo.bar','baz','bob','extra_key']
	modules = ['spanky','zmedico','antarus','ricer']

	def setUp(self):
		for k,v in (self.keys, self.modules):
			self.items[k] = v

	def testPortageModulesFile(self):
		self.BuildFile()
		f = PortageModulesFile(self.fname)
		for k in f.keys():
			self.assertEqual( f[k], self.items[k] )
		self.NukeFile()

	def BuildFile(self):
		fd,self.fname = mkstemp()
		f = os.fdopen(self.fname, 'wb')
		f.write('%s %s\n' % (self.cpv, ' '.join(self.keywords)))
		f.close()

	def NukeFile(self):
		import os
		os.unlink(self.fname)
