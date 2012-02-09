# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys
from _emerge.SlotObject import SlotObject
from collections import deque
class SequentialTaskQueue(SlotObject):

	__slots__ = ("max_jobs", "running_tasks") + \
		("_scheduling", "_task_queue")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self._task_queue = deque()
		self.running_tasks = set()
		if self.max_jobs is None:
			self.max_jobs = 1

	def add(self, task):
		self._task_queue.append(task)
		self.schedule()

	def addFront(self, task):
		self._task_queue.appendleft(task)
		self.schedule()

	def schedule(self):

		if self._scheduling:
			# Ignore any recursive schedule() calls triggered via
			# self._task_exit().
			return

		self._scheduling = True
		try:
			while self._task_queue and (self.max_jobs is True or
				len(self.running_tasks) < self.max_jobs):
				task = self._task_queue.popleft()
				cancelled = getattr(task, "cancelled", None)
				if not cancelled:
					self.running_tasks.add(task)
					task.addExitListener(self._task_exit)
					task.start()
		finally:
			self._scheduling = False

	def _task_exit(self, task):
		"""
		Since we can always rely on exit listeners being called, the set of
 		running tasks is always pruned automatically and there is never any need
		to actively prune it.
		"""
		self.running_tasks.remove(task)
		if self._task_queue:
			self.schedule()

	def clear(self):
		self._task_queue.clear()
		running_tasks = self.running_tasks
		while running_tasks:
			task = running_tasks.pop()
			task.removeExitListener(self._task_exit)
			task.cancel()

	def __bool__(self):
		return bool(self._task_queue or self.running_tasks)

	if sys.hexversion < 0x3000000:
		__nonzero__ = __bool__

	def __len__(self):
		return len(self._task_queue) + len(self.running_tasks)
