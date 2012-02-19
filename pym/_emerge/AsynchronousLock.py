# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import dummy_threading
import fcntl
import errno
import logging
import sys

try:
	import threading
except ImportError:
	threading = dummy_threading

import portage
from portage import os
from portage.exception import TryAgain
from portage.localization import _
from portage.locks import lockfile, unlockfile
from portage.util import writemsg_level
from _emerge.AbstractPollTask import AbstractPollTask
from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.SpawnProcess import SpawnProcess

class AsynchronousLock(AsynchronousTask):
	"""
	This uses the portage.locks module to acquire a lock asynchronously,
	using either a thread (if available) or a subprocess.

	The default behavior is to use a process instead of a thread, since
	there is currently no way to interrupt a thread that is waiting for
	a lock (notably, SIGINT doesn't work because python delivers all
	signals to the main thread).
	"""

	__slots__ = ('path', 'scheduler',) + \
		('_imp', '_force_async', '_force_dummy', '_force_process', \
		'_force_thread')

	_use_process_by_default = True

	def _start(self):

		if not self._force_async:
			try:
				self._imp = lockfile(self.path,
					wantnewlockfile=True, flags=os.O_NONBLOCK)
			except TryAgain:
				pass
			else:
				self.returncode = os.EX_OK
				self.wait()
				return

		if self._force_process or \
			(not self._force_thread and \
			(self._use_process_by_default or threading is dummy_threading)):
			self._imp = _LockProcess(path=self.path, scheduler=self.scheduler)
		else:
			self._imp = _LockThread(path=self.path,
				scheduler=self.scheduler,
				_force_dummy=self._force_dummy)

		self._imp.addExitListener(self._imp_exit)
		self._imp.start()

	def _imp_exit(self, imp):
		# call exit listeners
		self.wait()

	def _cancel(self):
		if isinstance(self._imp, AsynchronousTask):
			self._imp.cancel()

	def _poll(self):
		if isinstance(self._imp, AsynchronousTask):
			self._imp.poll()
		return self.returncode

	def _wait(self):
		if self.returncode is not None:
			return self.returncode
		self.returncode = self._imp.wait()
		return self.returncode

	def unlock(self):
		if self._imp is None:
			raise AssertionError('not locked')
		if isinstance(self._imp, (_LockProcess, _LockThread)):
			self._imp.unlock()
		else:
			unlockfile(self._imp)
		self._imp = None

class _LockThread(AbstractPollTask):
	"""
	This uses the portage.locks module to acquire a lock asynchronously,
	using a background thread. After the lock is acquired, the thread
	writes to a pipe in order to notify a poll loop running in the main
	thread.

	If the threading module is unavailable then the dummy_threading
	module will be used, and the lock will be acquired synchronously
	(before the start() method returns).
	"""

	__slots__ = ('path',) + \
		('_files', '_force_dummy', '_lock_obj',
		'_thread', '_reg_id',)

	def _start(self):
		pr, pw = os.pipe()
		self._files = {}
		self._files['pipe_read'] = pr
		self._files['pipe_write'] = pw
		for f in self._files.values():
			fcntl.fcntl(f, fcntl.F_SETFL,
				fcntl.fcntl(f, fcntl.F_GETFL) | os.O_NONBLOCK)
		self._reg_id = self.scheduler.register(self._files['pipe_read'],
			self.scheduler.IO_IN, self._output_handler)
		self._registered = True
		threading_mod = threading
		if self._force_dummy:
			threading_mod = dummy_threading
		self._thread = threading_mod.Thread(target=self._run_lock)
		self._thread.start()

	def _run_lock(self):
		self._lock_obj = lockfile(self.path, wantnewlockfile=True)
		os.write(self._files['pipe_write'], b'\0')

	def _output_handler(self, f, event):
		buf = None
		if event & self.scheduler.IO_IN:
			try:
				buf = os.read(self._files['pipe_read'], self._bufsize)
			except OSError as e:
				if e.errno not in (errno.EAGAIN,):
					raise
		if buf:
			self._unregister()
			self.returncode = os.EX_OK
			self.wait()

		return True

	def _cancel(self):
		# There's currently no way to force thread termination.
		pass

	def unlock(self):
		if self._lock_obj is None:
			raise AssertionError('not locked')
		if self.returncode is None:
			raise AssertionError('lock not acquired yet')
		unlockfile(self._lock_obj)
		self._lock_obj = None

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
				os.close(f)
			self._files = None

