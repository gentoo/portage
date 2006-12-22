# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

from cache import fs_template
from cache import cache_errors
import errno, os, stat
from cache.template import reconstruct_eclasses
# store the current key order *here*.
class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.location = os.path.join(self.location, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if not self.readonly and not os.path.exists(self.location):
			self._ensure_dirs()

	def __getitem__(self, cpv):
		fp = os.path.join(self.location, cpv)
		try:
			myf = open(fp, "r")
			try:
				d = self._parse_data(myf, cpv)
				if "_mtime_" not in d:
					"""Backward compatibility with old cache that uses mtime
					mangling."""
					d["_mtime_"] = long(os.fstat(myf.fileno()).st_mtime)
				return d
			finally:
				myf.close()
		except (IOError, OSError), e:
			if e.errno != errno.ENOENT:
				raise cache_errors.CacheCorruption(cpv, e)
			raise KeyError(cpv)

	def _parse_data(self, data, cpv):
		try:
			d = dict(map(lambda x:x.rstrip("\n").split("=", 1), data))
		except ValueError, e:
			# If a line is missing an "=", the split length is 1 instead of 2.
			raise cache_errors.CacheCorruption(cpv, e)
		if "_eclasses_" in d:
			d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"])
		return d
		
		for x in self._known_keys:
			if x not in d:
				d[x] = ''


		return d


	def _setitem(self, cpv, values):
#		import pdb;pdb.set_trace()
		s = cpv.rfind("/")
		fp = os.path.join(self.location,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:	myf=open(fp, "w")
		except (IOError, OSError), e:
			if errno.ENOENT == e.errno:
				try:
					self._ensure_dirs(cpv)
					myf=open(fp,"w")
				except (OSError, IOError),e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

		for k, v in values.iteritems():
			if k != "_mtime_" and (k == "_eclasses_" or k in self._known_keys):
				myf.write("%s=%s\n" % (k, v))

		myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])

		#update written.  now we move it.

		new_fp = os.path.join(self.location,cpv)
		try:	os.rename(fp, new_fp)
		except (OSError, IOError), e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
#		import pdb;pdb.set_trace()
		try:
			os.remove(os.path.join(self.location,cpv))
		except OSError, e:
			if errno.ENOENT == e.errno:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def __contains__(self, cpv):
		return os.path.exists(os.path.join(self.location, cpv))


	def iterkeys(self):
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

