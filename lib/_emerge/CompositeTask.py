# Copyright 1999-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousTask import AsynchronousTask
from portage import os

class CompositeTask(AsynchronousTask):

	__slots__ = ("_current_task",)

	_TASK_QUEUED = -1

	def _cancel(self):
		if self._current_task is not None:
			if self._current_task is self._TASK_QUEUED:
				self.returncode = 1
				self._current_task = None
				self._async_wait()
			else:
				self._current_task.cancel()
		elif self.returncode is None:
			# Assume that the task has not started yet.
			self._was_cancelled()
			self._async_wait()

	def _poll(self):
		"""
		This does a loop calling self._current_task.poll()
		repeatedly as long as the value of self._current_task
		keeps changing. It calls poll() a maximum of one time
		for a given self._current_task instance. This is useful
		since calling poll() on a task can trigger advance to
		the next task could eventually lead to the returncode
		being set in cases when polling only a single task would
		not have the same effect.
		"""

		prev = None
		while True:
			task = self._current_task
			if task is None or \
				task is self._TASK_QUEUED or \
				task is prev:
				# don't poll the same task more than once
				break
			task.poll()
			prev = task

		return self.returncode

	def _assert_current(self, task):
		"""
		Raises an AssertionError if the given task is not the
		same one as self._current_task. This can be useful
		for detecting bugs.
		"""
		if task is not self._current_task:
			raise AssertionError("Unrecognized task: %s" % (task,))

	def _default_exit(self, task):
		"""
		Calls _assert_current() on the given task and then sets the
		composite returncode attribute if task.returncode != os.EX_OK.
		If the task failed then self._current_task will be set to None.
		Subclasses can use this as a generic task exit callback.

		@rtype: int
		@return: The task.returncode attribute.
		"""
		self._assert_current(task)
		if task.returncode != os.EX_OK:
			self.returncode = task.returncode
			self.cancelled = task.cancelled
			self._current_task = None
		return task.returncode

	def _final_exit(self, task):
		"""
		Assumes that task is the final task of this composite task.
		Calls _default_exit() and sets self.returncode to the task's
		returncode and sets self._current_task to None.
		"""
		self._default_exit(task)
		self._current_task = None
		self.returncode = task.returncode
		return self.returncode

	def _default_final_exit(self, task):
		"""
		This calls _final_exit() and then wait().

		Subclasses can use this as a generic final task exit callback.

		"""
		self._final_exit(task)
		return self.wait()

	def _start_task(self, task, exit_handler):
		"""
		Register exit handler for the given task, set it
		as self._current_task, and call task.start().

		Subclasses can use this as a generic way to start
		a task.

		"""
		try:
			task.scheduler = self.scheduler
		except AttributeError:
			pass
		task.addExitListener(exit_handler)
		self._current_task = task
		task.start()

	def _task_queued(self, task):
		task.addStartListener(self._task_queued_start_handler)
		self._current_task = self._TASK_QUEUED

	def _task_queued_start_handler(self, task):
		self._current_task = task

	def _task_queued_wait(self):
		return self._current_task is not self._TASK_QUEUED or \
			self.cancelled or self.returncode is not None
