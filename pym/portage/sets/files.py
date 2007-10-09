# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

from portage.util import grabfile, write_atomic, ensure_dirs
from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
from portage.locks import lockfile, unlockfile
from portage import portage_gid
from portage.sets import PackageSet, EditablePackageSet, SetConfigError
from portage.env.loaders import ItemFileLoader, KeyListFileLoader
from portage.env.validators import ValidAtomValidator

__all__ = ["StaticFileSet", "ConfigFileSet", "WorldSet"]

class StaticFileSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	
	def __init__(self, filename):
		super(StaticFileSet, self).__init__()
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
				for fname in errors:
					for e in errors[fname]:
						self.errors.append(fname+": "+e)
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			self._setAtoms(data.keys())
			self._mtime = mtime
		
	def singleBuilder(self, options, settings, trees):
		if not "filename" in options:
			raise SetConfigError("no filename specified")
		return ConfigFileSet(options[filename])
	singleBuilder = classmethod(singleBuilder)
	
	def multiBuilder(self, options, settings, trees):
		rValue = {}
		directory = options.get("directory", os.path.join(settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH.lstrip(os.sep), "sets"))
		name_pattern = options.get("name_pattern", "sets/$name")
		if not "$name" in name_pattern and not "${name}" in name_pattern:
			raise SetConfigError("name_pattern doesn't include $name placeholder")
		if os.path.isdir(directory):
			for filename in os.listdir(directory):
				if filename.endswith(".metadata"):
					continue
				myname = name_pattern.replace("$name", filename)
				myname = myname.replace("${name}", filename)
				rValue[myname] = StaticFileSet(os.path.join(directory, filename))
		return rValue
	multiBuilder = classmethod(multiBuilder)
	
class ConfigFileSet(PackageSet):
	def __init__(self, filename):
		super(ConfigFileSet, self).__init__()
		self._filename = filename
		self.description = "Package set generated from %s" % self._filename
		self.loader = KeyListFileLoader(self._filename, ValidAtomValidator)

	def load(self):
		data, errors = self.loader.load()
		self._setAtoms(data.keys())
	
	def singleBuilder(self, options, settings, trees):
		if not "filename" in options:
			raise SetConfigError("no filename specified")
		return ConfigFileSet(options[filename])
	singleBuilder = classmethod(singleBuilder)
	
	def multiBuilder(self, options, settings, trees):
		rValue = {}
		directory = options.get("directory", os.path.join(settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH.lstrip(os.sep)))
		name_pattern = options.get("name_pattern", "sets/package_$suffix")
		if not "$suffix" in name_pattern and not "${suffix}" in name_pattern:
			raise SetConfigError("name_pattern doesn't include $suffix placeholder")
		for suffix in ["keywords", "use", "mask", "unmask"]:
			myname = name_pattern.replace("$suffix", suffix)
			myname = myname.replace("${suffix}", suffix)
			rValue[myname] = ConfigFileSet(os.path.join(directory, "package."+suffix))
		return rValue
	multiBuilder = classmethod(multiBuilder)

class WorldSet(StaticFileSet):
	description = "Set of packages that were directly installed by the user"
	
	def __init__(self, root):
		super(WorldSet, self).__init__(os.path.join(os.sep, root, PRIVATE_PATH.lstrip(os.sep), "world"))
		self._lock = None

	def _ensure_dirs(self):
		ensure_dirs(os.path.dirname(self._filename), gid=portage_gid, mode=02750, mask=02)

	def lock(self):
		self._ensure_dirs()
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		unlockfile(self._lock)
		self._lock = None

	def singleBuilder(self, options, settings, trees):
		return WorldSet(settings["ROOT"])
	singleBuilder = classmethod(singleBuilder)
