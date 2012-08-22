# Copyright 1998-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["bindbapi", "binarytree"]

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.checksum:hashfunc_map,perform_multiple_checksums,' + \
		'verify_all,_apply_hash_filter,_hash_filter',
	'portage.dbapi.dep_expand:dep_expand',
	'portage.dep:dep_getkey,isjustname,isvalidatom,match_from_list',
	'portage.output:EOutput,colorize',
	'portage.locks:lockfile,unlockfile',
	'portage.package.ebuild.fetch:_check_distfile,_hide_url_passwd',
	'portage.update:update_dbentries',
	'portage.util:atomic_ofstream,ensure_dirs,normalize_path,' + \
		'writemsg,writemsg_stdout',
	'portage.util.listdir:listdir',
	'portage.util._urlopen:urlopen@_urlopen',
	'portage.versions:best,catpkgsplit,catsplit,_pkg_str',
)

from portage.cache.mappings import slot_dict_class
from portage.const import CACHE_PATH
from portage.dbapi.virtual import fakedbapi
from portage.dep import Atom, use_reduce, paren_enclose
from portage.exception import AlarmSignal, InvalidData, InvalidPackageName, \
	PermissionDenied, PortageException
from portage.localization import _
from portage import _movefile
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode

import codecs
import errno
import io
import stat
import subprocess
import sys
import tempfile
import textwrap
import warnings
from gzip import GzipFile
from itertools import chain
try:
	from urllib.parse import urlparse
except ImportError:
	from urlparse import urlparse

if sys.hexversion >= 0x3000000:
	_unicode = str
	basestring = str
	long = int
else:
	_unicode = unicode

class UseCachedCopyOfRemoteIndex(Exception):
	# If the local copy is recent enough
	# then fetching the remote index can be skipped.
	pass

class bindbapi(fakedbapi):
	_known_keys = frozenset(list(fakedbapi._known_keys) + \
		["CHOST", "repository", "USE"])
	def __init__(self, mybintree=None, **kwargs):
		fakedbapi.__init__(self, **kwargs)
		self.bintree = mybintree
		self.move_ent = mybintree.move_ent
		self.cpvdict={}
		self.cpdict={}
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(
			["BUILD_TIME", "CHOST", "DEPEND", "EAPI", "IUSE", "KEYWORDS",
			"LICENSE", "PDEPEND", "PROPERTIES", "PROVIDE",
			"RDEPEND", "repository", "RESTRICT", "SLOT", "USE", "DEFINED_PHASES",
			])
		self._aux_cache_slot_dict = slot_dict_class(self._aux_cache_keys)
		self._aux_cache = {}

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def cpv_exists(self, cpv, myrepo=None):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cpv_exists(self, cpv)

	def cpv_inject(self, cpv, **kwargs):
		self._aux_cache.pop(cpv, None)
		fakedbapi.cpv_inject(self, cpv, **kwargs)

	def cpv_remove(self, cpv):
		self._aux_cache.pop(cpv, None)
		fakedbapi.cpv_remove(self, cpv)

	def aux_get(self, mycpv, wants, myrepo=None):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		cache_me = False
		if not self._known_keys.intersection(
			wants).difference(self._aux_cache_keys):
			aux_cache = self._aux_cache.get(mycpv)
			if aux_cache is not None:
				return [aux_cache.get(x, "") for x in wants]
			cache_me = True
		mysplit = mycpv.split("/")
		mylist = []
		tbz2name = mysplit[1]+".tbz2"
		if not self.bintree._remotepkgs or \
			not self.bintree.isremote(mycpv):
			tbz2_path = self.bintree.getname(mycpv)
			if not os.path.exists(tbz2_path):
				raise KeyError(mycpv)
			metadata_bytes = portage.xpak.tbz2(tbz2_path).get_data()
			def getitem(k):
				v = metadata_bytes.get(_unicode_encode(k,
					encoding=_encodings['repo.content'],
					errors='backslashreplace'))
				if v is not None:
					v = _unicode_decode(v,
						encoding=_encodings['repo.content'], errors='replace')
				return v
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

		if not mydata.setdefault('EAPI', _unicode_decode('0')):
			mydata['EAPI'] = _unicode_decode('0')

		if cache_me:
			aux_cache = self._aux_cache_slot_dict()
			for x in self._aux_cache_keys:
				aux_cache[x] = mydata.get(x, _unicode_decode(''))
			self._aux_cache[mycpv] = aux_cache
		return [mydata.get(x, _unicode_decode('')) for x in wants]

	def aux_update(self, cpv, values):
		if not self.bintree.populated:
			self.bintree.populate()
		tbz2path = self.bintree.getname(cpv)
		if not os.path.exists(tbz2path):
			raise KeyError(cpv)
		mytbz2 = portage.xpak.tbz2(tbz2path)
		mydata = mytbz2.get_data()

		for k, v in values.items():
			k = _unicode_encode(k,
				encoding=_encodings['repo.content'], errors='backslashreplace')
			v = _unicode_encode(v,
				encoding=_encodings['repo.content'], errors='backslashreplace')
			mydata[k] = v

		for k, v in list(mydata.items()):
			if not v:
				del mydata[k]
		mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))
		# inject will clear stale caches via cpv_inject.
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

	def getfetchsizes(self, pkg):
		"""
		This will raise MissingSignature if SIZE signature is not available,
		or InvalidSignature if SIZE signature is invalid.
		"""

		if not self.bintree.populated:
			self.bintree.populate()

		pkg = getattr(pkg, 'cpv', pkg)

		filesdict = {}
		if not self.bintree.isremote(pkg):
			pass
		else:
			metadata = self.bintree._remotepkgs[pkg]
			try:
				size = int(metadata["SIZE"])
			except KeyError:
				raise portage.exception.MissingSignature("SIZE")
			except ValueError:
				raise portage.exception.InvalidSignature(
					"SIZE: %s" % metadata["SIZE"])
			else:
				filesdict[os.path.basename(self.bintree.getname(pkg))] = size

		return filesdict

