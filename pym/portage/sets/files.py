# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

from portage.util import grabfile, write_atomic, ensure_dirs
from portage.const import PRIVATE_PATH
from portage.locks import lockfile, unlockfile
from portage import portage_gid
from portage.sets import PackageSet, EditablePackageSet
from portage.env.loaders import ItemFileLoader, KeyListFileLoader
from portage.env.validators import ValidAtomValidator

class StaticFileSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	
	def __init__(self, name, filename):
		super(StaticFileSet, self).__init__(name)
		self._filename = filename
		self._mtime = None
		self.description = "Package set loaded from file %s" % self._filename
		self.loader = ItemFileLoader(self._filename, ValidAtomValidator)

		metadata = grabfile(self._filename + ".metadata")
		key = None
		value = []
		for line in metadata:
			line = line.strip()
			if len(line) == 0 and key != None:
				setattr(self, key, " ".join(value))
				key = None
			elif line[-1] == ":" and key == None:
				key = line[:-1].lower()
				value = []
			elif key != None:
				value.append(line)
			else:
				pass
		else:
			if key != None:
				setattr(self, key, " ".join(value))
	
	def write(self):
		write_atomic(self._filename, "\n".join(sorted(self._atoms))+"\n")
	
	def load(self):
		try:
			mtime = os.stat(self._filename).st_mtime
		except (OSError, IOError):
			mtime = None
		if (not self._loaded or self._mtime != mtime):
			try:
				data, errors = self.loader.load()
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
			self._setAtoms(data.keys())
			self._mtime = mtime
	
class ConfigFileSet(PackageSet):
	def __init__(self, name, filename):
		super(ConfigFileSet, self).__init__(name)
		self._filename = filename
		self.description = "Package set generated from %s" % self._filename
		self.loader = KeyListFileLoader(self._filename, ValidAtomValidator)

	def load(self):
		data, errors = self.loader.load()
		self._setAtoms(data.keys())

class WorldSet(StaticFileSet):
	description = "Set of packages that were directly installed by the user"
	
	def __init__(self, name, root):
		super(WorldSet, self).__init__(name, os.path.join(os.sep, root, PRIVATE_PATH, "world"))
		self._lock = None

	def _ensure_dirs(self):
		ensure_dirs(os.path.dirname(self._filename), gid=portage_gid, mode=02750, mask=02)

	def lock(self):
		self._ensure_dirs()
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		unlockfile(self._lock)
		self._lock = None
