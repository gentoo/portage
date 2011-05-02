# Copyright 2005-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# Author(s): Nicholas Carpaski (carpaski@gentoo.org), Brian Harring (ferringb@gentoo.org)

__all__ = ["cache"]

import stat
import sys
from portage.util import normalize_path
import errno
from portage.exception import PermissionDenied
from portage import os

if sys.hexversion >= 0x3000000:
	long = int

class cache(object):
	"""
	Maintains the cache information about eclasses used in ebuild.
	"""
	def __init__(self, porttree_root, overlays=[]):

		self.eclasses = {} # {"Name": ("location","_mtime_")}
		self._eclass_locations = {}

		# screw with the porttree ordering, w/out having bash inherit match it, and I'll hurt you.
		# ~harring
		if porttree_root:
			self.porttree_root = porttree_root
			self.porttrees = [self.porttree_root] + overlays
			self.porttrees = tuple(map(normalize_path, self.porttrees))
			self._master_eclass_root = os.path.join(self.porttrees[0], "eclass")
			self.update_eclasses()
		else:
			self.porttree_root = None
			self.porttrees = ()
			self._master_eclass_root = None

	def copy(self):
		return self.__copy__()

	def __copy__(self):
		result = self.__class__(None)
		result.eclasses = self.eclasses.copy()
		result._eclass_locations = self._eclass_locations.copy()
		result.porttree_root = self.porttree_root
		result.porttrees = self.porttrees
		result._master_eclass_root = self._master_eclass_root
		return result

	def append(self, other):
		"""
		Append another instance to this instance. This will cause eclasses
		from the other instance to override any eclasses from this instance
		that have the same name.
		"""
		if not isinstance(other, self.__class__):
			raise TypeError(
				"expected type %s, got %s" % (self.__class__, type(other)))
		self.porttrees = self.porttrees + other.porttrees
		self.eclasses.update(other.eclasses)
		self._eclass_locations.update(other._eclass_locations)

	def update_eclasses(self):
		self.eclasses = {}
		self._eclass_locations = {}
		master_eclasses = {}
		eclass_len = len(".eclass")
		ignored_listdir_errnos = (errno.ENOENT, errno.ENOTDIR)
		for x in [normalize_path(os.path.join(y,"eclass")) for y in self.porttrees]:
			try:
				eclass_filenames = os.listdir(x)
			except OSError as e:
				if e.errno in ignored_listdir_errnos:
					del e
					continue
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(x)
				raise
			for y in eclass_filenames:
				if not y.endswith(".eclass"):
					continue
				try:
					mtime = os.stat(os.path.join(x, y))[stat.ST_MTIME]
				except OSError:
					continue
				ys=y[:-eclass_len]
				if x == self._master_eclass_root:
					master_eclasses[ys] = mtime
					self.eclasses[ys] = (x, mtime)
					self._eclass_locations[ys] = x
					continue

				master_mtime = master_eclasses.get(ys)
				if master_mtime is not None:
					if master_mtime == mtime:
						# It appears to be identical to the master,
						# so prefer the master entry.
						continue

				self.eclasses[ys] = (x, mtime)
				self._eclass_locations[ys] = x

	def is_eclass_data_valid(self, ec_dict):
		if not isinstance(ec_dict, dict):
			return False
		for eclass, tup in ec_dict.items():
			cached_data = self.eclasses.get(eclass, None)
			""" Only use the mtime for validation since the probability of a
			collision is small and, depending on the cache implementation, the
			path may not be specified (cache from rsync mirrors, for example).
			"""
			if cached_data is None or tup[1] != cached_data[1]:
				return False

		return True

	def get_eclass_data(self, inherits):
		ec_dict = {}
		for x in inherits:
			ec_dict[x] = self.eclasses[x]

		return ec_dict
