# Copyright 2012-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal
import sys
import traceback

import portage
from portage import os
from _emerge.SpawnProcess import SpawnProcess

class ForkProcess(SpawnProcess):

	__slots__ = ()

	def _spawn(self, args, fd_pipes=None, **kwargs):
		"""
		Fork a subprocess, apply local settings, and call fetch().
		"""

		parent_pid = os.getpid()
		pid = None
		try:
			pid = os.fork()

			if pid != 0:
				if not isinstance(pid, int):
					raise AssertionError(
						"fork returned non-integer: %s" % (repr(pid),))
				return [pid]

			rval = 1
			try:

				# Use default signal handlers in order to avoid problems
				# killing subprocesses as reported in bug #353239.
				signal.signal(signal.SIGINT, signal.SIG_DFL)
				signal.signal(signal.SIGTERM, signal.SIG_DFL)

				# Unregister SIGCHLD handler and wakeup_fd for the parent
				# process's event loop (bug 655656).
				signal.signal(signal.SIGCHLD, signal.SIG_DFL)
				try:
					wakeup_fd = signal.set_wakeup_fd(-1)
					if wakeup_fd > 0:
						os.close(wakeup_fd)
				except (ValueError, OSError):
					pass

				portage.locks._close_fds()
				# We don't exec, so use close_fds=False
				# (see _setup_pipes docstring).
				portage.process._setup_pipes(fd_pipes, close_fds=False)

				rval = self._run()
			except SystemExit:
				raise
			except:
				traceback.print_exc()
				# os._exit() skips stderr flush!
				sys.stderr.flush()
			finally:
				os._exit(rval)

		finally:
			if pid == 0 or (pid is None and os.getpid() != parent_pid):
				# Call os._exit() from a finally block in order
				# to suppress any finally blocks from earlier
				# in the call stack (see bug #345289). This
				# finally block has to be setup before the fork
				# in order to avoid a race condition.
				os._exit(1)

	def _run(self):
		raise NotImplementedError(self)
