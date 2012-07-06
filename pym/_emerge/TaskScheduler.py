# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.QueueScheduler import QueueScheduler
from _emerge.SequentialTaskQueue import SequentialTaskQueue

class TaskScheduler(object):

	"""
	A simple way to handle scheduling of AsynchrousTask instances. Simply
	add tasks and call run(). The run() method returns when no tasks remain.
	"""

	def __init__(self, main=True, max_jobs=None, max_load=None):
		self._queue = SequentialTaskQueue(max_jobs=max_jobs)
		self._scheduler = QueueScheduler(main=main,
			max_jobs=max_jobs, max_load=max_load)
		self.sched_iface = self._scheduler.sched_iface
		self.run = self._scheduler.run
		self.clear = self._scheduler.clear
		self.wait = self._queue.wait
		self._scheduler.add(self._queue)

	def add(self, task):
		self._queue.add(task)

