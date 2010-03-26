# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
import portage
from portage import os
from portage.util._pty import _create_pty_or_pipe

class AbstractEbuildProcess(SpawnProcess):

	__slots__ = ('phase', 'pkg', 'settings',)

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
