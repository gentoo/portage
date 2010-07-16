# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SlotObject import SlotObject
import portage
from portage import os
import errno

class EbuildBuildDir(SlotObject):

	__slots__ = ("dir_path", "pkg", "settings",
		"locked", "_catdir", "_lock_obj")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self.locked = False

	def lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		dir_path = self.dir_path
		if dir_path is None:
			root_config = self.pkg.root_config
			portdb = root_config.trees["porttree"].dbapi
			ebuild_path = portdb.findname(self.pkg.cpv)
			if ebuild_path is None:
				raise AssertionError(
					"ebuild not found for '%s'" % self.pkg.cpv)
			settings = self.settings
			settings.setcpv(self.pkg)
			debug = settings.get("PORTAGE_DEBUG") == "1"
			use_cache = 1 # always true
			portage.doebuild_environment(ebuild_path, "setup", root_config.root,
				self.settings, debug, use_cache, portdb)
			dir_path = self.settings["PORTAGE_BUILDDIR"]

		catdir = os.path.dirname(dir_path)
		self._catdir = catdir

		portage.util.ensure_dirs(os.path.dirname(catdir),
			gid=portage.portage_gid,
			mode=0o70, mask=0)
		catdir_lock = None
		try:
			catdir_lock = portage.locks.lockdir(catdir)
			portage.util.ensure_dirs(catdir,
				gid=portage.portage_gid,
				mode=0o70, mask=0)
			self._lock_obj = portage.locks.lockdir(dir_path)
		finally:
			self.locked = self._lock_obj is not None
			if catdir_lock is not None:
				portage.locks.unlockdir(catdir_lock)

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

	def unlock(self):
		if self._lock_obj is None:
			return

		portage.locks.unlockdir(self._lock_obj)
		self._lock_obj = None
		self.locked = False

		catdir = self._catdir
		catdir_lock = None
		try:
			catdir_lock = portage.locks.lockdir(catdir)
		finally:
			if catdir_lock:
				try:
					os.rmdir(catdir)
				except OSError as e:
					if e.errno not in (errno.ENOENT,
						errno.ENOTEMPTY, errno.EEXIST):
						raise
					del e
				portage.locks.unlockdir(catdir_lock)

	class AlreadyLocked(portage.exception.PortageException):
		pass

