# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
from portage import os

class MiscFunctionsProcess(AbstractEbuildProcess):
	"""
	Spawns misc-functions.sh with an existing ebuild environment.
	"""

	__slots__ = ('commands',)

	def _start(self):
		settings = self.settings
		settings.pop("EBUILD_PHASE", None)
		portage_bin_path = settings["PORTAGE_BIN_PATH"]
		misc_sh_binary = os.path.join(portage_bin_path,
			os.path.basename(portage.const.MISC_SH_BINARY))

		self.args = [portage._shell_quote(misc_sh_binary)] + self.commands
		self.logfile = settings.get("PORTAGE_LOG_FILE")

		portage._doebuild_exit_status_unlink(
			settings.get("EBUILD_EXIT_STATUS_FILE"))

		AbstractEbuildProcess._start(self)

	def _spawn(self, args, **kwargs):
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"
		return portage.spawn(" ".join(args), settings,
			debug=debug, **kwargs)

	def _set_returncode(self, wait_retval):
		AbstractEbuildProcess._set_returncode(self, wait_retval)
		self.returncode = portage._doebuild_exit_status_check_and_log(
			self.settings, self.phase, self.returncode)

