# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
import portage
import signal

class BinpkgExtractorAsync(SpawnProcess):

	__slots__ = ("image_dir", "pkg", "pkg_path")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		# Add -q to bzip2 opts, in order to avoid "trailing garbage after
		# EOF ignored" warning messages due to xpak trailer.
		# SIGPIPE handling (128 + SIGPIPE) should be compatible with
		# assert_sigpipe_ok() that's used by the ebuild unpack() helper.
		self.args = [self._shell_binary, "-c",
			("${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d} -cq -- %s | tar -xp -C %s -f - ; " + \
			"p=(${PIPESTATUS[@]}) ; " + \
			"if [[ ${p[0]} != 0 && ${p[0]} != %d ]] ; then " % (128 + signal.SIGPIPE) + \
			"echo bzip2 failed with status ${p[0]} ; exit ${p[0]} ; fi ; " + \
			"if [ ${p[1]} != 0 ] ; then " + \
			"echo tar failed with status ${p[1]} ; exit ${p[1]} ; fi ; " + \
			"exit 0 ;") % \
			(portage._shell_quote(self.pkg_path),
			portage._shell_quote(self.image_dir))]

		SpawnProcess._start(self)
