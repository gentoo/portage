# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.PollScheduler import PollScheduler

class AsyncScheduler(AsynchronousTask, PollScheduler):

	def __init__(self, max_jobs=None, max_load=None, **kwargs):
		AsynchronousTask.__init__(self)
		PollScheduler.__init__(self, **kwargs)

		if max_jobs is None:
			max_jobs = 1
		self._max_jobs = max_jobs
		self._max_load = max_load
		self._error_count = 0
		self._running_tasks = set()
		self._remaining_tasks = True
		self._term_check_id = None
		self._loadavg_check_id = None

	def _poll(self):
		if not (self._is_work_scheduled() or self._keep_scheduling()):
			self.wait()
		return self.returncode

	def _cancel(self):
		self._terminated.set()
		self._termination_check()

	def _terminate_tasks(self):
		for task in list(self._running_tasks):
			task.cancel()

	def _next_task(self):
		raise NotImplementedError(self)

	def _keep_scheduling(self):
		return self._remaining_tasks and not self._terminated_tasks

	def _running_job_count(self):
		return len(self._running_tasks)

	def _schedule_tasks(self):
		while self._keep_scheduling() and self._can_add_job():
			try:
				task = self._next_task()
			except StopIteration:
				self._remaining_tasks = False
			else:
				self._running_tasks.add(task)
				task.scheduler = self._sched_iface
				task.addExitListener(self._task_exit)
				task.start()

		# Triggers cleanup and exit listeners if there's nothing left to do.
		self.poll()

	def _task_exit(self, task):
		self._running_tasks.discard(task)
		if task.returncode != os.EX_OK:
			self._error_count += 1
		self._schedule()

	def _start(self):
		self._term_check_id = self._event_loop.idle_add(self._termination_check)
		if self._max_load is not None and \
			self._loadavg_latency is not None and \
			(self._max_jobs is True or self._max_jobs > 1):
			# We have to schedule periodically, in case the load
			# average has changed since the last call.
			self._loadavg_check_id = self._event_loop.timeout_add(
				self._loadavg_latency, self._schedule)
		self._schedule()

	def _wait(self):
		# Loop while there are jobs to be scheduled.
		while self._keep_scheduling():
			self._event_loop.iteration()

		# Clean shutdown of previously scheduled jobs. In the
		# case of termination, this allows for basic cleanup
		# such as flushing of buffered output to logs.
		while self._is_work_scheduled():
			self._event_loop.iteration()

		if self._term_check_id is not None:
			self._event_loop.source_remove(self._term_check_id)
			self._term_check_id = None

		if self._loadavg_check_id is not None:
			self._event_loop.source_remove(self._loadavg_check_id)
			self._loadavg_check_id = None

		if self._error_count > 0:
			self.returncode = 1
		else:
			self.returncode = os.EX_OK 

		return self.returncode
