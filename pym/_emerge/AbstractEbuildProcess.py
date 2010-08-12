# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_doebuild_exit_status_check_and_log'
)
from portage import os
from portage.util._pty import _create_pty_or_pipe

class AbstractEbuildProcess(SpawnProcess):

	__slots__ = ('settings',)
	_phases_without_builddir = ('clean', 'cleanrm', 'depend', 'help',)

	def _pipe(self, fd_pipes):
		stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def _can_log(self, slave_fd):
		# With sesandbox, logging works through a pty but not through a
		# normal pipe. So, disable logging if ptys are broken.
		# See Bug #162404.
		return not ('sesandbox' in self.settings.features \
			and self.settings.selinux_enabled()) or os.isatty(slave_fd)

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)
		phase = self.settings.get("EBUILD_PHASE")
		if not phase:
			phase = 'other'
		if phase not in self._phases_without_builddir:
			self.returncode = _doebuild_exit_status_check_and_log(
				self.settings, phase, self.returncode)
