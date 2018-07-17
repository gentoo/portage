# testCommandOututSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.process import find_binary
from portage.tests import TestCase, test_cps
from portage._sets.shell import CommandOutputSet

class CommandOutputSetTestCase(TestCase):
	"""Simple Test Case for CommandOutputSet"""

	def setUp(self):
		pass

	def tearDown(self):
		pass

	def testCommand(self):
		
		input = set(test_cps)
		command = find_binary("bash")
		command += " -c '"
		for a in input:
		  command += " echo -e \"%s\" ; " % a
		command += "'"
		s = CommandOutputSet(command)
		atoms = s.getAtoms()
		self.assertEqual(atoms, input)
