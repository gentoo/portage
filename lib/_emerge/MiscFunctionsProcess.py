# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:spawn'
)
from portage import os

class MiscFunctionsProcess(AbstractEbuildProcess):
	"""
	Spawns misc-functions.sh with an existing ebuild environment.
	"""

	__slots__ = ('commands', 'ld_preload_sandbox')

	def _start(self):
		settings = self.settings
		portage_bin_path = settings["PORTAGE_BIN_PATH"]
		misc_sh_binary = os.path.join(portage_bin_path,
			os.path.basename(portage.const.MISC_SH_BINARY))

		self.args = [portage._shell_quote(misc_sh_binary)] + self.commands
		if self.logfile is None and \
			self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
			self.logfile = settings.get("PORTAGE_LOG_FILE")

		AbstractEbuildProcess._start(self)

	def _spawn(self, args, **kwargs):
		# If self.ld_preload_sandbox is None, default to free=False,
		# in alignment with the spawn(free=False) default.
		kwargs.setdefault('free', False if self.ld_preload_sandbox is None
			else not self.ld_preload_sandbox)

		if self._dummy_pipe_fd is not None:
			self.settings["PORTAGE_PIPE_FD"] = str(self._dummy_pipe_fd)

		if "fakeroot" in self.settings.features:
			kwargs["fakeroot"] = True

		# Temporarily unset EBUILD_PHASE so that bashrc code doesn't
		# think this is a real phase.
		phase_backup = self.settings.pop("EBUILD_PHASE", None)
		try:
			return spawn(" ".join(args), self.settings, **kwargs)
		finally:
			if phase_backup is not None:
				self.settings["EBUILD_PHASE"] = phase_backup
			self.settings.pop("PORTAGE_PIPE_FD", None)
