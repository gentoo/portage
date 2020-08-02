# Copyright 2013-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import logging
import time

try:
	import threading
except ImportError:
	import dummy_threading as threading

import portage
from portage import os
from portage.util._async.TaskScheduler import TaskScheduler
from _emerge.CompositeTask import CompositeTask
from .FetchIterator import FetchIterator
from .DeletionIterator import DeletionIterator


class MirrorDistTask(CompositeTask):

	__slots__ = ('_config', '_fetch_iterator', '_term_rlock',
		'_term_callback_handle')

	def __init__(self, config):
		CompositeTask.__init__(self, scheduler=config.event_loop)
		self._config = config
		self._term_rlock = threading.RLock()
		self._term_callback_handle = None
		self._fetch_iterator = None

	def _start(self):
		self._fetch_iterator = FetchIterator(self._config)
		fetch = TaskScheduler(iter(self._fetch_iterator),
			max_jobs=self._config.options.jobs,
			max_load=self._config.options.load_average,
			event_loop=self._config.event_loop)
		self._start_task(fetch, self._fetch_exit)

	def _fetch_exit(self, fetch):

		self._assert_current(fetch)
		if self._was_cancelled():
			self._async_wait()
			return

		if self._config.options.delete:
			deletion = TaskScheduler(iter(DeletionIterator(self._config)),
				max_jobs=self._config.options.jobs,
				max_load=self._config.options.load_average,
				event_loop=self._config.event_loop)
			self._start_task(deletion, self._deletion_exit)
			return

		self._post_deletion()

	def _deletion_exit(self, deletion):

		self._assert_current(deletion)
		if self._was_cancelled():
			self._async_wait()
			return

		self._post_deletion()

	def _post_deletion(self):

		if self._config.options.recycle_db is not None:
			self._update_recycle_db()

		if self._config.options.scheduled_deletion_log is not None:
			self._scheduled_deletion_log()

		self._summary()

		self.returncode = os.EX_OK
		self._current_task = None
		self._async_wait()

	def _update_recycle_db(self):

		start_time = self._config.start_time
		recycle_dir = self._config.options.recycle_dir
		recycle_db = self._config.recycle_db
		r_deletion_delay = self._config.options.recycle_deletion_delay

		# Use a dict optimize access.
		recycle_db_cache = dict(recycle_db.items())

		for filename in os.listdir(recycle_dir):

			recycle_file = os.path.join(recycle_dir, filename)

			try:
				st = os.stat(recycle_file)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					logging.error(("stat failed for '%s' in "
						"recycle: %s") % (filename, e))
				continue

			value = recycle_db_cache.pop(filename, None)
			if value is None:
				logging.debug(("add '%s' to "
					"recycle db") % filename)
				recycle_db[filename] = (st.st_size, start_time)
			else:
				r_size, r_time = value
				if int(r_size) != st.st_size:
					recycle_db[filename] = (st.st_size, start_time)
				elif r_time + r_deletion_delay < start_time:
					if self._config.options.dry_run:
						logging.info(("dry-run: delete '%s' from "
							"recycle") % filename)
						logging.info(("drop '%s' from "
							"recycle db") % filename)
					else:
						try:
							os.unlink(recycle_file)
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								logging.error(("delete '%s' from "
									"recycle failed: %s") % (filename, e))
						else:
							logging.debug(("delete '%s' from "
								"recycle") % filename)
							try:
								del recycle_db[filename]
							except KeyError:
								pass
							else:
								logging.debug(("drop '%s' from "
									"recycle db") % filename)

		# Existing files were popped from recycle_db_cache,
		# so any remaining entries are for files that no
		# longer exist.
		for filename in recycle_db_cache:
			try:
				del recycle_db[filename]
			except KeyError:
				pass
			else:
				logging.debug(("drop non-existent '%s' from "
					"recycle db") % filename)

	def _scheduled_deletion_log(self):

		start_time = self._config.start_time
		dry_run = self._config.options.dry_run
		deletion_delay = self._config.options.deletion_delay
		distfiles_db = self._config.distfiles_db

		date_map = {}
		for filename, timestamp in self._config.deletion_db.items():
			date = timestamp + deletion_delay
			if date < start_time:
				date = start_time
			date = time.strftime("%Y-%m-%d", time.gmtime(date))
			date_files = date_map.get(date)
			if date_files is None:
				date_files = []
				date_map[date] = date_files
			date_files.append(filename)

		if dry_run:
			logging.warning("dry-run: scheduled-deletions log "
				"will be summarized via logging.info")

		lines = []
		for date in sorted(date_map):
			date_files = date_map[date]
			if dry_run:
				logging.info(("dry-run: scheduled deletions for %s: %s files") %
					(date, len(date_files)))
			lines.append("%s\n" % date)
			for filename in date_files:
				cpv = "unknown"
				if distfiles_db is not None:
					cpv = distfiles_db.get(filename, cpv)
				lines.append("\t%s\t%s\n" % (filename, cpv))

		if not dry_run:
			portage.util.write_atomic(
				self._config.options.scheduled_deletion_log,
				"".join(lines))

	def _summary(self):
		elapsed_time = time.time() - self._config.start_time
		fail_count = len(self._config.file_failures)
		delete_count = self._config.delete_count
		scheduled_deletion_count = self._config.scheduled_deletion_count - delete_count
		added_file_count = self._config.added_file_count
		added_byte_count = self._config.added_byte_count

		logging.info("finished in %i seconds" % elapsed_time)
		logging.info("failed to fetch %i files" % fail_count)
		logging.info("deleted %i files" % delete_count)
		logging.info("deletion of %i files scheduled" %
			scheduled_deletion_count)
		logging.info("added %i files" % added_file_count)
		logging.info("added %i bytes total" % added_byte_count)

	def _cleanup(self):
		"""
		Cleanup any callbacks that have been registered with the global
		event loop.
		"""
		# The self._term_callback_handle attribute requires locking
		# since it's modified by the thread safe terminate method.
		with self._term_rlock:
			if self._term_callback_handle not in (None, False):
				self._term_callback_handle.cancel()
			# This prevents the terminate method from scheduling
			# any more callbacks (since _cleanup must eliminate all
			# callbacks in order to ensure complete cleanup).
			self._term_callback_handle = False

	def terminate(self):
		with self._term_rlock:
			if self._term_callback_handle is None:
				self._term_callback_handle = self.scheduler.call_soon_threadsafe(
					self._term_callback)

	def _term_callback(self):
		if self._fetch_iterator is not None:
			self._fetch_iterator.terminate()
		self.cancel()
		if self.returncode is None:
			# In this case, the exit callback for self._current_task will
			# trigger notification of exit listeners. Don't call _async_wait()
			# yet, since that could trigger event loop recursion if the
			# current (cancelled) task's exit callback does not set the
			# returncode first.
			pass
		else:
			self._async_wait()

	def _async_wait(self):
		"""
		Override _async_wait to call self._cleanup().
		"""
		self._cleanup()
		super(MirrorDistTask, self)._async_wait()
