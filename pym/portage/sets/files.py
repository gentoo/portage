# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
import re
from itertools import chain

from portage.util import grabfile, write_atomic, ensure_dirs
from portage.const import PRIVATE_PATH, USER_CONFIG_PATH, EPREFIX_LSTRIP
from portage.locks import lockfile, unlockfile
from portage import portage_gid
from portage.sets.base import PackageSet, EditablePackageSet
from portage.sets import SetConfigError, SETPREFIX, get_boolean
from portage.env.loaders import ItemFileLoader, KeyListFileLoader
from portage.env.validators import ValidAtomValidator
from portage import dep_getkey, cpv_getkey

__all__ = ["StaticFileSet", "ConfigFileSet", "WorldSet"]

class StaticFileSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	_repopath_match = re.compile(r'.*\$\{repository:(?P<reponame>.+)\}.*')
	_repopath_sub = re.compile(r'\$\{repository:(?P<reponame>.+)\}')
		
	def __init__(self, filename, greedy=False, dbapi=None):
		super(StaticFileSet, self).__init__()
		self._filename = filename
		self._mtime = None
		self.description = "Package set loaded from file %s" % self._filename
		self.loader = ItemFileLoader(self._filename, self._validate)
		if greedy and not dbapi:
			self.errors.append("%s configured as greedy set, but no dbapi instance passed in constructor" % self._filename)
			greedy = False
		self.greedy = greedy
		self.dbapi = dbapi

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

	def _validate(self, atom):
		return ValidAtomValidator(atom)

	def write(self):
		write_atomic(self._filename, "\n".join(sorted(
			chain(self._atoms, self._nonatoms)))+"\n")
	
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
			if self.greedy:
				atoms = []
				for a in data.keys():
					matches = self.dbapi.match(a)
					for cpv in matches:
						atoms.append("%s:%s" % (cpv_getkey(cpv),
							self.dbapi.aux_get(cpv, ["SLOT"])[0]))
					# In addition to any installed slots, also try to pull
					# in the latest new slot that may be available.
					atoms.append(a)
			else:
				atoms = data.keys()
			self._setAtoms(atoms)
			self._mtime = mtime
		
	def singleBuilder(self, options, settings, trees):
		if not "filename" in options:
			raise SetConfigError("no filename specified")
		greedy = get_boolean(options, "greedy", False)
		filename = options["filename"]
		# look for repository path variables
		match = self._repopath_match.match(filename)
		if match:
			try:
				filename = self._repopath_sub.sub(trees["porttree"].dbapi.treemap[match.groupdict()["reponame"]], filename)
			except KeyError:
				raise SetConfigError("Could not find repository '%s'" % match.groupdict()["reponame"])
		return StaticFileSet(filename, greedy=greedy, dbapi=trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)
	
	def multiBuilder(self, options, settings, trees):
		rValue = {}
		directory = options.get("directory", os.path.join(settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH.lstrip(os.sep), "sets"))
		name_pattern = options.get("name_pattern", "${name}")
		if not "$name" in name_pattern and not "${name}" in name_pattern:
			raise SetConfigError("name_pattern doesn't include ${name} placeholder")
		greedy = get_boolean(options, "greedy", False)
		# look for repository path variables
		match = self._repopath_match.match(directory)
		if match:
			try:
				directory = self._repopath_sub.sub(trees["porttree"].dbapi.treemap[match.groupdict()["reponame"]], directory)
			except KeyError:
				raise SetConfigError("Could not find repository '%s'" % match.groupdict()["reponame"])
		if os.path.isdir(directory):
			for filename in os.listdir(directory):
				if filename.endswith(".metadata"):
					continue
				myname = name_pattern.replace("$name", filename)
				myname = myname.replace("${name}", filename)
				rValue[myname] = StaticFileSet(os.path.join(directory, filename), greedy=greedy, dbapi=trees["vartree"].dbapi)
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
		return ConfigFileSet(options["filename"])
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

class WorldSet(EditablePackageSet):
	description = "Set of packages that were directly installed by the user"
	
	def __init__(self, root):
		super(WorldSet, self).__init__()
		# most attributes exist twice as atoms and non-atoms are stored in 
		# separate files
		self._lock = None
		self._filename = os.path.join(os.sep, root, EPREFIX_LSTRIP, PRIVATE_PATH.lstrip(os.sep), "world")
		self.loader = ItemFileLoader(self._filename, self._validate)
		self._mtime = None
		
		self._filename2 = os.path.join(os.sep, root, EPREFIX_LSTRIP,  PRIVATE_PATH.lstrip(os.sep), "world_sets")
		self.loader2 = ItemFileLoader(self._filename2, self._validate2)
		self._mtime2 = None
		
	def _validate(self, atom):
		return ValidAtomValidator(atom)

	def _validate2(self, setname):
		return setname.startswith(SETPREFIX)

	def write(self):
		write_atomic(self._filename,
			"".join(sorted("%s\n" % x for x in self._atoms)))
		write_atomic(self._filename2, "\n".join(sorted(self._nonatoms))+"\n")
	
	def load(self):
		atoms = []
		nonatoms = []
		atoms_changed = False
		# load atoms and non-atoms from different files so the worldfile is 
		# backwards-compatible with older versions and other PMs, even though 
		# it's supposed to be private state data :/
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
			atoms = data.keys()
			self._mtime = mtime
			atoms_changed = True
		else:
			atoms.extend(self._atoms)
		try:
			mtime = os.stat(self._filename2).st_mtime
		except (OSError, IOError):
			mtime = None
		if (not self._loaded or self._mtime2 != mtime):
			try:
				data, errors = self.loader2.load()
				for fname in errors:
					for e in errors[fname]:
						self.errors.append(fname+": "+e)
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			nonatoms = data.keys()
			self._mtime2 = mtime
			atoms_changed = True
		else:
			nonatoms.extend(self._nonatoms)
		if atoms_changed:
			self._setAtoms(atoms+nonatoms)
		
	def _ensure_dirs(self):
		ensure_dirs(os.path.dirname(self._filename), gid=portage_gid, mode=02750, mask=02)

	def lock(self):
		self._ensure_dirs()
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		unlockfile(self._lock)
		self._lock = None

	def cleanPackage(self, vardb, cpv):
		self.lock()
		self._load() # loads latest from disk
		worldlist = list(self._atoms)
		mykey = cpv_getkey(cpv)
		newworldlist = []
		for x in worldlist:
			if dep_getkey(x) == mykey:
				matches = vardb.match(x, use_cache=0)
				if not matches:
					#zap our world entry
					pass
				elif len(matches) == 1 and matches[0] == cpv:
					#zap our world entry
					pass
				else:
					#others are around; keep it.
					newworldlist.append(x)
			else:
				#this doesn't match the package we're unmerging; keep it.
				newworldlist.append(x)

		newworldlist.extend(self._nonatoms)
		self.replace(newworldlist)
		self.unlock()

	def singleBuilder(self, options, settings, trees):
		return WorldSet(settings["ROOT"])
	singleBuilder = classmethod(singleBuilder)
