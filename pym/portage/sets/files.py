# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.util import grabfile_package, grabdict_package, write_atomic
import os

from portage.sets import PackageSet

class StaticFileSet(PackageSet):
	_operations = ["merge", "unmerge", "edit"]
	
	def __init__(self, name, filename):
		super(StaticFileSet, self).__init__(name)
		self._filename = filename
	
	def write(self):
		write_atomic(self._filename, "\n".join(self._atoms)+"\n")
	
	def load(self):
		mtime = os.stat(self._filename).st_mtime
		if not self._mtime or self._mtime != mtime:
			self._load()
			self._mtime = mtime
	
	def _load(self):
		self._setAtoms(grabfile_package(self._filename, recursive=True))
	
class ConfigFileSet(StaticFileSet):
	_operations = ["merge", "unmerge"]

	def write(self):
		raise NotImplementedError()
	
	def _load(self):
		self._setAtoms(grabdict_package(self._filename, recursive=True).keys())

