# Copyright 2012-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import functools
import multiprocessing
import signal
import sys

import portage
from portage import os
from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine
from _emerge.SpawnProcess import SpawnProcess

class ForkProcess(SpawnProcess):

	__slots__ = ('_proc', '_proc_join_task')

	# Number of seconds between poll attempts for process exit status
	# (after the sentinel has become ready).
	_proc_join_interval = 0.1

	def _spawn(self, args, fd_pipes=None, **kwargs):
		"""
		Override SpawnProcess._spawn to fork a subprocess that calls
		self._run(). This uses multiprocessing.Process in order to leverage
		any pre-fork and post-fork interpreter housekeeping that it provides,
		promoting a healthy state for the forked interpreter.
		"""
		# Since multiprocessing.Process closes sys.__stdin__, create a
		# temporary duplicate of fd_pipes[0] so that sys.__stdin__ can
		# be restored in the subprocess, in case this is needed for
		# things like PROPERTIES=interactive support.
		stdin_dup = None
		try:
			stdin_fd = fd_pipes.get(0)
			if stdin_fd is not None and stdin_fd == portage._get_stdin().fileno():
				stdin_dup = os.dup(stdin_fd)
				fcntl.fcntl(stdin_dup, fcntl.F_SETFD,
					fcntl.fcntl(stdin_fd, fcntl.F_GETFD))
				fd_pipes[0] = stdin_dup
			self._proc = multiprocessing.Process(target=self._bootstrap, args=(fd_pipes,))
			self._proc.start()
		finally:
			if stdin_dup is not None:
				os.close(stdin_dup)

		self._proc_join_task = asyncio.ensure_future(
			self._proc_join(self._proc, loop=self.scheduler), loop=self.scheduler)
		self._proc_join_task.add_done_callback(
			functools.partial(self._proc_join_done, self._proc))

		return [self._proc.pid]

	def _cancel(self):
		if self._proc is None:
			super(ForkProcess, self)._cancel()
		else:
			self._proc.terminate()

	def _async_wait(self):
		if self._proc_join_task is None:
			super(ForkProcess, self)._async_wait()

	def _async_waitpid(self):
		if self._proc_join_task is None:
			super(ForkProcess, self)._async_waitpid()

	@coroutine
	def _proc_join(self, proc, loop=None):
		sentinel_reader = self.scheduler.create_future()
		self.scheduler.add_reader(proc.sentinel,
			lambda: sentinel_reader.done() or sentinel_reader.set_result(None))
		try:
			yield sentinel_reader
		finally:
			# If multiprocessing.Process supports the close method, then
			# access to proc.sentinel will raise ValueError if the
			# sentinel has been closed. In this case it's not safe to call
			# remove_reader, since the file descriptor may have been closed
			# and then reallocated to a concurrent coroutine. When the
			# close method is not supported, proc.sentinel remains open
			# until proc's finalizer is called.
			try:
				self.scheduler.remove_reader(proc.sentinel)
			except ValueError:
				pass

		# Now that proc.sentinel is ready, poll until process exit
		# status has become available.
		while True:
			proc.join(0)
			if proc.exitcode is not None:
				break
			yield asyncio.sleep(self._proc_join_interval, loop=loop)

	def _proc_join_done(self, proc, future):
		future.cancelled() or future.result()
		self._was_cancelled()
		if self.returncode is None:
			self.returncode = proc.exitcode

		self._proc = None
		if hasattr(proc, 'close'):
			proc.close()
		self._proc_join_task = None
		self._async_wait()

	def _unregister(self):
		super(ForkProcess, self)._unregister()
		if self._proc is not None:
			if self._proc.is_alive():
				self._proc.terminate()
			self._proc = None
		if self._proc_join_task is not None:
			self._proc_join_task.cancel()
			self._proc_join_task = None

	def _bootstrap(self, fd_pipes):
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

				# Since multiprocessing.Process closes sys.__stdin__ and
				# makes sys.stdin refer to os.devnull, restore it when
				# appropriate.
				if 0 in fd_pipes:
					# It's possible that sys.stdin.fileno() is already 0,
					# and in that case the above _setup_pipes call will
					# have already updated its identity via dup2. Otherwise,
					# perform the dup2 call now, and also copy the file
					# descriptor flags.
					if sys.stdin.fileno() != 0:
						os.dup2(0, sys.stdin.fileno())
						fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFD,
							fcntl.fcntl(0, fcntl.F_GETFD))
					sys.__stdin__ = sys.stdin

				sys.exit(self._run())

	def _run(self):
		raise NotImplementedError(self)
