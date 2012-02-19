# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from _emerge.AbstractPollTask import AbstractPollTask
import signal
import errno

class SubProcess(AbstractPollTask):

	__slots__ = ("pid",) + \
		("_files", "_reg_id")

	# A file descriptor is required for the scheduler to monitor changes from
	# inside a poll() loop. When logging is not enabled, create a pipe just to
	# serve this purpose alone.
	_dummy_pipe_fd = 9

	# This is how much time we allow for waitpid to succeed after
	# we've sent a kill signal to our subprocess.
	_cancel_timeout = 1000 # 1 second

	def _poll(self):
		if self.returncode is not None:
			return self.returncode
		if self.pid is None:
			return self.returncode
		if self._registered:
			return self.returncode

		try:
			# With waitpid and WNOHANG, only check the
			# first element of the tuple since the second
			# element may vary (bug #337465).
			retval = os.waitpid(self.pid, os.WNOHANG)
		except OSError as e:
			if e.errno != errno.ECHILD:
				raise
			del e
			retval = (self.pid, 1)

		if retval[0] == 0:
			return None
		self._set_returncode(retval)
		self.wait()
		return self.returncode

	def _cancel(self):
		if self.isAlive():
			try:
				os.kill(self.pid, signal.SIGTERM)
			except OSError as e:
				if e.errno != errno.ESRCH:
					raise

	def isAlive(self):
		return self.pid is not None and \
			self.returncode is None

	def _wait(self):

		if self.returncode is not None:
			return self.returncode

		if self._registered:
			if self.cancelled:
				self._wait_loop(timeout=self._cancel_timeout)
				if self._registered:
					try:
						os.kill(self.pid, signal.SIGKILL)
					except OSError as e:
						if e.errno != errno.ESRCH:
							raise
						del e
					self._wait_loop(timeout=self._cancel_timeout)
					if self._registered:
						self._orphan_process_warn()
			else:
				self._wait_loop()

			if self.returncode is not None:
				return self.returncode

		if not isinstance(self.pid, int):
			# Get debug info for bug #403697.
			raise AssertionError(
				"%s: pid is non-integer: %s" %
				(self.__class__.__name__, repr(self.pid)))

		self._waitpid_loop()

		return self.returncode

	def _waitpid_loop(self):
		source_id = self.scheduler.child_watch_add(
			self.pid, self._waitpid_cb)
		try:
			while self.returncode is None:
				self.scheduler.iteration()
		finally:
			self.scheduler.source_remove(source_id)

	def _waitpid_cb(self, pid, condition, user_data=None):
		if pid != self.pid:
			raise AssertionError("expected pid %s, got %s" % (self.pid, pid))
		self._set_returncode((pid, condition))

	def _orphan_process_warn(self):
		pass

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		self._registered = False

		if self._reg_id is not None:
			self.scheduler.unregister(self._reg_id)
			self._reg_id = None

		if self._files is not None:
			for f in self._files.values():
				if isinstance(f, int):
					os.close(f)
				else:
					f.close()
			self._files = None

	def _set_returncode(self, wait_retval):
		"""
		Set the returncode in a manner compatible with
		subprocess.Popen.returncode: A negative value -N indicates
		that the child was terminated by signal N (Unix only).
		"""
		self._unregister()

		pid, status = wait_retval

		if os.WIFSIGNALED(status):
			retval = - os.WTERMSIG(status)
		else:
			retval = os.WEXITSTATUS(status)

		self.returncode = retval

