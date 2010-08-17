# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_post_phase_userpriv_perms,' + \
		'_spawn_actionmap,_doebuild_spawn'
)
from portage import os

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

		actionmap = self.actionmap
		if actionmap is None:
			actionmap = _spawn_actionmap(self.settings)

		return _doebuild_spawn(self.phase, self.settings,
				actionmap=actionmap, **kwargs)

	def _set_returncode(self, wait_retval):
		AbstractEbuildProcess._set_returncode(self, wait_retval)

		if self.phase == "test" and self.returncode != os.EX_OK and \
			"test-fail-continue" in self.settings.features:
			self.returncode = os.EX_OK

		_post_phase_userpriv_perms(self.settings)

