# Copyright 2005-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.cache import fs_template
from portage.cache import cache_errors
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import errno
import io
import stat
import sys

if sys.hexversion >= 0x3000000:
	long = int

# Coerce to unicode, in order to prevent TypeError when writing
# raw bytes to TextIOWrapper with python2.
_setitem_fmt = _unicode_decode("%s\n")

# store the current key order *here*.
class database(fs_template.FsBased):

	autocommits = True

	# do not screw with this ordering. _eclasses_ needs to be last
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'IUSE', 'REQUIRED_USE',
		'PDEPEND',   'PROVIDE', 'EAPI', 'PROPERTIES', 'DEFINED_PHASES')

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.location = os.path.join(self.location, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if len(self._known_keys) > len(self.auxdbkey_order) + 2:
			raise Exception("less ordered keys then auxdbkeys")
		if not os.path.exists(self.location):
			self._ensure_dirs()


	def _getitem(self, cpv):
		d = {}
		try:
			myf = io.open(_unicode_encode(os.path.join(self.location, cpv),
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
			for k,v in zip(self.auxdbkey_order, myf):
				d[k] = v.rstrip("\n")
		except (OSError, IOError) as e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			raise cache_errors.CacheCorruption(cpv, e)

		try:
			d["_mtime_"] = os.fstat(myf.fileno())[stat.ST_MTIME]
		except OSError as e:	
			myf.close()
			raise cache_errors.CacheCorruption(cpv, e)
		myf.close()
		return d


	def _setitem(self, cpv, values):
		s = cpv.rfind("/")
		fp=os.path.join(self.location,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:
			myf = io.open(_unicode_encode(fp,
				encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['repo.content'],
				errors='backslashreplace')
		except (OSError, IOError) as e:
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
		

		for x in self.auxdbkey_order:
			myf.write(_setitem_fmt % (values.get(x, ""),))

		myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])
		#update written.  now we move it.
		new_fp = os.path.join(self.location,cpv)
		try:
			os.rename(fp, new_fp)
		except (OSError, IOError) as e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
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
		dirs = [self.location]
		len_base = len(self.location)
		while len(dirs):
			for l in os.listdir(dirs[0]):
				if l.endswith(".cpickle"):
					continue
				p = os.path.join(dirs[0],l)
				st = os.lstat(p)
				if stat.S_ISDIR(st.st_mode):
					dirs.append(p)
					continue
				yield p[len_base+1:]
			dirs.pop(0)


	def commit(self):	pass
