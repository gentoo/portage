# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage.util.futures import asyncio
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.util._eventloop.global_event_loop import global_event_loop

from _emerge.getloadavg import getloadavg

class PollScheduler:

	# max time between loadavg checks (milliseconds)
	_loadavg_latency = None

	def __init__(self, main=False, event_loop=None):
		"""
		@param main: If True then use global_event_loop(), otherwise use
			a local EventLoop instance (default is False, for safe use in
			a non-main thread)
		@type main: bool
		"""
		self._term_rlock = threading.RLock()
		self._terminated = threading.Event()
		self._terminated_tasks = False
		self._term_check_handle = None
		self._max_jobs = 1
		self._max_load = None
		self._scheduling = False
		self._background = False
		if event_loop is not None:
			self._event_loop = event_loop
		elif main:
			self._event_loop = global_event_loop()
		else:
			self._event_loop = asyncio._safe_loop()
		self._sched_iface = SchedulerInterface(self._event_loop,
			is_background=self._is_background)

	def _is_background(self):
		return self._background

	def _cleanup(self):
		"""
		Cleanup any callbacks that have been registered with the global
		event loop.
		"""
		# The self._term_check_handle attribute requires locking
		# since it's modified by the thread safe terminate method.
		with self._term_rlock:
			if self._term_check_handle not in (None, False):
				self._term_check_handle.cancel()
			# This prevents the terminate method from scheduling
			# any more callbacks (since _cleanup must eliminate all
			# callbacks in order to ensure complete cleanup).
			self._term_check_handle = False

	def terminate(self):
		"""
		Schedules asynchronous, graceful termination of the scheduler
		at the earliest opportunity.

		This method is thread-safe (and safe for signal handlers).
		"""
		with self._term_rlock:
			if self._term_check_handle is None:
				self._terminated.set()
				self._term_check_handle = self._event_loop.call_soon_threadsafe(
					self._termination_check, True)

	def _termination_check(self, retry=False):
		"""
		Calls _terminate_tasks() if appropriate. It's guaranteed not to
		call it while _schedule_tasks() is being called. This method must
		only be called via the event loop thread.

		@param retry: If True then reschedule if scheduling state prevents
			immediate termination.
		@type retry: bool
		"""
		if self._terminated.is_set() and \
			not self._terminated_tasks:
			if not self._scheduling:
				self._scheduling = True
				try:
					self._terminated_tasks = True
					self._terminate_tasks()
				finally:
					self._scheduling = False

			elif retry:
				with self._term_rlock:
					self._term_check_handle = self._event_loop.call_soon(
						self._termination_check, True)

	def _terminate_tasks(self):
		"""
		Send signals to terminate all tasks. This is called once
		from _keep_scheduling() or _is_work_scheduled() in the event
		dispatching thread. It will not be called while the _schedule_tasks()
		implementation is running, in order to avoid potential
		interference. All tasks should be cleaned up at the earliest
		opportunity, but not necessarily before this method returns.
		Typically, this method will send kill signals and return without
		waiting for exit status. This allows basic cleanup to occur, such as
		flushing of buffered output to logs.
		"""
		raise NotImplementedError()

	def _keep_scheduling(self):
		"""
		@rtype: bool
		@return: True if there may be remaining tasks to schedule,
			False otherwise.
		"""
		return False

	def _schedule_tasks(self):
		"""
		This is called from inside the _schedule() method, which
		guarantees the following:

		1) It will not be called recursively.
		2) _terminate_tasks() will not be called while it is running.
		3) The state of the boolean _terminated_tasks variable will
		   not change while it is running.

		Unless this method is used to perform user interface updates,
		or something like that, the first thing it should do is check
		the state of _terminated_tasks and if that is True then it
		should return immediately (since there's no need to
		schedule anything after _terminate_tasks() has been called).
		"""
		pass

	def _schedule(self):
		"""
		Calls _schedule_tasks() and automatically returns early from
		any recursive calls to this method that the _schedule_tasks()
		call might trigger. This makes _schedule() safe to call from
		inside exit listeners. This method always returns True, so that
		it may be scheduled continuously via EventLoop.timeout_add().
		"""
		if self._scheduling:
			return True
		self._scheduling = True
		try:
			self._schedule_tasks()
		finally:
			self._scheduling = False
		return True

	def _is_work_scheduled(self):
		return bool(self._running_job_count())

	def _running_job_count(self):
		raise NotImplementedError(self)

	def _can_add_job(self):
		if self._terminated_tasks:
			return False

		max_jobs = self._max_jobs
		max_load = self._max_load

		if self._max_jobs is not True and \
			self._running_job_count() >= self._max_jobs:
			return False

		if max_load is not None and \
			(max_jobs is True or max_jobs > 1) and \
			self._running_job_count() >= 1:
			try:
				avg1, avg5, avg15 = getloadavg()
			except OSError:
				return False

			if avg1 >= max_load:
				return False

		return True
