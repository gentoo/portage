# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: BinpkgExtractorAsync.py 13715 2009-06-27 14:44:56Z grobian $

from _emerge.SpawnProcess import SpawnProcess
# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage
class BinpkgChpathtoolAsync(SpawnProcess):

	__slots__ = ("buildprefix", "eprefix", "image_dir", "pkg", "work_dir")

	_shell_binary = portage.const.BASH_BINARY
	_chpathtool_binary = \
			os.path.join(portage.const.PORTAGE_BIN_PATH, "chpathtool")

	def _start(self):
		b = os.path.join(self.work_dir, self.buildprefix.lstrip(os.path.sep))
		i = os.path.join(self.image_dir, self.eprefix.lstrip(os.path.sep))
		# make sure the directory structure for EPREFIX is set up in
		# the image, but avoid the last directory being there,
		# otherwise chpathtool will complain
		portage.util.ensure_dirs(i)
		os.rmdir(i)
		self.args = [self._shell_binary, "-c",
			"%s -q '%s' '%s' '%s' '%s'" % \
				(self._chpathtool_binary, b, i, self.buildprefix, self.eprefix)]

		self.env = self.pkg.root_config.settings.environ()
		SpawnProcess._start(self)

