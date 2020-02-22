# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.AsynchronousLock import AsynchronousLock

import portage
from portage import os
from portage.exception import PortageException
from portage.util.futures.compat_coroutine import coroutine
from portage.util.SlotObject import SlotObject

class EbuildBuildDir(SlotObject):

	__slots__ = ("scheduler", "settings",
		"locked", "_catdir", "_lock_obj")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self.locked = False

	def _assert_lock(self, async_lock):
		if async_lock.returncode != os.EX_OK:
			# TODO: create a better way to propagate this error to the caller
			raise AssertionError("AsynchronousLock failed with returncode %s" \
				% (async_lock.returncode,))

	def clean_log(self):
		"""Discard existing log. The log will not be be discarded
		in cases when it would not make sense, like when FEATURES=keepwork
		is enabled."""
		settings = self.settings
		if 'keepwork' in settings.features:
			return
		log_file = settings.get('PORTAGE_LOG_FILE')
		if log_file is not None and os.path.isfile(log_file):
			try:
				os.unlink(log_file)
			except OSError:
				pass

	@coroutine
	def async_lock(self):
		"""
		Acquire the lock asynchronously. Notification is available
		via the add_done_callback method of the returned Future instance.

		This raises an AlreadyLocked exception if async_lock() is called
		while a lock is already held. In order to avoid this, call
		async_unlock() or check whether the "locked" attribute is True
		or False before calling async_lock().

		@returns: Future, result is None
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		dir_path = self.settings.get('PORTAGE_BUILDDIR')
		if not dir_path:
			raise AssertionError('PORTAGE_BUILDDIR is unset')
		catdir = os.path.dirname(dir_path)
		self._catdir = catdir

		try:
			portage.util.ensure_dirs(os.path.dirname(catdir),
				gid=portage.portage_gid,
				mode=0o70, mask=0)
		except PortageException:
			if not os.path.isdir(os.path.dirname(catdir)):
				raise

		catdir_lock = AsynchronousLock(path=catdir, scheduler=self.scheduler)
		yield catdir_lock.async_start()
		yield catdir_lock.async_wait()

		self._assert_lock(catdir_lock)

		try:
			portage.util.ensure_dirs(catdir,
				gid=portage.portage_gid,
				mode=0o70, mask=0)
		except PortageException:
			if not os.path.isdir(catdir):
				raise

		builddir_lock = AsynchronousLock(path=dir_path, scheduler=self.scheduler)
		yield builddir_lock.async_start()
		yield builddir_lock.async_wait()

		try:
			self._assert_lock(builddir_lock)
		except AssertionError:
			yield catdir_lock.async_unlock()
			raise

		self._lock_obj = builddir_lock
		self.locked = True
		self.settings['PORTAGE_BUILDDIR_LOCKED'] = '1'
		yield catdir_lock.async_unlock()

	@coroutine
	def async_unlock(self):
		"""
		Release the lock asynchronously. Release notification is available
		via the add_done_callback method of the returned Future instance.

		@returns: Future, result is None
		"""
		if self._lock_obj is not None:
			yield self._lock_obj.async_unlock()

			self._lock_obj = None
			self.locked = False
			self.settings.pop('PORTAGE_BUILDDIR_LOCKED', None)
			catdir_lock = AsynchronousLock(
				path=self._catdir, scheduler=self.scheduler)
			yield catdir_lock.async_start()
			yield catdir_lock.async_wait()
			if catdir_lock.returncode == os.EX_OK:
				try:
					os.rmdir(self._catdir)
				except OSError:
					pass
				yield catdir_lock.async_unlock()

	class AlreadyLocked(portage.exception.PortageException):
		pass

