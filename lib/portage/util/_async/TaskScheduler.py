# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from .AsyncScheduler import AsyncScheduler

class TaskScheduler(AsyncScheduler):

	"""
	A simple way to handle scheduling of AbstractPollTask instances. Simply
	pass a task iterator into the constructor and call start(). Use the
	poll, wait, or addExitListener methods to be notified when all of the
	tasks have completed.
	"""

	def __init__(self, task_iter, **kwargs):
		AsyncScheduler.__init__(self, **kwargs)
		self._task_iter = task_iter

	def _next_task(self):
		return next(self._task_iter)
