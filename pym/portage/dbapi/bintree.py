from portage.dep import isvalidatom, isjustname, dep_getkey, match_from_list
from portage.dbapi.virtual import fakedbapi
from portage.exception import InvalidPackageName, InvalidAtom
from portage.output import green
from portage.util import normalize_path, writemsg, writemsg_stdout
from portage.versions import best, catpkgsplit, catsplit
from portage.update import update_dbentries

from portage import listdir, dep_expand

import portage.xpak, portage.getbinpkg

import os, errno, stat

class bindbapi(fakedbapi):
	def __init__(self, mybintree=None, settings=None):
		self.bintree = mybintree
		self.move_ent = mybintree.move_ent
		self.cpvdict={}
		self.cpdict={}
		if settings is None:
			from portage import settings
		self.settings = settings
		self._match_cache = {}
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(["SLOT"])
		self._aux_cache = {}

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def aux_get(self, mycpv, wants):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		cache_me = False
		if not set(wants).difference(self._aux_cache_keys):
			aux_cache = self._aux_cache.get(mycpv)
			if aux_cache is not None:
				return [aux_cache[x] for x in wants]
			cache_me = True
		mysplit = mycpv.split("/")
		mylist = []
		tbz2name = mysplit[1]+".tbz2"
		if not self.bintree._remotepkgs or \
			not self.bintree.isremote(mycpv):
			tbz2_path = self.bintree.getname(mycpv)
			if not os.path.exists(tbz2_path):
				raise KeyError(mycpv)
			getitem = portage.xpak.tbz2(tbz2_path).getfile
		else:
			getitem = self.bintree._remotepkgs[mycpv].get
		mydata = {}
		mykeys = wants
		if cache_me:
			mykeys = self._aux_cache_keys.union(wants)
		for x in mykeys:
			myval = getitem(x)
			# myval is None if the key doesn't exist
			# or the tbz2 is corrupt.
			if myval:
				mydata[x] = " ".join(myval.split())
		if "EAPI" in mykeys:
			if not mydata.setdefault("EAPI", "0"):
				mydata["EAPI"] = "0"
		if cache_me:
			aux_cache = {}
			for x in self._aux_cache_keys:
				aux_cache[x] = mydata.get(x, "")
			self._aux_cache[mycpv] = aux_cache
		return [mydata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		if not self.bintree.populated:
			self.bintree.populate()
		tbz2path = self.bintree.getname(cpv)
		if not os.path.exists(tbz2path):
			raise KeyError(cpv)
		mytbz2 = portage.xpak.tbz2(tbz2path)
		mydata = mytbz2.get_data()
		mydata.update(values)
		for k, v in mydata.items():
			if not v:
				del mydata[k]
		mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))
		self.bintree.inject(cpv)

	def cp_list(self, *pargs, **kwargs):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_list(self, *pargs, **kwargs)

	def cp_all(self):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_all(self)

	def cpv_all(self):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cpv_all(self)

