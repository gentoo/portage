# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging

from portage import os
from portage.util import writemsg_level
from portage.util.futures import asyncio
from _emerge.AbstractPollTask import AbstractPollTask
import signal
import errno

class SubProcess(AbstractPollTask):

	__slots__ = ("pid",) + \
		("_dummy_pipe_fd", "_files", "_waitpid_id")

	# This is how much time we allow for waitpid to succeed after
	# we've sent a kill signal to our subprocess.
	_cancel_timeout = 1 # seconds

	def _poll(self):
		# Simply rely on _async_waitpid_cb to set the returncode.
		return self.returncode

	def _cancel(self):
		if self.isAlive() and self.pid is not None:
			try:
				os.kill(self.pid, signal.SIGTERM)
			except OSError as e:
				if e.errno == errno.EPERM:
					# Reported with hardened kernel (bug #358211).
					writemsg_level(
						"!!! kill: (%i) - Operation not permitted\n" %
						(self.pid,), level=logging.ERROR,
						noiselevel=-1)
				elif e.errno != errno.ESRCH:
					raise

	def _async_wait(self):
		if self.returncode is None:
			raise asyncio.InvalidStateError('Result is not ready for %s' % (self,))
		else:
			# This calls _unregister, so don't call it until pid status
			# is available.
			super(SubProcess, self)._async_wait()

	def _async_waitpid(self):
		"""
		Wait for exit status of self.pid asynchronously, and then
		set the returncode, and finally notify exit listeners via the
		_async_wait method. Subclasses may override this method in order
		to implement an alternative means to retrieve pid exit status,
		or as a means to delay action until some pending task(s) have
		completed (such as reading data that the subprocess is supposed
		to have written to a pipe).
		"""
		if self.returncode is not None:
			self._async_wait()
		elif self._waitpid_id is None:
			self._waitpid_id = self.pid
			self.scheduler._asyncio_child_watcher.\
				add_child_handler(self.pid, self._async_waitpid_cb)

	def _async_waitpid_cb(self, pid, returncode):
		if pid != self.pid:
			raise AssertionError("expected pid %s, got %s" % (self.pid, pid))
		self.returncode = returncode
		self._async_wait()

	def _orphan_process_warn(self):
		pass

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self._waitpid_id is not None:
			self.scheduler._asyncio_child_watcher.\
				remove_child_handler(self._waitpid_id)
			self._waitpid_id = None

		if self._files is not None:
			for f in self._files.values():
				if isinstance(f, int):
					os.close(f)
				else:
					f.close()
			self._files = None
