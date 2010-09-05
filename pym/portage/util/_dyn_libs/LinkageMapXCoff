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

class LinkageMapXCoff(LinkageMapELF):

	"""Models dynamic linker dependencies."""

	_needed_aux_key = "NEEDED.XCOFF.1"

	class _ObjectKey(LinkageMapELF._ObjectKey):

		def __init__(self, obj, root):
			LinkageMapELF._ObjectKey.__init__(self, obj, root)

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
			# Return a tuple of the device and inode, as well as the basename,
			# because of hardlinks the device and inode might be identical.
			return (object_stat.st_dev, object_stat.st_ino, os.path.basename(abs_path.rstrip(os.sep)))

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
			LinkageMapXCoff._ObjectKey.__init__(self, obj, root)
			self.alt_paths = set()

		def __str__(self):
			return str(sorted(self.alt_paths))

	def rebuild(self, exclude_pkgs=None, include_file=None):
		"""
		Raises CommandNotFound if there are preserved libs
		and the scanelf binary is not available.
		"""

		os = _os_merge
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

		# have to call scanelf for preserved libs here as they aren't 
		# registered in NEEDED.XCOFF.1 files
		plibs = set()
		if self._dbapi.plib_registry and self._dbapi.plib_registry.getPreservedLibs():
			for items in self._dbapi.plib_registry.getPreservedLibs().values():
				plibs.update(items)
				for x in items:
					args = [BASH_BINARY, "-c", ':'
						+ '; member="' + x + '"'
						+ '; archive=${member}'
						+ '; if [[ ${member##*/} == .*"["*"]" ]]'
						+ '; then member=${member%/.*}/${member##*/.}'
							 + '; archive=${member%[*}'
						+ '; fi'
						+ '; member=${member#${archive}}'
						+ '; [[ -r ${archive} ]] || chmod a+r "${archive}"'
						+ '; eval $(aixdll-query "${archive}${member}" FILE MEMBER FLAGS FORMAT RUNPATH DEPLIBS)'
						+ '; [[ -n ${member} ]] && needed=${FILE##*/} || needed='
						+ '; for deplib in ${DEPLIBS}'
						+ '; do eval deplib=${deplib}'
						   + '; if [[ ${deplib} != "." && ${deplib} != ".." ]]'
						   + '; then needed="${needed}${needed:+,}${deplib}"'
						   + '; fi'
						+ '; done'
						+ '; [[ -n ${MEMBER} ]] && MEMBER="[${MEMBER}]"'
						+ '; [[ " ${FLAGS} " == *" SHROBJ "* ]] && soname=${FILE##*/}${MEMBER} || soname='
						+ '; echo "${FORMAT##* }${FORMAT%%-*};${FILE#${ROOT%/}}${MEMBER};${soname};${RUNPATH};${needed}"'
						+ '; [[ -z ${member} && -n ${MEMBER} ]] && echo "${FORMAT##* }${FORMAT%%-*};${FILE#${ROOT%/}};${FILE##*/};;"'
					]
					try:
						proc = subprocess.Popen(args, stdout=subprocess.PIPE)
					except EnvironmentError as e:
						if e.errno != errno.ENOENT:
							raise
						raise CommandNotFound("aixdll-query via " + argv[0])
					else:
						for l in proc.stdout:
							try:
								l = _unicode_decode(l,
									encoding=_encodings['content'], errors='strict')
							except UnicodeDecodeError:
								l = _unicode_decode(l,
									encoding=_encodings['content'], errors='replace')
								writemsg_level(_("\nError decoding characters " \
									"returned from aixdll-query: %s\n\n") % (l,),
									level=logging.ERROR, noiselevel=-1)
							l = l.rstrip("\n")
							if not l:
								continue
							fields = l.split(";")
							if len(fields) < 5:
								writemsg_level(_("\nWrong number of fields " \
									"returned from aixdll-query: %s\n\n") % (l,),
									level=logging.ERROR, noiselevel=-1)
								continue
							fields[1] = fields[1][root_len:]
							plibs.discard(fields[1])
							lines.append(";".join(fields))
						proc.wait()

		if plibs:
			# Preserved libraries that did not appear in the bash
			# aixdll-query code output.  This is known to happen with
			# statically linked libraries.  Generate dummy lines for
			# these, so we can assume that every preserved library has
			# an entry in self._obj_properties.  This is important in
			# order to prevent findConsumers from raising an unwanted
			# KeyError.
			for x in plibs:
				lines.append(";".join(['', x, '', '', '']))

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

			def as_contentmember(obj):
				if obj.endswith("]"):
					if obj.find("/") >= 0:
						return obj[:obj.rfind("/")] + "/." + obj[obj.rfind("/")+1:]
					return "." + obj
				return obj

			obj = as_contentmember(fields[1])
			soname = as_contentmember(fields[2])
			path = set([normalize_path(x) \
				for x in filter(None, fields[3].replace(
				"${ORIGIN}", os.path.dirname(obj)).replace(
				"$ORIGIN", os.path.dirname(obj)).split(":"))])
			needed = [as_contentmember(x) for x in fields[4].split(",") if x]

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

