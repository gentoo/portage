# Copyright 1999-2011 Gentoo Foundation
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

	def cancel(self):
		if self.isAlive():
			try:
				os.kill(self.pid, signal.SIGTERM)
			except OSError as e:
				if e.errno != errno.ESRCH:
					raise
				del e

		self.cancelled = True
		if self.pid is not None:
			self.wait()
		return self.returncode

	def isAlive(self):
		return self.pid is not None and \
			self.returncode is None

	def _wait(self):

		if self.returncode is not None:
			return self.returncode

		if self._registered:
			if self.cancelled:
				timeout = 1000
				self.scheduler.schedule(self._reg_id, timeout=timeout)
				if self._registered:
					try:
						os.kill(self.pid, signal.SIGKILL)
					except OSError as e:
						if e.errno != errno.ESRCH:
							raise
						del e
					self.scheduler.schedule(self._reg_id, timeout=timeout)
					if self._registered:
						self._orphan_process_warn()
			else:
				self.scheduler.schedule(self._reg_id)
			self._unregister()
			if self.returncode is not None:
				return self.returncode

		try:
			# With waitpid and WNOHANG, only check the
			# first element of the tuple since the second
			# element may vary (bug #337465).
			wait_retval = os.waitpid(self.pid, os.WNOHANG)
		except OSError as e:
			if e.errno != errno.ECHILD:
				raise
			del e
			self._set_returncode((self.pid, 1))
		else:
			if wait_retval[0] != 0:
				self._set_returncode(wait_retval)
			else:
				try:
					wait_retval = os.waitpid(self.pid, 0)
				except OSError as e:
					if e.errno != errno.ECHILD:
						raise
					del e
					self._set_returncode((self.pid, 1))
				else:
					self._set_returncode(wait_retval)

		return self.returncode

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
				f.close()
			self._files = None

	def _set_returncode(self, wait_retval):

		retval = wait_retval[1]

		if retval != os.EX_OK:
			if retval & 0xff:
				retval = (retval & 0xff) << 8
			else:
				retval = retval >> 8

		self.returncode = retval

