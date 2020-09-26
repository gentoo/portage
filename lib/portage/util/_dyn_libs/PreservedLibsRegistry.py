# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import json
import logging
import pickle
import stat

from portage import abssymlink
from portage import os
from portage import _encodings
from portage import _os_merge
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import PermissionDenied
from portage.localization import _
from portage.util import atomic_ofstream
from portage.util import writemsg_level
from portage.versions import cpv_getkey
from portage.locks import lockfile, unlockfile


class PreservedLibsRegistry:
	""" This class handles the tracking of preserved library objects """

	# JSON read support has been available since portage-2.2.0_alpha89.
	_json_write = True

	_json_write_opts = {
		"ensure_ascii": False,
		"indent": "\t",
		"sort_keys": True,
	}

	def __init__(self, root, filename):
		"""
			@param root: root used to check existence of paths in pruneNonExisting
		    @type root: String
			@param filename: absolute path for saving the preserved libs records
		    @type filename: String
		"""
		self._root = root
		self._filename = filename
		self._data = None
		self._lock = None

	def lock(self):
		"""Grab an exclusive lock on the preserved libs registry."""
		if self._lock is not None:
			raise AssertionError("already locked")
		self._lock = lockfile(self._filename)

	def unlock(self):
		"""Release our exclusive lock on the preserved libs registry."""
		if self._lock is None:
			raise AssertionError("not locked")
		unlockfile(self._lock)
		self._lock = None

	def load(self):
		""" Reload the registry data from file """
		self._data = None
		f = None
		content = None
		try:
			f = open(_unicode_encode(self._filename,
					encoding=_encodings['fs'], errors='strict'), 'rb')
			content = f.read()
		except EnvironmentError as e:
			if not hasattr(e, 'errno'):
				raise
			elif e.errno == errno.ENOENT:
				pass
			elif e.errno == PermissionDenied.errno:
				raise PermissionDenied(self._filename)
			else:
				raise
		finally:
			if f is not None:
				f.close()

		# content is empty if it's an empty lock file
		if content:
			try:
				self._data = json.loads(_unicode_decode(content,
					encoding=_encodings['repo.content'], errors='strict'))
			except SystemExit:
				raise
			except Exception as e:
				try:
					self._data = pickle.loads(content)
				except SystemExit:
					raise
				except Exception:
					writemsg_level(_("!!! Error loading '%s': %s\n") %
						(self._filename, e), level=logging.ERROR,
						noiselevel=-1)

		if self._data is None:
			self._data = {}
		else:
			for k, v in self._data.items():
				if isinstance(v, (list, tuple)) and len(v) == 3 and \
					isinstance(v[2], set):
					# convert set to list, for write with JSONEncoder
					self._data[k] = (v[0], v[1], list(v[2]))

		self._data_orig = self._data.copy()
		self.pruneNonExisting()

	def store(self):
		"""
		Store the registry data to the file. The existing inode will be
		replaced atomically, so if that inode is currently being used
		for a lock then that lock will be rendered useless. Therefore,
		it is important not to call this method until the current lock
		is ready to be immediately released.
		"""
		if os.environ.get("SANDBOX_ON") == "1" or \
			self._data == self._data_orig:
			return
		try:
			f = atomic_ofstream(self._filename, 'wb')
			if self._json_write:
				f.write(_unicode_encode(
					json.dumps(self._data, **self._json_write_opts),
					encoding=_encodings['repo.content'], errors='strict'))
			else:
				pickle.dump(self._data, f, protocol=2)
			f.close()
		except EnvironmentError as e:
			if e.errno != PermissionDenied.errno:
				writemsg_level("!!! %s %s\n" % (e, self._filename),
					level=logging.ERROR, noiselevel=-1)
		else:
			self._data_orig = self._data.copy()

	def _normalize_counter(self, counter):
		"""
		For simplicity, normalize as a unicode string
		and strip whitespace. This avoids the need for
		int conversion and a possible ValueError resulting
		from vardb corruption.
		"""
		if not isinstance(counter, str):
			counter = str(counter)
		return _unicode_decode(counter).strip()

	def register(self, cpv, slot, counter, paths):
		""" Register new objects in the registry. If there is a record with the
			same packagename (internally derived from cpv) and slot it is
			overwritten with the new data.
			@param cpv: package instance that owns the objects
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
			@param counter: vdb counter value for the package instance
			@type counter: String
			@param paths: absolute paths of objects that got preserved during an update
			@type paths: List
		"""
		cp = cpv_getkey(cpv)
		cps = cp+":"+slot
		counter = self._normalize_counter(counter)
		if len(paths) == 0 and cps in self._data \
				and self._data[cps][0] == cpv and \
				self._normalize_counter(self._data[cps][1]) == counter:
			del self._data[cps]
		elif len(paths) > 0:
			if isinstance(paths, set):
				# convert set to list, for write with JSONEncoder
				paths = list(paths)
			self._data[cps] = (cpv, counter, paths)

	def unregister(self, cpv, slot, counter):
		""" Remove a previous registration of preserved objects for the given package.
			@param cpv: package instance whose records should be removed
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
		"""
		self.register(cpv, slot, counter, [])

	def pruneNonExisting(self):
		""" Remove all records for objects that no longer exist on the filesystem. """

		os = _os_merge

		for cps in list(self._data):
			cpv, counter, _paths = self._data[cps]

			paths = []
			hardlinks = set()
			symlinks = {}
			for f in _paths:
				f_abs = os.path.join(self._root, f.lstrip(os.sep))
				try:
					lst = os.lstat(f_abs)
				except OSError:
					continue
				if stat.S_ISLNK(lst.st_mode):
					try:
						symlinks[f] = os.readlink(f_abs)
					except OSError:
						continue
				elif stat.S_ISREG(lst.st_mode):
					hardlinks.add(f)
					paths.append(f)

			# Only count symlinks as preserved if they still point to a hardink
			# in the same directory, in order to handle cases where a tool such
			# as eselect-opengl has updated the symlink to point to a hardlink
			# in a different directory (see bug #406837). The unused hardlink
			# is automatically found by _find_unused_preserved_libs, since the
			# soname symlink no longer points to it. After the hardlink is
			# removed by _remove_preserved_libs, it calls pruneNonExisting
			# which eliminates the irrelevant symlink from the registry here.
			for f, target in symlinks.items():
				if abssymlink(f, target=target) in hardlinks:
					paths.append(f)

			if len(paths) > 0:
				self._data[cps] = (cpv, counter, paths)
			else:
				del self._data[cps]

	def hasEntries(self):
		""" Check if this registry contains any records. """
		if self._data is None:
			self.load()
		return len(self._data) > 0

	def getPreservedLibs(self):
		""" Return a mapping of packages->preserved objects.
			@return mapping of package instances to preserved objects
			@rtype Dict cpv->list-of-paths
		"""
		if self._data is None:
			self.load()
		rValue = {}
		for cps in self._data:
			rValue[self._data[cps][0]] = self._data[cps][2]
		return rValue
