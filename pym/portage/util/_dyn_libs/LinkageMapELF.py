# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import logging
import subprocess

import portage
from portage import _encodings
from portage import _os_merge
from portage import _unicode_decode
from portage import _unicode_encode
from portage.cache.mappings import slot_dict_class
from portage.exception import CommandNotFound
from portage.localization import _
from portage.util import getlibpaths
from portage.util import grabfile
from portage.util import normalize_path
from portage.util import writemsg_level

class LinkageMapELF(object):

	"""Models dynamic linker dependencies."""

	_needed_aux_key = "NEEDED.ELF.2"
	_soname_map_class = slot_dict_class(
		("consumers", "providers"), prefix="")

	def __init__(self, vardbapi):
		self._dbapi = vardbapi
		self._root = self._dbapi.settings['ROOT']
		self._libs = {}
		self._obj_properties = {}
		self._obj_key_cache = {}
		self._defpath = set()
		self._path_key_cache = {}

	def _clear_cache(self):
		self._libs.clear()
		self._obj_properties.clear()
		self._obj_key_cache.clear()
		self._defpath.clear()
		self._path_key_cache.clear()

	def _path_key(self, path):
		key = self._path_key_cache.get(path)
		if key is None:
			key = self._ObjectKey(path, self._root)
			self._path_key_cache[path] = key
		return key

	def _obj_key(self, path):
		key = self._obj_key_cache.get(path)
		if key is None:
			key = self._ObjectKey(path, self._root)
			self._obj_key_cache[path] = key
		return key

	class _ObjectKey(object):

		"""Helper class used as _obj_properties keys for objects."""

		__slots__ = ("_key",)

		def __init__(self, obj, root):
			"""
			This takes a path to an object.

			@param object: path to a file
			@type object: string (example: '/usr/bin/bar')

			"""
			self._key = self._generate_object_key(obj, root)

		def __hash__(self):
			return hash(self._key)

		def __eq__(self, other):
			return self._key == other._key

		def _generate_object_key(self, obj, root):
			"""
			Generate object key for a given object.

			@param object: path to a file
			@type object: string (example: '/usr/bin/bar')
			@rtype: 2-tuple of types (long, int) if object exists. string if
				object does not exist.
			@return:
				1. 2-tuple of object's inode and device from a stat call, if object
					exists.
				2. realpath of object if object does not exist.

			"""

			os = _os_merge

			try:
				_unicode_encode(obj,
					encoding=_encodings['merge'], errors='strict')
			except UnicodeEncodeError:
				# The package appears to have been merged with a 
				# different value of sys.getfilesystemencoding(),
				# so fall back to utf_8 if appropriate.
				try:
					_unicode_encode(obj,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeEncodeError:
					pass
				else:
					os = portage.os

			abs_path = os.path.join(root, obj.lstrip(os.sep))
			try:
				object_stat = os.stat(abs_path)
			except OSError:
				# Use the realpath as the key if the file does not exists on the
				# filesystem.
				return os.path.realpath(abs_path)
			# Return a tuple of the device and inode.
			return (object_stat.st_dev, object_stat.st_ino)

		def file_exists(self):
			"""
			Determine if the file for this key exists on the filesystem.

			@rtype: Boolean
			@return:
				1. True if the file exists.
				2. False if the file does not exist or is a broken symlink.

			"""
			return isinstance(self._key, tuple)

	class _LibGraphNode(_ObjectKey):
		__slots__ = ("alt_paths",)

		def __init__(self, key):
			"""
			Create a _LibGraphNode from an existing _ObjectKey.
			This re-uses the _key attribute in order to avoid repeating
			any previous stat calls, which helps to avoid potential race
			conditions due to inconsistent stat results when the
			file system is being modified concurrently.
			"""
			self._key = key._key
			self.alt_paths = set()

		def __str__(self):
			return str(sorted(self.alt_paths))

	def rebuild(self, exclude_pkgs=None, include_file=None,
		preserve_paths=None):
		"""
		Raises CommandNotFound if there are preserved libs
		and the scanelf binary is not available.

		@param exclude_pkgs: A set of packages that should be excluded from
			the LinkageMap, since they are being unmerged and their NEEDED
			entries are therefore irrelevant and would only serve to corrupt
			the LinkageMap.
		@type exclude_pkgs: set
		@param include_file: The path of a file containing NEEDED entries for
			a package which does not exist in the vardbapi yet because it is
			currently being merged.
		@type include_file: String
		@param preserve_paths: Libraries preserved by a package instance that
			is currently being merged. They need to be explicitly passed to the
			LinkageMap, since they are not registered in the
			PreservedLibsRegistry yet.
		@type preserve_paths: set
		"""

		os = _os_merge
		root = self._root
		root_len = len(root) - 1
		self._clear_cache()
		self._defpath.update(getlibpaths(self._root, env=self._dbapi.settings))
		libs = self._libs
		obj_properties = self._obj_properties

		lines = []

		# Data from include_file is processed first so that it
		# overrides any data from previously installed files.
		if include_file is not None:
			for line in grabfile(include_file):
				lines.append((include_file, line))

		aux_keys = [self._needed_aux_key]
		can_lock = os.access(os.path.dirname(self._dbapi._dbroot), os.W_OK)
		if can_lock:
			self._dbapi.lock()
		try:
			for cpv in self._dbapi.cpv_all():
				if exclude_pkgs is not None and cpv in exclude_pkgs:
					continue
				needed_file = self._dbapi.getpath(cpv,
					filename=self._needed_aux_key)
				for line in self._dbapi.aux_get(cpv, aux_keys)[0].splitlines():
					lines.append((needed_file, line))
		finally:
			if can_lock:
				self._dbapi.unlock()

		# have to call scanelf for preserved libs here as they aren't 
		# registered in NEEDED.ELF.2 files
		plibs = set()
		if preserve_paths is not None:
			plibs.update(preserve_paths)
		if self._dbapi._plib_registry and \
			self._dbapi._plib_registry.hasEntries():
			for cpv, items in \
				self._dbapi._plib_registry.getPreservedLibs().items():
				if exclude_pkgs is not None and cpv in exclude_pkgs:
					# These preserved libs will either be unmerged,
					# rendering them irrelevant, or they will be
					# preserved in the replacement package and are
					# already represented via the preserve_paths
					# parameter.
					continue
				plibs.update(items)
		if plibs:
			args = ["/usr/bin/scanelf", "-qF", "%a;%F;%S;%r;%n"]
			args.extend(os.path.join(root, x.lstrip("." + os.sep)) \
				for x in plibs)
			try:
				proc = subprocess.Popen(args, stdout=subprocess.PIPE)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				raise CommandNotFound(args[0])
			else:
				for l in proc.stdout:
					try:
						l = _unicode_decode(l,
							encoding=_encodings['content'], errors='strict')
					except UnicodeDecodeError:
						l = _unicode_decode(l,
							encoding=_encodings['content'], errors='replace')
						writemsg_level(_("\nError decoding characters " \
							"returned from scanelf: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
					l = l[3:].rstrip("\n")
					if not l:
						continue
					fields = l.split(";")
					if len(fields) < 5:
						writemsg_level(_("\nWrong number of fields " \
							"returned from scanelf: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
						continue
					fields[1] = fields[1][root_len:]
					plibs.discard(fields[1])
					lines.append(("scanelf", ";".join(fields)))
				proc.wait()

		if plibs:
			# Preserved libraries that did not appear in the scanelf output.
			# This is known to happen with statically linked libraries.
			# Generate dummy lines for these, so we can assume that every
			# preserved library has an entry in self._obj_properties. This
			# is important in order to prevent findConsumers from raising
			# an unwanted KeyError.
			for x in plibs:
				lines.append(("plibs", ";".join(['', x, '', '', ''])))

		for location, l in lines:
			l = l.rstrip("\n")
			if not l:
				continue
			fields = l.split(";")
			if len(fields) < 5:
				writemsg_level(_("\nWrong number of fields " \
					"in %s: %s\n\n") % (location, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			soname = fields[2]
			path = set([normalize_path(x) \
				for x in filter(None, fields[3].replace(
				"${ORIGIN}", os.path.dirname(obj)).replace(
				"$ORIGIN", os.path.dirname(obj)).split(":"))])
			needed = [x for x in fields[4].split(",") if x]

			obj_key = self._obj_key(obj)
			indexed = True
			myprops = obj_properties.get(obj_key)
			if myprops is None:
				indexed = False
				myprops = (arch, needed, path, soname, set())
				obj_properties[obj_key] = myprops
			# All object paths are added into the obj_properties tuple.
			myprops[4].add(obj)

			# Don't index the same file more that once since only one
			# set of data can be correct and therefore mixing data
			# may corrupt the index (include_file overrides previously
			# installed).
			if indexed:
				continue

			arch_map = libs.get(arch)
			if arch_map is None:
				arch_map = {}
				libs[arch] = arch_map
			if soname:
				soname_map = arch_map.get(soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=set(), consumers=set())
					arch_map[soname] = soname_map
				soname_map.providers.add(obj_key)
			for needed_soname in needed:
				soname_map = arch_map.get(needed_soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=set(), consumers=set())
					arch_map[needed_soname] = soname_map
				soname_map.consumers.add(obj_key)

	def listBrokenBinaries(self, debug=False):
		"""
		Find binaries and their needed sonames, which have no providers.

		@param debug: Boolean to enable debug output
		@type debug: Boolean
		@rtype: dict (example: {'/usr/bin/foo': set(['libbar.so'])})
		@return: The return value is an object -> set-of-sonames mapping, where
			object is a broken binary and the set consists of sonames needed by
			object that have no corresponding libraries to fulfill the dependency.

		"""

		os = _os_merge

		class _LibraryCache(object):

			"""
			Caches properties associated with paths.

			The purpose of this class is to prevent multiple instances of
			_ObjectKey for the same paths.

			"""

			def __init__(cache_self):
				cache_self.cache = {}

			def get(cache_self, obj):
				"""
				Caches and returns properties associated with an object.

				@param obj: absolute path (can be symlink)
				@type obj: string (example: '/usr/lib/libfoo.so')
				@rtype: 4-tuple with types
					(string or None, string or None, 2-tuple, Boolean)
				@return: 4-tuple with the following components:
					1. arch as a string or None if it does not exist,
					2. soname as a string or None if it does not exist,
					3. obj_key as 2-tuple,
					4. Boolean representing whether the object exists.
					(example: ('libfoo.so.1', (123L, 456L), True))

				"""
				if obj in cache_self.cache:
					return cache_self.cache[obj]
				else:
					obj_key = self._obj_key(obj)
					# Check that the library exists on the filesystem.
					if obj_key.file_exists():
						# Get the arch and soname from LinkageMap._obj_properties if
						# it exists. Otherwise, None.
						arch, _needed, _path, soname, _objs = \
								self._obj_properties.get(obj_key, (None,)*5)
						return cache_self.cache.setdefault(obj, \
								(arch, soname, obj_key, True))
					else:
						return cache_self.cache.setdefault(obj, \
								(None, None, obj_key, False))

		rValue = {}
		cache = _LibraryCache()
		providers = self.listProviders()

		# Iterate over all obj_keys and their providers.
		for obj_key, sonames in providers.items():
			arch, _needed, path, _soname, objs = self._obj_properties[obj_key]
			path = path.union(self._defpath)
			# Iterate over each needed soname and the set of library paths that
			# fulfill the soname to determine if the dependency is broken.
			for soname, libraries in sonames.items():
				# validLibraries is used to store libraries, which satisfy soname,
				# so if no valid libraries are found, the soname is not satisfied
				# for obj_key.  If unsatisfied, objects associated with obj_key
				# must be emerged.
				validLibraries = set()
				# It could be the case that the library to satisfy the soname is
				# not in the obj's runpath, but a symlink to the library is (eg
				# libnvidia-tls.so.1 in nvidia-drivers).  Also, since LinkageMap
				# does not catalog symlinks, broken or missing symlinks may go
				# unnoticed.  As a result of these cases, check that a file with
				# the same name as the soname exists in obj's runpath.
				# XXX If we catalog symlinks in LinkageMap, this could be improved.
				for directory in path:
					cachedArch, cachedSoname, cachedKey, cachedExists = \
							cache.get(os.path.join(directory, soname))
					# Check that this library provides the needed soname.  Doing
					# this, however, will cause consumers of libraries missing
					# sonames to be unnecessarily emerged. (eg libmix.so)
					if cachedSoname == soname and cachedArch == arch:
						validLibraries.add(cachedKey)
						if debug and cachedKey not in \
								set(map(self._obj_key_cache.get, libraries)):
							# XXX This is most often due to soname symlinks not in
							# a library's directory.  We could catalog symlinks in
							# LinkageMap to avoid checking for this edge case here.
							writemsg_level(
								_("Found provider outside of findProviders:") + \
								(" %s -> %s %s\n" % (os.path.join(directory, soname),
								self._obj_properties[cachedKey][4], libraries)),
								level=logging.DEBUG,
								noiselevel=-1)
						# A valid library has been found, so there is no need to
						# continue.
						break
					if debug and cachedArch == arch and \
							cachedKey in self._obj_properties:
						writemsg_level((_("Broken symlink or missing/bad soname: " + \
							"%(dir_soname)s -> %(cachedKey)s " + \
							"with soname %(cachedSoname)s but expecting %(soname)s") % \
							{"dir_soname":os.path.join(directory, soname),
							"cachedKey": self._obj_properties[cachedKey],
							"cachedSoname": cachedSoname, "soname":soname}) + "\n",
							level=logging.DEBUG,
							noiselevel=-1)
				# This conditional checks if there are no libraries to satisfy the
				# soname (empty set).
				if not validLibraries:
					for obj in objs:
						rValue.setdefault(obj, set()).add(soname)
					# If no valid libraries have been found by this point, then
					# there are no files named with the soname within obj's runpath,
					# but if there are libraries (from the providers mapping), it is
					# likely that soname symlinks or the actual libraries are
					# missing or broken.  Thus those libraries are added to rValue
					# in order to emerge corrupt library packages.
					for lib in libraries:
						rValue.setdefault(lib, set()).add(soname)
						if debug:
							if not os.path.isfile(lib):
								writemsg_level(_("Missing library:") + " %s\n" % (lib,),
									level=logging.DEBUG,
									noiselevel=-1)
							else:
								writemsg_level(_("Possibly missing symlink:") + \
									"%s\n" % (os.path.join(os.path.dirname(lib), soname)),
									level=logging.DEBUG,
									noiselevel=-1)
		return rValue

	def listProviders(self):
		"""
		Find the providers for all object keys in LinkageMap.

		@rtype: dict (example:
			{(123L, 456L): {'libbar.so': set(['/lib/libbar.so.1.5'])}})
		@return: The return value is an object key -> providers mapping, where
			providers is a mapping of soname -> set-of-library-paths returned
			from the findProviders method.

		"""
		rValue = {}
		if not self._libs:
			self.rebuild()
		# Iterate over all object keys within LinkageMap.
		for obj_key in self._obj_properties:
			rValue.setdefault(obj_key, self.findProviders(obj_key))
		return rValue

	def isMasterLink(self, obj):
		"""
		Determine whether an object is a master link.

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/foo')
		@rtype: Boolean
		@return:
			1. True if obj is a master link
			2. False if obj is not a master link

		"""
		os = _os_merge
		basename = os.path.basename(obj)
		obj_key = self._obj_key(obj)
		if obj_key not in self._obj_properties:
			raise KeyError("%s (%s) not in object list" % (obj_key, obj))
		soname = self._obj_properties[obj_key][3]
		return (len(basename) < len(soname))

	def listLibraryObjects(self):
		"""
		Return a list of library objects.

		Known limitation: library objects lacking an soname are not included.

		@rtype: list of strings
		@return: list of paths to all providers

		"""
		rValue = []
		if not self._libs:
			self.rebuild()
		for arch_map in self._libs.values():
			for soname_map in arch_map.values():
				for obj_key in soname_map.providers:
					rValue.extend(self._obj_properties[obj_key][4])
		return rValue

	def getSoname(self, obj):
		"""
		Return the soname associated with an object.

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/bar')
		@rtype: string
		@return: soname as a string

		"""
		if not self._libs:
			self.rebuild()
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			return self._obj_properties[obj_key][3]
		if obj not in self._obj_key_cache:
			raise KeyError("%s not in object list" % obj)
		return self._obj_properties[self._obj_key_cache[obj]][3]

	def findProviders(self, obj):
		"""
		Find providers for an object or object key.

		This method may be called with a key from _obj_properties.

		In some cases, not all valid libraries are returned.  This may occur when
		an soname symlink referencing a library is in an object's runpath while
		the actual library is not.  We should consider cataloging symlinks within
		LinkageMap as this would avoid those cases and would be a better model of
		library dependencies (since the dynamic linker actually searches for
		files named with the soname in the runpaths).

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@rtype: dict (example: {'libbar.so': set(['/lib/libbar.so.1.5'])})
		@return: The return value is a soname -> set-of-library-paths, where
		set-of-library-paths satisfy soname.

		"""

		os = _os_merge

		rValue = {}

		if not self._libs:
			self.rebuild()

		# Determine the obj_key from the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
		else:
			obj_key = self._obj_key(obj)
			if obj_key not in self._obj_properties:
				raise KeyError("%s (%s) not in object list" % (obj_key, obj))

		arch, needed, path, _soname, _objs = self._obj_properties[obj_key]
		path_keys = set(self._path_key(x) for x in path.union(self._defpath))
		for soname in needed:
			rValue[soname] = set()
			if arch not in self._libs or soname not in self._libs[arch]:
				continue
			# For each potential provider of the soname, add it to rValue if it
			# resides in the obj's runpath.
			for provider_key in self._libs[arch][soname].providers:
				providers = self._obj_properties[provider_key][4]
				for provider in providers:
					if self._path_key(os.path.dirname(provider)) in path_keys:
						rValue[soname].add(provider)
		return rValue

	def findConsumers(self, obj):
		"""
		Find consumers of an object or object key.

		This method may be called with a key from _obj_properties.  If this
		method is going to be called with an object key, to avoid not catching
		shadowed libraries, do not pass new _ObjectKey instances to this method.
		Instead pass the obj as a string.

		In some cases, not all consumers are returned.  This may occur when
		an soname symlink referencing a library is in an object's runpath while
		the actual library is not. For example, this problem is noticeable for
		binutils since it's libraries are added to the path via symlinks that
		are gemerated in the /usr/$CHOST/lib/ directory by binutils-config.
		Failure to recognize consumers of these symlinks makes preserve-libs
		fail to preserve binutils libs that are needed by these unrecognized
		consumers.

		Note that library consumption via dlopen (common for kde plugins) is
		currently undetected. However, it is possible to use the
		corresponding libtool archive (*.la) files to detect such consumers
		(revdep-rebuild is able to detect them).

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@rtype: set of strings (example: set(['/bin/foo', '/usr/bin/bar']))
		@return: The return value is a soname -> set-of-library-paths, where
		set-of-library-paths satisfy soname.

		"""

		os = _os_merge

		rValue = set()

		if not self._libs:
			self.rebuild()

		# Determine the obj_key and the set of objects matching the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			objs = self._obj_properties[obj_key][4]
		else:
			objs = set([obj])
			obj_key = self._obj_key(obj)
			if obj_key not in self._obj_properties:
				raise KeyError("%s (%s) not in object list" % (obj_key, obj))

		# If there is another version of this lib with the
		# same soname and the master link points to that
		# other version, this lib will be shadowed and won't
		# have any consumers.
		if not isinstance(obj, self._ObjectKey):
			soname = self._obj_properties[obj_key][3]
			master_link = os.path.join(self._root,
				os.path.dirname(obj).lstrip(os.path.sep), soname)
			try:
				master_st = os.stat(master_link)
				obj_st = os.stat(obj)
			except OSError:
				pass
			else:
				if (obj_st.st_dev, obj_st.st_ino) != \
					(master_st.st_dev, master_st.st_ino):
					return set()

		# Determine the directory(ies) from the set of objects.
		objs_dir_keys = set(self._path_key(os.path.dirname(x)) for x in objs)
		defpath_keys = set(self._path_key(x) for x in self._defpath)

		arch, _needed, _path, soname, _objs = self._obj_properties[obj_key]
		if arch in self._libs and soname in self._libs[arch]:
			# For each potential consumer, add it to rValue if an object from the
			# arguments resides in the consumer's runpath.
			for consumer_key in self._libs[arch][soname].consumers:
				_arch, _needed, path, _soname, consumer_objs = \
						self._obj_properties[consumer_key]
				path_keys = defpath_keys.union(self._path_key(x) for x in path)
				if objs_dir_keys.intersection(path_keys):
					rValue.update(consumer_objs)
		return rValue
