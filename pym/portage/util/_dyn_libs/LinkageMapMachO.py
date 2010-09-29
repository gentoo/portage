# Copyright 1998-2010 Gentoo Foundation
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
from portage.const import EPREFIX

class LinkageMapMachO(object):

	"""Models dynamic linker dependencies."""

	_needed_aux_key = "NEEDED.MACHO.3"
	_installname_map_class = slot_dict_class(
		("consumers", "providers"), prefix="")

	def __init__(self, vardbapi):
		self._dbapi = vardbapi
		self._root = self._dbapi.root
		self._libs = {}
		self._obj_properties = {}
		self._obj_key_cache = {}
		self._path_key_cache = {}

	def _clear_cache(self):
		self._libs.clear()
		self._obj_properties.clear()
		self._obj_key_cache.clear()
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

		__slots__ = ("__weakref__", "_key")

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

			abs_path = os.path.join(root, obj.lstrip(os.path.sep))
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

		def __init__(self, obj, root):
			LinkageMapMachO._ObjectKey.__init__(self, obj, root)
			self.alt_paths = set()

		def __str__(self):
			return str(sorted(self.alt_paths))

	def rebuild(self, exclude_pkgs=None, include_file=None):
		"""
		Raises CommandNotFound if there are preserved libs
		and the scanmacho binary is not available.
		"""
		root = self._root
		root_len = len(root) - 1
		self._clear_cache()
		libs = self._libs
		obj_key_cache = self._obj_key_cache
		obj_properties = self._obj_properties

		os = _os_merge

		lines = []

		# Data from include_file is processed first so that it
		# overrides any data from previously installed files.
		if include_file is not None:
			lines += grabfile(include_file)

		aux_keys = [self._needed_aux_key]
		for cpv in self._dbapi.cpv_all():
			if exclude_pkgs is not None and cpv in exclude_pkgs:
				continue
			lines += self._dbapi.aux_get(cpv, aux_keys)[0].split('\n')
		# Cache NEEDED.* files avoid doing excessive IO for every rebuild.
		self._dbapi.flush_cache()

		# have to call scanmacho for preserved libs here as they aren't 
		# registered in NEEDED.MACHO.3 files
		plibs = set()
		if self._dbapi._plib_registry and self._dbapi._plib_registry.getPreservedLibs():
			args = [EPREFIX+"/usr/bin/scanmacho", "-qF", "%a;%F;%S;%n"]
			for items in self._dbapi._plib_registry.getPreservedLibs().values():
				plibs.update(items)
				args.extend(os.path.join(root, x.lstrip("." + os.sep)) \
						for x in items)
			try:
				proc = subprocess.Popen(args, stdout=subprocess.PIPE)
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				raise CommandNotFound(args[0])
			else:
				for l in proc.stdout:
					if not isinstance(l, unicode):
						l = unicode(l, encoding='utf_8', errors='replace')
					l = l.rstrip("\n")
					if not l:
						continue
					fields = l.split(";")
					if len(fields) < 4:
						writemsg_level("\nWrong number of fields " + \
							"returned from scanmacho: %s\n\n" % (l,),
							level=logging.ERROR, noiselevel=-1)
						continue
					fields[1] = fields[1][root_len:]
					plibs.discard(fields[1])
					lines.append(";".join(fields))
				proc.wait()

		if plibs:
			# Preserved libraries that did not appear in the scanmacho
			# output.  This is known to happen with statically linked
			# libraries.  Generate dummy lines for these, so we can
			# assume that every preserved library has an entry in
			# self._obj_properties.  This is important in order to
			# prevent findConsumers from raising an unwanted KeyError.
			for x in plibs:
				lines.append(";".join(['', x, '', '']))

		for l in lines:
			l = l.rstrip("\n")
			if not l:
				continue
			fields = l.split(";")
			if len(fields) < 4:
				writemsg_level("\nWrong number of fields " + \
					"in %s: %s\n\n" % (self._needed_aux_key, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			install_name = os.path.normpath(fields[2])
			needed = filter(None, fields[3].split(","))

			obj_key = self._obj_key(obj)
			indexed = True
			myprops = obj_properties.get(obj_key)
			if myprops is None:
				indexed = False
				myprops = (arch, needed, install_name, set())
				obj_properties[obj_key] = myprops
			# All object paths are added into the obj_properties tuple.
			myprops[3].add(obj)

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
			if install_name:
				installname_map = arch_map.get(install_name)
				if installname_map is None:
					installname_map = self._installname_map_class(
						providers=set(), consumers=set())
					arch_map[install_name] = installname_map
				installname_map.providers.add(obj_key)
			for needed_installname in needed:
				installname_map = arch_map.get(needed_installname)
				if installname_map is None:
					installname_map = self._installname_map_class(
						providers=set(), consumers=set())
					arch_map[needed_installname] = installname_map
				installname_map.consumers.add(obj_key)
		
	def listBrokenBinaries(self, debug=False):
		"""
		Find binaries and their needed install_names, which have no providers.

		@param debug: Boolean to enable debug output
		@type debug: Boolean
		@rtype: dict (example: {'/usr/bin/foo': set(['/usr/lib/libbar.dylib'])})
		@return: The return value is an object -> set-of-install_names
			mapping, where object is a broken binary and the set
			consists of install_names needed by object that have no
			corresponding libraries to fulfill the dependency.

		"""
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
				@type obj: string (example: '/usr/lib/libfoo.dylib')
				@rtype: 4-tuple with types
					(string or None, string or None, 2-tuple, Boolean)
				@return: 4-tuple with the following components:
					1. arch as a string or None if it does not exist,
					2. soname as a string or None if it does not exist,
					3. obj_key as 2-tuple,
					4. Boolean representing whether the object exists.
					(example: ('libfoo.1.dylib', (123L, 456L), True))

				"""
				if obj in cache_self.cache:
					return cache_self.cache[obj]
				else:
					obj_key = self._obj_key(obj)
					# Check that the library exists on the filesystem.
					if obj_key.file_exists():
						# Get the install_name from LinkageMapMachO._obj_properties if
						# it exists. Otherwise, None.
						arch = self._obj_properties.get(obj_key, (None,)*4)[0]
						install_name = self._obj_properties.get(obj_key, (None,)*4)[2]
						return cache_self.cache.setdefault(obj, \
								(arch, install_name, obj_key, True))
					else:
						return cache_self.cache.setdefault(obj, \
								(None, None, obj_key, False))

		rValue = {}
		cache = _LibraryCache()
		providers = self.listProviders()

		# Iterate over all obj_keys and their providers.
		for obj_key, install_names in providers.items():
			arch = self._obj_properties[obj_key][0]
			objs = self._obj_properties[obj_key][3]
			# Iterate over each needed install_name and the set of
			# library paths that fulfill the install_name to determine
			# if the dependency is broken.
			for install_name, libraries in install_names.items():
				# validLibraries is used to store libraries, which
				# satisfy install_name, so if no valid libraries are
				# found, the install_name is not satisfied for obj_key.
				# If unsatisfied, objects associated with obj_key must
				# be emerged.
				validLibrary = set() # for compat with LinkageMap
				cachedArch, cachedInstallname, cachedKey, cachedExists = \
						cache.get(install_name)
				# Check that the this library provides the needed soname.  Doing
				# this, however, will cause consumers of libraries missing
				# sonames to be unnecessarily emerged. (eg libmix.so)
				if cachedInstallname == install_name and cachedArch == arch:
					validLibrary.add(cachedKey)
					if debug and cachedKey not in \
							set(map(self._obj_key_cache.get, libraries)):
						# XXX This is most often due to soname symlinks not in
						# a library's directory.  We could catalog symlinks in
						# LinkageMap to avoid checking for this edge case here.
						print(_("Found provider outside of findProviders:"), \
								install_name, "->", cachedRealpath)
				if debug and cachedArch == arch and \
						cachedKey in self._obj_properties:
					print(_("Broken symlink or missing/bad install_name:"), \
							install_name, '->', cachedRealpath, \
							"with install_name", cachedInstallname, "but expecting", install_name)
				# This conditional checks if there are no libraries to
				# satisfy the install_name (empty set).
				if not validLibrary:
					for obj in objs:
						rValue.setdefault(obj, set()).add(install_name)
					# If no valid libraries have been found by this
					# point, then the install_name does not exist in the
					# filesystem, but if there are libraries (from the
					# providers mapping), it is likely that soname
					# symlinks or the actual libraries are missing or
					# broken.  Thus those libraries are added to rValue
					# in order to emerge corrupt library packages.
					for lib in libraries:
						rValue.setdefault(lib, set()).add(install_name)
						if debug:
							if not os.path.isfile(lib):
								print(_("Missing library:"), lib)
							else:
								print(_("Possibly missing symlink:"), \
										install_name)
		return rValue

	def listProviders(self):
		"""
		Find the providers for all object keys in LinkageMap.

		@rtype: dict (example:
			{(123L, 456L): {'libbar.dylib': set(['/lib/libbar.1.5.dylib'])}})
		@return: The return value is an object -> providers mapping, where
			providers is a mapping of install_name ->
			set-of-library-paths returned from the findProviders method.

		"""
		rValue = {}
		if not self._libs:
			self.rebuild()
		# Iterate over all binaries within LinkageMapMachO.
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
		basename = os.path.basename(obj)
		obj_key = self._obj_key(obj)
		if obj_key not in self._obj_properties:
			raise KeyError("%s (%s) not in object list" % (obj_key, obj))
		install_name = self._obj_properties[obj_key][2]
		return (len(basename) < len(os.path.basename(install_name)))

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
		for arch_map in self._libs.itervalues():
			for soname_map in arch_map.itervalues():
				for obj_key in soname_map.providers:
					rValue.extend(self._obj_properties[obj_key][3])
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
			return self._obj_properties[obj_key][2]
		if obj not in self._obj_key_cache:
			raise KeyError("%s not in object list" % obj)
		return self._obj_properties[self._obj_key_cache[obj]][2]

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
		@rtype: dict (example: {'libbar.dylib': set(['/lib/libbar.1.5.dylib'])})
		@return: The return value is a install_name -> set-of-library-paths, where
		set-of-library-paths satisfy install_name.

		"""
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

		arch, needed, install_name, _ = self._obj_properties[obj_key]
		for install_name in needed:
			rValue[install_name] = set()
			if arch not in self._libs or install_name not in self._libs[arch]:
				continue
			# For each potential provider of the install_name, add it to
			# rValue if it exists.  (Should be one)
			for provider_key in self._libs[arch][install_name].providers:
				providers = self._obj_properties[provider_key][3]
				for provider in providers:
					if os.path.exists(provider):
						rValue[install_name].add(provider)
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

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@rtype: set of strings (example: set(['/bin/foo', '/usr/bin/bar']))
		@return: The return value is a install_name -> set-of-library-paths, where
		set-of-library-paths satisfy install_name.

		"""
		rValue = set()

		if not self._libs:
			self.rebuild()

		# Determine the obj_key and the set of objects matching the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			objs = self._obj_properties[obj_key][3]
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
			install_name = self._obj_properties[obj_key][2]
			master_link = os.path.join(self._root,
					install_name.lstrip(os.path.sep))
			try:
				master_st = os.stat(master_link)
				obj_st = os.stat(obj)
			except OSError:
				pass
			else:
				if (obj_st.st_dev, obj_st.st_ino) != \
					(master_st.st_dev, master_st.st_ino):
					return set()

		arch = self._obj_properties[obj_key][0]
		install_name = self._obj_properties[obj_key][2]
		if arch in self._libs and install_name in self._libs[arch]:
			# For each potential consumer, add it to rValue if an object from the
			# arguments resides in the consumer's runpath.
			for consumer_key in self._libs[arch][install_name].consumers:
				consumer_objs = self._obj_properties[consumer_key][3]
				rValue.update(consumer_objs)
		return rValue