class binarytree(object):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self, root, pkgdir, virtual=None, settings=None, clone=None):
		if clone:
			writemsg("binartree.__init__(): deprecated " + \
				"use of clone parameter\n", noiselevel=-1)
			# XXX This isn't cloning. It's an instance of the same thing.
			self.root = clone.root
			self.pkgdir = clone.pkgdir
			self.dbapi = clone.dbapi
			self.populated = clone.populated
			self.tree = clone.tree
			self.remotepkgs = clone.remotepkgs
			self.invalids = clone.invalids
			self.settings = clone.settings
		else:
			self.root = root
			#self.pkgdir=settings["PKGDIR"]
			self.pkgdir = normalize_path(pkgdir)
			self.dbapi = bindbapi(self, settings=settings)
			self.update_ents = self.dbapi.update_ents
			self.move_slot_ent = self.dbapi.move_slot_ent
			self.populated = 0
			self.tree = {}
			self._remote_has_index = False
			self._remotepkgs = None # remote metadata indexed by cpv
			self.remotepkgs = {}  # indexed by tbz2 name (deprecated)
			self.invalids = []
			self.settings = settings
			self._pkg_paths = {}
			self._all_directory = os.path.isdir(
				os.path.join(self.pkgdir, "All"))
			self._pkgindex_version = 0
			self._pkgindex_hashes = ["MD5","SHA1"]
			self._pkgindex_file = os.path.join(self.pkgdir, "Packages")
			self._pkgindex_keys = set(["CPV", "SLOT", "MTIME", "SIZE"])
			self._pkgindex_header_keys = set(["ACCEPT_KEYWORDS", "CBUILD",
				"CHOST", "CONFIG_PROTECT", "CONFIG_PROTECT_MASK", "FEATURES",
				"GENTOO_MIRRORS", "INSTALL_MASK", "SYNC", "USE"])

	def move_ent(self, mylist):
		if not self.populated:
			self.populate()
		origcp = mylist[1]
		newcp = mylist[2]
		# sanity check
		for cp in [origcp, newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise InvalidPackageName(cp)
		origcat = origcp.split("/")[0]
		mynewcat = newcp.split("/")[0]
		origmatches=self.dbapi.cp_list(origcp)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:

			mycpsplit = catpkgsplit(mycpv)
			mynewcpv = newcp + "-" + mycpsplit[2]
			if mycpsplit[3] != "r0":
				mynewcpv += "-" + mycpsplit[3]
			myoldpkg = mycpv.split("/")[1]
			mynewpkg = mynewcpv.split("/")[1]

			if (mynewpkg != myoldpkg) and os.path.exists(self.getname(mynewcpv)):
				writemsg("!!! Cannot update binary: Destination exists.\n",
					noiselevel=-1)
				writemsg("!!! "+mycpv+" -> "+mynewcpv+"\n", noiselevel=-1)
				continue

			tbz2path = self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n",
					noiselevel=-1)
				continue

			moves += 1
			mytbz2 = portage.xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			updated_items = update_dbentries([mylist], mydata)
			mydata.update(updated_items)
			mydata["CATEGORY"] = mynewcat+"\n"
			if mynewpkg != myoldpkg:
				mydata[mynewpkg+".ebuild"] = mydata[myoldpkg+".ebuild"]
				del mydata[myoldpkg+".ebuild"]
				mydata["PF"] = mynewpkg + "\n"
			mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))

			self.dbapi.cpv_remove(mycpv)
			del self._pkg_paths[mycpv]
			new_path = self.getname(mynewcpv)
			self._pkg_paths[mynewcpv] = os.path.join(
				*new_path.split(os.path.sep)[-2:])
			if new_path != mytbz2:
				try:
					os.makedirs(os.path.dirname(new_path))
				except OSError, e:
					if e.errno != errno.EEXIST:
						raise
					del e
				os.rename(tbz2path, new_path)
				self._remove_symlink(mycpv)
				if new_path.split(os.path.sep)[-2] == "All":
					self._create_symlink(mynewcpv)
			self.inject(mynewcpv)

		return moves

	def _remove_symlink(self, cpv):
		"""Remove a ${PKGDIR}/${CATEGORY}/${PF}.tbz2 symlink and also remove
		the ${PKGDIR}/${CATEGORY} directory if empty.  The file will not be
		removed if os.path.islink() returns False."""
		mycat, mypkg = catsplit(cpv)
		mylink = os.path.join(self.pkgdir, mycat, mypkg + ".tbz2")
		if os.path.islink(mylink):
			"""Only remove it if it's really a link so that this method never
			removes a real package that was placed here to avoid a collision."""
			os.unlink(mylink)
		try:
			os.rmdir(os.path.join(self.pkgdir, mycat))
		except OSError, e:
			if e.errno not in (errno.ENOENT,
				errno.ENOTEMPTY, errno.EEXIST):
				raise
			del e

	def _create_symlink(self, cpv):
		"""Create a ${PKGDIR}/${CATEGORY}/${PF}.tbz2 symlink (and
		${PKGDIR}/${CATEGORY} directory, if necessary).  Any file that may
		exist in the location of the symlink will first be removed."""
		mycat, mypkg = catsplit(cpv)
		full_path = os.path.join(self.pkgdir, mycat, mypkg + ".tbz2")
		try:
			os.makedirs(os.path.dirname(full_path))
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise
			del e
		try:
			os.unlink(full_path)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			del e
		os.symlink(os.path.join("..", "All", mypkg + ".tbz2"), full_path)

	def prevent_collision(self, cpv):
		"""Make sure that the file location ${PKGDIR}/All/${PF}.tbz2 is safe to
		use for a given cpv.  If a collision will occur with an existing
		package from another category, the existing package will be bumped to
		${PKGDIR}/${CATEGORY}/${PF}.tbz2 so that both can coexist."""
		if not self._all_directory:
			return
		full_path = self.getname(cpv)
		if "All" == full_path.split(os.path.sep)[-2]:
			return
		"""Move a colliding package if it exists.  Code below this point only
		executes in rare cases."""
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		mypath = os.path.join("All", myfile)
		dest_path = os.path.join(self.pkgdir, mypath)
		if os.path.exists(dest_path):
			# For invalid packages, other_cat could be None.
			other_cat = portage.xpak.tbz2(dest_path).getfile("CATEGORY")
			if other_cat:
				other_cat = other_cat.strip()
				other_cpv = other_cat + "/" + mypkg
				self._move_from_all(other_cpv)
				self.inject(other_cpv)
		"""The file may or may not exist. Move it if necessary and update
		internal state for future calls to getname()."""
		self._move_to_all(cpv)
		if os.path.exists(full_path):
			self.inject(cpv)

	def _move_to_all(self, cpv):
		"""If the file exists, move it.  Whether or not it exists, update state
		for future getname() calls."""
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		src_path = os.path.join(self.pkgdir, mycat, myfile)
		try:
			mystat = os.lstat(src_path)
		except OSError, e:
			mystat = None
		if mystat and stat.S_ISREG(mystat.st_mode):
			try:
				os.makedirs(os.path.join(self.pkgdir, "All"))
			except OSError, e:
				if e.errno != errno.EEXIST:
					raise
				del e
			os.rename(src_path, os.path.join(self.pkgdir, "All", myfile))
			self._create_symlink(cpv)
		self._pkg_paths[cpv] = os.path.join("All", myfile)

	def _move_from_all(self, cpv):
		"""Move a package from ${PKGDIR}/All/${PF}.tbz2 to
		${PKGDIR}/${CATEGORY}/${PF}.tbz2 and update state from getname calls."""
		self._remove_symlink(cpv)
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		mypath = os.path.join(mycat, myfile)
		dest_path = os.path.join(self.pkgdir, mypath)
		try:
			os.makedirs(os.path.dirname(dest_path))
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise
			del e
		os.rename(os.path.join(self.pkgdir, "All", myfile), dest_path)
		self._pkg_paths[cpv] = mypath

	def populate(self, getbinpkgs=0, getbinpkgsonly=0):
		"populates the binarytree"
		from portage.locks import lockfile, unlockfile
		pkgindex_lock = None
		try:
			if os.access(self.pkgdir, os.W_OK):
				pkgindex_lock = lockfile(self._pkgindex_file,
					wantnewlockfile=1)
			self._populate(getbinpkgs, getbinpkgsonly)
		finally:
			if pkgindex_lock:
				unlockfile(pkgindex_lock)

	def _populate(self, getbinpkgs=0, getbinpkgsonly=0):
		if (not os.path.isdir(self.pkgdir) and not getbinpkgs):
			return 0

		categories = set(self.settings.categories)

		if not getbinpkgsonly:
			pkg_paths = {}
			dirs = listdir(self.pkgdir, dirsonly=True, EmptyOnError=True)
			if "All" in dirs:
				dirs.remove("All")
			dirs.sort()
			dirs.insert(0, "All")
			pkgindex = portage.getbinpkg.PackageIndex()
			pf_index = None
			try:
				f = open(self._pkgindex_file)
			except EnvironmentError:
				pass
			else:
				try:
					pkgindex.read(f)
				finally:
					f.close()
					del f
			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = portage.getbinpkg.PackageIndex()
			header = pkgindex.header
			metadata = pkgindex.packages
			update_pkgindex = False
			for mydir in dirs:
				for myfile in listdir(os.path.join(self.pkgdir, mydir)):
					if not myfile.endswith(".tbz2"):
						continue
					mypath = os.path.join(mydir, myfile)
					full_path = os.path.join(self.pkgdir, mypath)
					s = os.lstat(full_path)
					if stat.S_ISLNK(s.st_mode):
						continue

					# Validate data from the package index and try to avoid
					# reading the xpak if possible.
					if mydir != "All":
						possibilities = None
						d = metadata.get(mydir+"/"+myfile[:-5])
						if d:
							possibilities = [d]
					else:
						if pf_index is None:
							pf_index = {}
							for mycpv in metadata:
								mycat, mypf = catsplit(mycpv)
								pf_index.setdefault(
									mypf, []).append(metadata[mycpv])
						possibilities = pf_index.get(myfile[:-5])
					if possibilities:
						match = None
						for d in possibilities:
							try:
								if long(d["MTIME"]) != long(s.st_mtime):
									continue
							except (KeyError, ValueError):
								continue
							try:
								if long(d["SIZE"]) != long(s.st_size):
									continue
							except (KeyError, ValueError):
								continue
							if not self._pkgindex_keys.difference(d):
								match = d
								break
						if match:
							mycpv = match["CPV"]
							if mycpv in pkg_paths:
								# discard duplicates (All/ is preferred)
								continue
							pkg_paths[mycpv] = mypath
							# update the path if the package has been moved
							oldpath = d.get("PATH")
							if oldpath and oldpath != mypath:
								update_pkgindex = True
							if mypath != mycpv + ".tbz2":
								d["PATH"] = mypath
								if not oldpath:
									update_pkgindex = True
							else:
								d.pop("PATH", None)
								if oldpath:
									update_pkgindex = True
							self.dbapi.cpv_inject(mycpv)
							if not self.dbapi._aux_cache_keys.difference(d):
								aux_cache = {}
								for k in self.dbapi._aux_cache_keys:
									aux_cache[k] = d[k]
								self.dbapi._aux_cache[mycpv] = aux_cache
							continue
					mytbz2 = portage.xpak.tbz2(full_path)
					# For invalid packages, mycat could be None.
					mycat = mytbz2.getfile("CATEGORY")
					mypf = mytbz2.getfile("PF")
					slot = mytbz2.getfile("SLOT")
					mypkg = myfile[:-5]
					if not mycat or not mypf or not slot:
						#old-style or corrupt package
						writemsg("!!! Invalid binary package: '%s'\n" % full_path,
							noiselevel=-1)
						writemsg("!!! This binary package is not " + \
							"recoverable and should be deleted.\n",
							noiselevel=-1)
						self.invalids.append(mypkg)
						continue
					mycat = mycat.strip()
					slot = slot.strip()
					if mycat != mydir and mydir != "All":
						continue
					if mypkg != mypf.strip():
						continue
					mycpv = mycat + "/" + mypkg
					if mycpv in pkg_paths:
						# All is first, so it's preferred.
						continue
					if mycat not in categories:
						writemsg(("!!! Binary package has an " + \
							"unrecognized category: '%s'\n") % full_path,
							noiselevel=-1)
						writemsg(("!!! '%s' has a category that is not" + \
							" listed in /etc/portage/categories\n") % mycpv,
							noiselevel=-1)
						continue
					pkg_paths[mycpv] = mypath
					self.dbapi.cpv_inject(mycpv)
					update_pkgindex = True
					d = metadata.get(mycpv, {})
					if d:
						try:
							if long(d["MTIME"]) != long(s.st_mtime):
								d.clear()
						except (KeyError, ValueError):
							d.clear()
					if d:
						try:
							if long(d["SIZE"]) != long(s.st_size):
								d.clear()
						except (KeyError, ValueError):
							d.clear()

					d["CPV"] = mycpv
					d["SLOT"] = slot
					d["MTIME"] = str(long(s.st_mtime))
					d["SIZE"] = str(s.st_size)
					# record location if it's non-default
					if mypath != mycpv + ".tbz2":
						d["PATH"] = mypath
					else:
						d.pop("PATH", None)
					metadata[mycpv] = d
					if not self.dbapi._aux_cache_keys.difference(d):
						aux_cache = {}
						for k in self.dbapi._aux_cache_keys:
							aux_cache[k] = d[k]
						self.dbapi._aux_cache[mycpv] = aux_cache

			self._pkg_paths = pkg_paths
			# Do not bother to write the Packages index if $PKGDIR/All/ exists
			# since it will provide no benefit due to the need to read CATEGORY
			# from xpak.
			if update_pkgindex and os.access(self.pkgdir, os.W_OK):
				cpv_all = self._pkg_paths.keys()
				stale = set(metadata).difference(cpv_all)
				for cpv in stale:
					del metadata[cpv]
				from portage.util import atomic_ofstream
				f = atomic_ofstream(self._pkgindex_file)
				try:
					pkgindex.write(f)
				finally:
					f.close()

		if getbinpkgs and not self.settings["PORTAGE_BINHOST"]:
			writemsg("!!! PORTAGE_BINHOST unset, but use is requested.\n",
				noiselevel=-1)

		if getbinpkgs and \
			"PORTAGE_BINHOST" in self.settings and \
			not self._remotepkgs:

			base_url = self.settings["PORTAGE_BINHOST"]
			from portage.const import CACHE_PATH
			from urlparse import urlparse
			urldata = urlparse(base_url)
			pkgindex_file = os.path.join(CACHE_PATH, "binhost",
				urldata[1] + urldata[2], "Packages")
			pkgindex = portage.getbinpkg.PackageIndex()
			try:
				f = open(pkgindex_file)
				try:
					pkgindex.read(f)
				finally:
					f.close()
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
			local_timestamp = pkgindex.header.get("TIMESTAMP", None)
			import urllib, urlparse
			rmt_idx = portage.getbinpkg.PackageIndex()
			try:
				f = urllib.urlopen(urlparse.urljoin(base_url, "Packages"))
				try:
					rmt_idx.readHeader(f)
					remote_timestamp = rmt_idx.header.get("TIMESTAMP", None)
					if not remote_timestamp:
						# no timestamp in the header, something's wrong
						pkgindex = None
					else:
						if not self._pkgindex_version_supported(rmt_idx):
							writemsg("\n\n!!! Binhost package index version" + \
							" is not supported: '%s'\n" % \
							rmt_idx.header.get("VERSION"), noiselevel=-1)
							pkgindex = None
						elif local_timestamp != remote_timestamp:
							rmt_idx.readBody(f)
							pkgindex = rmt_idx
				finally:
					f.close()
			except EnvironmentError, e:
				writemsg("\n\n!!! Error fetching binhost package" + \
					" info from '%s'\n" % base_url)
				writemsg("!!! %s\n\n" % str(e))
				del e
				pkgindex = None
			if pkgindex is rmt_idx:
				pkgindex.modified = False # don't update the header
				from portage.util import atomic_ofstream, ensure_dirs
				ensure_dirs(os.path.dirname(pkgindex_file))
				f = atomic_ofstream(pkgindex_file)
				try:
					pkgindex.write(f)
				finally:
					f.close()
			if pkgindex:
				self._remotepkgs = pkgindex.packages
				self._remote_has_index = True
				self.remotepkgs = {}
				for cpv in self._remotepkgs:
					self.dbapi.cpv_inject(cpv)
				self.populated = 1
				return
			self._remotepkgs = {}
			try:
				chunk_size = long(self.settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except (ValueError, KeyError):
				chunk_size = 3000
			writemsg_stdout(green("Fetching binary packages info...\n"))
			self.remotepkgs = portage.getbinpkg.dir_get_metadata(
				self.settings["PORTAGE_BINHOST"], chunk_size=chunk_size)
			writemsg(green("  -- DONE!\n\n"))

			for mypkg in self.remotepkgs.keys():
				if not self.remotepkgs[mypkg].has_key("CATEGORY"):
					#old-style or corrupt package
					writemsg("!!! Invalid remote binary package: "+mypkg+"\n",
						noiselevel=-1)
					del self.remotepkgs[mypkg]
					continue
				mycat = self.remotepkgs[mypkg]["CATEGORY"].strip()
				fullpkg = mycat+"/"+mypkg[:-5]
				if mycat not in categories:
					writemsg(("!!! Remote binary package has an " + \
						"unrecognized category: '%s'\n") % fullpkg,
						noiselevel=-1)
					writemsg(("!!! '%s' has a category that is not" + \
						" listed in /etc/portage/categories\n") % fullpkg,
						noiselevel=-1)
					continue
				mykey = dep_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					#print "cpv_inject("+str(fullpkg)+")"
					self.dbapi.cpv_inject(fullpkg)
					metadata = self.remotepkgs[mypkg]
					for k, v in metadata.items():
						metadata[k] = v.strip()
					self._remotepkgs[fullpkg] = metadata
					#print "  -- Injected"
				except SystemExit, e:
					raise
				except:
					writemsg("!!! Failed to inject remote binary package:"+str(fullpkg)+"\n",
						noiselevel=-1)
					del self.remotepkgs[mypkg]
					continue
		self.populated=1

	def inject(self, cpv, filename=None):
		"""Add a freshly built package to the database.  This updates
		$PKGDIR/Packages with the new package metadata (including MD5).
		@param cpv: The cpv of the new package to inject
		@type cpv: string
		@param filename: File path of the package to inject, or None if it's
			already in the location returned by getname()
		@type filename: string
		@rtype: None
		"""
		mycat, mypkg = catsplit(cpv)
		if not self.populated:
			self.populate()
		if filename is None:
			full_path = self.getname(cpv)
		else:
			full_path = filename
		try:
			s = os.stat(full_path)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			del e
			writemsg("!!! Binary package does not exist: '%s'\n" % full_path,
				noiselevel=-1)
			return
		mytbz2 = portage.xpak.tbz2(full_path)
		slot = mytbz2.getfile("SLOT")
		if slot is None:
			writemsg("!!! Invalid binary package: '%s'\n" % full_path,
				noiselevel=-1)
			return
		slot = slot.strip()
		from portage.checksum import perform_multiple_checksums
		digests = perform_multiple_checksums(
			full_path, hashes=self._pkgindex_hashes)
		self.dbapi.cpv_inject(cpv)
		self.dbapi._aux_cache.pop(cpv, None)

		# Reread the Packages index (in case it's been changed by another
		# process) and then updated it, all while holding a lock.
		from portage.locks import lockfile, unlockfile
		pkgindex_lock = None
		try:
			pkgindex_lock = lockfile(self._pkgindex_file,
				wantnewlockfile=1)
			if filename is not None:
				os.rename(filename, self.getname(cpv))
			if self._all_directory and \
				self.getname(cpv).split(os.path.sep)[-2] == "All":
				self._create_symlink(cpv)
			pkgindex = portage.getbinpkg.PackageIndex()
			try:
				f = open(self._pkgindex_file)
			except EnvironmentError:
				pass
			else:
				try:
					pkgindex.read(f)
				finally:
					f.close()
					del f
			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = portage.getbinpkg.PackageIndex()
			d = digests
			d["CPV"] = cpv
			d["SLOT"] = slot
			d["MTIME"] = str(long(s.st_mtime))
			d["SIZE"] = str(s.st_size)
			rel_path = self._pkg_paths[cpv]
			# record location if it's non-default
			if rel_path != cpv + ".tbz2":
				d["PATH"] = rel_path
			keys = ["USE", "IUSE", "DESCRIPTION", "LICENSE", "PROVIDE", \
				"RDEPEND", "DEPEND", "PDEPEND"]
			from itertools import izip
			d.update(izip(keys, self.dbapi.aux_get(cpv, keys)))
			use = d["USE"].split()
			iuse = set(d["IUSE"].split())
			use = [f for f in use if f in iuse]
			if not iuse:
				del d["IUSE"]
			use.sort()
			d["USE"] = " ".join(use)
			d["DESC"] = d["DESCRIPTION"]
			del d["DESCRIPTION"]
			from portage.dep import paren_reduce, use_reduce, \
				paren_normalize, paren_enclose
			for k in "LICENSE", "RDEPEND", "DEPEND", "PDEPEND", "PROVIDE":
				deps = paren_reduce(d[k])
				deps = use_reduce(deps, uselist=use)
				deps = paren_normalize(deps)
				deps = paren_enclose(deps)
				if deps:
					d[k] = deps
				else:
					del d[k]
			pkgindex.packages[cpv] = d
			self._update_pkgindex_header(pkgindex.header)
			from portage.util import atomic_ofstream
			f = atomic_ofstream(os.path.join(self.pkgdir, "Packages"))
			try:
				pkgindex.write(f)
			finally:
				f.close()
		finally:
			if pkgindex_lock:
				unlockfile(pkgindex_lock)

	def _update_pkgindex_header(self, header):
		portdir = normalize_path(os.path.realpath(self.settings["PORTDIR"]))
		profiles_base = os.path.join(portdir, "profiles")
		profile_path = normalize_path(os.path.realpath(self.settings.profile_path))
		profile_path = profile_path.lstrip(profiles_base)
		header["PROFILE"] = profile_path
		header["VERSION"] = str(self._pkgindex_version)
		for k in self._pkgindex_header_keys:
			v = self.settings.get(k, None)
			if v:
				header[k] = v
			else:
				header.pop(k, None)

	def _pkgindex_version_supported(self, pkgindex):
		version = pkgindex.header.get("VERSION")
		if version:
			try:
				if int(version) <= self._pkgindex_version:
					return True
			except ValueError:
				pass
		return False

	def exists_specific(self, cpv):
		if not self.populated:
			self.populate()
		return self.dbapi.match(
			dep_expand("="+cpv, mydb=self.dbapi, settings=self.settings))

	def dep_bestmatch(self, mydep):
		"compatibility method -- all matches, not just visible ones"
		if not self.populated:
			self.populate()
		writemsg("\n\n", 1)
		writemsg("mydep: %s\n" % mydep, 1)
		mydep = dep_expand(mydep, mydb=self.dbapi, settings=self.settings)
		writemsg("mydep: %s\n" % mydep, 1)
		mykey = dep_getkey(mydep)
		writemsg("mykey: %s\n" % mykey, 1)
		mymatch = best(match_from_list(mydep,self.dbapi.cp_list(mykey)))
		writemsg("mymatch: %s\n" % mymatch, 1)
		if mymatch is None:
			return ""
		return mymatch

	def getname(self, pkgname):
		"""Returns a file location for this package.  The default location is
		${PKGDIR}/All/${PF}.tbz2, but will be ${PKGDIR}/${CATEGORY}/${PF}.tbz2
		in the rare event of a collision.  The prevent_collision() method can
		be called to ensure that ${PKGDIR}/All/${PF}.tbz2 is available for a
		specific cpv."""
		if not self.populated:
			self.populate()
		mycpv = pkgname
		mypath = self._pkg_paths.get(mycpv, None)
		if mypath:
			return os.path.join(self.pkgdir, mypath)
		mycat, mypkg = catsplit(mycpv)
		if self._all_directory:
			mypath = os.path.join("All", mypkg + ".tbz2")
			if mypath in self._pkg_paths.values():
				mypath = os.path.join(mycat, mypkg + ".tbz2")
		else:
			mypath = os.path.join(mycat, mypkg + ".tbz2")
		self._pkg_paths[mycpv] = mypath # cache for future lookups
		return os.path.join(self.pkgdir, mypath)

	def isremote(self, pkgname):
		"Returns true if the package is kept remotely."
		remote = pkgname in self._remotepkgs and \
			not os.path.exists(self.getname(pkgname))
		return remote

	def get_use(self, pkgname):
		writemsg("deprecated use of binarytree.get_use()," + \
			" use dbapi.aux_get() instead", noiselevel=-1)
		return self.dbapi.aux_get(pkgname, ["USE"])[0].split()

	def gettbz2(self, pkgname):
		"fetches the package from a remote site, if necessary."
		print "Fetching '"+str(pkgname)+"'"
		mysplit  = pkgname.split("/")
		tbz2name = mysplit[1]+".tbz2"
		if not self.isremote(pkgname):
			if (tbz2name not in self.invalids):
				return
			else:
				writemsg("Resuming download of this tbz2, but it is possible that it is corrupt.\n",
					noiselevel=-1)
		tbz2_path = self.getname(pkgname)
		mydest = os.path.dirname(self.getname(pkgname))
		try:
			os.makedirs(mydest, 0775)
		except (OSError, IOError):
			pass
		from urlparse import urljoin
		base_url = self.settings["PORTAGE_BINHOST"]
		fcmd = self.settings["RESUMECOMMAND"]
		if self._remote_has_index:
			rel_url = self._remotepkgs[pkgname].get("PATH")
			if not rel_url:
				rel_url = pkgname+".tbz2"
			url = urljoin(base_url, rel_url)
			success = portage.getbinpkg.file_get(url, mydest, fcmd=fcmd)
		else:
			url = urljoin(base_url, tbz2name)
			success = portage.getbinpkg.file_get(url, mydest, fcmd=fcmd)
		if success and "strict" in self.settings.features:
			metadata = self._remotepkgs[pkgname]
			digests = {}
			from portage.checksum import hashfunc_map, verify_all
			for k in hashfunc_map:
				v = metadata.get(k)
				if not v:
					continue
				digests[k] = v
			if "SIZE" in metadata:
				try:
					digests["size"] = long(self._remotepkgs[pkgname]["SIZE"])
				except ValueError:
					writemsg("!!! Malformed SIZE attribute in remote " + \
					"metadata for '%s'\n" % pkgname)
			if digests:
				ok, reason = verify_all(tbz2_path, digests)
				if not ok:
					raise portage.exception.DigestException(
						tuple([tbz2_path]+list(reason)))
		if not success:
			try:
				os.unlink(self.getname(pkgname))
			except OSError:
				pass
			raise portage.exception.FileNotFound(mydest)
		self.inject(pkgname)

	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		myslot = ""
		try:
			myslot = self.dbapi.aux_get(mycatpkg,["SLOT"])[0]
		except SystemExit, e:
			raise
		except Exception, e:
			pass
		return myslot
