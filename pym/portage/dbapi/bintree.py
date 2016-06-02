# Copyright 1998-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

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
	'portage.util.path:first_existing',
	'portage.util._urlopen:urlopen@_urlopen',
	'portage.versions:best,catpkgsplit,catsplit,_pkg_str',
)

from portage.cache.mappings import slot_dict_class
from portage.const import CACHE_PATH, SUPPORTED_XPAK_EXTENSIONS
from portage.dbapi.virtual import fakedbapi
from portage.dep import Atom, use_reduce, paren_enclose
from portage.exception import AlarmSignal, InvalidData, InvalidPackageName, \
	ParseError, PermissionDenied, PortageException
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
import time
import traceback
import warnings
from gzip import GzipFile
from itertools import chain
try:
	from urllib.parse import urlparse
except ImportError:
	from urlparse import urlparse

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
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
		# Always enable multi_instance mode for bindbapi indexing. This
		# does not affect the local PKGDIR file layout, since that is
		# controlled independently by FEATURES=binpkg-multi-instance.
		# The multi_instance mode is useful for the following reasons:
		# * binary packages with the same cpv from multiple binhosts
		#   can be considered simultaneously
		# * if binpkg-multi-instance is disabled, it's still possible
		#   to properly access a PKGDIR which has binpkg-multi-instance
		#   layout (or mixed layout)
		fakedbapi.__init__(self, exclusive_slots=False,
			multi_instance=True, **kwargs)
		self.bintree = mybintree
		self.move_ent = mybintree.move_ent
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(
			["BUILD_ID", "BUILD_TIME", "CHOST", "DEFINED_PHASES",
			"DEPEND", "EAPI", "HDEPEND", "IUSE", "KEYWORDS",
			"LICENSE", "MD5", "PDEPEND", "PROPERTIES", "PROVIDE",
			"PROVIDES", "RDEPEND", "repository", "REQUIRES", "RESTRICT",
			"SIZE", "SLOT", "USE", "_mtime_"
			])
		self._aux_cache_slot_dict = slot_dict_class(self._aux_cache_keys)
		self._aux_cache = {}

	@property
	def writable(self):
		"""
		Check if PKGDIR is writable, or permissions are sufficient
		to create it if it does not exist yet.
		@rtype: bool
		@return: True if PKGDIR is writable or can be created,
			False otherwise
		"""
		return os.access(first_existing(self.bintree.pkgdir), os.W_OK)

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def cpv_exists(self, cpv, myrepo=None):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cpv_exists(self, cpv)

	def cpv_inject(self, cpv, **kwargs):
		if not self.bintree.populated:
			self.bintree.populate()
		fakedbapi.cpv_inject(self, cpv,
			metadata=cpv._metadata, **kwargs)

	def cpv_remove(self, cpv):
		if not self.bintree.populated:
			self.bintree.populate()
		fakedbapi.cpv_remove(self, cpv)

	def aux_get(self, mycpv, wants, myrepo=None):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		# Support plain string for backward compatibility with API
		# consumers (including portageq, which passes in a cpv from
		# a command-line argument).
		instance_key = self._instance_key(mycpv,
			support_string=True)
		if not self._known_keys.intersection(
			wants).difference(self._aux_cache_keys):
			aux_cache = self.cpvdict[instance_key]
			if aux_cache is not None:
				return [aux_cache.get(x, "") for x in wants]
		mysplit = mycpv.split("/")
		mylist = []
		tbz2name = mysplit[1]+".tbz2"
		if not self.bintree._remotepkgs or \
			not self.bintree.isremote(mycpv):
			try:
				tbz2_path = self.bintree._pkg_paths[instance_key]
			except KeyError:
				raise KeyError(mycpv)
			tbz2_path = os.path.join(self.bintree.pkgdir, tbz2_path)
			try:
				st = os.lstat(tbz2_path)
			except OSError:
				raise KeyError(mycpv)
			metadata_bytes = portage.xpak.tbz2(tbz2_path).get_data()
			def getitem(k):
				if k == "_mtime_":
					return _unicode(st[stat.ST_MTIME])
				elif k == "SIZE":
					return _unicode(st.st_size)
				v = metadata_bytes.get(_unicode_encode(k,
					encoding=_encodings['repo.content'],
					errors='backslashreplace'))
				if v is not None:
					v = _unicode_decode(v,
						encoding=_encodings['repo.content'], errors='replace')
				return v
		else:
			getitem = self.cpvdict[instance_key].get
		mydata = {}
		mykeys = wants
		for x in mykeys:
			myval = getitem(x)
			# myval is None if the key doesn't exist
			# or the tbz2 is corrupt.
			if myval:
				mydata[x] = " ".join(myval.split())

		if not mydata.setdefault('EAPI', '0'):
			mydata['EAPI'] = '0'

		return [mydata.get(x, '') for x in wants]

	def aux_update(self, cpv, values):
		if not self.bintree.populated:
			self.bintree.populate()
		build_id = None
		try:
			build_id = cpv.build_id
		except AttributeError:
			if self.bintree._multi_instance:
				# The cpv.build_id attribute is required if we are in
				# multi-instance mode, since otherwise we won't know
				# which instance to update.
				raise
			else:
				cpv = self._instance_key(cpv, support_string=True)[0]
				build_id = cpv.build_id

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
		self.bintree.inject(cpv, filename=tbz2path)

	def cp_list(self, *pargs, **kwargs):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_list(self, *pargs, **kwargs)

	def cp_all(self, sort=False):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_all(self, sort=sort)

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
			metadata = self.bintree._remotepkgs[self._instance_key(pkg)]
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

