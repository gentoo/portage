# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

from pathlib import Path
from portage.cache import fs_template
from portage.cache import cache_errors
import errno
import io
import stat
import tempfile
import os as _os
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.exception import InvalidData
from portage.versions import _pkg_str
from portage.util import unroot


class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.location = self.location / unroot(self.label)
		write_keys = set(self._known_keys)
		write_keys.add("_eclasses_")
		write_keys.add("_%s_" % (self.validation_chf,))
		self._write_keys = sorted(write_keys)
		if not self.readonly and not self.location.exists():
			self._ensure_dirs()

	def _getitem(self, cpv):
		fp = self.location / cpv
		try:
			with fp.open('r', encoding=_encodings['repo.content'], errors='replace') as myf:
				lines = myf.read().split("\n")
				if not lines[-1]:
					lines.pop()
				d = self._parse_data(lines, cpv)
				if '_mtime_' not in d:
					# Backward compatibility with old cache
					# that uses mtime mangling.
					d['_mtime_'] = _os.fstat(myf.fileno())[stat.ST_MTIME]
				return d
		except (IOError, OSError) as e:
			if e.errno != errno.ENOENT:
				raise cache_errors.CacheCorruption(cpv, e)
			raise KeyError(cpv, e)

	def _parse_data(self, data, cpv):
		try:
			return dict( x.split("=", 1) for x in data )
		except ValueError as e:
			# If a line is missing an "=", the split length is 1 instead of 2.
			raise cache_errors.CacheCorruption(cpv, e)

	def _setitem(self, cpv, values):
		try:
			fd, fp = tempfile.mkstemp(dir=self.location)
			fp = Path(fp)
		except EnvironmentError as e:
			raise cache_errors.CacheCorruption(cpv, e)

		with io.open(fd, mode='w',
			encoding=_encodings['repo.content'],
			errors='backslashreplace') as myf:
			for k in self._write_keys:
				v = values.get(k)
				if not v:
					continue
				myf.write("%s=%s\n" % (k, v))

		self._ensure_access(fp)

		#update written.  now we move it.

		new_fp = self.location / cpv
		try:
			fp.rename(new_fp)
		except EnvironmentError as e:
			success = False
			try:
				if errno.ENOENT == e.errno:
					try:
						self._ensure_dirs(Path(cpv))
						fp.rename(new_fp)
						success = True
					except EnvironmentError as e:
						raise cache_errors.CacheCorruption(cpv, e)
				else:
					raise cache_errors.CacheCorruption(cpv, e)
			finally:
				if not success:
					fp.unlink()

	def _delitem(self, cpv):
		try:
			os.remove(self.location / cpv)
		except OSError as e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

	def __contains__(self, cpv):
		return os.path.exists(os.path.join(self.location, cpv))

	def __iter__(self):
		"""generator for walking the dir struct"""
		dirs = [(0, self.location)]
		while dirs:
			depth, dir_path = dirs.pop()
			if not dir_path.exists():
				continue
			for p in dir_path.iterdir():
				try:
					st = os.lstat(p)
				except OSError:
					# Cache entry disappeared.
					continue
				if stat.S_ISDIR(st.st_mode):
					# Only recurse 1 deep, in order to avoid iteration over
					# entries from another nested cache instance. This can
					# happen if the user nests an overlay inside
					# /var/db/repos/gentoo/local as in bug #302764.
					if depth < 1:
						dirs.append((depth+1, p))
					continue

				try:
					yield _pkg_str(str(p.relative_to(self.location)))
				except InvalidData:
					continue


class md5_database(database):

	validation_chf = 'md5'
	store_eclass_paths = False


class mtime_md5_database(database):
	validation_chf = 'md5'
	chf_types = ('md5', 'mtime')
