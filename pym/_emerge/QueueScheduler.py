# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.PollScheduler import PollScheduler

class QueueScheduler(PollScheduler):

	"""
	Add instances of SequentialTaskQueue and then call run(). The
	run() method returns when no tasks remain.
	"""

	def __init__(self, main=True, max_jobs=None, max_load=None):
		PollScheduler.__init__(self, main=main)

		if max_jobs is None:
			max_jobs = 1

		self._max_jobs = max_jobs
		self._max_load = max_load

		self._queues = []
		self._schedule_listeners = []

	def add(self, q):
		self._queues.append(q)

	def remove(self, q):
		self._queues.remove(q)

	def clear(self):
		for q in self._queues:
			q.clear()

	def run(self, timeout=None):

		timeout_callback = None
		if timeout is not None:
			def timeout_callback():
				timeout_callback.timed_out = True
				return False
			timeout_callback.timed_out = False
			timeout_callback.timeout_id = self.sched_iface.timeout_add(
				timeout, timeout_callback)

		term_check_id = self.sched_iface.idle_add(self._termination_check)
		try:
			while not (timeout_callback is not None and
				timeout_callback.timed_out):
				# We don't have any callbacks to trigger _schedule(),
				# so we have to call it explicitly here.
				self._schedule()
				if self._keep_scheduling():
					self.sched_iface.iteration()
				else:
					break

			while self._is_work_scheduled() and \
				not (timeout_callback is not None and
				timeout_callback.timed_out):
				self.sched_iface.iteration()
		finally:
			self.sched_iface.source_remove(term_check_id)
			if timeout_callback is not None:
				self.sched_iface.unregister(timeout_callback.timeout_id)

	def _schedule_tasks(self):
		"""
		@rtype: bool
		@return: True if there may be remaining tasks to schedule,
			False otherwise.
		"""
		if self._terminated_tasks:
			return

		while self._can_add_job():
			n = self._max_jobs - self._running_job_count()
			if n < 1:
				break

			if not self._start_next_job(n):
				return

	def _keep_scheduling(self):
		return not self._terminated_tasks and any(self._queues)

	def _running_job_count(self):
		job_count = 0
		for q in self._queues:
			job_count += len(q.running_tasks)
		self._jobs = job_count
		return job_count

	def _start_next_job(self, n=1):
		started_count = 0
		for q in self._queues:
			initial_job_count = len(q.running_tasks)
			q.schedule()
			final_job_count = len(q.running_tasks)
			if final_job_count > initial_job_count:
				started_count += (final_job_count - initial_job_count)
			if started_count >= n:
				break
		return started_count

