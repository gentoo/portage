# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import re
from itertools import chain

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.util import grabfile, write_atomic, ensure_dirs, normalize_path
from portage.const import USER_CONFIG_PATH, VCS_DIRS, WORLD_FILE, WORLD_SETS_FILE
from portage.localization import _
from portage.locks import lockfile, unlockfile
from portage import portage_gid
from portage._sets.base import PackageSet, EditablePackageSet
from portage._sets import SetConfigError, SETPREFIX, get_boolean
from portage.env.loaders import ItemFileLoader, KeyListFileLoader
from portage.env.validators import ValidAtomValidator
from portage import cpv_getkey

__all__ = ["StaticFileSet", "ConfigFileSet", "WorldSelectedSet",
		"WorldSelectedPackagesSet", "WorldSelectedSetsSet"]

class StaticFileSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	_repopath_match = re.compile(r'.*\$\{repository:(?P<reponame>.+)\}.*')
	_repopath_sub = re.compile(r'\$\{repository:(?P<reponame>.+)\}')

	def __init__(self, filename, greedy=False, dbapi=None):
		super(StaticFileSet, self).__init__(allow_repo=True)
		self._filename = filename
		self._mtime = None
		self.description = "Package set loaded from file %s" % self._filename
		self.loader = ItemFileLoader(self._filename, self._validate)
		if greedy and not dbapi:
			self.errors.append(_("%s configured as greedy set, but no dbapi instance passed in constructor") % self._filename)
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
		return bool(atom[:1] == SETPREFIX or ValidAtomValidator(atom, allow_repo=True))

	def write(self):
		write_atomic(self._filename, "".join("%s\n" % (atom,) \
			for atom in sorted(chain(self._atoms, self._nonatoms))))

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
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			if self.greedy:
				atoms = []
				for a in data:
					matches = self.dbapi.match(a)
					for cpv in matches:
						pkg = self.dbapi._pkg_str(cpv, None)
						atoms.append("%s:%s" % (pkg.cp, pkg.slot))
					# In addition to any installed slots, also try to pull
					# in the latest new slot that may be available.
					atoms.append(a)
			else:
				atoms = iter(data)
			self._setAtoms(atoms)
			self._mtime = mtime

	def singleBuilder(self, options, settings, trees):
		if not "filename" in options:
			raise SetConfigError(_("no filename specified"))
		greedy = get_boolean(options, "greedy", False)
		filename = options["filename"]
		# look for repository path variables
		match = self._repopath_match.match(filename)
		if match:
			try:
				filename = self._repopath_sub.sub(trees["porttree"].dbapi.treemap[match.groupdict()["reponame"]], filename)
			except KeyError:
				raise SetConfigError(_("Could not find repository '%s'") % match.groupdict()["reponame"])
		return StaticFileSet(filename, greedy=greedy, dbapi=trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)

	def multiBuilder(self, options, settings, trees):
		rValue = {}
		directory = options.get("directory",
			os.path.join(settings["PORTAGE_CONFIGROOT"],
			USER_CONFIG_PATH, "sets"))
		name_pattern = options.get("name_pattern", "${name}")
		if not "$name" in name_pattern and not "${name}" in name_pattern:
			raise SetConfigError(_("name_pattern doesn't include ${name} placeholder"))
		greedy = get_boolean(options, "greedy", False)
		# look for repository path variables
		match = self._repopath_match.match(directory)
		if match:
			try:
				directory = self._repopath_sub.sub(trees["porttree"].dbapi.treemap[match.groupdict()["reponame"]], directory)
			except KeyError:
				raise SetConfigError(_("Could not find repository '%s'") % match.groupdict()["reponame"])

		try:
			directory = _unicode_decode(directory,
				encoding=_encodings['fs'], errors='strict')
			# Now verify that we can also encode it.
			_unicode_encode(directory,
				encoding=_encodings['fs'], errors='strict')
		except UnicodeError:
			directory = _unicode_decode(directory,
				encoding=_encodings['fs'], errors='replace')
			raise SetConfigError(
				_("Directory path contains invalid character(s) for encoding '%s': '%s'") \
				% (_encodings['fs'], directory))

		vcs_dirs = [_unicode_encode(x, encoding=_encodings['fs']) for x in VCS_DIRS]
		if os.path.isdir(directory):
			directory = normalize_path(directory)

			for parent, dirs, files in os.walk(directory):
				try:
					parent = _unicode_decode(parent,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				for d in dirs[:]:
					if d in vcs_dirs or d.startswith(b".") or d.endswith(b"~"):
						dirs.remove(d)
				for filename in files:
					try:
						filename = _unicode_decode(filename,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeDecodeError:
						continue
					if filename.startswith(".") or filename.endswith("~"):
						continue
					if filename.endswith(".metadata"):
						continue
					filename = os.path.join(parent,
						filename)[1 + len(directory):]
					myname = name_pattern.replace("$name", filename)
					myname = myname.replace("${name}", filename)
					rValue[myname] = StaticFileSet(
						os.path.join(directory, filename),
						greedy=greedy, dbapi=trees["vartree"].dbapi)
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
		self._setAtoms(iter(data))

	def singleBuilder(self, options, settings, trees):
		if not "filename" in options:
			raise SetConfigError(_("no filename specified"))
		return ConfigFileSet(options["filename"])
	singleBuilder = classmethod(singleBuilder)

	def multiBuilder(self, options, settings, trees):
		rValue = {}
		directory = options.get("directory",
			os.path.join(settings["PORTAGE_CONFIGROOT"], USER_CONFIG_PATH))
		name_pattern = options.get("name_pattern", "sets/package_$suffix")
		if not "$suffix" in name_pattern and not "${suffix}" in name_pattern:
			raise SetConfigError(_("name_pattern doesn't include $suffix placeholder"))
		for suffix in ["keywords", "use", "mask", "unmask"]:
			myname = name_pattern.replace("$suffix", suffix)
			myname = myname.replace("${suffix}", suffix)
			rValue[myname] = ConfigFileSet(os.path.join(directory, "package."+suffix))
		return rValue
	multiBuilder = classmethod(multiBuilder)

class WorldSelectedSet(EditablePackageSet):
	description = "Set of packages and subsets that were directly installed by the user"

	def __init__(self, eroot):
		super(WorldSelectedSet, self).__init__(allow_repo=True)
		self._pkgset = WorldSelectedPackagesSet(eroot)
		self._setset = WorldSelectedSetsSet(eroot)

	def write(self):
		self._pkgset._atoms = self._atoms.copy()
		self._pkgset.write()
		self._setset._nonatoms = self._nonatoms.copy()
		self._setset.write()

	def load(self):
		# Iterating over these sets does not force them to load if they
		# have been loaded previously.
		self._pkgset.load()
		self._setset.load()
		self._setAtoms(chain(self._pkgset, self._setset))

	def lock(self):
		self._pkgset.lock()
		self._setset.lock()

	def unlock(self):
		self._pkgset.unlock()
		self._setset.unlock()

	def cleanPackage(self, vardb, cpv):
		self._pkgset.cleanPackage(vardb, cpv)

	def singleBuilder(self, options, settings, trees):
		return WorldSelectedSet(settings["EROOT"])
	singleBuilder = classmethod(singleBuilder)

class WorldSelectedPackagesSet(EditablePackageSet):
	description = "Set of packages that were directly installed by the user"

	def __init__(self, eroot):
		super(WorldSelectedPackagesSet, self).__init__(allow_repo=True)
		self._lock = None
		self._filename = os.path.join(eroot, WORLD_FILE)
		self.loader = ItemFileLoader(self._filename, self._validate)
		self._mtime = None

	def _validate(self, atom):
		return ValidAtomValidator(atom, allow_repo=True)

	def write(self):
		write_atomic(self._filename,
			"".join(sorted("%s\n" % x for x in self._atoms)))

	def load(self):
		atoms = []
		atoms_changed = False
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
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			atoms = list(data)
			self._mtime = mtime
			atoms_changed = True
		else:
			atoms.extend(self._atoms)

		if atoms_changed:
			self._setAtoms(atoms)

	def _ensure_dirs(self):
		ensure_dirs(os.path.dirname(self._filename), gid=portage_gid, mode=0o2750, mask=0o2)

	def lock(self):
		if self._lock is not None:
			raise AssertionError("already locked")
		self._ensure_dirs()
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		if self._lock is None:
			raise AssertionError("not locked")
		unlockfile(self._lock)
		self._lock = None

	def cleanPackage(self, vardb, cpv):
		'''
		Before calling this function you should call lock and load.
		After calling this function you should call unlock.
		'''
		if not self._lock:
			raise AssertionError('cleanPackage needs the set to be locked')

		worldlist = list(self._atoms)
		mykey = cpv_getkey(cpv)
		newworldlist = []
		for x in worldlist:
			if x.cp == mykey:
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

	def singleBuilder(self, options, settings, trees):
		return WorldSelectedPackagesSet(settings["EROOT"])
	singleBuilder = classmethod(singleBuilder)

class WorldSelectedSetsSet(EditablePackageSet):
	description = "Set of sets that were directly installed by the user"

	def __init__(self, eroot):
		super(WorldSelectedSetsSet, self).__init__(allow_repo=True)
		self._lock = None
		self._filename = os.path.join(eroot, WORLD_SETS_FILE)
		self.loader = ItemFileLoader(self._filename, self._validate)
		self._mtime = None

	def _validate(self, setname):
		return setname.startswith(SETPREFIX)

	def write(self):
		write_atomic(self._filename,
			"".join(sorted("%s\n" % x for x in self._nonatoms)))

	def load(self):
		atoms_changed = False
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
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			nonatoms = list(data)
			self._mtime = mtime
			atoms_changed = True
		else:
			nonatoms = list(self._nonatoms)

		if atoms_changed:
			self._setAtoms(nonatoms)

	def lock(self):
		if self._lock is not None:
			raise AssertionError("already locked")
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		if self._lock is None:
			raise AssertionError("not locked")
		unlockfile(self._lock)
		self._lock = None

	def singleBuilder(self, options, settings, trees):
		return WorldSelectedSetsSet(settings["EROOT"])
	singleBuilder = classmethod(singleBuilder)
