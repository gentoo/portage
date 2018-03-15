# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import multiprocessing

from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._async.TaskScheduler import TaskScheduler
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures.wait import wait, FIRST_COMPLETED


def iter_completed(futures, max_jobs=None, max_load=None, loop=None):
	"""
	This is similar to asyncio.as_completed, but takes an iterator of
	futures as input, and includes support for max_jobs and max_load
	parameters.

	@param futures: iterator of asyncio.Future (or compatible)
	@type futures: iterator
	@param max_jobs: max number of futures to process concurrently (default
		is multiprocessing.cpu_count())
	@type max_jobs: int
	@param max_load: max load allowed when scheduling a new future,
		otherwise schedule no more than 1 future at a time (default
		is multiprocessing.cpu_count())
	@type max_load: int or float
	@param loop: event loop
	@type loop: EventLoop
	@return: iterator of futures that are done
	@rtype: iterator
	"""
	loop = loop or global_event_loop()
	max_jobs = max_jobs or multiprocessing.cpu_count()
	max_load = max_load or multiprocessing.cpu_count()

	future_map = {}
	def task_generator():
		for future in futures:
			future_map[id(future)] = future
			yield AsyncTaskFuture(future=future)

	scheduler = TaskScheduler(
		task_generator(),
		max_jobs=max_jobs,
		max_load=max_load,
		event_loop=loop)

	try:
		scheduler.start()

		# scheduler should ensure that future_map is non-empty until
		# task_generator is exhausted
		while future_map:
			done, pending = loop.run_until_complete(
				wait(list(future_map.values()), return_when=FIRST_COMPLETED))
			for future in done:
				del future_map[id(future)]
				yield future

	finally:
		# cleanup in case of interruption by SIGINT, etc
		scheduler.cancel()
		scheduler.wait()
