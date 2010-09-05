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

		def __init__(self, obj, root):
			LinkageMapPeCoff._ObjectKey.__init__(self, obj, root)
			self.alt_paths = set()

		def __str__(self):
			return str(sorted(self.alt_paths))

	def rebuild(self, exclude_pkgs=None, include_file=None):
		"""
		Raises CommandNotFound if there are preserved libs
		and the readpecoff binary is not available.
		"""
		root = self._root
		root_len = len(root) - 1
		self._clear_cache()
		self._defpath.update(getlibpaths(self._root))
		libs = self._libs
		obj_key_cache = self._obj_key_cache
		obj_properties = self._obj_properties

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

		# have to call readpecoff for preserved libs here as they aren't 
		# registered in NEEDED.PECOFF.1 files
		if self._dbapi.plib_registry and self._dbapi.plib_registry.getPreservedLibs():
			args = ["readpecoff", self._dbapi.settings.get('CHOST')]
			for items in self._dbapi.plib_registry.getPreservedLibs().values():
				args.extend(os.path.join(root, x.lstrip("." + os.path.sep)) \
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
					l = l.lstrip().rstrip()
					if not l:
						continue
					lines.append(l)
				proc.wait()

		for l in lines:
			l = l.rstrip("\n")
			if not l:
				continue
			fields = l.split(";")
			if len(fields) < 5:
				writemsg_level(_("\nWrong number of fields " \
					"in %s: %s\n\n") % (self._needed_aux_key, l),
					level=logging.ERROR, noiselevel=-1)
				continue
			arch = fields[0]
			obj = fields[1]
			soname = fields[2]
			path = set([normalize_path(x) \
				for x in filter(None, fields[3].replace(
				"${ORIGIN}", os.path.dirname(obj)).replace(
				"$ORIGIN", os.path.dirname(obj)).split(":"))])
			needed = filter(None, fields[4].split(","))

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
