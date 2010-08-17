# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_post_phase_userpriv_perms,' + \
		'_spawn_actionmap,_unsandboxed_phases,spawn@doebuild_spawn'
)
from portage import _shell_quote
from portage import os
from portage.const import EBUILD_SH_BINARY

class EbuildProcess(AbstractEbuildProcess):

	__slots__ = ('actionmap',)

	def _start(self):
		# Don't open the log file during the clean phase since the
		# open file can result in an nfs lock on $T/build.log which
		# prevents the clean phase from removing $T.
		if self.phase not in ("clean", "cleanrm"):
			self.logfile = self.settings.get("PORTAGE_LOG_FILE")
		AbstractEbuildProcess._start(self)

	def _spawn(self, args, **kwargs):
		self.settings["EBUILD_PHASE"] = self.phase
		if self.phase in _unsandboxed_phases:
			kwargs['free'] = True
		if self.phase == 'depend':
			kwargs['droppriv'] = 'userpriv' in self.settings.features
		actionmap = self.actionmap
		if actionmap is None:
			actionmap = _spawn_actionmap(self.settings)
		if self.phase in actionmap:
			kwargs.update(actionmap[self.phase]["args"])
			cmd = actionmap[self.phase]["cmd"] % self.phase
		else:
			if self.phase == 'cleanrm':
				ebuild_sh_arg = 'clean'
			else:
				ebuild_sh_arg = self.phase

			cmd = "%s %s" % (_shell_quote(os.path.join(
				self.settings["PORTAGE_BIN_PATH"],
				os.path.basename(EBUILD_SH_BINARY))), ebuild_sh_arg)
		try:
			return doebuild_spawn(cmd, self.settings, **kwargs)
		finally:
			self.settings.pop("EBUILD_PHASE", None)

	def _set_returncode(self, wait_retval):
		AbstractEbuildProcess._set_returncode(self, wait_retval)

		if self.phase == "test" and self.returncode != os.EX_OK and \
			"test-fail-continue" in self.settings.features:
			self.returncode = os.EX_OK

		_post_phase_userpriv_perms(self.settings)

