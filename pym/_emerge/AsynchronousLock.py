# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import dummy_threading
import fcntl
try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage import os
from portage.exception import TryAgain
from portage.locks import lockfile, unlockfile
from _emerge.AbstractPollTask import AbstractPollTask
from _emerge.PollConstants import PollConstants

class AsynchronousLock(AbstractPollTask):
	"""
	This uses the portage.locks module to acquire a lock asynchronously,
	using a background thread. After the lock is acquired, the thread
	writes to a pipe in order to notify a poll loop running in the main
	thread.

	If the threading module is unavailable then the dummy_threading
	module will be used, and the lock will be acquired synchronously
	(before the start() method returns).
	"""

	__slots__ = ('lock_obj', 'path',) + \
		('_files', '_force_thread', '_force_dummy',
		'_thread', '_reg_id',)

	def _start(self):

		if self._force_thread:
			self._start_thread()
			return

		try:
			self.lock_obj = lockfile(self.path,
				wantnewlockfile=True, flags=os.O_NONBLOCK)
		except TryAgain:
			self._start_thread()
		else:
			self.returncode = os.EX_OK
			self.wait()

	def _start_thread(self):
		pr, pw = os.pipe()
		self._files = {}
		self._files['pipe_read'] = os.fdopen(pr, 'rb', 0)
		self._files['pipe_write'] = os.fdopen(pw, 'wb', 0)
		for k, f in self._files.items():
			fcntl.fcntl(f.fileno(), fcntl.F_SETFL,
				fcntl.fcntl(f.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK)
		self._reg_id = self.scheduler.register(self._files['pipe_read'].fileno(),
			PollConstants.POLLIN, self._output_handler)
		self._registered = True
		threading_mod = threading
		if self._force_dummy:
			threading_mod = dummy_threading
		self._thread = threading_mod.Thread(target=self._run_lock)
		self._thread.start()

	def _run_lock(self):
		self.lock_obj = lockfile(self.path, wantnewlockfile=True)
		self._files['pipe_write'].write(b'\0')

	def _output_handler(self, f, event):
		buf = self._read_buf(self._files['pipe_read'], event)
		if buf:
			self._unregister()
			self.returncode = os.EX_OK
			self.wait()

	def _wait(self):
		if self.returncode is not None:
			return self.returncode
		if self._registered:
			self.scheduler.schedule(self._reg_id)
		return self.returncode

	def unlock(self):
		if self.lock_obj is None:
			raise AssertionError('not locked')
		unlockfile(self.lock_obj)
		self.lock_obj = None

	def _unregister(self):
		self._registered = False

		if self._thread is not None:
			self._thread.join()
			self._thread = None

		if self._reg_id is not None:
			self.scheduler.unregister(self._reg_id)
			self._reg_id = None

		if self._files is not None:
			for f in self._files.values():
				f.close()
			self._files = None
