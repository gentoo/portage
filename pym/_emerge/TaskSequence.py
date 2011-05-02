# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from _emerge.CompositeTask import CompositeTask
from _emerge.AsynchronousTask import AsynchronousTask
from collections import deque

class TaskSequence(CompositeTask):
	"""
	A collection of tasks that executes sequentially. Each task
	must have a addExitListener() method that can be used as
	a means to trigger movement from one task to the next.
	"""

	__slots__ = ("_task_queue",)

	def __init__(self, **kwargs):
		AsynchronousTask.__init__(self, **kwargs)
		self._task_queue = deque()

	def add(self, task):
		self._task_queue.append(task)

	def _start(self):
		self._start_next_task()

	def _cancel(self):
		self._task_queue.clear()
		CompositeTask._cancel(self)

	def _start_next_task(self):
		self._start_task(self._task_queue.popleft(),
			self._task_exit_handler)

	def _task_exit_handler(self, task):
		if self._default_exit(task) != os.EX_OK:
			self.wait()
		elif self._task_queue:
			self._start_next_task()
		else:
			self._final_exit(task)
			self.wait()

