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
from portage.const import EPREFIX

class LinkageMapMachO(object):

	"""Models dynamic linker dependencies."""

	_needed_aux_key = "NEEDED.MACHO.3"
	_installname_map_class = slot_dict_class(
		("consumers", "providers"), prefix="")

	class _obj_properties_class(object):

		__slots__ = ("arch", "needed", "install_name", "alt_paths",
			"owner",)

		def __init__(self, arch, needed, install_name, alt_paths, owner):
			self.arch = arch
			self.needed = needed
			self.install_name = install_name
			self.alt_paths = alt_paths
			self.owner = owner

	def __init__(self, vardbapi):
		self._dbapi = vardbapi
		self._root = self._dbapi.settings['ROOT']
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
		and the scanmacho binary is not available.

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
		libs = self._libs
		obj_properties = self._obj_properties

		lines = []

		# Data from include_file is processed first so that it
		# overrides any data from previously installed files.
		if include_file is not None:
			for line in grabfile(include_file):
				lines.append((None, include_file, line))

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
					lines.append((cpv, needed_file, line))
		finally:
			if can_lock:
				self._dbapi.unlock()

		# have to call scanmacho for preserved libs here as they aren't 
		# registered in NEEDED.MACHO.3 files
		plibs = {}
		if preserve_paths is not None:
			plibs.update((x, None) for x in preserve_paths)
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
				plibs.update((x, cpv) for x in items)
		if plibs:
			args = [EPREFIX + "/usr/bin/scanmacho", "-qF", "%a;%F;%S;%n"]
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
							"returned from scanmacho: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
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
					owner = plibs.pop(fields[1], None)
					lines.append((owner, "scanmacho", ";".join(fields)))
				proc.wait()
				proc.stdout.close()

		if plibs:
			# Preserved libraries that did not appear in the scanmacho output.
			# This is known to happen with statically linked libraries.
			# Generate dummy lines for these, so we can assume that every
			# preserved library has an entry in self._obj_properties. This
			# is important in order to prevent findConsumers from raising
			# an unwanted KeyError.
			for x, cpv in plibs.items():
				lines.append((cpv, "plibs", ";".join(['', x, '', '', ''])))

		# Share identical frozenset instances when available,
		# in order to conserve memory.
		frozensets = {}

		for owner, location, l in lines:
			l = l.rstrip("\n")
			if not l:
				continue
			fields = l.split(";")
			if len(fields) < 4:
				writemsg_level(_("\nWrong number of fields " \
					"in %s: %s\n\n") % (location, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			install_name = os.path.normpath(fields[2])
			needed = frozenset(x for x in fields[3].split(",") if x)
			needed = frozensets.setdefault(needed, needed)

			obj_key = self._obj_key(obj)
			indexed = True
			myprops = obj_properties.get(obj_key)
			if myprops is None:
				indexed = False
				myprops = self._obj_properties_class(
					arch, needed, install_name, [], owner)
				obj_properties[obj_key] = myprops
			# All object paths are added into the obj_properties tuple.
			myprops.alt_paths.append(obj)

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
						providers=[], consumers=[])
					arch_map[install_name] = installname_map
				installname_map.providers.append(obj_key)
			for needed_installname in needed:
				installname_map = arch_map.get(needed_installname)
				if installname_map is None:
					installname_map = self._installname_map_class(
						providers=[], consumers=[])
					arch_map[needed_installname] = installname_map
				installname_map.consumers.append(obj_key)

		for arch, install_names in libs.items():
			for install_name_node in install_names.values():
				install_name_node.providers = tuple(set(install_name_node.providers))
				install_name_node.consumers = tuple(set(install_name_node.consumers))

	def listBrokenBinaries(self, debug=False):
		"""
		Find binaries and their needed install_names, which have no providers.

		@param debug: Boolean to enable debug output
		@type debug: Boolean
		@rtype: dict (example: {'/usr/bin/foo': set(['/usr/lib/libbar.dylib'])})
		@return: The return value is an object -> set-of-install_names mapping, where
			object is a broken binary and the set consists of install_names needed by
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
						obj_props = self._obj_properties.get(obj_key)
						if obj_props is None:
							arch = None
							install_name = None
						else:
							arch = obj_props.arch
							install_name = obj_props.install_name
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
			obj_props = self._obj_properties[obj_key]
			arch = obj_props.arch
			objs = obj_props.alt_paths
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
			{(123L, 456L): {'libbar.dylib': set(['/lib/libbar.1.5.dylib'])}})
		@return: The return value is an object -> providers mapping, where
			providers is a mapping of install_name -> set-of-library-paths returned
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
		Determine whether an object is a "master" symlink, which means
		that its basename is the same as the beginning part of the
		soname and it lacks the soname's version component.

		Examples:

		install_name              | master symlink name
		-----------------------------------------------
		libarchive.2.8.4.dylib    | libarchive.dylib
		(typically the install_name is libarchive.2.dylib)

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/foo')
		@rtype: Boolean
		@return:
			1. True if obj is a master link
			2. False if obj is not a master link

		"""
		os = _os_merge
		obj_key = self._obj_key(obj)
		if obj_key not in self._obj_properties:
			raise KeyError("%s (%s) not in object list" % (obj_key, obj))
		basename = os.path.basename(obj)
		install_name = self._obj_properties[obj_key].install_name
		return (len(basename) < len(os.path.basename(install_name)) and \
			basename.endswith(".dylib") and \
			os.path.basename(install_name).startswith(basename[:-6]))

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
					rValue.extend(self._obj_properties[obj_key].alt_paths)
		return rValue

	def getOwners(self, obj):
		"""
		Return the package(s) associated with an object. Raises KeyError
		if the object is unknown. Returns an empty tuple if the owner(s)
		are unknown.

		NOTE: For preserved libraries, the owner(s) may have been
		previously uninstalled, but these uninstalled owners can be
		returned by this method since they are registered in the
		PreservedLibsRegistry.

		@param obj: absolute path to an object
		@type obj: string (example: '/usr/bin/bar')
		@rtype: tuple
		@return: a tuple of cpv
		"""
		if not self._libs:
			self.rebuild()
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
		else:
			obj_key = self._obj_key_cache.get(obj)
			if obj_key is None:
				raise KeyError("%s not in object list" % obj)
		obj_props = self._obj_properties.get(obj_key)
		if obj_props is None:
			raise KeyError("%s not in object list" % obj_key)
		if obj_props.owner is None:
			return ()
		return (obj_props.owner,)

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
			return self._obj_properties[obj_key].install_name
		if obj not in self._obj_key_cache:
			raise KeyError("%s not in object list" % obj)
		return self._obj_properties[self._obj_key_cache[obj]].install_name

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

		obj_props = self._obj_properties[obj_key]
		arch = obj_props.arch
		needed = obj_props.needed
		install_name = obj_props.install_name
		for install_name in needed:
			rValue[install_name] = set()
			if arch not in self._libs or install_name not in self._libs[arch]:
				continue
			# For each potential provider of the install_name, add it to
			# rValue if it exists.  (Should be one)
			for provider_key in self._libs[arch][install_name].providers:
				providers = self._obj_properties[provider_key].alt_paths
				for provider in providers:
					if os.path.exists(provider):
						rValue[install_name].add(provider)
		return rValue

	def findConsumers(self, obj, exclude_providers=None, greedy=True):
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

		The exclude_providers argument is useful for determining whether
		removal of one or more packages will create unsatisfied consumers. When
		this option is given, consumers are excluded from the results if there
		is an alternative provider (which is not excluded) of the required
		soname such that the consumers will remain satisfied if the files
		owned by exclude_providers are removed.

		@param obj: absolute path to an object or a key from _obj_properties
		@type obj: string (example: '/usr/bin/bar') or _ObjectKey
		@param exclude_providers: A collection of callables that each take a
			single argument referring to the path of a library (example:
			'/usr/lib/libssl.0.9.8.dylib'), and return True if the library is
			owned by a provider which is planned for removal.
		@type exclude_providers: collection
		@param greedy: If True, then include consumers that are satisfied
		by alternative providers, otherwise omit them. Default is True.
		@type greedy: Boolean
		@rtype: set of strings (example: set(['/bin/foo', '/usr/bin/bar']))
		@return: The return value is a install_name -> set-of-library-paths, where
		set-of-library-paths satisfy install_name.

		"""

		os = _os_merge

		if not self._libs:
			self.rebuild()

		# Determine the obj_key and the set of objects matching the arguments.
		if isinstance(obj, self._ObjectKey):
			obj_key = obj
			if obj_key not in self._obj_properties:
				raise KeyError("%s not in object list" % obj_key)
			objs = self._obj_properties[obj_key].alt_paths
		else:
			objs = set([obj])
			obj_key = self._obj_key(obj)
			if obj_key not in self._obj_properties:
				raise KeyError("%s (%s) not in object list" % (obj_key, obj))

		# If there is another version of this lib with the
		# same install_name and the install_name symlink points to that
		# other version, this lib will be shadowed and won't
		# have any consumers.
		if not isinstance(obj, self._ObjectKey):
			install_name = self._obj_properties[obj_key].install_name
			master_link = os.path.join(self._root,
					install_name.lstrip(os.path.sep))
			obj_path = os.path.join(self._root, obj.lstrip(os.sep))
			try:
				master_st = os.stat(master_link)
				obj_st = os.stat(obj_path)
			except OSError:
				pass
			else:
				if (obj_st.st_dev, obj_st.st_ino) != \
					(master_st.st_dev, master_st.st_ino):
					return set()

		obj_props = self._obj_properties[obj_key]
		arch = obj_props.arch
		install_name = obj_props.install_name

		install_name_node = None
		arch_map = self._libs.get(arch)
		if arch_map is not None:
			install_name_node = arch_map.get(install_name)

		satisfied_consumer_keys = set()
		if install_name_node is not None:
			if exclude_providers is not None and not greedy:
				relevant_dir_keys = set()
				for provider_key in install_name_node.providers:
					if not greedy and provider_key == obj_key:
						continue
					provider_objs = self._obj_properties[provider_key].alt_paths
					for p in provider_objs:
						provider_excluded = False
						if exclude_providers is not None:
							for excluded_provider_isowner in exclude_providers:
								if excluded_provider_isowner(p):
									provider_excluded = True
									break
						if not provider_excluded:
							# This provider is not excluded. It will
							# satisfy a consumer of this install_name.
							relevant_dir_keys.add(self._path_key(p))

				if relevant_dir_keys:
					for consumer_key in install_name_node.consumers:
							satisfied_consumer_keys.add(consumer_key)

		rValue = set()
		if install_name_node is not None:
			# For each potential consumer, add it to rValue.
			for consumer_key in install_name_node.consumers:
				if consumer_key in satisfied_consumer_keys:
					continue
				consumer_props = self._obj_properties[consumer_key]
				consumer_objs = consumer_props.alt_paths
				rValue.update(consumer_objs)
		return rValue
