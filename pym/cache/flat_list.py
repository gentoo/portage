import fs_template
import cache_errors
import os, stat

# store the current key order *here*.
class database(fs_template.FsBased):

	autocommits = True

	# do not screw with this ordering. _eclasses_ needs to be last
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE','_eclasses_')

	def __init__(self, label, auxdbkeys, **config):
		super(database,self).__init__(label, auxdbkeys, **config)
		self._base = os.path.join(self._base, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if len(self._known_keys) > len(self.auxdbkey_order) + 2:
			raise Exception("less ordered keys then auxdbkeys")
		if not os.path.exists(self._base):
			self._ensure_dirs()


	def _getitem(self, cpv):
		d = {}
		try:
			myf = open(os.path.join(self._base, cpv),"r")
			for k,v in zip(self.auxdbkey_order, myf):
				d[k] = v.rstrip("\n")
		except (OSError, IOError),e:
			if isinstance(e,IOError) and e.errno == 2:
#				print "caught for %s" % cpv, e
#				l=os.listdir(os.path.dirname(os.path.join(self._base,cpv)))
#				l.sort()
#				print l
				raise KeyError(cpv)
			raise cache_errors.CacheCorruption(cpv, e)

		try:	d["_mtime_"] = os.fstat(myf.fileno()).st_mtime
		except OSError, e:	
			myf.close()
			raise cache_errors.CacheCorruption(cpv, e)
		myf.close()
		return d


	def _setitem(self, cpv, values):
		s = cpv.rfind("/")
		fp=os.path.join(self._base,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:	myf=open(fp, "w")
		except (OSError, IOError), e:
			if e.errno == 2:
				try:
					self._ensure_dirs(cpv)
					myf=open(fp,"w")
				except (OSError, IOError),e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)
		

		for x in self.auxdbkey_order:
			myf.write(values.get(x,"")+"\n")

		myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])
		#update written.  now we move it.
		new_fp = os.path.join(self._base,cpv)
		try:	os.rename(fp, new_fp)
		except (OSError, IOError), e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
		try:
			os.remove(os.path.join(self._base,cpv))
		except OSError, e:
			if e.errno == 2:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def has_key(self, cpv):
		return os.path.exists(os.path.join(self._base, cpv))


	def iterkeys(self):
		"""generator for walking the dir struct"""
		dirs = [self._base]
		len_base = len(self._base)
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