class binarytree(object):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self, _unused=DeprecationWarning, pkgdir=None,
		virtual=DeprecationWarning, settings=None):

		if pkgdir is None:
			raise TypeError("pkgdir parameter is required")

		if settings is None:
			raise TypeError("settings parameter is required")

		if _unused is not DeprecationWarning:
			warnings.warn("The first parameter of the "
				"portage.dbapi.bintree.binarytree"
				" constructor is now unused. Instead "
				"settings['ROOT'] is used.",
				DeprecationWarning, stacklevel=2)

		if virtual is not DeprecationWarning:
			warnings.warn("The 'virtual' parameter of the "
				"portage.dbapi.bintree.binarytree"
				" constructor is unused",
				DeprecationWarning, stacklevel=2)

		if True:
			self.pkgdir = normalize_path(pkgdir)
			# NOTE: Event if binpkg-multi-instance is disabled, it's
			# still possible to access a PKGDIR which uses the
			# binpkg-multi-instance layout (or mixed layout).
			self._multi_instance = ("binpkg-multi-instance" in
				settings.features)
			if self._multi_instance:
				self._allocate_filename = self._allocate_filename_multi
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
			self._populating = False
			self._all_directory = os.path.isdir(
				os.path.join(self.pkgdir, "All"))
			self._pkgindex_version = 0
			self._pkgindex_hashes = ["MD5","SHA1"]
			self._pkgindex_file = os.path.join(self.pkgdir, "Packages")
			self._pkgindex_keys = self.dbapi._aux_cache_keys.copy()
			self._pkgindex_keys.update(["CPV", "SIZE"])
			self._pkgindex_aux_keys = \
				["BASE_URI", "BUILD_ID", "BUILD_TIME", "CHOST",
				"DEFINED_PHASES", "DEPEND", "DESCRIPTION", "EAPI",
				"HDEPEND", "IUSE", "KEYWORDS", "LICENSE", "PDEPEND",
				"PKGINDEX_URI", "PROPERTIES", "PROVIDE", "PROVIDES",
				"RDEPEND", "repository", "REQUIRES", "RESTRICT",
				"SIZE", "SLOT", "USE"]
			self._pkgindex_aux_keys = list(self._pkgindex_aux_keys)
			self._pkgindex_use_evaluated_keys = \
				("DEPEND", "HDEPEND", "LICENSE", "RDEPEND",
				"PDEPEND", "PROPERTIES", "PROVIDE", "RESTRICT")
			self._pkgindex_header_keys = set([
				"ACCEPT_KEYWORDS", "ACCEPT_LICENSE",
				"ACCEPT_PROPERTIES", "ACCEPT_RESTRICT", "CBUILD",
				"CONFIG_PROTECT", "CONFIG_PROTECT_MASK", "FEATURES",
				"GENTOO_MIRRORS", "INSTALL_MASK", "IUSE_IMPLICIT", "USE",
				"USE_EXPAND", "USE_EXPAND_HIDDEN", "USE_EXPAND_IMPLICIT",
				"USE_EXPAND_UNPREFIXED"])
			self._pkgindex_default_pkg_data = {
				"BUILD_ID"           : "",
				"BUILD_TIME"         : "",
				"DEFINED_PHASES"     : "",
				"DEPEND"  : "",
				"EAPI"    : "0",
				"HDEPEND" : "",
				"IUSE"    : "",
				"KEYWORDS": "",
				"LICENSE" : "",
				"PATH"    : "",
				"PDEPEND" : "",
				"PROPERTIES" : "",
				"PROVIDE" : "",
				"PROVIDES": "",
				"RDEPEND" : "",
				"REQUIRES": "",
				"RESTRICT": "",
				"SLOT"    : "0",
				"USE"     : "",
			}
			self._pkgindex_inherited_keys = ["CHOST", "repository"]

			# Populate the header with appropriate defaults.
			self._pkgindex_default_header_data = {
				"CHOST"        : self.settings.get("CHOST", ""),
				"repository"   : "",
			}

			self._pkgindex_translated_keys = (
				("DESCRIPTION"   ,   "DESC"),
				("_mtime_"       ,   "MTIME"),
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
				raise InvalidPackageName(_unicode(atom))
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
			updated_items = update_dbentries([mylist], mydata, parent=mycpv)
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
			del self._pkg_paths[self.dbapi._instance_key(mycpv)]
			metadata = self.dbapi._aux_cache_slot_dict()
			for k in self.dbapi._aux_cache_keys:
				v = mydata.get(_unicode_encode(k))
				if v is not None:
					v = _unicode_decode(v)
					metadata[k] = " ".join(v.split())
			mynewcpv = _pkg_str(mynewcpv, metadata=metadata)
			new_path = self.getname(mynewcpv)
			self._pkg_paths[
				self.dbapi._instance_key(mynewcpv)] = new_path[len(self.pkgdir)+1:]
			if new_path != mytbz2:
				self._ensure_dir(os.path.dirname(new_path))
				_movefile(tbz2path, new_path, mysettings=self.settings)
			self.inject(mynewcpv)

		return moves

	def prevent_collision(self, cpv):
		warnings.warn("The "
			"portage.dbapi.bintree.binarytree.prevent_collision "
			"method is deprecated.",
			DeprecationWarning, stacklevel=2)

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

	def _file_permissions(self, path):
		try:
			pkgdir_st = os.stat(self.pkgdir)
		except OSError:
			pass
		else:
			pkgdir_gid = pkgdir_st.st_gid
			pkgdir_grp_mode = 0o0060 & pkgdir_st.st_mode
			try:
				portage.util.apply_permissions(path, gid=pkgdir_gid,
					mode=pkgdir_grp_mode, mask=0)
			except PortageException:
				pass

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
		self.dbapi.clear()
		_instance_key = self.dbapi._instance_key
		if True:
			pkg_paths = {}
			self._pkg_paths = pkg_paths
			dir_files = {}
			for parent, dir_names, file_names in os.walk(self.pkgdir):
				relative_parent = parent[len(self.pkgdir)+1:]
				dir_files[relative_parent] = file_names

			pkgindex = self._load_pkgindex()
			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = self._new_pkgindex()
			header = pkgindex.header
			metadata = {}
			basename_index = {}
			for d in pkgindex.packages:
				cpv = _pkg_str(d["CPV"], metadata=d,
					settings=self.settings)
				d["CPV"] = cpv
				metadata[_instance_key(cpv)] = d
				path = d.get("PATH")
				if not path:
					path = cpv + ".tbz2"
				basename = os.path.basename(path)
				basename_index.setdefault(basename, []).append(d)

			update_pkgindex = False
			for mydir, file_names in dir_files.items():
				try:
					mydir = _unicode_decode(mydir,
						encoding=_encodings["fs"], errors="strict")
				except UnicodeDecodeError:
					continue
				for myfile in file_names:
					try:
						myfile = _unicode_decode(myfile,
							encoding=_encodings["fs"], errors="strict")
					except UnicodeDecodeError:
						continue
					if not myfile.endswith(SUPPORTED_XPAK_EXTENSIONS):
						continue
					mypath = os.path.join(mydir, myfile)
					full_path = os.path.join(self.pkgdir, mypath)
					s = os.lstat(full_path)

					if not stat.S_ISREG(s.st_mode):
						continue

					# Validate data from the package index and try to avoid
					# reading the xpak if possible.
					possibilities = basename_index.get(myfile)
					if possibilities:
						match = None
						for d in possibilities:
							try:
								if long(d["_mtime_"]) != s[stat.ST_MTIME]:
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
							instance_key = _instance_key(mycpv)
							pkg_paths[instance_key] = mypath
							# update the path if the package has been moved
							oldpath = d.get("PATH")
							if oldpath and oldpath != mypath:
								update_pkgindex = True
							# Omit PATH if it is the default path for
							# the current Packages format version.
							if mypath != mycpv + ".tbz2":
								d["PATH"] = mypath
								if not oldpath:
									update_pkgindex = True
							else:
								d.pop("PATH", None)
								if oldpath:
									update_pkgindex = True
							self.dbapi.cpv_inject(mycpv)
							continue
					if not os.access(full_path, os.R_OK):
						writemsg(_("!!! Permission denied to read " \
							"binary package: '%s'\n") % full_path,
							noiselevel=-1)
						self.invalids.append(myfile[:-5])
						continue
					pkg_metadata = self._read_metadata(full_path, s,
						keys=chain(self.dbapi._aux_cache_keys,
						("PF", "CATEGORY")))
					mycat = pkg_metadata.get("CATEGORY", "")
					mypf = pkg_metadata.get("PF", "")
					slot = pkg_metadata.get("SLOT", "")
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

					multi_instance = False
					invalid_name = False
					build_id = None
					if myfile.endswith(".xpak"):
						multi_instance = True
						build_id = self._parse_build_id(myfile)
						if build_id < 1:
							invalid_name = True
						elif myfile != "%s-%s.xpak" % (
							mypf, build_id):
							invalid_name = True
						else:
							mypkg = mypkg[:-len(str(build_id))-1]
					elif myfile != mypf + ".tbz2":
						invalid_name = True

					if invalid_name:
						writemsg(_("\n!!! Binary package name is "
							"invalid: '%s'\n") % full_path,
							noiselevel=-1)
						continue

					if pkg_metadata.get("BUILD_ID"):
						try:
							build_id = long(pkg_metadata["BUILD_ID"])
						except ValueError:
							writemsg(_("!!! Binary package has "
								"invalid BUILD_ID: '%s'\n") %
								full_path, noiselevel=-1)
							continue
					else:
						build_id = None

					if multi_instance:
						name_split = catpkgsplit("%s/%s" %
							(mycat, mypf))
						if (name_split is None or
							tuple(catsplit(mydir)) != name_split[:2]):
							continue
					elif mycat != mydir and mydir != "All":
						continue
					if mypkg != mypf.strip():
						continue
					mycpv = mycat + "/" + mypkg
					if not self.dbapi._category_re.match(mycat):
						writemsg(_("!!! Binary package has an " \
							"unrecognized category: '%s'\n") % full_path,
							noiselevel=-1)
						writemsg(_("!!! '%s' has a category that is not" \
							" listed in %setc/portage/categories\n") % \
							(mycpv, self.settings["PORTAGE_CONFIGROOT"]),
							noiselevel=-1)
						continue
					if build_id is not None:
						pkg_metadata["BUILD_ID"] = _unicode(build_id)
					pkg_metadata["SIZE"] = _unicode(s.st_size)
					# Discard items used only for validation above.
					pkg_metadata.pop("CATEGORY")
					pkg_metadata.pop("PF")
					mycpv = _pkg_str(mycpv,
						metadata=self.dbapi._aux_cache_slot_dict(
						pkg_metadata))
					pkg_paths[_instance_key(mycpv)] = mypath
					self.dbapi.cpv_inject(mycpv)
					update_pkgindex = True
					d = metadata.get(_instance_key(mycpv),
						pkgindex._pkg_slot_dict())
					if d:
						try:
							if long(d["_mtime_"]) != s[stat.ST_MTIME]:
								d.clear()
						except (KeyError, ValueError):
							d.clear()
					if d:
						try:
							if long(d["SIZE"]) != long(s.st_size):
								d.clear()
						except (KeyError, ValueError):
							d.clear()

					for k in self._pkgindex_allowed_pkg_keys:
						v = pkg_metadata.get(k)
						if v is not None:
							d[k] = v
					d["CPV"] = mycpv

					try:
						self._eval_use_flags(mycpv, d)
					except portage.exception.InvalidDependString:
						writemsg(_("!!! Invalid binary package: '%s'\n") % \
							self.getname(mycpv), noiselevel=-1)
						self.dbapi.cpv_remove(mycpv)
						del pkg_paths[_instance_key(mycpv)]

					# record location if it's non-default
					if mypath != mycpv + ".tbz2":
						d["PATH"] = mypath
					else:
						d.pop("PATH", None)
					metadata[_instance_key(mycpv)] = d

			for instance_key in list(metadata):
				if instance_key not in pkg_paths:
					del metadata[instance_key]

			# Do not bother to write the Packages index if $PKGDIR/All/ exists
			# since it will provide no benefit due to the need to read CATEGORY
			# from xpak.
			if update_pkgindex and os.access(self.pkgdir, os.W_OK):
				del pkgindex.packages[:]
				pkgindex.packages.extend(iter(metadata.values()))
				self._update_pkgindex_header(pkgindex.header)
				self._pkgindex_write(pkgindex)

		if getbinpkgs and not self.settings.get("PORTAGE_BINHOST"):
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
			try:
				download_timestamp = \
					float(pkgindex.header.get("DOWNLOAD_TIMESTAMP", 0))
			except ValueError:
				download_timestamp = 0
			remote_timestamp = None
			rmt_idx = self._new_pkgindex()
			proc = None
			tmp_filename = None
			try:
				# urlparse.urljoin() only works correctly with recognized
				# protocols and requires the base url to have a trailing
				# slash, so join manually...
				url = base_url.rstrip("/") + "/Packages"
				f = None

				try:
					ttl = float(pkgindex.header.get("TTL", 0))
				except ValueError:
					pass
				else:
					if download_timestamp and ttl and \
						download_timestamp + ttl > time.time():
						raise UseCachedCopyOfRemoteIndex()

				# Don't use urlopen for https, since it doesn't support
				# certificate/hostname verification (bug #469888).
				if parsed_url.scheme not in ('https',):
					try:
						f = _urlopen(url, if_modified_since=local_timestamp)
						if hasattr(f, 'headers') and f.headers.get('timestamp', ''):
							remote_timestamp = f.headers.get('timestamp')
					except IOError as err:
						if hasattr(err, 'code') and err.code == 304: # not modified (since local_timestamp)
							raise UseCachedCopyOfRemoteIndex()

						if parsed_url.scheme in ('ftp', 'http', 'https'):
							# This protocol is supposedly supported by urlopen,
							# so apparently there's a problem with the url
							# or a bug in urlopen.
							if self.settings.get("PORTAGE_DEBUG", "0") != "0":
								traceback.print_exc()

							raise
					except ValueError:
						raise ParseError("Invalid Portage BINHOST value '%s'"
										 % url.lstrip())

				if f is None:

					path = parsed_url.path.rstrip("/") + "/Packages"

					if parsed_url.scheme == 'ssh':
						# Use a pipe so that we can terminate the download
						# early if we detect that the TIMESTAMP header
						# matches that of the cached Packages file.
						ssh_args = ['ssh']
						if port is not None:
							ssh_args.append("-p%s" % (port,))
						# NOTE: shlex evaluates embedded quotes
						ssh_args.extend(portage.util.shlex_split(
							self.settings.get("PORTAGE_SSH_OPTS", "")))
						ssh_args.append(user_passwd + host)
						ssh_args.append('--')
						ssh_args.append('cat')
						ssh_args.append(path)

						proc = subprocess.Popen(ssh_args,
							stdout=subprocess.PIPE)
						f = proc.stdout
					else:
						setting = 'FETCHCOMMAND_' + parsed_url.scheme.upper()
						fcmd = self.settings.get(setting)
						if not fcmd:
							fcmd = self.settings.get('FETCHCOMMAND')
							if not fcmd:
								raise EnvironmentError("FETCHCOMMAND is unset")

						fd, tmp_filename = tempfile.mkstemp()
						tmp_dirname, tmp_basename = os.path.split(tmp_filename)
						os.close(fd)

						fcmd_vars = {
							"DISTDIR": tmp_dirname,
							"FILE": tmp_basename,
							"URI": url
						}

						for k in ("PORTAGE_SSH_OPTS",):
							v = self.settings.get(k)
							if v is not None:
								fcmd_vars[k] = v

						success = portage.getbinpkg.file_get(
							fcmd=fcmd, fcmd_vars=fcmd_vars)
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
				# With Python 2, the EnvironmentError message may
				# contain bytes or unicode, so use _unicode to ensure
				# safety with all locales (bug #532784).
				try:
					error_msg = _unicode(e)
				except UnicodeDecodeError as uerror:
					error_msg = _unicode(uerror.object,
						encoding='utf_8', errors='replace')
				writemsg("!!! %s\n\n" % error_msg)
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
				pkgindex.header["DOWNLOAD_TIMESTAMP"] = "%d" % time.time()
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
				remote_base_uri = pkgindex.header.get("URI", base_url)
				for d in pkgindex.packages:
					cpv = _pkg_str(d["CPV"], metadata=d,
						settings=self.settings)
					instance_key = _instance_key(cpv)
					# Local package instances override remote instances
					# with the same instance_key.
					if instance_key in metadata:
						continue

					d["CPV"] = cpv
					d["BASE_URI"] = remote_base_uri
					d["PKGINDEX_URI"] = url
					self._remotepkgs[instance_key] = d
					metadata[instance_key] = d
					self.dbapi.cpv_inject(cpv)

				self._remote_has_index = True

		self.populated=1

	def inject(self, cpv, filename=None):
		"""Add a freshly built package to the database.  This updates
		$PKGDIR/Packages with the new package metadata (including MD5).
		@param cpv: The cpv of the new package to inject
		@type cpv: string
		@param filename: File path of the package to inject, or None if it's
			already in the location returned by getname()
		@type filename: string
		@rtype: _pkg_str or None
		@return: A _pkg_str instance on success, or None on failure.
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
		metadata = self._read_metadata(full_path, s)
		slot = metadata.get("SLOT")
		try:
			self._eval_use_flags(cpv, metadata)
		except portage.exception.InvalidDependString:
			slot = None
		if slot is None:
			writemsg(_("!!! Invalid binary package: '%s'\n") % full_path,
				noiselevel=-1)
			return

		fetched = False
		try:
			build_id = cpv.build_id
		except AttributeError:
			build_id = None
		else:
			instance_key = self.dbapi._instance_key(cpv)
			if instance_key in self.dbapi.cpvdict:
				# This means we've been called by aux_update (or
				# similar). The instance key typically changes (due to
				# file modification), so we need to discard existing
				# instance key references.
				self.dbapi.cpv_remove(cpv)
				self._pkg_paths.pop(instance_key, None)
				if self._remotepkgs is not None:
					fetched = self._remotepkgs.pop(instance_key, None)

		cpv = _pkg_str(cpv, metadata=metadata, settings=self.settings)

		# Reread the Packages index (in case it's been changed by another
		# process) and then updated it, all while holding a lock.
		pkgindex_lock = None
		try:
			pkgindex_lock = lockfile(self._pkgindex_file,
				wantnewlockfile=1)
			if filename is not None:
				new_filename = self.getname(cpv, allocate_new=True)
				try:
					samefile = os.path.samefile(filename, new_filename)
				except OSError:
					samefile = False
				if not samefile:
					self._ensure_dir(os.path.dirname(new_filename))
					_movefile(filename, new_filename, mysettings=self.settings)
				full_path = new_filename

			basename = os.path.basename(full_path)
			pf = catsplit(cpv)[1]
			if (build_id is None and not fetched and
				basename.endswith(".xpak")):
				# Apply the newly assigned BUILD_ID. This is intended
				# to occur only for locally built packages. If the
				# package was fetched, we want to preserve its
				# attributes, so that we can later distinguish that it
				# is identical to its remote counterpart.
				build_id = self._parse_build_id(basename)
				metadata["BUILD_ID"] = _unicode(build_id)
				cpv = _pkg_str(cpv, metadata=metadata,
					settings=self.settings)
				binpkg = portage.xpak.tbz2(full_path)
				binary_data = binpkg.get_data()
				binary_data[b"BUILD_ID"] = _unicode_encode(
					metadata["BUILD_ID"])
				binpkg.recompose_mem(portage.xpak.xpak_mem(binary_data))

			self._file_permissions(full_path)
			pkgindex = self._load_pkgindex()
			if not self._pkgindex_version_supported(pkgindex):
				pkgindex = self._new_pkgindex()

			d = self._inject_file(pkgindex, cpv, full_path)
			self._update_pkgindex_header(pkgindex.header)
			self._pkgindex_write(pkgindex)

		finally:
			if pkgindex_lock:
				unlockfile(pkgindex_lock)

		# This is used to record BINPKGMD5 in the installed package
		# database, for a package that has just been built.
		cpv._metadata["MD5"] = d["MD5"]

		return cpv

	def _read_metadata(self, filename, st, keys=None):
		if keys is None:
			keys = self.dbapi._aux_cache_keys
			metadata = self.dbapi._aux_cache_slot_dict()
		else:
			metadata = {}
		binary_metadata = portage.xpak.tbz2(filename).get_data()
		for k in keys:
			if k == "_mtime_":
				metadata[k] = _unicode(st[stat.ST_MTIME])
			elif k == "SIZE":
				metadata[k] = _unicode(st.st_size)
			else:
				v = binary_metadata.get(_unicode_encode(k))
				if v is not None:
					v = _unicode_decode(v)
					metadata[k] = " ".join(v.split())
		metadata.setdefault("EAPI", "0")
		return metadata

	def _inject_file(self, pkgindex, cpv, filename):
		"""
		Add a package to internal data structures, and add an
		entry to the given pkgindex.
		@param pkgindex: The PackageIndex instance to which an entry
			will be added.
		@type pkgindex: PackageIndex
		@param cpv: A _pkg_str instance corresponding to the package
			being injected.
		@type cpv: _pkg_str
		@param filename: Absolute file path of the package to inject.
		@type filename: string
		@rtype: dict
		@return: A dict corresponding to the new entry which has been
			added to pkgindex. This may be used to access the checksums
			which have just been generated.
		"""
		# Update state for future isremote calls.
		instance_key = self.dbapi._instance_key(cpv)
		if self._remotepkgs is not None:
			self._remotepkgs.pop(instance_key, None)

		self.dbapi.cpv_inject(cpv)
		self._pkg_paths[instance_key] = filename[len(self.pkgdir)+1:]
		d = self._pkgindex_entry(cpv)

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

		pkgindex.packages.append(d)
		return d

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
			self._file_permissions(fname)
			# some seconds might have elapsed since TIMESTAMP
			os.utime(fname, (atime, mtime))

	def _pkgindex_entry(self, cpv):
		"""
		Performs checksums, and gets size and mtime via lstat.
		Raises InvalidDependString if necessary.
		@rtype: dict
		@return: a dict containing entry for the give cpv.
		"""

		pkg_path = self.getname(cpv)

		d = dict(cpv._metadata.items())
		d.update(perform_multiple_checksums(
			pkg_path, hashes=self._pkgindex_hashes))

		d["CPV"] = cpv
		st = os.lstat(pkg_path)
		d["_mtime_"] = _unicode(st[stat.ST_MTIME])
		d["SIZE"] = _unicode(st.st_size)

		rel_path = pkg_path[len(self.pkgdir)+1:]
		# record location if it's non-default
		if rel_path != cpv + ".tbz2":
			d["PATH"] = rel_path

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
		header["VERSION"] = _unicode(self._pkgindex_version)
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

		# These values may be useful for using a binhost without
		# having a local copy of the profile (bug #470006).
		for k in self.settings.get("USE_EXPAND_IMPLICIT", "").split():
			k = "USE_EXPAND_VALUES_" + k
			v = self.settings.get(k)
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
		use = frozenset(metadata.get("USE", "").split())
		for k in self._pkgindex_use_evaluated_keys:
			if k.endswith('DEPEND'):
				token_class = Atom
			else:
				token_class = None

			deps = metadata.get(k)
			if deps is None:
				continue
			try:
				deps = use_reduce(deps, uselist=use, token_class=token_class)
				deps = paren_enclose(deps)
			except portage.exception.InvalidDependString as e:
				writemsg("%s: %s\n" % (k, e), noiselevel=-1)
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

	def getname(self, cpv, allocate_new=None):
		"""Returns a file location for this package.
		If cpv has both build_time and build_id attributes, then the
		path to the specific corresponding instance is returned.
		Otherwise, allocate a new path and return that. When allocating
		a new path, behavior depends on the binpkg-multi-instance
		FEATURES setting.
		"""
		if not self.populated:
			self.populate()

		try:
			cpv.cp
		except AttributeError:
			cpv = _pkg_str(cpv)

		filename = None
		if allocate_new:
			filename = self._allocate_filename(cpv)
		elif self._is_specific_instance(cpv):
			instance_key = self.dbapi._instance_key(cpv)
			path = self._pkg_paths.get(instance_key)
			if path is not None:
				filename = os.path.join(self.pkgdir, path)

		if filename is None and not allocate_new:
			try:
				instance_key = self.dbapi._instance_key(cpv,
					support_string=True)
			except KeyError:
				pass
			else:
				filename = self._pkg_paths.get(instance_key)
				if filename is not None:
					filename = os.path.join(self.pkgdir, filename)

		if filename is None:
			if self._multi_instance:
				pf = catsplit(cpv)[1]
				filename = "%s-%s.xpak" % (
					os.path.join(self.pkgdir, cpv.cp, pf), "1")
			else:
				filename = os.path.join(self.pkgdir, cpv + ".tbz2")

		return filename

	def _is_specific_instance(self, cpv):
		specific = True
		try:
			build_time = cpv.build_time
			build_id = cpv.build_id
		except AttributeError:
			specific = False
		else:
			if build_time is None or build_id is None:
				specific = False
		return specific

	def _max_build_id(self, cpv):
		max_build_id = 0
		for x in self.dbapi.cp_list(cpv.cp):
			if (x == cpv and x.build_id is not None and
				x.build_id > max_build_id):
				max_build_id = x.build_id
		return max_build_id

	def _allocate_filename(self, cpv):
		return os.path.join(self.pkgdir, cpv + ".tbz2")

	def _allocate_filename_multi(self, cpv):

		# First, get the max build_id found when _populate was
		# called.
		max_build_id = self._max_build_id(cpv)

		# A new package may have been added concurrently since the
		# last _populate call, so use increment build_id until
		# we locate an unused id.
		pf = catsplit(cpv)[1]
		build_id = max_build_id + 1

		while True:
			filename = "%s-%s.xpak" % (
				os.path.join(self.pkgdir, cpv.cp, pf), build_id)
			if os.path.exists(filename):
				build_id += 1
			else:
				return filename

	@staticmethod
	def _parse_build_id(filename):
		build_id = -1
		hyphen = filename.rfind("-", 0, -6)
		if hyphen != -1:
			build_id = filename[hyphen+1:-5]
		try:
			build_id = long(build_id)
		except ValueError:
			pass
		return build_id

	def isremote(self, pkgname):
		"""Returns true if the package is kept remotely and it has not been
		downloaded (or it is only partially downloaded)."""
		if (self._remotepkgs is None or
		self.dbapi._instance_key(pkgname) not in self._remotepkgs):
			return False
		# Presence in self._remotepkgs implies that it's remote. When a
		# package is downloaded, state is updated by self.inject().
		return True

	def get_pkgindex_uri(self, cpv):
		"""Returns the URI to the Packages file for a given package."""
		uri = None
		if self._remotepkgs is not None:
			metadata = self._remotepkgs.get(self.dbapi._instance_key(cpv))
			if metadata is not None:
				uri = metadata["PKGINDEX_URI"]
		return uri

	def gettbz2(self, pkgname):
		"""Fetches the package from a remote site, if necessary.  Attempts to
		resume if the file appears to be partially downloaded."""
		instance_key = self.dbapi._instance_key(pkgname)
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
			rel_url = self._remotepkgs[instance_key].get("PATH")
			if not rel_url:
				rel_url = pkgname+".tbz2"
			remote_base_uri = self._remotepkgs[instance_key]["BASE_URI"]
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

	def _get_digests(self, pkg):

		try:
			cpv = pkg.cpv
		except AttributeError:
			cpv = pkg

		_instance_key = self.dbapi._instance_key
		instance_key = _instance_key(cpv)
		digests = {}
		metadata = (None if self._remotepkgs is None else
			self._remotepkgs.get(instance_key))
		if metadata is None:
			for d in self._load_pkgindex().packages:
				if (d["CPV"] == cpv and
					instance_key == _instance_key(_pkg_str(d["CPV"],
					metadata=d, settings=self.settings))):
					metadata = d
					break

		if metadata is None:
			return digests

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

		return digests

	def digestCheck(self, pkg):
		"""
		Verify digests for the given package and raise DigestException
		if verification fails.
		@rtype: bool
		@return: True if digests could be located, False otherwise.
		"""

		digests = self._get_digests(pkg)

		if not digests:
			return False

		try:
			cpv = pkg.cpv
		except AttributeError:
			cpv = pkg

		pkg_path = self.getname(cpv)
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
			myslot = self.dbapi._pkg_str(mycatpkg, None).slot
		except KeyError:
			pass
		return myslot