def _pkgindex_cpv_map_latest_build(pkgindex):
	"""
	Given a PackageIndex instance, create a dict of cpv -> metadata map.
	If multiple packages have identical CPV values, prefer the package
	with latest BUILD_TIME value.
	@param pkgindex: A PackageIndex instance.
	@type pkgindex: PackageIndex
	@rtype: dict
	@return: a dict containing entry for the give cpv.
	"""
	cpv_map = {}

	for d in pkgindex.packages:
		cpv = d["CPV"]

		try:
			cpv = _pkg_str(cpv)
		except InvalidData:
			writemsg(_("!!! Invalid remote binary package: %s\n") % cpv,
				noiselevel=-1)
			continue

		btime = d.get('BUILD_TIME', '')
		try:
			btime = int(btime)
		except ValueError:
			btime = None

		other_d = cpv_map.get(cpv)
		if other_d is not None:
			other_btime = other_d.get('BUILD_TIME', '')
			try:
				other_btime = int(other_btime)
			except ValueError:
				other_btime = None
			if other_btime and (not btime or other_btime > btime):
				continue

		cpv_map[_pkg_str(cpv)] = d

	return cpv_map

class binarytree(object):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self, _unused=None, pkgdir=None,
		virtual=DeprecationWarning, settings=None):

		if pkgdir is None:
			raise TypeError("pkgdir parameter is required")

		if settings is None:
			raise TypeError("settings parameter is required")

		if _unused is not None and _unused != settings['ROOT']:
			warnings.warn("The root parameter of the "
				"portage.dbapi.bintree.binarytree"
				" constructor is now unused. Use "
				"settings['ROOT'] instead.",
				DeprecationWarning, stacklevel=2)

		if virtual is not DeprecationWarning:
			warnings.warn("The 'virtual' parameter of the "
				"portage.dbapi.bintree.binarytree"
				" constructor is unused",
				DeprecationWarning, stacklevel=2)

		if True:
			self.pkgdir = normalize_path(pkgdir)
			self.dbapi = bindbapi(self, settings=settings)
			self.update_ents = self.dbapi.update_ents
			self.move_slot_ent = self.dbapi.move_slot_ent
			self.populated = 0
			self.tree = {}
			self._remote_has_index = False
			self._remotepkgs = None # remote metadata indexed by cpv
			self.invalids = []
			self.settings = settings
			self._pkg_paths = {}
			self._pkgindex_uri = {}
			self._populating = False
			self._all_directory = os.path.isdir(
				os.path.join(self.pkgdir, "All"))
			self._pkgindex_version = 0
			self._pkgindex_hashes = ["MD5","SHA1"]
			self._pkgindex_file = os.path.join(self.pkgdir, "Packages")
			self._pkgindex_keys = self.dbapi._aux_cache_keys.copy()
			self._pkgindex_keys.update(["CPV", "MTIME", "SIZE"])
			self._pkgindex_aux_keys = \
				["BUILD_TIME", "CHOST", "DEPEND", "DESCRIPTION", "EAPI",
				"IUSE", "KEYWORDS", "LICENSE", "PDEPEND", "PROPERTIES",
				"PROVIDE", "RDEPEND", "repository", "SLOT", "USE", "DEFINED_PHASES",
				"BASE_URI"]
			self._pkgindex_aux_keys = list(self._pkgindex_aux_keys)
			self._pkgindex_use_evaluated_keys = \
				("LICENSE", "RDEPEND", "DEPEND",
				"PDEPEND", "PROPERTIES", "PROVIDE")
			self._pkgindex_header_keys = set([
				"ACCEPT_KEYWORDS", "ACCEPT_LICENSE",
				"ACCEPT_PROPERTIES", "CBUILD",
				"CONFIG_PROTECT", "CONFIG_PROTECT_MASK", "FEATURES",
				"GENTOO_MIRRORS", "INSTALL_MASK", "SYNC", "USE"])
			self._pkgindex_default_pkg_data = {
				"BUILD_TIME"         : "",
				"DEPEND"  : "",
				"EAPI"    : "0",
				"IUSE"    : "",
				"KEYWORDS": "",
				"LICENSE" : "",
				"PATH"    : "",
				"PDEPEND" : "",
				"PROPERTIES" : "",
				"PROVIDE" : "",
				"RDEPEND" : "",
				"RESTRICT": "",
				"SLOT"    : "0",
				"USE"     : "",
				"DEFINED_PHASES" : "",
			}
			self._pkgindex_inherited_keys = ["CHOST", "repository"]

			# Populate the header with appropriate defaults.
			self._pkgindex_default_header_data = {
				"CHOST"        : self.settings.get("CHOST", ""),
				"repository"   : "",
			}

			# It is especially important to populate keys like
			# "repository" that save space when entries can
			# inherit them from the header. If an existing
			# pkgindex header already defines these keys, then
			# they will appropriately override our defaults.
			main_repo = self.settings.repositories.mainRepo()
			if main_repo is not None and not main_repo.missing_repo_name:
				self._pkgindex_default_header_data["repository"] = \
					main_repo.name

			self._pkgindex_translated_keys = (
				("DESCRIPTION"   ,   "DESC"),
				("repository"    ,   "REPO"),
			)

			self._pkgindex_allowed_pkg_keys = set(chain(
				self._pkgindex_keys,
				self._pkgindex_aux_keys,
				self._pkgindex_hashes,
				self._pkgindex_default_pkg_data,
				self._pkgindex_inherited_keys,
				chain(*self._pkgindex_translated_keys)
			))

	@property
	def root(self):
		warnings.warn("The root attribute of "
			"portage.dbapi.bintree.binarytree"
			" is deprecated. Use "
			"settings['ROOT'] instead.",
			DeprecationWarning, stacklevel=3)
		return self.settings['ROOT']

	def move_ent(self, mylist, repo_match=None):
		if not self.populated:
			self.populate()
		origcp = mylist[1]
		newcp = mylist[2]
		# sanity check
		for atom in (origcp, newcp):
			if not isjustname(atom):
				raise InvalidPackageName(str(atom))
		mynewcat = catsplit(newcp)[0]
		origmatches=self.dbapi.cp_list(origcp)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			try:
				mycpv = self.dbapi._pkg_str(mycpv, None)
			except (KeyError, InvalidData):
				continue
			mycpv_cp = portage.cpv_getkey(mycpv)
			if mycpv_cp != origcp:
				# Ignore PROVIDE virtual match.
				continue
			if repo_match is not None \
				and not repo_match(mycpv.repo):
				continue

			# Use isvalidatom() to check if this move is valid for the
			# EAPI (characters allowed in package names may vary).
			if not isvalidatom(newcp, eapi=mycpv.eapi):
				continue

			mynewcpv = mycpv.replace(mycpv_cp, _unicode(newcp), 1)
			myoldpkg = catsplit(mycpv)[1]
			mynewpkg = catsplit(mynewcpv)[1]

			if (mynewpkg != myoldpkg) and os.path.exists(self.getname(mynewcpv)):
				writemsg(_("!!! Cannot update binary: Destination exists.\n"),
					noiselevel=-1)
				writemsg("!!! "+mycpv+" -> "+mynewcpv+"\n", noiselevel=-1)
				continue

			tbz2path = self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg(_("!!! Cannot update readonly binary: %s\n") % mycpv,
					noiselevel=-1)
				continue

			moves += 1
			mytbz2 = portage.xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			updated_items = update_dbentries([mylist], mydata, eapi=mycpv.eapi)
			mydata.update(updated_items)
			mydata[b'PF'] = \
				_unicode_encode(mynewpkg + "\n",
				encoding=_encodings['repo.content'])
			mydata[b'CATEGORY'] = \
				_unicode_encode(mynewcat + "\n",
				encoding=_encodings['repo.content'])
			if mynewpkg != myoldpkg:
				ebuild_data = mydata.pop(_unicode_encode(myoldpkg + '.ebuild',
					encoding=_encodings['repo.content']), None)
				if ebuild_data is not None:
					mydata[_unicode_encode(mynewpkg + '.ebuild',
						encoding=_encodings['repo.content'])] = ebuild_data

			mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))

			self.dbapi.cpv_remove(mycpv)
			del self._pkg_paths[mycpv]
			new_path = self.getname(mynewcpv)
			self._pkg_paths[mynewcpv] = os.path.join(
				*new_path.split(os.path.sep)[-2:])
			if new_path != mytbz2:
				self._ensure_dir(os.path.dirname(new_path))
				_movefile(tbz2path, new_path, mysettings=self.settings)
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
		except OSError as e:
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
		self._ensure_dir(os.path.dirname(full_path))
		try:
			os.unlink(full_path)
		except OSError as e:
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

		# Copy group permissions for new directories that
		# may have been created.
		for path in ("All", catsplit(cpv)[0]):
			path = os.path.join(self.pkgdir, path)
			self._ensure_dir(path)
			if not os.access(path, os.W_OK):
				raise PermissionDenied("access('%s', W_OK)" % path)

		full_path = self.getname(cpv)
		if "All" == full_path.split(os.path.sep)[-2]:
			return
		"""Move a colliding package if it exists.  Code below this point only
		executes in rare cases."""
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		mypath = os.path.join("All", myfile)
		dest_path = os.path.join(self.pkgdir, mypath)

		try:
			st = os.lstat(dest_path)
		except OSError:
			st = None
		else:
			if stat.S_ISLNK(st.st_mode):
				st = None
				try:
					os.unlink(dest_path)
				except OSError:
					if os.path.exists(dest_path):
						raise

		if st is not None:
			# For invalid packages, other_cat could be None.
			other_cat = portage.xpak.tbz2(dest_path).getfile(b"CATEGORY")
			if other_cat:
				other_cat = _unicode_decode(other_cat,
					encoding=_encodings['repo.content'], errors='replace')
				other_cat = other_cat.strip()
				other_cpv = other_cat + "/" + mypkg
				self._move_from_all(other_cpv)
				self.inject(other_cpv)
		self._move_to_all(cpv)

	def _ensure_dir(self, path):
		"""
		Create the specified directory. Also, copy gid and group mode
		bits from self.pkgdir if possible.
		@param cat_dir: Absolute path of the directory to be created.
		@type cat_dir: String
		"""
		try:
			pkgdir_st = os.stat(self.pkgdir)
		except OSError:
			ensure_dirs(path)
			return
		pkgdir_gid = pkgdir_st.st_gid
		pkgdir_grp_mode = 0o2070 & pkgdir_st.st_mode
		try:
			ensure_dirs(path, gid=pkgdir_gid, mode=pkgdir_grp_mode, mask=0)
		except PortageException:
			if not os.path.isdir(path):
				raise

	def _move_to_all(self, cpv):
		"""If the file exists, move it.  Whether or not it exists, update state
		for future getname() calls."""
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		self._pkg_paths[cpv] = os.path.join("All", myfile)
		src_path = os.path.join(self.pkgdir, mycat, myfile)
		try:
			mystat = os.lstat(src_path)
		except OSError as e:
			mystat = None
		if mystat and stat.S_ISREG(mystat.st_mode):
			self._ensure_dir(os.path.join(self.pkgdir, "All"))
			dest_path = os.path.join(self.pkgdir, "All", myfile)
			_movefile(src_path, dest_path, mysettings=self.settings)
			self._create_symlink(cpv)
			self.inject(cpv)

	def _move_from_all(self, cpv):
		"""Move a package from ${PKGDIR}/All/${PF}.tbz2 to
		${PKGDIR}/${CATEGORY}/${PF}.tbz2 and update state from getname calls."""
		self._remove_symlink(cpv)
		mycat, mypkg = catsplit(cpv)
		myfile = mypkg + ".tbz2"
		mypath = os.path.join(mycat, myfile)
		dest_path = os.path.join(self.pkgdir, mypath)
		self._ensure_dir(os.path.dirname(dest_path))
		src_path = os.path.join(self.pkgdir, "All", myfile)
		_movefile(src_path, dest_path, mysettings=self.settings)
		self._pkg_paths[cpv] = mypath

	def populate(self, getbinpkgs=0):
		"populates the binarytree"

		if self._populating:
			return

		pkgindex_lock = None
		try:
			if os.access(self.pkgdir, os.W_OK):
				pkgindex_lock = lockfile(self._pkgindex_file,
					wantnewlockfile=1)
			self._populating = True
			self._populate(getbinpkgs)
		finally:
			if pkgindex_lock:
				unlockfile(pkgindex_lock)
			self._populating = False

	def _populate(self, getbinpkgs=0):
		if (not os.path.isdir(self.pkgdir) and not getbinpkgs):
			return 0

		# Clear all caches in case populate is called multiple times
		# as may be the case when _global_updates calls populate()
		# prior to performing package moves since it only wants to
		# operate on local packages (getbinpkgs=0).
		self._remotepkgs = None
		self.dbapi._clear_cache()
		self.dbapi._aux_cache.clear()
		if True:
			pkg_paths = {}
			self._pkg_paths = pkg_paths
			dirs = listdir(self.pkgdir, dirsonly=True, EmptyOnError=True)
			if "All" in dirs:
				dirs.remove("All")
			dirs.sort()
			dirs.insert(0, "All")
			pkgindex = self._load_pkgindex()
			pf_index = None
			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = self._new_pkgindex()
			header = pkgindex.header
			metadata = {}
			for d in pkgindex.packages:
				metadata[d["CPV"]] = d
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
								if long(d["MTIME"]) != s[stat.ST_MTIME]:
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
							mycpv = _pkg_str(mycpv)
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
								aux_cache = self.dbapi._aux_cache_slot_dict()
								for k in self.dbapi._aux_cache_keys:
									aux_cache[k] = d[k]
								self.dbapi._aux_cache[mycpv] = aux_cache
							continue
					if not os.access(full_path, os.R_OK):
						writemsg(_("!!! Permission denied to read " \
							"binary package: '%s'\n") % full_path,
							noiselevel=-1)
						self.invalids.append(myfile[:-5])
						continue
					metadata_bytes = portage.xpak.tbz2(full_path).get_data()
					mycat = _unicode_decode(metadata_bytes.get(b"CATEGORY", ""),
						encoding=_encodings['repo.content'], errors='replace')
					mypf = _unicode_decode(metadata_bytes.get(b"PF", ""),
						encoding=_encodings['repo.content'], errors='replace')
					slot = _unicode_decode(metadata_bytes.get(b"SLOT", ""),
						encoding=_encodings['repo.content'], errors='replace')
					mypkg = myfile[:-5]
					if not mycat or not mypf or not slot:
						#old-style or corrupt package
						writemsg(_("\n!!! Invalid binary package: '%s'\n") % full_path,
							noiselevel=-1)
						missing_keys = []
						if not mycat:
							missing_keys.append("CATEGORY")
						if not mypf:
							missing_keys.append("PF")
						if not slot:
							missing_keys.append("SLOT")
						msg = []
						if missing_keys:
							missing_keys.sort()
							msg.append(_("Missing metadata key(s): %s.") % \
								", ".join(missing_keys))
						msg.append(_(" This binary package is not " \
							"recoverable and should be deleted."))
						for line in textwrap.wrap("".join(msg), 72):
							writemsg("!!! %s\n" % line, noiselevel=-1)
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
					if not self.dbapi._category_re.match(mycat):
						writemsg(_("!!! Binary package has an " \
							"unrecognized category: '%s'\n") % full_path,
							noiselevel=-1)
						writemsg(_("!!! '%s' has a category that is not" \
							" listed in %setc/portage/categories\n") % \
							(mycpv, self.settings["PORTAGE_CONFIGROOT"]),
							noiselevel=-1)
						continue
					mycpv = _pkg_str(mycpv)
					pkg_paths[mycpv] = mypath
					self.dbapi.cpv_inject(mycpv)
					update_pkgindex = True
					d = metadata.get(mycpv, {})
					if d:
						try:
							if long(d["MTIME"]) != s[stat.ST_MTIME]:
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
					d["MTIME"] = str(s[stat.ST_MTIME])
					d["SIZE"] = str(s.st_size)

					d.update(zip(self._pkgindex_aux_keys,
						self.dbapi.aux_get(mycpv, self._pkgindex_aux_keys)))
					try:
						self._eval_use_flags(mycpv, d)
					except portage.exception.InvalidDependString:
						writemsg(_("!!! Invalid binary package: '%s'\n") % \
							self.getname(mycpv), noiselevel=-1)
						self.dbapi.cpv_remove(mycpv)
						del pkg_paths[mycpv]

					# record location if it's non-default
					if mypath != mycpv + ".tbz2":
						d["PATH"] = mypath
					else:
						d.pop("PATH", None)
					metadata[mycpv] = d
					if not self.dbapi._aux_cache_keys.difference(d):
						aux_cache = self.dbapi._aux_cache_slot_dict()
						for k in self.dbapi._aux_cache_keys:
							aux_cache[k] = d[k]
						self.dbapi._aux_cache[mycpv] = aux_cache

			for cpv in list(metadata):
				if cpv not in pkg_paths:
					del metadata[cpv]

			# Do not bother to write the Packages index if $PKGDIR/All/ exists
			# since it will provide no benefit due to the need to read CATEGORY
			# from xpak.
			if update_pkgindex and os.access(self.pkgdir, os.W_OK):
				del pkgindex.packages[:]
				pkgindex.packages.extend(iter(metadata.values()))
				self._update_pkgindex_header(pkgindex.header)
				self._pkgindex_write(pkgindex)

		if getbinpkgs and not self.settings["PORTAGE_BINHOST"]:
			writemsg(_("!!! PORTAGE_BINHOST unset, but use is requested.\n"),
				noiselevel=-1)

		if not getbinpkgs or 'PORTAGE_BINHOST' not in self.settings:
			self.populated=1
			return
		self._remotepkgs = {}
		for base_url in self.settings["PORTAGE_BINHOST"].split():
			parsed_url = urlparse(base_url)
			host = parsed_url.netloc
			port = parsed_url.port
			user = None
			passwd = None
			user_passwd = ""
			if "@" in host:
				user, host = host.split("@", 1)
				user_passwd = user + "@"
				if ":" in user:
					user, passwd = user.split(":", 1)
			port_args = []
			if port is not None:
				port_str = ":%s" % (port,)
				if host.endswith(port_str):
					host = host[:-len(port_str)]
			pkgindex_file = os.path.join(self.settings["EROOT"], CACHE_PATH, "binhost",
				host, parsed_url.path.lstrip("/"), "Packages")
			pkgindex = self._new_pkgindex()
			try:
				f = io.open(_unicode_encode(pkgindex_file,
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace')
				try:
					pkgindex.read(f)
				finally:
					f.close()
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
			local_timestamp = pkgindex.header.get("TIMESTAMP", None)
			remote_timestamp = None
			rmt_idx = self._new_pkgindex()
			proc = None
			tmp_filename = None
			try:
				# urlparse.urljoin() only works correctly with recognized
				# protocols and requires the base url to have a trailing
				# slash, so join manually...
				url = base_url.rstrip("/") + "/Packages"
				try:
					f = _urlopen(url, if_modified_since=local_timestamp)
					if hasattr(f, 'headers') and f.headers.get('timestamp', ''):
						remote_timestamp = f.headers.get('timestamp')
				except IOError as err:
					if hasattr(err, 'code') and err.code == 304: # not modified (since local_timestamp)
						raise UseCachedCopyOfRemoteIndex()

					path = parsed_url.path.rstrip("/") + "/Packages"

					if parsed_url.scheme == 'sftp':
						# The sftp command complains about 'Illegal seek' if
						# we try to make it write to /dev/stdout, so use a
						# temp file instead.
						fd, tmp_filename = tempfile.mkstemp()
						os.close(fd)
						if port is not None:
							port_args = ['-P', "%s" % (port,)]
						proc = subprocess.Popen(['sftp'] + port_args + \
							[user_passwd + host + ":" + path, tmp_filename])
						if proc.wait() != os.EX_OK:
							raise
						f = open(tmp_filename, 'rb')
					elif parsed_url.scheme == 'ssh':
						if port is not None:
							port_args = ['-p', "%s" % (port,)]
						proc = subprocess.Popen(['ssh'] + port_args + \
							[user_passwd + host, '--', 'cat', path],
							stdout=subprocess.PIPE)
						f = proc.stdout
					else:
						setting = 'FETCHCOMMAND_' + parsed_url.scheme.upper()
						fcmd = self.settings.get(setting)
						if not fcmd:
							raise
						fd, tmp_filename = tempfile.mkstemp()
						tmp_dirname, tmp_basename = os.path.split(tmp_filename)
						os.close(fd)
						success = portage.getbinpkg.file_get(url,
						     tmp_dirname, fcmd=fcmd, filename=tmp_basename)
						if not success:
							raise EnvironmentError("%s failed" % (setting,))
						f = open(tmp_filename, 'rb')

				f_dec = codecs.iterdecode(f,
					_encodings['repo.content'], errors='replace')
				try:
					rmt_idx.readHeader(f_dec)
					if not remote_timestamp: # in case it had not been read from HTTP header
						remote_timestamp = rmt_idx.header.get("TIMESTAMP", None)
					if not remote_timestamp:
						# no timestamp in the header, something's wrong
						pkgindex = None
						writemsg(_("\n\n!!! Binhost package index " \
						" has no TIMESTAMP field.\n"), noiselevel=-1)
					else:
						if not self._pkgindex_version_supported(rmt_idx):
							writemsg(_("\n\n!!! Binhost package index version" \
							" is not supported: '%s'\n") % \
							rmt_idx.header.get("VERSION"), noiselevel=-1)
							pkgindex = None
						elif local_timestamp != remote_timestamp:
							rmt_idx.readBody(f_dec)
							pkgindex = rmt_idx
				finally:
					# Timeout after 5 seconds, in case close() blocks
					# indefinitely (see bug #350139).
					try:
						try:
							AlarmSignal.register(5)
							f.close()
						finally:
							AlarmSignal.unregister()
					except AlarmSignal:
						writemsg("\n\n!!! %s\n" % \
							_("Timed out while closing connection to binhost"),
							noiselevel=-1)
			except UseCachedCopyOfRemoteIndex:
				writemsg_stdout("\n")
				writemsg_stdout(
					colorize("GOOD", _("Local copy of remote index is up-to-date and will be used.")) + \
					"\n")
				rmt_idx = pkgindex
			except EnvironmentError as e:
				writemsg(_("\n\n!!! Error fetching binhost package" \
					" info from '%s'\n") % _hide_url_passwd(base_url))
				writemsg("!!! %s\n\n" % str(e))
				del e
				pkgindex = None
			if proc is not None:
				if proc.poll() is None:
					proc.kill()
					proc.wait()
				proc = None
			if tmp_filename is not None:
				try:
					os.unlink(tmp_filename)
				except OSError:
					pass
			if pkgindex is rmt_idx:
				pkgindex.modified = False # don't update the header
				try:
					ensure_dirs(os.path.dirname(pkgindex_file))
					f = atomic_ofstream(pkgindex_file)
					pkgindex.write(f)
					f.close()
				except (IOError, PortageException):
					if os.access(os.path.dirname(pkgindex_file), os.W_OK):
						raise
					# The current user doesn't have permission to cache the
					# file, but that's alright.
			if pkgindex:
				# Organize remote package list as a cpv -> metadata map.
				remotepkgs = _pkgindex_cpv_map_latest_build(pkgindex)
				remote_base_uri = pkgindex.header.get("URI", base_url)
				for cpv, remote_metadata in remotepkgs.items():
					remote_metadata["BASE_URI"] = remote_base_uri
					self._pkgindex_uri[cpv] = url
				self._remotepkgs.update(remotepkgs)
				self._remote_has_index = True
				for cpv in remotepkgs:
					self.dbapi.cpv_inject(cpv)
				if True:
					# Remote package instances override local package
					# if they are not identical.
					hash_names = ["SIZE"] + self._pkgindex_hashes
					for cpv, local_metadata in metadata.items():
						remote_metadata = self._remotepkgs.get(cpv)
						if remote_metadata is None:
							continue
						# Use digests to compare identity.
						identical = True
						for hash_name in hash_names:
							local_value = local_metadata.get(hash_name)
							if local_value is None:
								continue
							remote_value = remote_metadata.get(hash_name)
							if remote_value is None:
								continue
							if local_value != remote_value:
								identical = False
								break
						if identical:
							del self._remotepkgs[cpv]
						else:
							# Override the local package in the aux_get cache.
							self.dbapi._aux_cache[cpv] = remote_metadata
				else:
					# Local package instances override remote instances.
					for cpv in metadata:
						self._remotepkgs.pop(cpv, None)
				continue
			try:
				chunk_size = long(self.settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except (ValueError, KeyError):
				chunk_size = 3000
			writemsg_stdout("\n")
			writemsg_stdout(
				colorize("GOOD", _("Fetching bininfo from ")) + \
				_hide_url_passwd(base_url) + "\n")
			remotepkgs = portage.getbinpkg.dir_get_metadata(
				base_url, chunk_size=chunk_size)

			for mypkg, remote_metadata in remotepkgs.items():
				mycat = remote_metadata.get("CATEGORY")
				if mycat is None:
					#old-style or corrupt package
					writemsg(_("!!! Invalid remote binary package: %s\n") % mypkg,
						noiselevel=-1)
					continue
				mycat = mycat.strip()
				try:
					fullpkg = _pkg_str(mycat+"/"+mypkg[:-5])
				except InvalidData:
					writemsg(_("!!! Invalid remote binary package: %s\n") % mypkg,
						noiselevel=-1)
					continue

				if fullpkg in metadata:
					# When using this old protocol, comparison with the remote
					# package isn't supported, so the local package is always
					# preferred even if getbinpkgsonly is enabled.
					continue

				if not self.dbapi._category_re.match(mycat):
					writemsg(_("!!! Remote binary package has an " \
						"unrecognized category: '%s'\n") % fullpkg,
						noiselevel=-1)
					writemsg(_("!!! '%s' has a category that is not" \
						" listed in %setc/portage/categories\n") % \
						(fullpkg, self.settings["PORTAGE_CONFIGROOT"]),
						noiselevel=-1)
					continue
				mykey = portage.cpv_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					self.dbapi.cpv_inject(fullpkg)
					for k, v in remote_metadata.items():
						remote_metadata[k] = v.strip()
					remote_metadata["BASE_URI"] = base_url

					# Eliminate metadata values with names that digestCheck
					# uses, since they are not valid when using the old
					# protocol. Typically this is needed for SIZE metadata
					# which corresponds to the size of the unpacked files
					# rather than the binpkg file size, triggering digest
					# verification failures as reported in bug #303211.
					remote_metadata.pop('SIZE', None)
					for k in portage.checksum.hashfunc_map:
						remote_metadata.pop(k, None)

					self._remotepkgs[fullpkg] = remote_metadata
				except SystemExit as e:
					raise
				except:
					writemsg(_("!!! Failed to inject remote binary package: %s\n") % fullpkg,
						noiselevel=-1)
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
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			writemsg(_("!!! Binary package does not exist: '%s'\n") % full_path,
				noiselevel=-1)
			return
		mytbz2 = portage.xpak.tbz2(full_path)
		slot = mytbz2.getfile("SLOT")
		if slot is None:
			writemsg(_("!!! Invalid binary package: '%s'\n") % full_path,
				noiselevel=-1)
			return
		slot = slot.strip()
		self.dbapi.cpv_inject(cpv)

		# Reread the Packages index (in case it's been changed by another
		# process) and then updated it, all while holding a lock.
		pkgindex_lock = None
		created_symlink = False
		try:
			pkgindex_lock = lockfile(self._pkgindex_file,
				wantnewlockfile=1)
			if filename is not None:
				new_filename = self.getname(cpv)
				try:
					samefile = os.path.samefile(filename, new_filename)
				except OSError:
					samefile = False
				if not samefile:
					self._ensure_dir(os.path.dirname(new_filename))
					_movefile(filename, new_filename, mysettings=self.settings)
			if self._all_directory and \
				self.getname(cpv).split(os.path.sep)[-2] == "All":
				self._create_symlink(cpv)
				created_symlink = True
			pkgindex = self._load_pkgindex()

			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = self._new_pkgindex()

			# Discard remote metadata to ensure that _pkgindex_entry
			# gets the local metadata. This also updates state for future
			# isremote calls.
			if self._remotepkgs is not None:
				self._remotepkgs.pop(cpv, None)

			# Discard cached metadata to ensure that _pkgindex_entry
			# doesn't return stale metadata.
			self.dbapi._aux_cache.pop(cpv, None)

			try:
				d = self._pkgindex_entry(cpv)
			except portage.exception.InvalidDependString:
				writemsg(_("!!! Invalid binary package: '%s'\n") % \
					self.getname(cpv), noiselevel=-1)
				self.dbapi.cpv_remove(cpv)
				del self._pkg_paths[cpv]
				return

			# If found, remove package(s) with duplicate path.
			path = d.get("PATH", "")
			for i in range(len(pkgindex.packages) - 1, -1, -1):
				d2 = pkgindex.packages[i]
				if path and path == d2.get("PATH"):
					# Handle path collisions in $PKGDIR/All
					# when CPV is not identical.
					del pkgindex.packages[i]
				elif cpv == d2.get("CPV"):
					if path == d2.get("PATH", ""):
						del pkgindex.packages[i]
					elif created_symlink and not d2.get("PATH", ""):
						# Delete entry for the package that was just
						# overwritten by a symlink to this package.
						del pkgindex.packages[i]

			pkgindex.packages.append(d)

			self._update_pkgindex_header(pkgindex.header)
			self._pkgindex_write(pkgindex)

		finally:
			if pkgindex_lock:
				unlockfile(pkgindex_lock)

	def _pkgindex_write(self, pkgindex):
		contents = codecs.getwriter(_encodings['repo.content'])(io.BytesIO())
		pkgindex.write(contents)
		contents = contents.getvalue()
		atime = mtime = long(pkgindex.header["TIMESTAMP"])
		output_files = [(atomic_ofstream(self._pkgindex_file, mode="wb"),
			self._pkgindex_file, None)]

		if "compress-index" in self.settings.features:
			gz_fname = self._pkgindex_file + ".gz"
			fileobj = atomic_ofstream(gz_fname, mode="wb")
			output_files.append((GzipFile(filename='', mode="wb",
				fileobj=fileobj, mtime=mtime), gz_fname, fileobj))

		for f, fname, f_close in output_files:
			f.write(contents)
			f.close()
			if f_close is not None:
				f_close.close()
			# some seconds might have elapsed since TIMESTAMP
			os.utime(fname, (atime, mtime))

	def _pkgindex_entry(self, cpv):
		"""
		Performs checksums and evaluates USE flag conditionals.
		Raises InvalidDependString if necessary.
		@rtype: dict
		@return: a dict containing entry for the give cpv.
		"""

		pkg_path = self.getname(cpv)

		d = dict(zip(self._pkgindex_aux_keys,
			self.dbapi.aux_get(cpv, self._pkgindex_aux_keys)))

		d.update(perform_multiple_checksums(
			pkg_path, hashes=self._pkgindex_hashes))

		d["CPV"] = cpv
		st = os.stat(pkg_path)
		d["MTIME"] = str(st[stat.ST_MTIME])
		d["SIZE"] = str(st.st_size)

		rel_path = self._pkg_paths[cpv]
		# record location if it's non-default
		if rel_path != cpv + ".tbz2":
			d["PATH"] = rel_path

		self._eval_use_flags(cpv, d)
		return d

	def _new_pkgindex(self):
		return portage.getbinpkg.PackageIndex(
			allowed_pkg_keys=self._pkgindex_allowed_pkg_keys,
			default_header_data=self._pkgindex_default_header_data,
			default_pkg_data=self._pkgindex_default_pkg_data,
			inherited_keys=self._pkgindex_inherited_keys,
			translated_keys=self._pkgindex_translated_keys)

	def _update_pkgindex_header(self, header):
		portdir = normalize_path(os.path.realpath(self.settings["PORTDIR"]))
		profiles_base = os.path.join(portdir, "profiles") + os.path.sep
		if self.settings.profile_path:
			profile_path = normalize_path(
				os.path.realpath(self.settings.profile_path))
			if profile_path.startswith(profiles_base):
				profile_path = profile_path[len(profiles_base):]
			header["PROFILE"] = profile_path
		header["VERSION"] = str(self._pkgindex_version)
		base_uri = self.settings.get("PORTAGE_BINHOST_HEADER_URI")
		if base_uri:
			header["URI"] = base_uri
		else:
			header.pop("URI", None)
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

	def _eval_use_flags(self, cpv, metadata):
		use = frozenset(metadata["USE"].split())
		raw_use = use
		iuse = set(f.lstrip("-+") for f in metadata["IUSE"].split())
		use = [f for f in use if f in iuse]
		use.sort()
		metadata["USE"] = " ".join(use)
		for k in self._pkgindex_use_evaluated_keys:
			if k.endswith('DEPEND'):
				token_class = Atom
			else:
				token_class = None

			try:
				deps = metadata[k]
				deps = use_reduce(deps, uselist=raw_use, token_class=token_class)
				deps = paren_enclose(deps)
			except portage.exception.InvalidDependString as e:
				writemsg("%s: %s\n" % (k, str(e)),
					noiselevel=-1)
				raise
			metadata[k] = deps

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
		"""Returns true if the package is kept remotely and it has not been
		downloaded (or it is only partially downloaded)."""
		if self._remotepkgs is None or pkgname not in self._remotepkgs:
			return False
		# Presence in self._remotepkgs implies that it's remote. When a
		# package is downloaded, state is updated by self.inject().
		return True

	def get_pkgindex_uri(self, pkgname):
		"""Returns the URI to the Packages file for a given package."""
		return self._pkgindex_uri.get(pkgname)



	def gettbz2(self, pkgname):
		"""Fetches the package from a remote site, if necessary.  Attempts to
		resume if the file appears to be partially downloaded."""
		tbz2_path = self.getname(pkgname)
		tbz2name = os.path.basename(tbz2_path)
		resume = False
		if os.path.exists(tbz2_path):
			if tbz2name[:-5] not in self.invalids:
				return
			else:
				resume = True
				writemsg(_("Resuming download of this tbz2, but it is possible that it is corrupt.\n"),
					noiselevel=-1)
		
		mydest = os.path.dirname(self.getname(pkgname))
		self._ensure_dir(mydest)
		# urljoin doesn't work correctly with unrecognized protocols like sftp
		if self._remote_has_index:
			rel_url = self._remotepkgs[pkgname].get("PATH")
			if not rel_url:
				rel_url = pkgname+".tbz2"
			remote_base_uri = self._remotepkgs[pkgname]["BASE_URI"]
			url = remote_base_uri.rstrip("/") + "/" + rel_url.lstrip("/")
		else:
			url = self.settings["PORTAGE_BINHOST"].rstrip("/") + "/" + tbz2name
		protocol = urlparse(url)[0]
		fcmd_prefix = "FETCHCOMMAND"
		if resume:
			fcmd_prefix = "RESUMECOMMAND"
		fcmd = self.settings.get(fcmd_prefix + "_" + protocol.upper())
		if not fcmd:
			fcmd = self.settings.get(fcmd_prefix)
		success = portage.getbinpkg.file_get(url, mydest, fcmd=fcmd)
		if not success:
			try:
				os.unlink(self.getname(pkgname))
			except OSError:
				pass
			raise portage.exception.FileNotFound(mydest)
		self.inject(pkgname)

	def _load_pkgindex(self):
		pkgindex = self._new_pkgindex()
		try:
			f = io.open(_unicode_encode(self._pkgindex_file,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace')
		except EnvironmentError:
			pass
		else:
			try:
				pkgindex.read(f)
			finally:
				f.close()
		return pkgindex

	def digestCheck(self, pkg):
		"""
		Verify digests for the given package and raise DigestException
		if verification fails.
		@rtype: bool
		@return: True if digests could be located, False otherwise.
		"""
		cpv = pkg
		if not isinstance(cpv, basestring):
			cpv = pkg.cpv
			pkg = None

		pkg_path = self.getname(cpv)
		metadata = None
		if self._remotepkgs is None or cpv not in self._remotepkgs:
			for d in self._load_pkgindex().packages:
				if d["CPV"] == cpv:
					metadata = d
					break
		else:
			metadata = self._remotepkgs[cpv]
		if metadata is None:
			return False

		digests = {}
		for k in hashfunc_map:
			v = metadata.get(k)
			if not v:
				continue
			digests[k] = v

		if "SIZE" in metadata:
			try:
				digests["size"] = int(metadata["SIZE"])
			except ValueError:
				writemsg(_("!!! Malformed SIZE attribute in remote " \
				"metadata for '%s'\n") % cpv)

		if not digests:
			return False

		hash_filter = _hash_filter(
			self.settings.get("PORTAGE_CHECKSUM_FILTER", ""))
		if not hash_filter.transparent:
			digests = _apply_hash_filter(digests, hash_filter)
		eout = EOutput()
		eout.quiet = self.settings.get("PORTAGE_QUIET") == "1"
		ok, st = _check_distfile(pkg_path, digests, eout, show_errors=0)
		if not ok:
			ok, reason = verify_all(pkg_path, digests)
			if not ok:
				raise portage.exception.DigestException(
					(pkg_path,) + tuple(reason))

		return True

	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		myslot = ""
		try:
			myslot = self.dbapi.aux_get(mycatpkg,["SLOT"])[0]
		except SystemExit as e:
			raise
		except Exception as e:
			pass
		return myslot
