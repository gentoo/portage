# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.util._ctypes import find_library, LoadLibrary
from portage.util._async.ForkProcess import ForkProcess

class SyncfsProcess(ForkProcess):
	"""
	Isolate ctypes usage in a subprocess, in order to avoid
	potential problems with stale cached libraries as
	described in bug #448858, comment #14 (also see
	https://bugs.python.org/issue14597).
	"""

	__slots__ = ('paths',)

	@staticmethod
	def _get_syncfs():

		filename = find_library("c")
		if filename is not None:
			library = LoadLibrary(filename)
			if library is not None:
				try:
					return library.syncfs
				except AttributeError:
					pass

		return None

	def _run(self):

		syncfs_failed = False
		syncfs = self._get_syncfs()

		if syncfs is not None:
			for path in self.paths:
				try:
					fd = os.open(path, os.O_RDONLY)
				except OSError:
					pass
				else:
					try:
						if syncfs(fd) != 0:
							# Happens with PyPy (bug #446610)
							syncfs_failed = True
					finally:
						os.close(fd)

		if syncfs is None or syncfs_failed:
			return 1
		return os.EX_OK