class _LockProcess(AbstractPollTask):
	"""
	This uses the portage.locks module to acquire a lock asynchronously,
	using a subprocess. After the lock is acquired, the process
	writes to a pipe in order to notify a poll loop running in the main
	process. The unlock() method notifies the subprocess to release the
	lock and exit.
	"""

	__slots__ = ('path',) + \
		('_acquired', '_kill_test', '_proc', '_files', '_reg_id', '_unlocked')

	def _start(self):
		in_pr, in_pw = os.pipe()
		out_pr, out_pw = os.pipe()
		self._files = {}
		self._files['pipe_in'] = in_pr
		self._files['pipe_out'] = out_pw
		fcntl.fcntl(in_pr, fcntl.F_SETFL,
			fcntl.fcntl(in_pr, fcntl.F_GETFL) | os.O_NONBLOCK)
		self._reg_id = self.scheduler.register(in_pr,
			self.scheduler.IO_IN, self._output_handler)
		self._registered = True
		self._proc = SpawnProcess(
			args=[portage._python_interpreter,
				os.path.join(portage._bin_path, 'lock-helper.py'), self.path],
				env=dict(os.environ, PORTAGE_PYM_PATH=portage._pym_path),
				fd_pipes={0:out_pr, 1:in_pw, 2:sys.stderr.fileno()},
				scheduler=self.scheduler)
		self._proc.addExitListener(self._proc_exit)
		self._proc.start()
		os.close(out_pr)
		os.close(in_pw)

	def _proc_exit(self, proc):

		if self._files is not None:
			# Close pipe_out if it's still open, since it's useless
			# after the process has exited. This helps to avoid
			# "ResourceWarning: unclosed file" since Python 3.2.
			try:
				pipe_out = self._files.pop('pipe_out')
			except KeyError:
				pass
			else:
				os.close(pipe_out)

		if proc.returncode != os.EX_OK:
			# Typically, this will happen due to the
			# process being killed by a signal.

			if not self._acquired:
				# If the lock hasn't been aquired yet, the
				# caller can check the returncode and handle
				# this failure appropriately.
				if not (self.cancelled or self._kill_test):
					writemsg_level("_LockProcess: %s\n" % \
						_("failed to acquire lock on '%s'") % (self.path,),
						level=logging.ERROR, noiselevel=-1)
				self._unregister()
				self.returncode = proc.returncode
				self.wait()
				return

			if not self.cancelled and \
				not self._unlocked:
				# We don't want lost locks going unnoticed, so it's
				# only safe to ignore if either the cancel() or
				# unlock() methods have been previously called.
				raise AssertionError("lock process failed with returncode %s" \
					% (proc.returncode,))

	def _cancel(self):
		if self._proc is not None:
			self._proc.cancel()

	def _poll(self):
		if self._proc is not None:
			self._proc.poll()
		return self.returncode

	def _output_handler(self, f, event):
		buf = None
		if event & self.scheduler.IO_IN:
			try:
				buf = os.read(self._files['pipe_in'], self._bufsize)
			except OSError as e:
				if e.errno not in (errno.EAGAIN,):
					raise
		if buf:
			self._acquired = True
			self._unregister()
			self.returncode = os.EX_OK
			self.wait()

		return True

	def _unregister(self):
		self._registered = False

		if self._reg_id is not None:
			self.scheduler.unregister(self._reg_id)
			self._reg_id = None

		if self._files is not None:
			try:
				pipe_in = self._files.pop('pipe_in')
			except KeyError:
				pass
			else:
				os.close(pipe_in)

	def unlock(self):
		if self._proc is None:
			raise AssertionError('not locked')
		if self.returncode is None:
			raise AssertionError('lock not acquired yet')
		if self.returncode != os.EX_OK:
			raise AssertionError("lock process failed with returncode %s" \
				% (self.returncode,))
		self._unlocked = True
		os.write(self._files['pipe_out'], b'\0')
		os.close(self._files['pipe_out'])
		self._files = None
		self._proc.wait()
		self._proc = None
