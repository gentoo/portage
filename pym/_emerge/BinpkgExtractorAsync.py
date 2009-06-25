# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SpawnProcess import SpawnProcess
try:
	import portage
except ImportError:
	from os import path as osp
	import sys
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
	import portage
class BinpkgExtractorAsync(SpawnProcess):

	__slots__ = ("image_dir", "pkg", "pkg_path")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		self.args = [self._shell_binary, "-c",
			"bzip2 -dqc -- %s | tar -xp -C %s -f -" % \
			(portage._shell_quote(self.pkg_path),
			portage._shell_quote(self.image_dir))]

		self.env = self.pkg.root_config.settings.environ()
		SpawnProcess._start(self)

