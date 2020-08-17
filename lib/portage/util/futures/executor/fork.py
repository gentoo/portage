# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ForkExecutor',
)

import collections
import functools
import os
import sys
import traceback

from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.futures import asyncio
from portage.util.cpuinfo import get_cpu_count


class ForkExecutor:
	"""
	An implementation of concurrent.futures.Executor that forks a
	new process for each task, with support for cancellation of tasks.

	This is entirely driven by an event loop.
	"""
	def __init__(self, max_workers=None, loop=None):
		self._max_workers = max_workers or get_cpu_count()
		self._loop = asyncio._wrap_loop(loop)
		self._submit_queue = collections.deque()
		self._running_tasks = {}
		self._shutdown = False
		self._shutdown_future = self._loop.create_future()

	def submit(self, fn, *args, **kwargs):
		"""Submits a callable to be executed with the given arguments.

		Schedules the callable to be executed as fn(*args, **kwargs) and returns
		a Future instance representing the execution of the callable.

		Returns:
			A Future representing the given call.
		"""
		future = self._loop.create_future()
		proc = AsyncFunction(target=functools.partial(
			self._guarded_fn_call, fn, args, kwargs))
		self._submit_queue.append((future, proc))
		self._schedule()
		return future

	def _schedule(self):
		while (not self._shutdown and self._submit_queue and
			(self._max_workers is True or len(self._running_tasks) < self._max_workers)):
			future, proc = self._submit_queue.popleft()
			future.add_done_callback(functools.partial(self._cancel_cb, proc))
			proc.addExitListener(functools.partial(self._proc_exit, future))
			proc.scheduler = self._loop
			proc.start()
			self._running_tasks[id(proc)] = proc

	def _cancel_cb(self, proc, future):
		if future.cancelled():
			# async, handle the rest in _proc_exit
			proc.cancel()

	@staticmethod
	def _guarded_fn_call(fn, args, kwargs):
		try:
			result = fn(*args, **kwargs)
			exception = None
		except Exception as e:
			result = None
			exception = _ExceptionWithTraceback(e)

		return result, exception

	def _proc_exit(self, future, proc):
		if not future.cancelled():
			if proc.returncode == os.EX_OK:
				result, exception = proc.result
				if exception is not None:
					future.set_exception(exception)
				else:
					future.set_result(result)
			else:
				# TODO: add special exception class for this, maybe
				# distinguish between kill and crash
				future.set_exception(
					Exception('pid {} crashed or killed, exitcode {}'.\
						format(proc.pid, proc.returncode)))

		del self._running_tasks[id(proc)]
		self._schedule()
		if self._shutdown and not self._running_tasks:
			self._shutdown_future.set_result(None)

	def shutdown(self, wait=True):
		self._shutdown = True
		if not self._running_tasks and not self._shutdown_future.done():
			self._shutdown_future.set_result(None)
		if wait:
			self._loop.run_until_complete(self._shutdown_future)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.shutdown(wait=True)
		return False


class _ExceptionWithTraceback:
	def __init__(self, exc):
		tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
		tb = ''.join(tb)
		self.exc = exc
		self.tb = '\n"""\n%s"""' % tb
	def __reduce__(self):
		return _rebuild_exc, (self.exc, self.tb)


class _RemoteTraceback(Exception):
	def __init__(self, tb):
		self.tb = tb
	def __str__(self):
		return self.tb


def _rebuild_exc(exc, tb):
	exc.__cause__ = _RemoteTraceback(tb)
	return exc


if sys.version_info < (3,):
	# Python 2 does not support exception chaining, so
	# don't bother to preserve the traceback.
	_ExceptionWithTraceback = lambda exc: exc
