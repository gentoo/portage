# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SpawnProcess import SpawnProcess
# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage

class BinpkgExtractorAsync(SpawnProcess):

	__slots__ = ("image_dir", "pkg", "pkg_path")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		self.args = [self._shell_binary, "-c",
			("bzip2 -dqc -- %s | tar -xp -C %s -f -") % \
			(portage._shell_quote(self.pkg_path),
			portage._shell_quote(self.image_dir))]

		self.env = os.environ.copy()
		SpawnProcess._start(self)
