# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

import os as _os
import sys
from portage.cache import template
from portage import os

from portage.proxy.lazyimport import lazyimport
lazyimport(globals(),
	'portage.exception:PortageException',
	'portage.util:apply_permissions',
)
del lazyimport

if sys.hexversion >= 0x3000000:
	long = int

class FsBased(template.database):
	"""template wrapping fs needed options, and providing _ensure_access as a way to 
	attempt to ensure files have the specified owners/perms"""

	def __init__(self, *args, **config):

		for x, y in (("gid", -1), ("perms", -1)):
			if x in config:
				setattr(self, "_"+x, config[x])
				del config[x]
			else:
				setattr(self, "_"+x, y)
		super(FsBased, self).__init__(*args, **config)

		if self.label.startswith(os.path.sep):
			# normpath.
			self.label = os.path.sep + os.path.normpath(self.label).lstrip(os.path.sep)


	def _ensure_access(self, path, mtime=-1):
		"""returns true or false if it's able to ensure that path is properly chmod'd and chowned.
		if mtime is specified, attempts to ensure that's correct also"""
		try:
			apply_permissions(path, gid=self._gid, mode=self._perms)
			if mtime != -1:
				mtime=long(mtime)
				os.utime(path, (mtime, mtime))
		except (PortageException, EnvironmentError):
			return False
		return True

	def _ensure_dirs(self, path=None):
		"""with path!=None, ensure beyond self.location.  otherwise, ensure self.location"""
		if path:
			path = os.path.dirname(path)
			base = self.location
		else:
			path = self.location
			base='/'

		for dir in path.lstrip(os.path.sep).rstrip(os.path.sep).split(os.path.sep):
			base = os.path.join(base,dir)
			if not os.path.exists(base):
				if self._perms != -1:
					um = os.umask(0)
				try:
					perms = self._perms
					if perms == -1:
						perms = 0
					perms |= 0o755
					os.mkdir(base, perms)
					if self._gid != -1:
						os.chown(base, -1, self._gid)
				finally:
					if self._perms != -1:
						os.umask(um)

	def _prune_empty_dirs(self):
		all_dirs = []
		for parent, dirs, files in os.walk(self.location):
			for x in dirs:
				all_dirs.append(_os.path.join(parent, x))
		while all_dirs:
			try:
				_os.rmdir(all_dirs.pop())
			except OSError:
				pass

def gen_label(base, label):
	"""if supplied label is a path, generate a unique label based upon label, and supplied base path"""
	if label.find(os.path.sep) == -1:
		return label
	label = label.strip("\"").strip("'")
	label = os.path.join(*(label.rstrip(os.path.sep).split(os.path.sep)))
	tail = os.path.split(label)[1]
	return "%s-%X" % (tail, abs(label.__hash__()))

