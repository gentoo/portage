# Copyright: 2005-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

from portage.cache import fs_template
from portage.cache import cache_errors
import errno
import io
import stat
import sys
import os as _os
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode

if sys.hexversion >= 0x3000000:
	long = int

# Coerce to unicode, in order to prevent TypeError when writing
# raw bytes to TextIOWrapper with python2.
_setitem_fmt = _unicode_decode("%s=%s\n")

class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.location = os.path.join(self.location, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))
		write_keys = set(self._known_keys)
		write_keys.add("_eclasses_")
		write_keys.add("_%s_" % (self.validation_chf,))
		self._write_keys = sorted(write_keys)
		if not self.readonly and not os.path.exists(self.location):
			self._ensure_dirs()

	def _getitem(self, cpv):
		# Don't use os.path.join, for better performance.
		fp = self.location + _os.sep + cpv
		try:
			myf = io.open(_unicode_encode(fp,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
			try:
				lines = myf.read().split("\n")
				if not lines[-1]:
					lines.pop()
				d = self._parse_data(lines, cpv)
				if '_mtime_' not in d:
					# Backward compatibility with old cache
					# that uses mtime mangling.
					d['_mtime_'] = _os.fstat(myf.fileno())[stat.ST_MTIME]
				return d
			finally:
				myf.close()
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
		s = cpv.rfind("/")
		fp = os.path.join(self.location,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:
			myf = io.open(_unicode_encode(fp,
				encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['repo.content'],
				errors='backslashreplace')
		except (IOError, OSError) as e:
			if errno.ENOENT == e.errno:
				try:
					self._ensure_dirs(cpv)
					myf = io.open(_unicode_encode(fp,
						encoding=_encodings['fs'], errors='strict'),
						mode='w', encoding=_encodings['repo.content'],
						errors='backslashreplace')
				except (OSError, IOError) as e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

		try:
			for k in self._write_keys:
				v = values.get(k)
				if not v:
					continue
				myf.write(_setitem_fmt % (k, v))
		finally:
			myf.close()
		self._ensure_access(fp)

		#update written.  now we move it.

		new_fp = os.path.join(self.location,cpv)
		try:
			os.rename(fp, new_fp)
		except (OSError, IOError) as e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)

	def _delitem(self, cpv):
#		import pdb;pdb.set_trace()
		try:
			os.remove(os.path.join(self.location,cpv))
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
		len_base = len(self.location)
		while dirs:
			depth, dir_path = dirs.pop()
			try:
				dir_list = os.listdir(dir_path)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				continue
			for l in dir_list:
				if l.endswith(".cpickle"):
					continue
				p = os.path.join(dir_path, l)
				try:
					st = os.lstat(p)
				except OSError:
					# Cache entry disappeared.
					continue
				if stat.S_ISDIR(st.st_mode):
					# Only recurse 1 deep, in order to avoid iteration over
					# entries from another nested cache instance. This can
					# happen if the user nests an overlay inside
					# /usr/portage/local as in bug #302764.
					if depth < 1:
						dirs.append((depth+1, p))
					continue
				yield p[len_base+1:]


class md5_database(database):

	validation_chf = 'md5'
	store_eclass_paths = False
