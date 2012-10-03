# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal
import traceback

import portage
from portage import os
from _emerge.SpawnProcess import SpawnProcess

class ForkProcess(SpawnProcess):

	def _spawn(self, args, fd_pipes=None, **kwargs):
		"""
		Fork a subprocess, apply local settings, and call fetch().
		"""

		pid = os.fork()
		if pid != 0:
			if not isinstance(pid, int):
				raise AssertionError(
					"fork returned non-integer: %s" % (repr(pid),))
			portage.process.spawned_pids.append(pid)
			return [pid]

		portage.locks._close_fds()
		# Disable close_fds since we don't exec (see _setup_pipes docstring).
		portage.process._setup_pipes(fd_pipes, close_fds=False)

		# Use default signal handlers in order to avoid problems
		# killing subprocesses as reported in bug #353239.
		signal.signal(signal.SIGINT, signal.SIG_DFL)
		signal.signal(signal.SIGTERM, signal.SIG_DFL)

		rval = 1
		try:
			rval = self._run()
		except SystemExit:
			raise
		except:
			traceback.print_exc()
		finally:
			# Call os._exit() from finally block, in order to suppress any
			# finally blocks from earlier in the call stack. See bug #345289.
			os._exit(rval)

	def _run(self):
		raise NotImplementedError(self)
