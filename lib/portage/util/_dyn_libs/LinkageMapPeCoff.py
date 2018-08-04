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
from portage.util._dyn_libs.LinkageMapELF import LinkageMapELF

class LinkageMapPeCoff(LinkageMapELF):

	"""Models dynamic linker dependencies."""

	# NEEDED.PECOFF.1 has effectively the _same_ format as NEEDED.ELF.2,
	# but we keep up the relation "scanelf" -> "NEEDED.ELF", "readpecoff" ->
	# "NEEDED.PECOFF", "scanmacho" -> "NEEDED.MACHO", etc. others will follow.
	_needed_aux_key = "NEEDED.PECOFF.1"

	class _ObjectKey(LinkageMapELF._ObjectKey):

		"""Helper class used as _obj_properties keys for objects."""

		def _generate_object_key(self, obj, root):
			"""
			Generate object key for a given object. This is different from the
			Linux implementation, since some systems (e.g. interix) don't have
			"inodes", thus the inode field is always zero, or a random value,
			making it inappropriate for identifying a file... :)

			@param object: path to a file
			@type object: string (example: '/usr/bin/bar')
			@rtype: 2-tuple of types (bool, string)
			@return:
				2-tuple of boolean indicating existance, and absolut path
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
				return (False, os.path.realpath(abs_path))
			# On Interix, the inode field may always be zero, since the
			# filesystem (NTFS) has no inodes ...
			return (True, os.path.realpath(abs_path))

		def file_exists(self):
			"""
			Determine if the file for this key exists on the filesystem.

			@rtype: Boolean
			@return:
				1. True if the file exists.
				2. False if the file does not exist or is a broken symlink.

			"""
			return self._key[0]

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
		and the readpecoff binary is not available.

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

		# have to call readpecoff for preserved libs here as they aren't 
		# registered in NEEDED.PECOFF.1 files
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
			args = ["readpecoff", self._dbapi.settings.get('CHOST')]
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
							"returned from readpecoff: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
					l = l[3:].rstrip("\n")
					if not l:
						continue
					fields = l.split(";")
					if len(fields) < 5:
						writemsg_level(_("\nWrong number of fields " \
							"returned from readpecoff: %s\n\n") % (l,),
							level=logging.ERROR, noiselevel=-1)
						continue
					fields[1] = fields[1][root_len:]
					owner = plibs.pop(fields[1], None)
					lines.append((owner, "readpecoff", ";".join(fields)))
				proc.wait()

		if plibs:
			# Preserved libraries that did not appear in the scanelf output.
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
			if len(fields) < 5:
				writemsg_level(_("\nWrong number of fields " \
					"in %s: %s\n\n") % (location, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			soname = fields[2]
			path = frozenset(normalize_path(x) \
				for x in filter(None, fields[3].replace(
				"${ORIGIN}", os.path.dirname(obj)).replace(
				"$ORIGIN", os.path.dirname(obj)).split(":")))
			path = frozensets.setdefault(path, path)
			needed = frozenset(x for x in fields[4].split(",") if x)
			needed = frozensets.setdefault(needed, needed)

			obj_key = self._obj_key(obj)
			indexed = True
			myprops = obj_properties.get(obj_key)
			if myprops is None:
				indexed = False
				myprops = self._obj_properties_class(
					arch, needed, path, soname, [], owner)
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
			if soname:
				soname_map = arch_map.get(soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=[], consumers=[])
					arch_map[soname] = soname_map
				soname_map.providers.append(obj_key)
			for needed_soname in needed:
				soname_map = arch_map.get(needed_soname)
				if soname_map is None:
					soname_map = self._soname_map_class(
						providers=[], consumers=[])
					arch_map[needed_soname] = soname_map
				soname_map.consumers.append(obj_key)

		for arch, sonames in libs.items():
			for soname_node in sonames.values():
				soname_node.providers = tuple(set(soname_node.providers))
				soname_node.consumers = tuple(set(soname_node.consumers))
