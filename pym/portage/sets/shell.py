# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import subprocess, os

from portage.sets import PackageSet

class CommandOutputSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, name, command):
		super(CommandOutputSet, self).__init__(name)
		self._command = command
	
	def load(self):
		pipe = subprocess.Popen(self._command, stdout=subprocess.PIPE, shell=True)
		if pipe.wait() == os.EX_OK:
			text = pipe.stdout.read()
			self._setNodes(text.split("\n"))
		
