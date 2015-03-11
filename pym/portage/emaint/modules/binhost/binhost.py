# Copyright 2005-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import stat

import portage
from portage import os
from portage.util import writemsg
from portage.versions import _pkg_str

import sys

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	long = int

class BinhostHandler(object):

	short_desc = "Generate a metadata index for binary packages"

	def name():
		return "binhost"
	name = staticmethod(name)

	def __init__(self):
		eroot = portage.settings['EROOT']
		self._bintree = portage.db[eroot]["bintree"]
		self._bintree.populate()
		self._pkgindex_file = self._bintree._pkgindex_file
		self._pkgindex = self._bintree._load_pkgindex()

	def _need_update(self, cpv, data):

		if "MD5" not in data:
			return True

		size = data.get("SIZE")
		if size is None:
			return True

		mtime = data.get("_mtime_")
		if mtime is None:
			return True

		pkg_path = self._bintree.getname(cpv)
		try:
			s = os.lstat(pkg_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				raise
			# We can't update the index for this one because
			# it disappeared.
			return False

		try:
			if long(mtime) != s[stat.ST_MTIME]:
				return True
			if long(size) != long(s.st_size):
				return True
		except ValueError:
			return True

		return False

	def check(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		missing = []
		cpv_all = self._bintree.dbapi.cpv_all()
		cpv_all.sort()
		maxval = len(cpv_all)
		if onProgress:
			onProgress(maxval, 0)
		pkgindex = self._pkgindex
		missing = []
		metadata = {}
		for d in pkgindex.packages:
			metadata[d["CPV"]] = d
		for i, cpv in enumerate(cpv_all):
			d = metadata.get(cpv)
			if not d or self._need_update(cpv, d):
				missing.append(cpv)
			if onProgress:
				onProgress(maxval, i+1)
		errors = ["'%s' is not in Packages" % cpv for cpv in missing]
		stale = set(metadata).difference(cpv_all)
		for cpv in stale:
			errors.append("'%s' is not in the repository" % cpv)
		return errors

	def fix(self,  **kwargs):
		onProgress = kwargs.get('onProgress', None)
		bintree = self._bintree
		_instance_key = bintree.dbapi._instance_key
		cpv_all = self._bintree.dbapi.cpv_all()
		cpv_all.sort()
		missing = []
		maxval = 0
		if onProgress:
			onProgress(maxval, 0)
		pkgindex = self._pkgindex
		missing = []
		stale = []
		metadata = {}
		for d in pkgindex.packages:
			cpv = _pkg_str(d["CPV"], metadata=d,
				settings=bintree.settings)
			d["CPV"] = cpv
			metadata[_instance_key(cpv)] = d
			if not bintree.dbapi.cpv_exists(cpv):
				stale.append(cpv)

		for cpv in cpv_all:
			d = metadata.get(_instance_key(cpv))
			if not d or self._need_update(cpv, d):
				missing.append(cpv)

		if missing or stale:
			from portage import locks
			pkgindex_lock = locks.lockfile(
				self._pkgindex_file, wantnewlockfile=1)
			try:
				# Repopulate with lock held.
				bintree._populate()
				cpv_all = self._bintree.dbapi.cpv_all()
				cpv_all.sort()

				pkgindex = bintree._load_pkgindex()
				self._pkgindex = pkgindex

				# Recount stale/missing packages, with lock held.
				missing = []
				stale = []
				metadata = {}
				for d in pkgindex.packages:
					cpv = _pkg_str(d["CPV"], metadata=d,
						settings=bintree.settings)
					d["CPV"] = cpv
					metadata[_instance_key(cpv)] = d
					if not bintree.dbapi.cpv_exists(cpv):
						stale.append(cpv)

				for cpv in cpv_all:
					d = metadata.get(_instance_key(cpv))
					if not d or self._need_update(cpv, d):
						missing.append(cpv)

				maxval = len(missing)
				for i, cpv in enumerate(missing):
					d = bintree._pkgindex_entry(cpv)
					try:
						bintree._eval_use_flags(cpv, d)
					except portage.exception.InvalidDependString:
						writemsg("!!! Invalid binary package: '%s'\n" % \
							bintree.getname(cpv), noiselevel=-1)
					else:
						metadata[_instance_key(cpv)] = d

					if onProgress:
						onProgress(maxval, i+1)

				for cpv in stale:
					del metadata[_instance_key(cpv)]

				# We've updated the pkgindex, so set it to
				# repopulate when necessary.
				bintree.populated = False

				del pkgindex.packages[:]
				pkgindex.packages.extend(metadata.values())
				bintree._pkgindex_write(self._pkgindex)

			finally:
				locks.unlockfile(pkgindex_lock)

		if onProgress:
			if maxval == 0:
				maxval = 1
			onProgress(maxval, maxval)
		return None
