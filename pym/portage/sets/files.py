# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.util import grabfile, grabfile_package, grabdict_package, write_atomic
import os

from portage.sets import PackageSet, EditablePackageSet

class StaticFileSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	
	def __init__(self, name, filename):
		super(StaticFileSet, self).__init__(name)
		self._filename = filename
		self._mtime = None
		self.description = "Package set loaded from file %s" % self._filename
		metadata = grabfile(self._filename + ".metadata")
		key = None
		for line in metadata:
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
	
	def write(self):
		write_atomic(self._filename, "\n".join(self._atoms)+"\n")
	
	def load(self):
		try:
			mtime = os.stat(self._filename).st_mtime
		except (OSError, IOError):
			mtime = None
		if not self._loaded or self._mtime != mtime:
			self._setAtoms(grabfile_package(self._filename, recursive=True))
			self._mtime = mtime
	
class ConfigFileSet(PackageSet):
	def __init__(self, name, filename):
		super(ConfigFileSet, self).__init__(name)
		self._filename = filename
		self.description = "Package set generated from %s" % self._filename

	def load(self):
		self._setAtoms(grabdict_package(self._filename, recursive=True).keys())

