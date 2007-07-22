# testCommandOututSet.py -- Portage Unit Testing Functionality
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.tests import TestCase, test_cps
from portage.sets.shell import CommandOutputSet

class CommandOutputSetTestCase(TestCase):
	"""Simple Test Case for CommandOutputSet"""

	def setUp(self):
		pass

	def tearDown(self):
		pass

	def testCommand(self):
		
		input = set(test_cps)
		command = "/usr/bin/echo -e "
		for a in input:
		  command += "\"%s\n\"" % a
		s = CommandOutputSet('testset', command)
		atoms = s.getAtoms()
		self.assertEqual(atoms, input)
