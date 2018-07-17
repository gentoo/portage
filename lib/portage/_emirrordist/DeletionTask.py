# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import logging

from portage import os
from portage.util._async.FileCopier import FileCopier
from _emerge.CompositeTask import CompositeTask

class DeletionTask(CompositeTask):

	__slots__ = ('distfile', 'config')

	def _start(self):

		distfile_path = os.path.join(
			self.config.options.distfiles, self.distfile)

		if self.config.options.recycle_dir is not None:
			distfile_path = os.path.join(self.config.options.distfiles, self.distfile)
			recycle_path = os.path.join(
				self.config.options.recycle_dir, self.distfile)
			if self.config.options.dry_run:
				logging.info(("dry-run: move '%s' from "
					"distfiles to recycle") % self.distfile)
			else:
				logging.debug(("move '%s' from "
					"distfiles to recycle") % self.distfile)
				try:
					os.rename(distfile_path, recycle_path)
				except OSError as e:
					if e.errno != errno.EXDEV:
						logging.error(("rename %s from distfiles to "
							"recycle failed: %s") % (self.distfile, e))
				else:
					self.returncode = os.EX_OK
					self._async_wait()
					return

				self._start_task(
					FileCopier(src_path=distfile_path,
						dest_path=recycle_path,
						background=False),
					self._recycle_copier_exit)
				return

		success = True

		if self.config.options.dry_run:
			logging.info(("dry-run: delete '%s' from "
				"distfiles") % self.distfile)
		else:
			logging.debug(("delete '%s' from "
				"distfiles") % self.distfile)
			try:
				os.unlink(distfile_path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					logging.error("%s unlink failed in distfiles: %s" %
						(self.distfile, e))
					success = False

		if success:
			self._success()
			self.returncode = os.EX_OK
		else:
			self.returncode = 1

		self._async_wait()

	def _recycle_copier_exit(self, copier):

		self._assert_current(copier)
		if self._was_cancelled():
			self.wait()
			return

		success = True
		if copier.returncode == os.EX_OK:

			try:
				os.unlink(copier.src_path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					logging.error("%s unlink failed in distfiles: %s" %
						(self.distfile, e))
					success = False

		else:
			logging.error(("%s copy from distfiles "
				"to recycle failed: %s") % (self.distfile, e))
			success = False

		if success:
			self._success()
			self.returncode = os.EX_OK
		else:
			self.returncode = 1

		self._current_task = None
		self.wait()

	def _success(self):

		cpv = "unknown"
		if self.config.distfiles_db is not None:
			cpv = self.config.distfiles_db.get(self.distfile, cpv)

		self.config.delete_count += 1
		self.config.log_success("%s\t%s\tremoved" % (cpv, self.distfile))

		if self.config.distfiles_db is not None:
			try:
				del self.config.distfiles_db[self.distfile]
			except KeyError:
				pass
			else:
				logging.debug(("drop '%s' from "
					"distfiles db") % self.distfile)

		if self.config.deletion_db is not None:
			try:
				del self.config.deletion_db[self.distfile]
			except KeyError:
				pass
			else:
				logging.debug(("drop '%s' from "
					"deletion db") % self.distfile)
