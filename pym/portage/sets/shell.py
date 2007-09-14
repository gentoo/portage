# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import subprocess
import os

from portage.sets import PackageSet

class CommandOutputSet(PackageSet):
	"""This class creates a PackageSet from the output of a shell command.
	   The shell command should produce one atom per line, that is:

	   >>> atom1
	       atom2
	       ...
	       atomN

	   Args:
	     name: A string that identifies the set.
	     command: A string or sequence identifying the command to run
	     (see the subprocess.Popen documentaion for the format)
	"""
	_operations = ["merge", "unmerge"]

	def __init__(self, name, command):
		super(CommandOutputSet, self).__init__(name)
		self._command = command
		self.description = "Package set generated from output of '%s'" % self._command
	
	def load(self):
		pipe = subprocess.Popen(self._command, stdout=subprocess.PIPE, shell=True)
		if pipe.wait() == os.EX_OK:
			text = pipe.stdout.read()
			self._setAtoms(text.split("\n"))
		
