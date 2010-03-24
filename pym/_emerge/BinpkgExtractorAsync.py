# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
import portage
import os

class BinpkgExtractorAsync(SpawnProcess):

	__slots__ = ("image_dir", "pkg", "pkg_path")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		self.args = [self._shell_binary, "-c",
			("bzip2 -dqc -- %s | tar -xp -C %s -f - ; " + \
			"p=(${PIPESTATUS[@]}) ; " + \
			"if [ ${p[0]} != 0 ] ; then " + \
			"echo bzip2 failed with status ${p[0]} ; exit ${p[0]} ; fi ; " + \
			"if [ ${p[1]} != 0 ] ; then " + \
			"echo tar failed with status ${p[1]} ; exit ${p[1]} ; fi ; " + \
			"exit 0 ;") % \
			(portage._shell_quote(self.pkg_path),
			portage._shell_quote(self.image_dir))]

		self.env = os.environ.copy()
		SpawnProcess._start(self)
