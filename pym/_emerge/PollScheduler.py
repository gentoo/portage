# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import gzip
import errno

try:
	import threading
except ImportError:
	import dummy_threading as threading

from portage import _encodings
from portage import _unicode_encode
from portage.util import writemsg_level
from portage.util.SlotObject import SlotObject
from portage.util._eventloop.EventLoop import EventLoop
from portage.util._eventloop.global_event_loop import global_event_loop

from _emerge.getloadavg import getloadavg

class PollScheduler(object):

	# max time between loadavg checks (milliseconds)
	_loadavg_latency = 30000

	class _sched_iface_class(SlotObject):
		__slots__ = ("IO_ERR", "IO_HUP", "IO_IN", "IO_NVAL", "IO_OUT",
			"IO_PRI", "child_watch_add",
			"idle_add", "io_add_watch", "iteration",
			"output", "register", "run",
			"source_remove", "timeout_add", "unregister")

	def __init__(self, main=False):
		"""
		@param main: If True then use global_event_loop(), otherwise use
			a local EventLoop instance (default is False, for safe use in
			a non-main thread)
		@type main: bool
		"""
		self._terminated = threading.Event()
		self._terminated_tasks = False
		self._max_jobs = 1
		self._max_load = None
		self._jobs = 0
		self._scheduling = False
		self._background = False
		if main:
			self._event_loop = global_event_loop()
		else:
			self._event_loop = EventLoop(main=False)
		self.sched_iface = self._sched_iface_class(
			IO_ERR=self._event_loop.IO_ERR,
			IO_HUP=self._event_loop.IO_HUP,
			IO_IN=self._event_loop.IO_IN,
			IO_NVAL=self._event_loop.IO_NVAL,
			IO_OUT=self._event_loop.IO_OUT,
			IO_PRI=self._event_loop.IO_PRI,
			child_watch_add=self._event_loop.child_watch_add,
			idle_add=self._event_loop.idle_add,
			io_add_watch=self._event_loop.io_add_watch,
			iteration=self._event_loop.iteration,
			output=self._task_output,
			register=self._event_loop.io_add_watch,
			source_remove=self._event_loop.source_remove,
			timeout_add=self._event_loop.timeout_add,
			unregister=self._event_loop.source_remove)

	def terminate(self):
		"""
		Schedules asynchronous, graceful termination of the scheduler
		at the earliest opportunity.

		This method is thread-safe (and safe for signal handlers).
		"""
		self._terminated.set()

	def _termination_check(self):
		"""
		Calls _terminate_tasks() if appropriate. It's guaranteed not to
		call it while _schedule_tasks() is being called. The check should
		be executed for each iteration of the event loop, for response to
		termination signals at the earliest opportunity. It always returns
		True, for continuous scheduling via idle_add.
		"""
		if not self._scheduling and \
			self._terminated.is_set() and \
			not self._terminated_tasks:
			self._scheduling = True
			try:
				self._terminated_tasks = True
				self._terminate_tasks()
			finally:
				self._scheduling = False
		return True

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
		inside exit listeners.
		"""
		if self._scheduling:
			return False
		self._scheduling = True
		try:
			self._schedule_tasks()
		finally:
			self._scheduling = False

	def _main_loop(self):
		term_check_id = self.sched_iface.idle_add(self._termination_check)
		loadavg_check_id = None
		if self._max_load is not None:
			# We have to schedule periodically, in case the load
			# average has changed since the last call.
			loadavg_check_id = self.sched_iface.timeout_add(
				self._loadavg_latency, self._schedule)

		try:
			# Populate initial event sources. Unless we're scheduling
			# based on load average, we only need to do this once
			# here, since it can be called during the loop from within
			# event handlers.
			self._schedule()

			# Loop while there are jobs to be scheduled.
			while self._keep_scheduling():
				self.sched_iface.iteration()

			# Clean shutdown of previously scheduled jobs. In the
			# case of termination, this allows for basic cleanup
			# such as flushing of buffered output to logs.
			while self._is_work_scheduled():
				self.sched_iface.iteration()
		finally:
			self.sched_iface.source_remove(term_check_id)
			if loadavg_check_id is not None:
				self.sched_iface.source_remove(loadavg_check_id)

	def _is_work_scheduled(self):
		return bool(self._running_job_count())

	def _running_job_count(self):
		return self._jobs

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

	def _task_output(self, msg, log_path=None, background=None,
		level=0, noiselevel=-1):
		"""
		Output msg to stdout if not self._background. If log_path
		is not None then append msg to the log (appends with
		compression if the filename extension of log_path
		corresponds to a supported compression type).
		"""

		if background is None:
			# If the task does not have a local background value
			# (like for parallel-fetch), then use the global value.
			background = self._background

		msg_shown = False
		if not background:
			writemsg_level(msg, level=level, noiselevel=noiselevel)
			msg_shown = True

		if log_path is not None:
			try:
				f = open(_unicode_encode(log_path,
					encoding=_encodings['fs'], errors='strict'),
					mode='ab')
				f_real = f
			except IOError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					raise
				if not msg_shown:
					writemsg_level(msg, level=level, noiselevel=noiselevel)
			else:

				if log_path.endswith('.gz'):
					# NOTE: The empty filename argument prevents us from
					# triggering a bug in python3 which causes GzipFile
					# to raise AttributeError if fileobj.name is bytes
					# instead of unicode.
					f =  gzip.GzipFile(filename='', mode='ab', fileobj=f)

				f.write(_unicode_encode(msg))
				f.close()
				if f_real is not f:
					f_real.close()
