# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from _emerge.SlotObject import SlotObject
from collections import deque
class SequentialTaskQueue(SlotObject):

	__slots__ = ("max_jobs", "running_tasks") + \
		("_dirty", "_scheduling", "_task_queue")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self._task_queue = deque()
		self.running_tasks = set()
		if self.max_jobs is None:
			self.max_jobs = 1
		self._dirty = True

	def add(self, task):
		self._task_queue.append(task)
		self._dirty = True
		self.schedule()

	def addFront(self, task):
		self._task_queue.appendleft(task)
		self._dirty = True
		self.schedule()

	def schedule(self):

		if not self._dirty:
			return False

		if not self:
			return False

		if self._scheduling:
			# Ignore any recursive schedule() calls triggered via
			# self._task_exit().
			return False

		self._scheduling = True

		task_queue = self._task_queue
		running_tasks = self.running_tasks
		max_jobs = self.max_jobs
		state_changed = False

		while task_queue and \
			(max_jobs is True or len(running_tasks) < max_jobs):
			task = task_queue.popleft()
			cancelled = getattr(task, "cancelled", None)
			if not cancelled:
				running_tasks.add(task)
				task.addExitListener(self._task_exit)
				task.start()
			state_changed = True

		self._dirty = False
		self._scheduling = False

		return state_changed

	def _task_exit(self, task):
		"""
		Since we can always rely on exit listeners being called, the set of
 		running tasks is always pruned automatically and there is never any need
		to actively prune it.
		"""
		self.running_tasks.remove(task)
		if self._task_queue:
			self._dirty = True
			self.schedule()

	def clear(self):
		self._task_queue.clear()
		running_tasks = self.running_tasks
		while running_tasks:
			task = running_tasks.pop()
			task.removeExitListener(self._task_exit)
			task.cancel()
		self._dirty = False

	def __bool__(self):
		return bool(self._task_queue or self.running_tasks)

	if sys.hexversion < 0x3000000:
		__nonzero__ = __bool__

	def __len__(self):
		return len(self._task_queue) + len(self.running_tasks)
