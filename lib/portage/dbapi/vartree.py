# Copyright 1998-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	"vardbapi", "vartree", "dblink"] + \
	["write_contents", "tar_contents"]

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'hashlib:md5',
	'portage.checksum:_perform_md5_merge@perform_md5',
	'portage.data:portage_gid,portage_uid,secpass',
	'portage.dbapi.dep_expand:dep_expand',
	'portage.dbapi._MergeProcess:MergeProcess',
	'portage.dbapi._SyncfsProcess:SyncfsProcess',
	'portage.dep:dep_getkey,isjustname,isvalidatom,match_from_list,' + \
	 	'use_reduce,_slot_separator,_repo_separator',
	'portage.eapi:_get_eapi_attrs',
	'portage.elog:collect_ebuild_messages,collect_messages,' + \
		'elog_process,_merge_logentries',
	'portage.locks:lockdir,unlockdir,lockfile,unlockfile',
	'portage.output:bold,colorize',
	'portage.package.ebuild.doebuild:doebuild_environment,' + \
		'_merge_unicode_error',
	'portage.package.ebuild.prepare_build_dirs:prepare_build_dirs',
	'portage.package.ebuild._ipc.QueryCommand:QueryCommand',
	'portage.process:find_binary',
	'portage.util:apply_secpass_permissions,ConfigProtect,ensure_dirs,' + \
		'writemsg,writemsg_level,write_atomic,atomic_ofstream,writedict,' + \
		'grabdict,normalize_path,new_protect_filename',
	'portage.util._compare_files:compare_files',
	'portage.util.digraph:digraph',
	'portage.util.env_update:env_update',
	'portage.util.install_mask:install_mask_dir,InstallMask,_raise_exc',
	'portage.util.listdir:dircache,listdir',
	'portage.util.movefile:movefile',
	'portage.util.path:first_existing,iter_parents',
	'portage.util.writeable_check:get_ro_checker',
	'portage.util._xattr:xattr',
	'portage.util._dyn_libs.PreservedLibsRegistry:PreservedLibsRegistry',
	'portage.util._dyn_libs.LinkageMapELF:LinkageMapELF@LinkageMap',
	'portage.util._dyn_libs.NeededEntry:NeededEntry',
	'portage.util._async.SchedulerInterface:SchedulerInterface',
	'portage.util._eventloop.global_event_loop:global_event_loop',
	'portage.versions:best,catpkgsplit,catsplit,cpv_getkey,vercmp,' + \
		'_get_slot_re,_pkgsplit@pkgsplit,_pkg_str,_unknown_repo',
	'subprocess',
	'tarfile',
)

from portage.const import CACHE_PATH, CONFIG_MEMORY_FILE, \
	MERGING_IDENTIFIER, PORTAGE_PACKAGE_ATOM, PRIVATE_PATH, VDB_PATH
from portage.dbapi import dbapi
from portage.exception import CommandNotFound, \
	InvalidData, InvalidLocation, InvalidPackageName, \
	FileNotFound, PermissionDenied, UnsupportedAPIException
from portage.localization import _
from portage.util.futures import asyncio

from portage import abssymlink, _movefile, bsd_chflags

# This is a special version of the os module, wrapped for unicode support.
from portage import os
from portage import shutil
from portage import _encodings
from portage import _os_merge
from portage import _selinux_merge
from portage import _unicode_decode
from portage import _unicode_encode
from portage.util.futures.compat_coroutine import coroutine
from portage.util.futures.executor.fork import ForkExecutor
from ._VdbMetadataDelta import VdbMetadataDelta

from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildPhase import EbuildPhase
from _emerge.emergelog import emergelog
from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from _emerge.SpawnProcess import SpawnProcess
from ._ContentsCaseSensitivityManager import ContentsCaseSensitivityManager

import argparse
import errno
import fnmatch
import functools
import gc
import grp
import io
from itertools import chain
import logging
import os as _os
import operator
import pickle
import platform
import pwd
import re
import stat
import tempfile
import textwrap
import time
import warnings


class vardbapi(dbapi):

	_excluded_dirs = ["CVS", "lost+found"]
	_excluded_dirs = [re.escape(x) for x in _excluded_dirs]
	_excluded_dirs = re.compile(r'^(\..*|' + MERGING_IDENTIFIER + '.*|' + \
		"|".join(_excluded_dirs) + r')$')

	_aux_cache_version        = "1"
	_owners_cache_version     = "1"

	# Number of uncached packages to trigger cache update, since
	# it's wasteful to update it for every vdb change.
	_aux_cache_threshold = 5

	_aux_cache_keys_re = re.compile(r'^NEEDED\..*$')
	_aux_multi_line_re = re.compile(r'^(CONTENTS|NEEDED\..*)$')
	_pkg_str_aux_keys = dbapi._pkg_str_aux_keys + ("BUILD_ID", "BUILD_TIME", "_mtime_")

	def __init__(self, _unused_param=DeprecationWarning,
		categories=None, settings=None, vartree=None):
		"""
		The categories parameter is unused since the dbapi class
		now has a categories property that is generated from the
		available packages.
		"""

		# Used by emerge to check whether any packages
		# have been added or removed.
		self._pkgs_changed = False

		# The _aux_cache_threshold doesn't work as designed
		# if the cache is flushed from a subprocess, so we
		# use this to avoid waste vdb cache updates.
		self._flush_cache_enabled = True

		#cache for category directory mtimes
		self.mtdircache = {}

		#cache for dependency checks
		self.matchcache = {}

		#cache for cp_list results
		self.cpcache = {}

		self.blockers = None
		if settings is None:
			settings = portage.settings
		self.settings = settings

		if _unused_param is not DeprecationWarning:
			warnings.warn("The first parameter of the "
				"portage.dbapi.vartree.vardbapi"
				" constructor is now unused. Instead "
				"settings['ROOT'] is used.",
				DeprecationWarning, stacklevel=2)

		self._eroot = settings['EROOT']
		self._dbroot = self._eroot + VDB_PATH
		self._lock = None
		self._lock_count = 0

		self._conf_mem_file = self._eroot + CONFIG_MEMORY_FILE
		self._fs_lock_obj = None
		self._fs_lock_count = 0
		self._slot_locks = {}

		if vartree is None:
			vartree = portage.db[settings['EROOT']]['vartree']
		self.vartree = vartree
		self._aux_cache_keys = set(
			["BDEPEND", "BUILD_TIME", "CHOST", "COUNTER", "DEPEND",
			"DESCRIPTION", "EAPI", "HOMEPAGE",
			"BUILD_ID", "IDEPEND", "IUSE", "KEYWORDS",
			"LICENSE", "PDEPEND", "PROPERTIES", "RDEPEND",
			"repository", "RESTRICT" , "SLOT", "USE", "DEFINED_PHASES",
			"PROVIDES", "REQUIRES"
			])
		self._aux_cache_obj = None
		self._aux_cache_filename = os.path.join(self._eroot,
			CACHE_PATH, "vdb_metadata.pickle")
		self._cache_delta_filename = os.path.join(self._eroot,
			CACHE_PATH, "vdb_metadata_delta.json")
		self._cache_delta = VdbMetadataDelta(self)
		self._counter_path = os.path.join(self._eroot,
			CACHE_PATH, "counter")

		self._plib_registry = PreservedLibsRegistry(settings["ROOT"],
			os.path.join(self._eroot, PRIVATE_PATH, "preserved_libs_registry"))
		self._linkmap = LinkageMap(self)
		self._owners = self._owners_db(self)

		self._cached_counter = None

	@property
	def writable(self):
		"""
		Check if var/db/pkg is writable, or permissions are sufficient
		to create it if it does not exist yet.
		@rtype: bool
		@return: True if var/db/pkg is writable or can be created,
			False otherwise
		"""
		return os.access(first_existing(self._dbroot), os.W_OK)

	@property
	def root(self):
		warnings.warn("The root attribute of "
			"portage.dbapi.vartree.vardbapi"
			" is deprecated. Use "
			"settings['ROOT'] instead.",
			DeprecationWarning, stacklevel=3)
		return self.settings['ROOT']

	def getpath(self, mykey, filename=None):
		# This is an optimized hotspot, so don't use unicode-wrapped
		# os module and don't use os.path.join().
		rValue = self._eroot + VDB_PATH + _os.sep + mykey
		if filename is not None:
			# If filename is always relative, we can do just
			# rValue += _os.sep + filename
			rValue = _os.path.join(rValue, filename)
		return rValue

	def lock(self):
		"""
		Acquire a reentrant lock, blocking, for cooperation with concurrent
		processes. State is inherited by subprocesses, allowing subprocesses
		to reenter a lock that was acquired by a parent process. However,
		a lock can be released only by the same process that acquired it.
		"""
		if self._lock_count:
			self._lock_count += 1
		else:
			if self._lock is not None:
				raise AssertionError("already locked")
			# At least the parent needs to exist for the lock file.
			ensure_dirs(self._dbroot)
			self._lock = lockdir(self._dbroot)
			self._lock_count += 1

	def unlock(self):
		"""
		Release a lock, decrementing the recursion level. Each unlock() call
		must be matched with a prior lock() call, or else an AssertionError
		will be raised if unlock() is called while not locked.
		"""
		if self._lock_count > 1:
			self._lock_count -= 1
		else:
			if self._lock is None:
				raise AssertionError("not locked")
			self._lock_count = 0
			unlockdir(self._lock)
			self._lock = None

	def _fs_lock(self):
		"""
		Acquire a reentrant lock, blocking, for cooperation with concurrent
		processes.
		"""
		if self._fs_lock_count < 1:
			if self._fs_lock_obj is not None:
				raise AssertionError("already locked")
			try:
				self._fs_lock_obj = lockfile(self._conf_mem_file)
			except InvalidLocation:
				self.settings._init_dirs()
				self._fs_lock_obj = lockfile(self._conf_mem_file)
		self._fs_lock_count += 1

	def _fs_unlock(self):
		"""
		Release a lock, decrementing the recursion level.
		"""
		if self._fs_lock_count <= 1:
			if self._fs_lock_obj is None:
				raise AssertionError("not locked")
			unlockfile(self._fs_lock_obj)
			self._fs_lock_obj = None
		self._fs_lock_count -= 1

	def _slot_lock(self, slot_atom):
		"""
		Acquire a slot lock (reentrant).

		WARNING: The varbapi._slot_lock method is not safe to call
		in the main process when that process is scheduling
		install/uninstall tasks in parallel, since the locks would
		be inherited by child processes. In order to avoid this sort
		of problem, this method should be called in a subprocess
		(typically spawned by the MergeProcess class).
		"""
		lock, counter = self._slot_locks.get(slot_atom, (None, 0))
		if lock is None:
			lock_path = self.getpath("%s:%s" % (slot_atom.cp, slot_atom.slot))
			ensure_dirs(os.path.dirname(lock_path))
			lock = lockfile(lock_path, wantnewlockfile=True)
		self._slot_locks[slot_atom] = (lock, counter + 1)

	def _slot_unlock(self, slot_atom):
		"""
		Release a slot lock (or decrementing recursion level).
		"""
		lock, counter = self._slot_locks.get(slot_atom, (None, 0))
		if lock is None:
			raise AssertionError("not locked")
		counter -= 1
		if counter == 0:
			unlockfile(lock)
			del self._slot_locks[slot_atom]
		else:
			self._slot_locks[slot_atom] = (lock, counter)

	def _bump_mtime(self, cpv):
		"""
		This is called before an after any modifications, so that consumers
		can use directory mtimes to validate caches. See bug #290428.
		"""
		base = self._eroot + VDB_PATH
		cat = catsplit(cpv)[0]
		catdir = base + _os.sep + cat
		t = time.time()
		t = (t, t)
		try:
			for x in (catdir, base):
				os.utime(x, t)
		except OSError:
			ensure_dirs(catdir)

	def cpv_exists(self, mykey, myrepo=None):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.getpath(mykey))

	def cpv_counter(self, mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		try:
			return int(self.aux_get(mycpv, ["COUNTER"])[0])
		except (KeyError, ValueError):
			pass
		writemsg_level(_("portage: COUNTER for %s was corrupted; " \
			"resetting to value of 0\n") % (mycpv,),
			level=logging.ERROR, noiselevel=-1)
		return 0

	def cpv_inject(self, mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		ensure_dirs(self.getpath(mycpv))
		counter = self.counter_tick(mycpv=mycpv)
		# write local package counter so that emerge clean does the right thing
		write_atomic(self.getpath(mycpv, filename="COUNTER"), str(counter))

	def isInjected(self, mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.getpath(mycpv, filename="INJECTED")):
				return True
			if not os.path.exists(self.getpath(mycpv, filename="CONTENTS")):
				return True
		return False

	def move_ent(self, mylist, repo_match=None):
		origcp = mylist[1]
		newcp = mylist[2]

		# sanity check
		for atom in (origcp, newcp):
			if not isjustname(atom):
				raise InvalidPackageName(str(atom))
		origmatches = self.match(origcp, use_cache=0)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			mycpv_cp = mycpv.cp
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

			mynewcpv = mycpv.replace(mycpv_cp, str(newcp), 1)
			mynewcat = catsplit(newcp)[0]
			origpath = self.getpath(mycpv)
			if not os.path.exists(origpath):
				continue
			moves += 1
			if not os.path.exists(self.getpath(mynewcat)):
				#create the directory
				ensure_dirs(self.getpath(mynewcat))
			newpath = self.getpath(mynewcpv)
			if os.path.exists(newpath):
				#dest already exists; keep this puppy where it is.
				continue
			_movefile(origpath, newpath, mysettings=self.settings)
			self._clear_pkg_cache(self._dblink(mycpv))
			self._clear_pkg_cache(self._dblink(mynewcpv))

			# We need to rename the ebuild now.
			old_pf = catsplit(mycpv)[1]
			new_pf = catsplit(mynewcpv)[1]
			if new_pf != old_pf:
				try:
					os.rename(os.path.join(newpath, old_pf + ".ebuild"),
						os.path.join(newpath, new_pf + ".ebuild"))
				except EnvironmentError as e:
					if e.errno != errno.ENOENT:
						raise
					del e
			write_atomic(os.path.join(newpath, "PF"), new_pf+"\n")
			write_atomic(os.path.join(newpath, "CATEGORY"), mynewcat+"\n")

		return moves

	def cp_list(self, mycp, use_cache=1):
		mysplit=catsplit(mycp)
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat = os.stat(self.getpath(mysplit[0])).st_mtime_ns
		except OSError:
			mystat = 0
		if use_cache and mycp in self.cpcache:
			cpc = self.cpcache[mycp]
			if cpc[0] == mystat:
				return cpc[1][:]
		cat_dir = self.getpath(mysplit[0])
		try:
			dir_list = os.listdir(cat_dir)
		except EnvironmentError as e:
			if e.errno == PermissionDenied.errno:
				raise PermissionDenied(cat_dir)
			del e
			dir_list = []

		returnme = []
		for x in dir_list:
			if self._excluded_dirs.match(x) is not None:
				continue
			ps = pkgsplit(x)
			if not ps:
				self.invalidentry(os.path.join(self.getpath(mysplit[0]), x))
				continue
			if len(mysplit) > 1:
				if ps[0] == mysplit[1]:
					cpv = "%s/%s" % (mysplit[0], x)
					metadata = dict(zip(self._aux_cache_keys,
						self.aux_get(cpv, self._aux_cache_keys)))
					returnme.append(_pkg_str(cpv, metadata=metadata,
						settings=self.settings, db=self))
		self._cpv_sort_ascending(returnme)
		if use_cache:
			self.cpcache[mycp] = [mystat, returnme[:]]
		elif mycp in self.cpcache:
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self, use_cache=1):
		"""
		Set use_cache=0 to bypass the portage.cachedir() cache in cases
		when the accuracy of mtime staleness checks should not be trusted
		(generally this is only necessary in critical sections that
		involve merge or unmerge of packages).
		"""
		return list(self._iter_cpv_all(use_cache=use_cache))

	def _iter_cpv_all(self, use_cache=True, sort=False):
		returnme = []
		basepath = os.path.join(self._eroot, VDB_PATH) + os.path.sep

		if use_cache:
			from portage import listdir
		else:
			def listdir(p, **kwargs):
				try:
					return [x for x in os.listdir(p) \
						if os.path.isdir(os.path.join(p, x))]
				except EnvironmentError as e:
					if e.errno == PermissionDenied.errno:
						raise PermissionDenied(p)
					del e
					return []

		catdirs = listdir(basepath, EmptyOnError=1, ignorecvs=1, dirsonly=1)
		if sort:
			catdirs.sort()

		for x in catdirs:
			if self._excluded_dirs.match(x) is not None:
				continue
			if not self._category_re.match(x):
				continue

			pkgdirs = listdir(basepath + x, EmptyOnError=1, dirsonly=1)
			if sort:
				pkgdirs.sort()

			for y in pkgdirs:
				if self._excluded_dirs.match(y) is not None:
					continue
				subpath = x + "/" + y
				# -MERGING- should never be a cpv, nor should files.
				try:
					subpath = _pkg_str(subpath, db=self)
				except InvalidData:
					self.invalidentry(self.getpath(subpath))
					continue

				yield subpath

	def cp_all(self, use_cache=1, sort=False):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			try:
				mysplit = catpkgsplit(y)
			except InvalidData:
				self.invalidentry(self.getpath(y))
				continue
			if not mysplit:
				self.invalidentry(self.getpath(y))
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return sorted(d) if sort else list(d)

	def checkblockers(self, origdep):
		pass

	def _clear_cache(self):
		self.mtdircache.clear()
		self.matchcache.clear()
		self.cpcache.clear()
		self._aux_cache_obj = None

	def _add(self, pkg_dblink):
		self._pkgs_changed = True
		self._clear_pkg_cache(pkg_dblink)

	def _remove(self, pkg_dblink):
		self._pkgs_changed = True
		self._clear_pkg_cache(pkg_dblink)

	def _clear_pkg_cache(self, pkg_dblink):
		# Due to 1 second mtime granularity in <python-2.5, mtime checks
		# are not always sufficient to invalidate vardbapi caches. Therefore,
		# the caches need to be actively invalidated here.
		self.mtdircache.pop(pkg_dblink.cat, None)
		self.matchcache.pop(pkg_dblink.cat, None)
		self.cpcache.pop(pkg_dblink.mysplit[0], None)
		dircache.pop(pkg_dblink.dbcatdir, None)

	def match(self, origdep, use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		cache_key = (mydep, mydep.unevaluated_atom)
		mykey = dep_getkey(mydep)
		mycat = catsplit(mykey)[0]
		if not use_cache:
			if mycat in self.matchcache:
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			return list(self._iter_match(mydep,
				self.cp_list(mydep.cp, use_cache=use_cache)))
		try:
			curmtime = os.stat(os.path.join(self._eroot, VDB_PATH, mycat)).st_mtime_ns
		except (IOError, OSError):
			curmtime=0

		if mycat not in self.matchcache or \
			self.mtdircache[mycat] != curmtime:
			# clear cache entry
			self.mtdircache[mycat] = curmtime
			self.matchcache[mycat] = {}
		if mydep not in self.matchcache[mycat]:
			mymatch = list(self._iter_match(mydep,
				self.cp_list(mydep.cp, use_cache=use_cache)))
			self.matchcache[mycat][cache_key] = mymatch
		return self.matchcache[mycat][cache_key][:]

	def findname(self, mycpv, myrepo=None):
		return self.getpath(str(mycpv), filename=catsplit(mycpv)[1]+".ebuild")

	def flush_cache(self):
		"""If the current user has permission and the internal aux_get cache has
		been updated, save it to disk and mark it unmodified.  This is called
		by emerge after it has loaded the full vdb for use in dependency
		calculations.  Currently, the cache is only written if the user has
		superuser privileges (since that's required to obtain a lock), but all
		users have read access and benefit from faster metadata lookups (as
		long as at least part of the cache is still valid)."""
		if self._flush_cache_enabled and \
			self._aux_cache is not None and \
			secpass >= 2 and \
			(len(self._aux_cache["modified"]) >= self._aux_cache_threshold or
			not os.path.exists(self._cache_delta_filename)):

			ensure_dirs(os.path.dirname(self._aux_cache_filename))

			self._owners.populate() # index any unindexed contents
			valid_nodes = set(self.cpv_all())
			for cpv in list(self._aux_cache["packages"]):
				if cpv not in valid_nodes:
					del self._aux_cache["packages"][cpv]
			del self._aux_cache["modified"]
			timestamp = time.time()
			self._aux_cache["timestamp"] = timestamp

			with atomic_ofstream(self._aux_cache_filename, 'wb') as f:
				pickle.dump(self._aux_cache, f, protocol=2)

			apply_secpass_permissions(
				self._aux_cache_filename, mode=0o644)

			self._cache_delta.initialize(timestamp)
			apply_secpass_permissions(
				self._cache_delta_filename, mode=0o644)

			self._aux_cache["modified"] = set()

	@property
	def _aux_cache(self):
		if self._aux_cache_obj is None:
			self._aux_cache_init()
		return self._aux_cache_obj

	def _aux_cache_init(self):
		aux_cache = None
		open_kwargs = {}
		try:
			with open(_unicode_encode(self._aux_cache_filename,
				encoding=_encodings['fs'], errors='strict'),
				mode='rb', **open_kwargs) as f:
				mypickle = pickle.Unpickler(f)
				try:
					mypickle.find_global = None
				except AttributeError:
					# TODO: If py3k, override Unpickler.find_class().
					pass
				aux_cache = mypickle.load()
		except (SystemExit, KeyboardInterrupt):
			raise
		except Exception as e:
			if isinstance(e, EnvironmentError) and \
				getattr(e, 'errno', None) in (errno.ENOENT, errno.EACCES):
				pass
			else:
				writemsg(_("!!! Error loading '%s': %s\n") % \
					(self._aux_cache_filename, e), noiselevel=-1)
			del e

		if not aux_cache or \
			not isinstance(aux_cache, dict) or \
			aux_cache.get("version") != self._aux_cache_version or \
			not aux_cache.get("packages"):
			aux_cache = {"version": self._aux_cache_version}
			aux_cache["packages"] = {}

		owners = aux_cache.get("owners")
		if owners is not None:
			if not isinstance(owners, dict):
				owners = None
			elif "version" not in owners:
				owners = None
			elif owners["version"] != self._owners_cache_version:
				owners = None
			elif "base_names" not in owners:
				owners = None
			elif not isinstance(owners["base_names"], dict):
				owners = None

		if owners is None:
			owners = {
				"base_names" : {},
				"version"    : self._owners_cache_version
			}
			aux_cache["owners"] = owners

		aux_cache["modified"] = set()
		self._aux_cache_obj = aux_cache

	def aux_get(self, mycpv, wants, myrepo = None):
		"""This automatically caches selected keys that are frequently needed
		by emerge for dependency calculations.  The cached metadata is
		considered valid if the mtime of the package directory has not changed
		since the data was cached.  The cache is stored in a pickled dict
		object with the following format:

		{version:"1", "packages":{cpv1:(mtime,{k1,v1, k2,v2, ...}), cpv2...}}

		If an error occurs while loading the cache pickle or the version is
		unrecognized, the cache will simple be recreated from scratch (it is
		completely disposable).
		"""
		cache_these_wants = self._aux_cache_keys.intersection(wants)
		for x in wants:
			if self._aux_cache_keys_re.match(x) is not None:
				cache_these_wants.add(x)

		if not cache_these_wants:
			mydata = self._aux_get(mycpv, wants)
			return [mydata[x] for x in wants]

		cache_these = set(self._aux_cache_keys)
		cache_these.update(cache_these_wants)

		mydir = self.getpath(mycpv)
		mydir_stat = None
		try:
			mydir_stat = os.stat(mydir)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			raise KeyError(mycpv)
		# Use float mtime when available.
		mydir_mtime = mydir_stat.st_mtime
		pkg_data = self._aux_cache["packages"].get(mycpv)
		pull_me = cache_these.union(wants)
		mydata = {"_mtime_" : mydir_mtime}
		cache_valid = False
		cache_incomplete = False
		cache_mtime = None
		metadata = None
		if pkg_data is not None:
			if not isinstance(pkg_data, tuple) or len(pkg_data) != 2:
				pkg_data = None
			else:
				cache_mtime, metadata = pkg_data
				if not isinstance(cache_mtime, (float, int)) or \
					not isinstance(metadata, dict):
					pkg_data = None

		if pkg_data:
			cache_mtime, metadata = pkg_data
			if isinstance(cache_mtime, float):
				if cache_mtime == mydir_stat.st_mtime:
					cache_valid = True

				# Handle truncated mtime in order to avoid cache
				# invalidation for livecd squashfs (bug 564222).
				elif int(cache_mtime) == mydir_stat.st_mtime:
					cache_valid = True
			else:
				# Cache may contain integer mtime.
				cache_valid = cache_mtime == mydir_stat[stat.ST_MTIME]

		if cache_valid:
			# Migrate old metadata to unicode.
			for k, v in metadata.items():
				metadata[k] = _unicode_decode(v,
					encoding=_encodings['repo.content'], errors='replace')

			mydata.update(metadata)
			pull_me.difference_update(mydata)

		if pull_me:
			# pull any needed data and cache it
			aux_keys = list(pull_me)
			mydata.update(self._aux_get(mycpv, aux_keys, st=mydir_stat))
			if not cache_valid or cache_these.difference(metadata):
				cache_data = {}
				if cache_valid and metadata:
					cache_data.update(metadata)
				for aux_key in cache_these:
					cache_data[aux_key] = mydata[aux_key]
				self._aux_cache["packages"][str(mycpv)] = \
					(mydir_mtime, cache_data)
				self._aux_cache["modified"].add(mycpv)

		eapi_attrs = _get_eapi_attrs(mydata['EAPI'])
		if _get_slot_re(eapi_attrs).match(mydata['SLOT']) is None:
			# Empty or invalid slot triggers InvalidAtom exceptions when
			# generating slot atoms for packages, so translate it to '0' here.
			mydata['SLOT'] = '0'

		return [mydata[x] for x in wants]

	def _aux_get(self, mycpv, wants, st=None):
		mydir = self.getpath(mycpv)
		if st is None:
			try:
				st = os.stat(mydir)
			except OSError as e:
				if e.errno == errno.ENOENT:
					raise KeyError(mycpv)
				elif e.errno == PermissionDenied.errno:
					raise PermissionDenied(mydir)
				else:
					raise
		if not stat.S_ISDIR(st.st_mode):
			raise KeyError(mycpv)
		results = {}
		env_keys = []
		for x in wants:
			if x == "_mtime_":
				results[x] = st[stat.ST_MTIME]
				continue
			try:
				with io.open(
					_unicode_encode(os.path.join(mydir, x),
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace') as f:
					myd = f.read()
			except IOError:
				if x not in self._aux_cache_keys and \
					self._aux_cache_keys_re.match(x) is None:
					env_keys.append(x)
					continue
				myd = ''

			# Preserve \n for metadata that is known to
			# contain multiple lines.
			if self._aux_multi_line_re.match(x) is None:
				myd = " ".join(myd.split())

			results[x] = myd

		if env_keys:
			env_results = self._aux_env_search(mycpv, env_keys)
			for k in env_keys:
				v = env_results.get(k)
				if v is None:
					v = ''
				if self._aux_multi_line_re.match(k) is None:
					v = " ".join(v.split())
				results[k] = v

		if results.get("EAPI") == "":
			results["EAPI"] = '0'

		return results

	def _aux_env_search(self, cpv, variables):
		"""
		Search environment.bz2 for the specified variables. Returns
		a dict mapping variables to values, and any variables not
		found in the environment will not be included in the dict.
		This is useful for querying variables like ${SRC_URI} and
		${A}, which are not saved in separate files but are available
		in environment.bz2 (see bug #395463).
		"""
		env_file = self.getpath(cpv, filename="environment.bz2")
		if not os.path.isfile(env_file):
			return {}
		bunzip2_cmd = portage.util.shlex_split(
			self.settings.get("PORTAGE_BUNZIP2_COMMAND", ""))
		if not bunzip2_cmd:
			bunzip2_cmd = portage.util.shlex_split(
				self.settings["PORTAGE_BZIP2_COMMAND"])
			bunzip2_cmd.append("-d")
		args = bunzip2_cmd + ["-c", env_file]
		try:
			proc = subprocess.Popen(args, stdout=subprocess.PIPE)
		except EnvironmentError as e:
			if e.errno != errno.ENOENT:
				raise
			raise portage.exception.CommandNotFound(args[0])

		# Parts of the following code are borrowed from
		# filter-bash-environment.py (keep them in sync).
		var_assign_re = re.compile(r'(^|^declare\s+-\S+\s+|^declare\s+|^export\s+)([^=\s]+)=("|\')?(.*)$')
		close_quote_re = re.compile(r'(\\"|"|\')\s*$')
		def have_end_quote(quote, line):
			close_quote_match = close_quote_re.search(line)
			return close_quote_match is not None and \
				close_quote_match.group(1) == quote

		variables = frozenset(variables)
		results = {}
		for line in proc.stdout:
			line = _unicode_decode(line,
				encoding=_encodings['content'], errors='replace')
			var_assign_match = var_assign_re.match(line)
			if var_assign_match is not None:
				key = var_assign_match.group(2)
				quote = var_assign_match.group(3)
				if quote is not None:
					if have_end_quote(quote,
						line[var_assign_match.end(2)+2:]):
						value = var_assign_match.group(4)
					else:
						value = [var_assign_match.group(4)]
						for line in proc.stdout:
							line = _unicode_decode(line,
								encoding=_encodings['content'],
								errors='replace')
							value.append(line)
							if have_end_quote(quote, line):
								break
						value = ''.join(value)
					# remove trailing quote and whitespace
					value = value.rstrip()[:-1]
				else:
					value = var_assign_match.group(4).rstrip()

				if key in variables:
					results[key] = value

		proc.wait()
		proc.stdout.close()
		return results

	def aux_update(self, cpv, values):
		mylink = self._dblink(cpv)
		if not mylink.exists():
			raise KeyError(cpv)
		self._bump_mtime(cpv)
		self._clear_pkg_cache(mylink)
		for k, v in values.items():
			if v:
				mylink.setfile(k, v)
			else:
				try:
					os.unlink(os.path.join(self.getpath(cpv), k))
				except EnvironmentError:
					pass
		self._bump_mtime(cpv)

	@coroutine
	def unpack_metadata(self, pkg, dest_dir, loop=None):
		"""
		Unpack package metadata to a directory. This method is a coroutine.

		@param pkg: package to unpack
		@type pkg: _pkg_str or portage.config
		@param dest_dir: destination directory
		@type dest_dir: str
		"""
		loop = asyncio._wrap_loop(loop)
		if not isinstance(pkg, portage.config):
			cpv = pkg
		else:
			cpv = pkg.mycpv
		dbdir = self.getpath(cpv)
		def async_copy():
			for parent, dirs, files in os.walk(dbdir, onerror=_raise_exc):
				for key in files:
					shutil.copy(os.path.join(parent, key),
						os.path.join(dest_dir, key))
				break
		yield loop.run_in_executor(ForkExecutor(loop=loop), async_copy)

	@coroutine
	def unpack_contents(self, pkg, dest_dir,
		include_config=None, include_unmodified_config=None, loop=None):
		"""
		Unpack package contents to a directory. This method is a coroutine.

		This copies files from the installed system, in the same way
		as the quickpkg(1) command. Default behavior for handling
		of protected configuration files is controlled by the
		QUICKPKG_DEFAULT_OPTS variable. The relevant quickpkg options
		are --include-config and --include-unmodified-config. When
		a configuration file is not included because it is protected,
		an ewarn message is logged.

		@param pkg: package to unpack
		@type pkg: _pkg_str or portage.config
		@param dest_dir: destination directory
		@type dest_dir: str
		@param include_config: Include all files protected by
			CONFIG_PROTECT (as a security precaution, default is False
			unless modified by QUICKPKG_DEFAULT_OPTS).
		@type include_config: bool
		@param include_unmodified_config: Include files protected by
			CONFIG_PROTECT that have not been modified since installation
			(as a security precaution, default is False unless modified
			by QUICKPKG_DEFAULT_OPTS).
		@type include_unmodified_config: bool
		"""
		loop = asyncio._wrap_loop(loop)
		if not isinstance(pkg, portage.config):
			settings = self.settings
			cpv = pkg
		else:
			settings = pkg
			cpv = settings.mycpv

		scheduler = SchedulerInterface(loop)
		parser = argparse.ArgumentParser()
		parser.add_argument('--include-config',
			choices=('y', 'n'),
			default='n')
		parser.add_argument('--include-unmodified-config',
			choices=('y', 'n'),
			default='n')

		# Method parameters may override QUICKPKG_DEFAULT_OPTS.
		opts_list = portage.util.shlex_split(settings.get('QUICKPKG_DEFAULT_OPTS', ''))
		if include_config is not None:
			opts_list.append('--include-config={}'.format(
				'y' if include_config else 'n'))
		if include_unmodified_config is not None:
			opts_list.append('--include-unmodified-config={}'.format(
				'y' if include_unmodified_config else 'n'))

		opts, args = parser.parse_known_args(opts_list)

		tar_cmd = ('tar', '-x', '--xattrs', '--xattrs-include=*', '-C', dest_dir)
		pr, pw = os.pipe()
		proc = (yield asyncio.create_subprocess_exec(*tar_cmd, stdin=pr))
		os.close(pr)
		with os.fdopen(pw, 'wb', 0) as pw_file:
			excluded_config_files = (yield loop.run_in_executor(ForkExecutor(loop=loop),
				functools.partial(self._dblink(cpv).quickpkg,
				pw_file,
				include_config=opts.include_config == 'y',
				include_unmodified_config=opts.include_unmodified_config == 'y')))
		yield proc.wait()
		if proc.returncode != os.EX_OK:
			raise PortageException('command failed: {}'.format(tar_cmd))

		if excluded_config_files:
			log_lines = ([_("Config files excluded by QUICKPKG_DEFAULT_OPTS (see quickpkg(1) man page):")] +
				['\t{}'.format(name) for name in excluded_config_files])
			out = io.StringIO()
			for line in log_lines:
				portage.elog.messages.ewarn(line, phase='install', key=cpv, out=out)
			scheduler.output(out.getvalue(),
				background=self.settings.get("PORTAGE_BACKGROUND") == "1",
				log_path=settings.get("PORTAGE_LOG_FILE"))

	def counter_tick(self, myroot=None, mycpv=None):
		"""
		@param myroot: ignored, self._eroot is used instead
		"""
		return self.counter_tick_core(incrementing=1, mycpv=mycpv)

	def get_counter_tick_core(self, myroot=None, mycpv=None):
		"""
		Use this method to retrieve the counter instead
		of having to trust the value of a global counter
		file that can lead to invalid COUNTER
		generation. When cache is valid, the package COUNTER
		files are not read and we rely on the timestamp of
		the package directory to validate cache. The stat
		calls should only take a short time, so performance
		is sufficient without having to rely on a potentially
		corrupt global counter file.

		The global counter file located at
		$CACHE_PATH/counter serves to record the
		counter of the last installed package and
		it also corresponds to the total number of
		installation actions that have occurred in
		the history of this package database.

		@param myroot: ignored, self._eroot is used instead
		"""
		del myroot
		counter = -1
		try:
			with io.open(
				_unicode_encode(self._counter_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				try:
					counter = int(f.readline().strip())
				except (OverflowError, ValueError) as e:
					writemsg(_("!!! COUNTER file is corrupt: '%s'\n") %
						self._counter_path, noiselevel=-1)
					writemsg("!!! %s\n" % (e,), noiselevel=-1)
		except EnvironmentError as e:
			# Silently allow ENOENT since files under
			# /var/cache/ are allowed to disappear.
			if e.errno != errno.ENOENT:
				writemsg(_("!!! Unable to read COUNTER file: '%s'\n") % \
					self._counter_path, noiselevel=-1)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
			del e

		if self._cached_counter == counter:
			max_counter = counter
		else:
			# We must ensure that we return a counter
			# value that is at least as large as the
			# highest one from the installed packages,
			# since having a corrupt value that is too low
			# can trigger incorrect AUTOCLEAN behavior due
			# to newly installed packages having lower
			# COUNTERs than the previous version in the
			# same slot.
			max_counter = counter
			for cpv in self.cpv_all():
				try:
					pkg_counter = int(self.aux_get(cpv, ["COUNTER"])[0])
				except (KeyError, OverflowError, ValueError):
					continue
				if pkg_counter > max_counter:
					max_counter = pkg_counter

		return max_counter + 1

	def counter_tick_core(self, myroot=None, incrementing=1, mycpv=None):
		"""
		This method will grab the next COUNTER value and record it back
		to the global file. Note that every package install must have
		a unique counter, since a slotmove update can move two packages
		into the same SLOT and in that case it's important that both
		packages have different COUNTER metadata.

		@param myroot: ignored, self._eroot is used instead
		@param mycpv: ignored
		@rtype: int
		@return: new counter value
		"""
		myroot = None
		mycpv = None
		self.lock()
		try:
			counter = self.get_counter_tick_core() - 1
			if incrementing:
				#increment counter
				counter += 1
				# update new global counter file
				try:
					write_atomic(self._counter_path, str(counter))
				except InvalidLocation:
					self.settings._init_dirs()
					write_atomic(self._counter_path, str(counter))
			self._cached_counter = counter

			# Since we hold a lock, this is a good opportunity
			# to flush the cache. Note that this will only
			# flush the cache periodically in the main process
			# when _aux_cache_threshold is exceeded.
			self.flush_cache()
		finally:
			self.unlock()

		return counter

	def _dblink(self, cpv):
		category, pf = catsplit(cpv)
		return dblink(category, pf, settings=self.settings,
			vartree=self.vartree, treetype="vartree")

	def removeFromContents(self, pkg, paths, relative_paths=True):
		"""
		@param pkg: cpv for an installed package
		@type pkg: string
		@param paths: paths of files to remove from contents
		@type paths: iterable
		"""
		if not hasattr(pkg, "getcontents"):
			pkg = self._dblink(pkg)
		root = self.settings['ROOT']
		root_len = len(root) - 1
		new_contents = pkg.getcontents().copy()
		removed = 0

		for filename in paths:
			filename = _unicode_decode(filename,
				encoding=_encodings['content'], errors='strict')
			filename = normalize_path(filename)
			if relative_paths:
				relative_filename = filename
			else:
				relative_filename = filename[root_len:]
			contents_key = pkg._match_contents(relative_filename)
			if contents_key:
				# It's possible for two different paths to refer to the same
				# contents_key, due to directory symlinks. Therefore, pass a
				# default value to pop, in order to avoid a KeyError which
				# could otherwise be triggered (see bug #454400).
				new_contents.pop(contents_key, None)
				removed += 1

		if removed:
			# Also remove corresponding NEEDED lines, so that they do
			# no corrupt LinkageMap data for preserve-libs.
			needed_filename = os.path.join(pkg.dbdir, LinkageMap._needed_aux_key)
			new_needed = None
			try:
				with io.open(_unicode_encode(needed_filename,
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace') as f:
					needed_lines = f.readlines()
			except IOError as e:
				if e.errno not in (errno.ENOENT, errno.ESTALE):
					raise
			else:
				new_needed = []
				for l in needed_lines:
					l = l.rstrip("\n")
					if not l:
						continue
					try:
						entry = NeededEntry.parse(needed_filename, l)
					except InvalidData as e:
						writemsg_level("\n%s\n\n" % (e,),
							level=logging.ERROR, noiselevel=-1)
						continue

					filename = os.path.join(root, entry.filename.lstrip(os.sep))
					if filename in new_contents:
						new_needed.append(entry)

			self.writeContentsToContentsFile(pkg, new_contents, new_needed=new_needed)

	def writeContentsToContentsFile(self, pkg, new_contents, new_needed=None):
		"""
		@param pkg: package to write contents file for
		@type pkg: dblink
		@param new_contents: contents to write to CONTENTS file
		@type new_contents: contents dictionary of the form
					{u'/path/to/file' : (contents_attribute 1, ...), ...}
		@param new_needed: new NEEDED entries
		@type new_needed: list of NeededEntry
		"""
		root = self.settings['ROOT']
		self._bump_mtime(pkg.mycpv)
		if new_needed is not None:
			f = atomic_ofstream(os.path.join(pkg.dbdir, LinkageMap._needed_aux_key))
			for entry in new_needed:
				f.write(str(entry))
			f.close()
		f = atomic_ofstream(os.path.join(pkg.dbdir, "CONTENTS"))
		write_contents(new_contents, root, f)
		f.close()
		self._bump_mtime(pkg.mycpv)
		pkg._clear_contents_cache()

	class _owners_cache:
		"""
		This class maintains an hash table that serves to index package
		contents by mapping the basename of file to a list of possible
		packages that own it. This is used to optimize owner lookups
		by narrowing the search down to a smaller number of packages.
		"""
		_new_hash = md5
		_hash_bits = 16
		_hex_chars = _hash_bits // 4

		def __init__(self, vardb):
			self._vardb = vardb

		def add(self, cpv):
			eroot_len = len(self._vardb._eroot)
			pkg_hash = self._hash_pkg(cpv)
			db = self._vardb._dblink(cpv)
			if not db.getcontents():
				# Empty path is a code used to represent empty contents.
				self._add_path("", pkg_hash)

			for x in db._contents.keys():
				self._add_path(x[eroot_len:], pkg_hash)

			self._vardb._aux_cache["modified"].add(cpv)

		def _add_path(self, path, pkg_hash):
			"""
			Empty path is a code that represents empty contents.
			"""
			if path:
				name = os.path.basename(path.rstrip(os.path.sep))
				if not name:
					return
			else:
				name = path
			name_hash = self._hash_str(name)
			base_names = self._vardb._aux_cache["owners"]["base_names"]
			pkgs = base_names.get(name_hash)
			if pkgs is None:
				pkgs = {}
				base_names[name_hash] = pkgs
			pkgs[pkg_hash] = None

		def _hash_str(self, s):
			h = self._new_hash()
			# Always use a constant utf_8 encoding here, since
			# the "default" encoding can change.
			h.update(_unicode_encode(s,
				encoding=_encodings['repo.content'],
				errors='backslashreplace'))
			h = h.hexdigest()
			h = h[-self._hex_chars:]
			h = int(h, 16)
			return h

		def _hash_pkg(self, cpv):
			counter, mtime = self._vardb.aux_get(
				cpv, ["COUNTER", "_mtime_"])
			try:
				counter = int(counter)
			except ValueError:
				counter = 0
			return (str(cpv), counter, mtime)

	class _owners_db:

		def __init__(self, vardb):
			self._vardb = vardb

		def populate(self):
			self._populate()

		def _populate(self):
			owners_cache = vardbapi._owners_cache(self._vardb)
			cached_hashes = set()
			base_names = self._vardb._aux_cache["owners"]["base_names"]

			# Take inventory of all cached package hashes.
			for name, hash_values in list(base_names.items()):
				if not isinstance(hash_values, dict):
					del base_names[name]
					continue
				cached_hashes.update(hash_values)

			# Create sets of valid package hashes and uncached packages.
			uncached_pkgs = set()
			hash_pkg = owners_cache._hash_pkg
			valid_pkg_hashes = set()
			for cpv in self._vardb.cpv_all():
				hash_value = hash_pkg(cpv)
				valid_pkg_hashes.add(hash_value)
				if hash_value not in cached_hashes:
					uncached_pkgs.add(cpv)

			# Cache any missing packages.
			for cpv in uncached_pkgs:
				owners_cache.add(cpv)

			# Delete any stale cache.
			stale_hashes = cached_hashes.difference(valid_pkg_hashes)
			if stale_hashes:
				for base_name_hash, bucket in list(base_names.items()):
					for hash_value in stale_hashes.intersection(bucket):
						del bucket[hash_value]
					if not bucket:
						del base_names[base_name_hash]

			return owners_cache

		def get_owners(self, path_iter):
			"""
			@return the owners as a dblink -> set(files) mapping.
			"""
			owners = {}
			for owner, f in self.iter_owners(path_iter):
				owned_files = owners.get(owner)
				if owned_files is None:
					owned_files = set()
					owners[owner] = owned_files
				owned_files.add(f)
			return owners

		def getFileOwnerMap(self, path_iter):
			owners = self.get_owners(path_iter)
			file_owners = {}
			for pkg_dblink, files in owners.items():
				for f in files:
					owner_set = file_owners.get(f)
					if owner_set is None:
						owner_set = set()
						file_owners[f] = owner_set
					owner_set.add(pkg_dblink)
			return file_owners

		def iter_owners(self, path_iter):
			"""
			Iterate over tuples of (dblink, path). In order to avoid
			consuming too many resources for too much time, resources
			are only allocated for the duration of a given iter_owners()
			call. Therefore, to maximize reuse of resources when searching
			for multiple files, it's best to search for them all in a single
			call.
			"""

			if not isinstance(path_iter, list):
				path_iter = list(path_iter)
			owners_cache = self._populate()
			vardb = self._vardb
			root = vardb._eroot
			hash_pkg = owners_cache._hash_pkg
			hash_str = owners_cache._hash_str
			base_names = self._vardb._aux_cache["owners"]["base_names"]
			case_insensitive = "case-insensitive-fs" \
				in vardb.settings.features

			dblink_cache = {}

			def dblink(cpv):
				x = dblink_cache.get(cpv)
				if x is None:
					if len(dblink_cache) > 20:
						# Ensure that we don't run out of memory.
						raise StopIteration()
					x = self._vardb._dblink(cpv)
					dblink_cache[cpv] = x
				return x

			while path_iter:

				path = path_iter.pop()
				if case_insensitive:
					path = path.lower()
				is_basename = os.sep != path[:1]
				if is_basename:
					name = path
				else:
					name = os.path.basename(path.rstrip(os.path.sep))

				if not name:
					continue

				name_hash = hash_str(name)
				pkgs = base_names.get(name_hash)
				owners = []
				if pkgs is not None:
					try:
						for hash_value in pkgs:
							if not isinstance(hash_value, tuple) or \
								len(hash_value) != 3:
								continue
							cpv, counter, mtime = hash_value
							if not isinstance(cpv, str):
								continue
							try:
								current_hash = hash_pkg(cpv)
							except KeyError:
								continue

							if current_hash != hash_value:
								continue

							if is_basename:
								for p in dblink(cpv)._contents.keys():
									if os.path.basename(p) == name:
										owners.append((cpv, dblink(cpv).
										_contents.unmap_key(
										p)[len(root):]))
							else:
								key = dblink(cpv)._match_contents(path)
								if key is not False:
									owners.append(
										(cpv, key[len(root):]))

					except StopIteration:
						path_iter.append(path)
						del owners[:]
						dblink_cache.clear()
						gc.collect()
						for x in self._iter_owners_low_mem(path_iter):
							yield x
						return
					else:
						for cpv, p in owners:
							yield (dblink(cpv), p)

		def _iter_owners_low_mem(self, path_list):
			"""
			This implemention will make a short-lived dblink instance (and
			parse CONTENTS) for every single installed package. This is
			slower and but uses less memory than the method which uses the
			basename cache.
			"""

			if not path_list:
				return

			case_insensitive = "case-insensitive-fs" \
				in self._vardb.settings.features
			path_info_list = []
			for path in path_list:
				if case_insensitive:
					path = path.lower()
				is_basename = os.sep != path[:1]
				if is_basename:
					name = path
				else:
					name = os.path.basename(path.rstrip(os.path.sep))
				path_info_list.append((path, name, is_basename))

			# Do work via the global event loop, so that it can be used
			# for indication of progress during the search (bug #461412).
			event_loop = asyncio._safe_loop()
			root = self._vardb._eroot

			def search_pkg(cpv, search_future):
				dblnk = self._vardb._dblink(cpv)
				results = []
				for path, name, is_basename in path_info_list:
					if is_basename:
						for p in dblnk._contents.keys():
							if os.path.basename(p) == name:
								results.append((dblnk,
									dblnk._contents.unmap_key(
										p)[len(root):]))
					else:
						key = dblnk._match_contents(path)
						if key is not False:
							results.append(
								(dblnk, key[len(root):]))
				search_future.set_result(results)

			for cpv in self._vardb.cpv_all():
				search_future = event_loop.create_future()
				event_loop.call_soon(search_pkg, cpv, search_future)
				event_loop.run_until_complete(search_future)
				for result in search_future.result():
					yield result

class vartree:
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self, root=None, virtual=DeprecationWarning, categories=None,
		settings=None):

		if settings is None:
			settings = portage.settings

		if root is not None and root != settings['ROOT']:
			warnings.warn("The 'root' parameter of the "
				"portage.dbapi.vartree.vartree"
				" constructor is now unused. Use "
				"settings['ROOT'] instead.",
				DeprecationWarning, stacklevel=2)

		if virtual is not DeprecationWarning:
			warnings.warn("The 'virtual' parameter of the "
				"portage.dbapi.vartree.vartree"
				" constructor is unused",
				DeprecationWarning, stacklevel=2)

		self.settings = settings
		self.dbapi = vardbapi(settings=settings, vartree=self)
		self.populated = 1

	@property
	def root(self):
		warnings.warn("The root attribute of "
			"portage.dbapi.vartree.vartree"
			" is deprecated. Use "
			"settings['ROOT'] instead.",
			DeprecationWarning, stacklevel=3)
		return self.settings['ROOT']

	def getpath(self, mykey, filename=None):
		return self.dbapi.getpath(mykey, filename=filename)

	def zap(self, mycpv):
		return

	def inject(self, mycpv):
		return

	def get_provide(self, mycpv):
		return []

	def get_all_provides(self):
		return {}

	def dep_bestmatch(self, mydep, use_cache=1):
		"compatibility method -- all matches, not just visible ones"
		#mymatch=best(match(dep_expand(mydep,self.dbapi),self.dbapi))
		mymatch = best(self.dbapi.match(
			dep_expand(mydep, mydb=self.dbapi, settings=self.settings),
			use_cache=use_cache))
		if mymatch is None:
			return ""
		return mymatch

	def dep_match(self, mydep, use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch = match(mydep,self.dbapi)
		mymatch = self.dbapi.match(mydep, use_cache=use_cache)
		if mymatch is None:
			return []
		return mymatch

	def exists_specific(self, cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallcpv(self):
		"""temporary function, probably to be renamed --- Gets a list of all
		category/package-versions installed on the system."""
		return self.dbapi.cpv_all()

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def getebuildpath(self, fullpackage):
		cat, package = catsplit(fullpackage)
		return self.getpath(fullpackage, filename=package+".ebuild")

	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			return self.dbapi._pkg_str(mycatpkg, None).slot
		except KeyError:
			return ""

	def populate(self):
		self.populated=1

class dblink:
	"""
	This class provides an interface to the installed package database
	At present this is implemented as a text backend in /var/db/pkg.
	"""

	_normalize_needed = re.compile(r'//|^[^/]|./$|(^|/)\.\.?(/|$)')

	_contents_re = re.compile(r'^(' + \
		r'(?P<dir>(dev|dir|fif) (.+))|' + \
		r'(?P<obj>(obj) (.+) (\S+) (\d+))|' + \
		r'(?P<sym>(sym) (.+) -> (.+) ((\d+)|(?P<oldsym>(' + \
		r'\(\d+, \d+L, \d+L, \d+, \d+, \d+, \d+L, \d+, (\d+), \d+\)))))' + \
		r')$'
	)

	# These files are generated by emerge, so we need to remove
	# them when they are the only thing left in a directory.
	_infodir_cleanup = frozenset(["dir", "dir.old"])

	_ignored_unlink_errnos = (
		errno.EBUSY, errno.ENOENT,
		errno.ENOTDIR, errno.EISDIR)

	_ignored_rmdir_errnos = (
		errno.EEXIST, errno.ENOTEMPTY,
		errno.EBUSY, errno.ENOENT,
		errno.ENOTDIR, errno.EISDIR,
		errno.EPERM)

	def __init__(self, cat, pkg, myroot=None, settings=None, treetype=None,
		vartree=None, blockers=None, scheduler=None, pipe=None):
		"""
		Creates a DBlink object for a given CPV.
		The given CPV may not be present in the database already.

		@param cat: Category
		@type cat: String
		@param pkg: Package (PV)
		@type pkg: String
		@param myroot: ignored, settings['ROOT'] is used instead
		@type myroot: String (Path)
		@param settings: Typically portage.settings
		@type settings: portage.config
		@param treetype: one of ['porttree','bintree','vartree']
		@type treetype: String
		@param vartree: an instance of vartree corresponding to myroot.
		@type vartree: vartree
		"""

		if settings is None:
			raise TypeError("settings argument is required")

		mysettings = settings
		self._eroot = mysettings['EROOT']
		self.cat = cat
		self.pkg = pkg
		self.mycpv = self.cat + "/" + self.pkg
		if self.mycpv == settings.mycpv and \
			isinstance(settings.mycpv, _pkg_str):
			self.mycpv = settings.mycpv
		else:
			self.mycpv = _pkg_str(self.mycpv)
		self.mysplit = list(self.mycpv.cpv_split[1:])
		self.mysplit[0] = self.mycpv.cp
		self.treetype = treetype
		if vartree is None:
			vartree = portage.db[self._eroot]["vartree"]
		self.vartree = vartree
		self._blockers = blockers
		self._scheduler = scheduler
		self.dbroot = normalize_path(os.path.join(self._eroot, VDB_PATH))
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/"+MERGING_IDENTIFIER+pkg
		self.dbdir = self.dbpkgdir
		self.settings = mysettings
		self._verbose = self.settings.get("PORTAGE_VERBOSE") == "1"

		self.myroot = self.settings['ROOT']
		self._installed_instance = None
		self.contentscache = None
		self._contents_inodes = None
		self._contents_basenames = None
		self._linkmap_broken = False
		self._device_path_map = {}
		self._hardlink_merge_map = {}
		self._hash_key = (self._eroot, self.mycpv)
		self._protect_obj = None
		self._pipe = pipe
		self._postinst_failure = False

		# When necessary, this attribute is modified for
		# compliance with RESTRICT=preserve-libs.
		self._preserve_libs = "preserve-libs" in mysettings.features
		self._contents = ContentsCaseSensitivityManager(self)
		self._slot_locks = []

	def __hash__(self):
		return hash(self._hash_key)

	def __eq__(self, other):
		return isinstance(other, dblink) and \
			self._hash_key == other._hash_key

	def _get_protect_obj(self):

		if self._protect_obj is None:
			self._protect_obj = ConfigProtect(self._eroot,
			portage.util.shlex_split(
				self.settings.get("CONFIG_PROTECT", "")),
			portage.util.shlex_split(
				self.settings.get("CONFIG_PROTECT_MASK", "")),
			case_insensitive=("case-insensitive-fs"
					in self.settings.features))

		return self._protect_obj

	def isprotected(self, obj):
		return self._get_protect_obj().isprotected(obj)

	def updateprotect(self):
		self._get_protect_obj().updateprotect()

	def lockdb(self):
		self.vartree.dbapi.lock()

	def unlockdb(self):
		self.vartree.dbapi.unlock()

	def _slot_locked(f):
		"""
		A decorator function which, when parallel-install is enabled,
		acquires and releases slot locks for the current package and
		blocked packages. This is required in order to account for
		interactions with blocked packages (involving resolution of
		file collisions).
		"""
		def wrapper(self, *args, **kwargs):
			if "parallel-install" in self.settings.features:
				self._acquire_slot_locks(
					kwargs.get("mydbapi", self.vartree.dbapi))
			try:
				return f(self, *args, **kwargs)
			finally:
				self._release_slot_locks()
		return wrapper

	def _acquire_slot_locks(self, db):
		"""
		Acquire slot locks for the current package and blocked packages.
		"""

		slot_atoms = []

		try:
			slot = self.mycpv.slot
		except AttributeError:
			slot, = db.aux_get(self.mycpv, ["SLOT"])
			slot = slot.partition("/")[0]

		slot_atoms.append(portage.dep.Atom(
			"%s:%s" % (self.mycpv.cp, slot)))

		for blocker in self._blockers or []:
			slot_atoms.append(blocker.slot_atom)

		# Sort atoms so that locks are acquired in a predictable
		# order, preventing deadlocks with competitors that may
		# be trying to acquire overlapping locks.
		slot_atoms.sort()
		for slot_atom in slot_atoms:
			self.vartree.dbapi._slot_lock(slot_atom)
			self._slot_locks.append(slot_atom)

	def _release_slot_locks(self):
		"""
		Release all slot locks.
		"""
		while self._slot_locks:
			self.vartree.dbapi._slot_unlock(self._slot_locks.pop())

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir

	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)

	def delete(self):
		"""
		Remove this entry from the database
		"""
		try:
			os.lstat(self.dbdir)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ENOTDIR, errno.ESTALE):
				raise
			return

		# Check validity of self.dbdir before attempting to remove it.
		if not self.dbdir.startswith(self.dbroot):
			writemsg(_("portage.dblink.delete(): invalid dbdir: %s\n") % \
				self.dbdir, noiselevel=-1)
			return

		if self.dbdir is self.dbpkgdir:
			counter, = self.vartree.dbapi.aux_get(
				self.mycpv, ["COUNTER"])
			self.vartree.dbapi._cache_delta.recordEvent(
				"remove", self.mycpv,
				self.settings["SLOT"].split("/")[0], counter)

		shutil.rmtree(self.dbdir)
		# If empty, remove parent category directory.
		try:
			os.rmdir(os.path.dirname(self.dbdir))
		except OSError:
			pass
		self.vartree.dbapi._remove(self)

		# Use self.dbroot since we need an existing path for syncfs.
		try:
			self._merged_path(self.dbroot, os.lstat(self.dbroot))
		except OSError:
			pass

		self._post_merge_sync()

	def clearcontents(self):
		"""
		For a given db entry (self), erase the CONTENTS values.
		"""
		self.lockdb()
		try:
			if os.path.exists(self.dbdir+"/CONTENTS"):
				os.unlink(self.dbdir+"/CONTENTS")
		finally:
			self.unlockdb()

	def _clear_contents_cache(self):
		self.contentscache = None
		self._contents_inodes = None
		self._contents_basenames = None
		self._contents.clear_cache()

	def getcontents(self):
		"""
		Get the installed files of a given package (aka what that package installed)
		"""
		if self.contentscache is not None:
			return self.contentscache
		contents_file = os.path.join(self.dbdir, "CONTENTS")
		pkgfiles = {}
		try:
			with io.open(_unicode_encode(contents_file,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				mylines = f.readlines()
		except EnvironmentError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			self.contentscache = pkgfiles
			return pkgfiles

		null_byte = "\0"
		normalize_needed = self._normalize_needed
		contents_re = self._contents_re
		obj_index = contents_re.groupindex['obj']
		dir_index = contents_re.groupindex['dir']
		sym_index = contents_re.groupindex['sym']
		# The old symlink format may exist on systems that have packages
		# which were installed many years ago (see bug #351814).
		oldsym_index = contents_re.groupindex['oldsym']
		# CONTENTS files already contain EPREFIX
		myroot = self.settings['ROOT']
		if myroot == os.path.sep:
			myroot = None
		# used to generate parent dir entries
		dir_entry = ("dir",)
		eroot_split_len = len(self.settings["EROOT"].split(os.sep)) - 1
		pos = 0
		errors = []
		for pos, line in enumerate(mylines):
			if null_byte in line:
				# Null bytes are a common indication of corruption.
				errors.append((pos + 1, _("Null byte found in CONTENTS entry")))
				continue
			line = line.rstrip("\n")
			m = contents_re.match(line)
			if m is None:
				errors.append((pos + 1, _("Unrecognized CONTENTS entry")))
				continue

			if m.group(obj_index) is not None:
				base = obj_index
				#format: type, mtime, md5sum
				data = (m.group(base+1), m.group(base+4), m.group(base+3))
			elif m.group(dir_index) is not None:
				base = dir_index
				#format: type
				data = (m.group(base+1),)
			elif m.group(sym_index) is not None:
				base = sym_index
				if m.group(oldsym_index) is None:
					mtime = m.group(base+5)
				else:
					mtime = m.group(base+8)
				#format: type, mtime, dest
				data = (m.group(base+1), mtime, m.group(base+3))
			else:
				# This won't happen as long the regular expression
				# is written to only match valid entries.
				raise AssertionError(_("required group not found " + \
					"in CONTENTS entry: '%s'") % line)

			path = m.group(base+2)
			if normalize_needed.search(path) is not None:
				path = normalize_path(path)
				if not path.startswith(os.path.sep):
					path = os.path.sep + path

			if myroot is not None:
				path = os.path.join(myroot, path.lstrip(os.path.sep))

			# Implicitly add parent directories, since we can't necessarily
			# assume that they are explicitly listed in CONTENTS, and it's
			# useful for callers if they can rely on parent directory entries
			# being generated here (crucial for things like dblink.isowner()).
			path_split = path.split(os.sep)
			path_split.pop()
			while len(path_split) > eroot_split_len:
				parent = os.sep.join(path_split)
				if parent in pkgfiles:
					break
				pkgfiles[parent] = dir_entry
				path_split.pop()

			pkgfiles[path] = data

		if errors:
			writemsg(_("!!! Parse error in '%s'\n") % contents_file, noiselevel=-1)
			for pos, e in errors:
				writemsg(_("!!!   line %d: %s\n") % (pos, e), noiselevel=-1)
		self.contentscache = pkgfiles
		return pkgfiles

	def quickpkg(self, output_file, include_config=False, include_unmodified_config=False):
		"""
		Create a tar file appropriate for use by quickpkg.

		@param output_file: Write binary tar stream to file.
		@type output_file: file
		@param include_config: Include all files protected by CONFIG_PROTECT
			(as a security precaution, default is False).
		@type include_config: bool
		@param include_unmodified_config: Include files protected by CONFIG_PROTECT
			that have not been modified since installation (as a security precaution,
			default is False).
		@type include_unmodified_config: bool
		@rtype: list
		@return: Paths of protected configuration files which have been omitted.
		"""
		settings = self.settings
		cpv = self.mycpv
		xattrs = 'xattr' in settings.features
		contents = self.getcontents()
		excluded_config_files = []
		protect = None

		if not include_config:
			confprot = ConfigProtect(settings['EROOT'],
				portage.util.shlex_split(settings.get('CONFIG_PROTECT', '')),
				portage.util.shlex_split(settings.get('CONFIG_PROTECT_MASK', '')),
				case_insensitive=('case-insensitive-fs' in settings.features))

			def protect(filename):
				if not confprot.isprotected(filename):
					return False
				if include_unmodified_config:
					file_data = contents[filename]
					if file_data[0] == 'obj':
						orig_md5 = file_data[2].lower()
						cur_md5 = perform_md5(filename, calc_prelink=1)
						if orig_md5 == cur_md5:
							return False
				excluded_config_files.append(filename)
				return True

		# The tarfile module will write pax headers holding the
		# xattrs only if PAX_FORMAT is specified here.
		with tarfile.open(fileobj=output_file, mode='w|',
			format=tarfile.PAX_FORMAT if xattrs else tarfile.DEFAULT_FORMAT) as tar:
			tar_contents(contents, settings['ROOT'], tar, protect=protect, xattrs=xattrs)

		return excluded_config_files

	def _prune_plib_registry(self, unmerge=False,
		needed=None, preserve_paths=None):
		# remove preserved libraries that don't have any consumers left
		if not (self._linkmap_broken or
			self.vartree.dbapi._linkmap is None or
			self.vartree.dbapi._plib_registry is None):
			self.vartree.dbapi._fs_lock()
			plib_registry = self.vartree.dbapi._plib_registry
			plib_registry.lock()
			try:
				plib_registry.load()

				unmerge_with_replacement = \
					unmerge and preserve_paths is not None
				if unmerge_with_replacement:
					# If self.mycpv is about to be unmerged and we
					# have a replacement package, we want to exclude
					# the irrelevant NEEDED data that belongs to
					# files which are being unmerged now.
					exclude_pkgs = (self.mycpv,)
				else:
					exclude_pkgs = None

				self._linkmap_rebuild(exclude_pkgs=exclude_pkgs,
					include_file=needed, preserve_paths=preserve_paths)

				if unmerge:
					unmerge_preserve = None
					if not unmerge_with_replacement:
						unmerge_preserve = \
							self._find_libs_to_preserve(unmerge=True)
					counter = self.vartree.dbapi.cpv_counter(self.mycpv)
					try:
						slot = self.mycpv.slot
					except AttributeError:
						slot = _pkg_str(self.mycpv, slot=self.settings["SLOT"]).slot
					plib_registry.unregister(self.mycpv, slot, counter)
					if unmerge_preserve:
						for path in sorted(unmerge_preserve):
							contents_key = self._match_contents(path)
							if not contents_key:
								continue
							obj_type = self.getcontents()[contents_key][0]
							self._display_merge(_(">>> needed   %s %s\n") % \
								(obj_type, contents_key), noiselevel=-1)
						plib_registry.register(self.mycpv,
							slot, counter, unmerge_preserve)
						# Remove the preserved files from our contents
						# so that they won't be unmerged.
						self.vartree.dbapi.removeFromContents(self,
							unmerge_preserve)

				unmerge_no_replacement = \
					unmerge and not unmerge_with_replacement
				cpv_lib_map = self._find_unused_preserved_libs(
					unmerge_no_replacement)
				if cpv_lib_map:
					self._remove_preserved_libs(cpv_lib_map)
					self.vartree.dbapi.lock()
					try:
						for cpv, removed in cpv_lib_map.items():
							if not self.vartree.dbapi.cpv_exists(cpv):
								continue
							self.vartree.dbapi.removeFromContents(cpv, removed)
					finally:
						self.vartree.dbapi.unlock()

				plib_registry.store()
			finally:
				plib_registry.unlock()
				self.vartree.dbapi._fs_unlock()

	@_slot_locked
	def unmerge(self, pkgfiles=None, trimworld=None, cleanup=True,
		ldpath_mtimes=None, others_in_slot=None, needed=None,
		preserve_paths=None):
		"""
		Calls prerm
		Unmerges a given package (CPV)
		calls postrm
		calls cleanrm
		calls env_update

		@param pkgfiles: files to unmerge (generally self.getcontents() )
		@type pkgfiles: Dictionary
		@param trimworld: Unused
		@type trimworld: Boolean
		@param cleanup: cleanup to pass to doebuild (see doebuild)
		@type cleanup: Boolean
		@param ldpath_mtimes: mtimes to pass to env_update (see env_update)
		@type ldpath_mtimes: Dictionary
		@param others_in_slot: all dblink instances in this slot, excluding self
		@type others_in_slot: list
		@param needed: Filename containing libraries needed after unmerge.
		@type needed: String
		@param preserve_paths: Libraries preserved by a package instance that
			is currently being merged. They need to be explicitly passed to the
			LinkageMap, since they are not registered in the
			PreservedLibsRegistry yet.
		@type preserve_paths: set
		@rtype: Integer
		@return:
		1. os.EX_OK if everything went well.
		2. return code of the failed phase (for prerm, postrm, cleanrm)
		"""

		if trimworld is not None:
			warnings.warn("The trimworld parameter of the " + \
				"portage.dbapi.vartree.dblink.unmerge()" + \
				" method is now unused.",
				DeprecationWarning, stacklevel=2)

		background = False
		log_path = self.settings.get("PORTAGE_LOG_FILE")
		if self._scheduler is None:
			# We create a scheduler instance and use it to
			# log unmerge output separately from merge output.
			self._scheduler = SchedulerInterface(asyncio._safe_loop())
		if self.settings.get("PORTAGE_BACKGROUND") == "subprocess":
			if self.settings.get("PORTAGE_BACKGROUND_UNMERGE") == "1":
				self.settings["PORTAGE_BACKGROUND"] = "1"
				self.settings.backup_changes("PORTAGE_BACKGROUND")
				background = True
			elif self.settings.get("PORTAGE_BACKGROUND_UNMERGE") == "0":
				self.settings["PORTAGE_BACKGROUND"] = "0"
				self.settings.backup_changes("PORTAGE_BACKGROUND")
		elif self.settings.get("PORTAGE_BACKGROUND") == "1":
			background = True

		self.vartree.dbapi._bump_mtime(self.mycpv)
		showMessage = self._display_merge
		if self.vartree.dbapi._categories is not None:
			self.vartree.dbapi._categories = None

		# When others_in_slot is not None, the backup has already been
		# handled by the caller.
		caller_handles_backup = others_in_slot is not None

		# When others_in_slot is supplied, the security check has already been
		# done for this slot, so it shouldn't be repeated until the next
		# replacement or unmerge operation.
		if others_in_slot is None:
			slot = self.vartree.dbapi._pkg_str(self.mycpv, None).slot
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (portage.cpv_getkey(self.mycpv), slot))
			others_in_slot = []
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					settings=self.settings, vartree=self.vartree,
					treetype="vartree", pipe=self._pipe))

			retval = self._security_check([self] + others_in_slot)
			if retval:
				return retval

		contents = self.getcontents()
		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath = os.path.join(self.dbdir, self.pkg + ".ebuild")
		failures = 0
		ebuild_phase = "prerm"
		mystuff = os.listdir(self.dbdir)
		for x in mystuff:
			if x.endswith(".ebuild"):
				if x[:-7] != self.pkg:
					# Clean up after vardbapi.move_ent() breakage in
					# portage versions before 2.1.2
					os.rename(os.path.join(self.dbdir, x), myebuildpath)
					write_atomic(os.path.join(self.dbdir, "PF"), self.pkg+"\n")
				break

		if self.mycpv != self.settings.mycpv or \
			"EAPI" not in self.settings.configdict["pkg"]:
			# We avoid a redundant setcpv call here when
			# the caller has already taken care of it.
			self.settings.setcpv(self.mycpv, mydb=self.vartree.dbapi)

		eapi_unsupported = False
		try:
			doebuild_environment(myebuildpath, "prerm",
				settings=self.settings, db=self.vartree.dbapi)
		except UnsupportedAPIException as e:
			eapi_unsupported = e

		if self._preserve_libs and "preserve-libs" in \
			self.settings["PORTAGE_RESTRICT"].split():
			self._preserve_libs = False

		builddir_lock = None
		scheduler = self._scheduler
		retval = os.EX_OK
		try:
			# Only create builddir_lock if the caller
			# has not already acquired the lock.
			if "PORTAGE_BUILDDIR_LOCKED" not in self.settings:
				builddir_lock = EbuildBuildDir(
					scheduler=scheduler,
					settings=self.settings)
				scheduler.run_until_complete(builddir_lock.async_lock())
				prepare_build_dirs(settings=self.settings, cleanup=True)
				log_path = self.settings.get("PORTAGE_LOG_FILE")

			# Do this before the following _prune_plib_registry call, since
			# that removes preserved libraries from our CONTENTS, and we
			# may want to backup those libraries first.
			if not caller_handles_backup:
				retval = self._pre_unmerge_backup(background)
				if retval != os.EX_OK:
					showMessage(_("!!! FAILED prerm: quickpkg: %s\n") % retval,
						level=logging.ERROR, noiselevel=-1)
					return retval

			self._prune_plib_registry(unmerge=True, needed=needed,
				preserve_paths=preserve_paths)

			# Log the error after PORTAGE_LOG_FILE is initialized
			# by prepare_build_dirs above.
			if eapi_unsupported:
				# Sometimes this happens due to corruption of the EAPI file.
				failures += 1
				showMessage(_("!!! FAILED prerm: %s\n") % \
					os.path.join(self.dbdir, "EAPI"),
					level=logging.ERROR, noiselevel=-1)
				showMessage("%s\n" % (eapi_unsupported,),
					level=logging.ERROR, noiselevel=-1)
			elif os.path.isfile(myebuildpath):
				phase = EbuildPhase(background=background,
					phase=ebuild_phase, scheduler=scheduler,
					settings=self.settings)
				phase.start()
				retval = phase.wait()

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					failures += 1
					showMessage(_("!!! FAILED prerm: %s\n") % retval,
						level=logging.ERROR, noiselevel=-1)

			self.vartree.dbapi._fs_lock()
			try:
				self._unmerge_pkgfiles(pkgfiles, others_in_slot)
			finally:
				self.vartree.dbapi._fs_unlock()
			self._clear_contents_cache()

			if not eapi_unsupported and os.path.isfile(myebuildpath):
				ebuild_phase = "postrm"
				phase = EbuildPhase(background=background,
					phase=ebuild_phase, scheduler=scheduler,
					settings=self.settings)
				phase.start()
				retval = phase.wait()

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					failures += 1
					showMessage(_("!!! FAILED postrm: %s\n") % retval,
						level=logging.ERROR, noiselevel=-1)

		finally:
			self.vartree.dbapi._bump_mtime(self.mycpv)
			try:
					if not eapi_unsupported and os.path.isfile(myebuildpath):
						if retval != os.EX_OK:
							msg_lines = []
							msg = _("The '%(ebuild_phase)s' "
							"phase of the '%(cpv)s' package "
							"has failed with exit value %(retval)s.") % \
							{"ebuild_phase":ebuild_phase, "cpv":self.mycpv,
							"retval":retval}
							from textwrap import wrap
							msg_lines.extend(wrap(msg, 72))
							msg_lines.append("")

							ebuild_name = os.path.basename(myebuildpath)
							ebuild_dir = os.path.dirname(myebuildpath)
							msg = _("The problem occurred while executing "
							"the ebuild file named '%(ebuild_name)s' "
							"located in the '%(ebuild_dir)s' directory. "
							"If necessary, manually remove "
							"the environment.bz2 file and/or the "
							"ebuild file located in that directory.") % \
							{"ebuild_name":ebuild_name, "ebuild_dir":ebuild_dir}
							msg_lines.extend(wrap(msg, 72))
							msg_lines.append("")

							msg = _("Removal "
							"of the environment.bz2 file is "
							"preferred since it may allow the "
							"removal phases to execute successfully. "
							"The ebuild will be "
							"sourced and the eclasses "
							"from the current ebuild repository will be used "
							"when necessary. Removal of "
							"the ebuild file will cause the "
							"pkg_prerm() and pkg_postrm() removal "
							"phases to be skipped entirely.")
							msg_lines.extend(wrap(msg, 72))

							self._eerror(ebuild_phase, msg_lines)

					self._elog_process(phasefilter=("prerm", "postrm"))

					if retval == os.EX_OK:
						try:
							doebuild_environment(myebuildpath, "cleanrm",
								settings=self.settings, db=self.vartree.dbapi)
						except UnsupportedAPIException:
							pass
						phase = EbuildPhase(background=background,
							phase="cleanrm", scheduler=scheduler,
							settings=self.settings)
						phase.start()
						retval = phase.wait()
			finally:
					if builddir_lock is not None:
						scheduler.run_until_complete(
							builddir_lock.async_unlock())

		if log_path is not None:

			if not failures and 'unmerge-logs' not in self.settings.features:
				try:
					os.unlink(log_path)
				except OSError:
					pass

			try:
				st = os.stat(log_path)
			except OSError:
				pass
			else:
				if st.st_size == 0:
					try:
						os.unlink(log_path)
					except OSError:
						pass

		if log_path is not None and os.path.exists(log_path):
			# Restore this since it gets lost somewhere above and it
			# needs to be set for _display_merge() to be able to log.
			# Note that the log isn't necessarily supposed to exist
			# since if PORTAGE_LOGDIR is unset then it's a temp file
			# so it gets cleaned above.
			self.settings["PORTAGE_LOG_FILE"] = log_path
		else:
			self.settings.pop("PORTAGE_LOG_FILE", None)

		env_update(target_root=self.settings['ROOT'],
			prev_mtimes=ldpath_mtimes,
			contents=contents, env=self.settings,
			writemsg_level=self._display_merge, vardbapi=self.vartree.dbapi)

		unmerge_with_replacement = preserve_paths is not None
		if not unmerge_with_replacement:
			# When there's a replacement package which calls us via treewalk,
			# treewalk will automatically call _prune_plib_registry for us.
			# Otherwise, we need to call _prune_plib_registry ourselves.
			# Don't pass in the "unmerge=True" flag here, since that flag
			# is intended to be used _prior_ to unmerge, not after.
			self._prune_plib_registry()

		return os.EX_OK

	def _display_merge(self, msg, level=0, noiselevel=0):
		if not self._verbose and noiselevel >= 0 and level < logging.WARN:
			return
		if self._scheduler is None:
			writemsg_level(msg, level=level, noiselevel=noiselevel)
		else:
			log_path = None
			if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
				log_path = self.settings.get("PORTAGE_LOG_FILE")
			background = self.settings.get("PORTAGE_BACKGROUND") == "1"

			if background and log_path is None:
				if level >= logging.WARN:
					writemsg_level(msg, level=level, noiselevel=noiselevel)
			else:
				self._scheduler.output(msg,
					log_path=log_path, background=background,
					level=level, noiselevel=noiselevel)

	def _show_unmerge(self, zing, desc, file_type, file_name):
		self._display_merge("%s %s %s %s\n" % \
			(zing, desc.ljust(8), file_type, file_name))

	def _unmerge_pkgfiles(self, pkgfiles, others_in_slot):
		"""

		Unmerges the contents of a package from the liveFS
		Removes the VDB entry for self

		@param pkgfiles: typically self.getcontents()
		@type pkgfiles: Dictionary { filename: [ 'type', '?', 'md5sum' ] }
		@param others_in_slot: all dblink instances in this slot, excluding self
		@type others_in_slot: list
		@rtype: None
		"""

		os = _os_merge
		perf_md5 = perform_md5
		showMessage = self._display_merge
		show_unmerge = self._show_unmerge
		ignored_unlink_errnos = self._ignored_unlink_errnos
		ignored_rmdir_errnos = self._ignored_rmdir_errnos

		if not pkgfiles:
			showMessage(_("No package files given... Grabbing a set.\n"))
			pkgfiles = self.getcontents()

		if others_in_slot is None:
			others_in_slot = []
			slot = self.vartree.dbapi._pkg_str(self.mycpv, None).slot
			slot_matches = self.vartree.dbapi.match(
				"%s:%s" % (portage.cpv_getkey(self.mycpv), slot))
			for cur_cpv in slot_matches:
				if cur_cpv == self.mycpv:
					continue
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					settings=self.settings,
					vartree=self.vartree, treetype="vartree", pipe=self._pipe))

		cfgfiledict = grabdict(self.vartree.dbapi._conf_mem_file)
		stale_confmem = []
		protected_symlinks = {}

		unmerge_orphans = "unmerge-orphans" in self.settings.features
		calc_prelink = "prelink-checksums" in self.settings.features

		if pkgfiles:
			self.updateprotect()
			mykeys = list(pkgfiles)
			mykeys.sort()
			mykeys.reverse()

			#process symlinks second-to-last, directories last.
			mydirs = set()

			uninstall_ignore = portage.util.shlex_split(
				self.settings.get("UNINSTALL_IGNORE", ""))

			def unlink(file_name, lstatobj):
				if bsd_chflags:
					if lstatobj.st_flags != 0:
						bsd_chflags.lchflags(file_name, 0)
					parent_name = os.path.dirname(file_name)
					# Use normal stat/chflags for the parent since we want to
					# follow any symlinks to the real parent directory.
					pflags = os.stat(parent_name).st_flags
					if pflags != 0:
						bsd_chflags.chflags(parent_name, 0)
				try:
					if not stat.S_ISLNK(lstatobj.st_mode):
						# Remove permissions to ensure that any hardlinks to
						# suid/sgid files are rendered harmless.
						os.chmod(file_name, 0)
					os.unlink(file_name)
				except OSError as ose:
					# If the chmod or unlink fails, you are in trouble.
					# With Prefix this can be because the file is owned
					# by someone else (a screwup by root?), on a normal
					# system maybe filesystem corruption.  In any case,
					# if we backtrace and die here, we leave the system
					# in a totally undefined state, hence we just bleed
					# like hell and continue to hopefully finish all our
					# administrative and pkg_postinst stuff.
					self._eerror("postrm",
						["Could not chmod or unlink '%s': %s" % \
						(file_name, ose)])
				else:

					# Even though the file no longer exists, we log it
					# here so that _unmerge_dirs can see that we've
					# removed a file from this device, and will record
					# the parent directory for a syncfs call.
					self._merged_path(file_name, lstatobj, exists=False)

				finally:
					if bsd_chflags and pflags != 0:
						# Restore the parent flags we saved before unlinking
						bsd_chflags.chflags(parent_name, pflags)

			unmerge_desc = {}
			unmerge_desc["cfgpro"] = _("cfgpro")
			unmerge_desc["replaced"] = _("replaced")
			unmerge_desc["!dir"] = _("!dir")
			unmerge_desc["!empty"] = _("!empty")
			unmerge_desc["!fif"] = _("!fif")
			unmerge_desc["!found"] = _("!found")
			unmerge_desc["!md5"] = _("!md5")
			unmerge_desc["!mtime"] = _("!mtime")
			unmerge_desc["!obj"] = _("!obj")
			unmerge_desc["!sym"] = _("!sym")
			unmerge_desc["!prefix"] = _("!prefix")

			real_root = self.settings['ROOT']
			real_root_len = len(real_root) - 1
			eroot = self.settings["EROOT"]

			infodirs = frozenset(infodir for infodir in chain(
				self.settings.get("INFOPATH", "").split(":"),
				self.settings.get("INFODIR", "").split(":")) if infodir)
			infodirs_inodes = set()
			for infodir in infodirs:
				infodir = os.path.join(real_root, infodir.lstrip(os.sep))
				try:
					statobj = os.stat(infodir)
				except OSError:
					pass
				else:
					infodirs_inodes.add((statobj.st_dev, statobj.st_ino))

			for i, objkey in enumerate(mykeys):

				obj = normalize_path(objkey)
				if os is _os_merge:
					try:
						_unicode_encode(obj,
							encoding=_encodings['merge'], errors='strict')
					except UnicodeEncodeError:
						# The package appears to have been merged with a
						# different value of sys.getfilesystemencoding(),
						# so fall back to utf_8 if appropriate.
						try:
							_unicode_encode(obj,
								encoding=_encodings['fs'], errors='strict')
						except UnicodeEncodeError:
							pass
						else:
							os = portage.os
							perf_md5 = portage.checksum.perform_md5

				file_data = pkgfiles[objkey]
				file_type = file_data[0]

				# don't try to unmerge the prefix offset itself
				if len(obj) <= len(eroot) or not obj.startswith(eroot):
					show_unmerge("---", unmerge_desc["!prefix"], file_type, obj)
					continue

				statobj = None
				try:
					statobj = os.stat(obj)
				except OSError:
					pass
				lstatobj = None
				try:
					lstatobj = os.lstat(obj)
				except (OSError, AttributeError):
					pass
				islink = lstatobj is not None and stat.S_ISLNK(lstatobj.st_mode)
				if lstatobj is None:
						show_unmerge("---", unmerge_desc["!found"], file_type, obj)
						continue

				f_match = obj[len(eroot)-1:]
				ignore = False
				for pattern in uninstall_ignore:
					if fnmatch.fnmatch(f_match, pattern):
						ignore = True
						break

				if not ignore:
					if islink and f_match in \
						("/lib", "/usr/lib", "/usr/local/lib"):
						# Ignore libdir symlinks for bug #423127.
						ignore = True

				if ignore:
					show_unmerge("---", unmerge_desc["cfgpro"], file_type, obj)
					continue

				# don't use EROOT, CONTENTS entries already contain EPREFIX
				if obj.startswith(real_root):
					relative_path = obj[real_root_len:]
					is_owned = False
					for dblnk in others_in_slot:
						if dblnk.isowner(relative_path):
							is_owned = True
							break

					if is_owned and islink and \
						file_type in ("sym", "dir") and \
						statobj and stat.S_ISDIR(statobj.st_mode):
						# A new instance of this package claims the file, so
						# don't unmerge it. If the file is symlink to a
						# directory and the unmerging package installed it as
						# a symlink, but the new owner has it listed as a
						# directory, then we'll produce a warning since the
						# symlink is a sort of orphan in this case (see
						# bug #326685).
						symlink_orphan = False
						for dblnk in others_in_slot:
							parent_contents_key = \
								dblnk._match_contents(relative_path)
							if not parent_contents_key:
								continue
							if not parent_contents_key.startswith(
								real_root):
								continue
							if dblnk.getcontents()[
								parent_contents_key][0] == "dir":
								symlink_orphan = True
								break

						if symlink_orphan:
							protected_symlinks.setdefault(
								(statobj.st_dev, statobj.st_ino),
								[]).append(relative_path)

					if is_owned:
						show_unmerge("---", unmerge_desc["replaced"], file_type, obj)
						continue
					elif relative_path in cfgfiledict:
						stale_confmem.append(relative_path)

				# Don't unlink symlinks to directories here since that can
				# remove /lib and /usr/lib symlinks.
				if unmerge_orphans and \
					lstatobj and not stat.S_ISDIR(lstatobj.st_mode) and \
					not (islink and statobj and stat.S_ISDIR(statobj.st_mode)) and \
					not self.isprotected(obj):
					try:
						unlink(obj, lstatobj)
					except EnvironmentError as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
					continue

				lmtime = str(lstatobj[stat.ST_MTIME])
				if (pkgfiles[objkey][0] not in ("dir", "fif", "dev")) and (lmtime != pkgfiles[objkey][1]):
					show_unmerge("---", unmerge_desc["!mtime"], file_type, obj)
					continue

				if file_type == "dir" and not islink:
					if lstatobj is None or not stat.S_ISDIR(lstatobj.st_mode):
						show_unmerge("---", unmerge_desc["!dir"], file_type, obj)
						continue
					mydirs.add((obj, (lstatobj.st_dev, lstatobj.st_ino)))
				elif file_type == "sym" or (file_type == "dir" and islink):
					if not islink:
						show_unmerge("---", unmerge_desc["!sym"], file_type, obj)
						continue

					# If this symlink points to a directory then we don't want
					# to unmerge it if there are any other packages that
					# installed files into the directory via this symlink
					# (see bug #326685).
					# TODO: Resolving a symlink to a directory will require
					# simulation if $ROOT != / and the link is not relative.
					if islink and statobj and stat.S_ISDIR(statobj.st_mode) \
						and obj.startswith(real_root):

						relative_path = obj[real_root_len:]
						try:
							target_dir_contents = os.listdir(obj)
						except OSError:
							pass
						else:
							if target_dir_contents:
								# If all the children are regular files owned
								# by this package, then the symlink should be
								# safe to unmerge.
								all_owned = True
								for child in target_dir_contents:
									child = os.path.join(relative_path, child)
									if not self.isowner(child):
										all_owned = False
										break
									try:
										child_lstat = os.lstat(os.path.join(
											real_root, child.lstrip(os.sep)))
									except OSError:
										continue

									if not stat.S_ISREG(child_lstat.st_mode):
										# Nested symlinks or directories make
										# the issue very complex, so just
										# preserve the symlink in order to be
										# on the safe side.
										all_owned = False
										break

								if not all_owned:
									protected_symlinks.setdefault(
										(statobj.st_dev, statobj.st_ino),
										[]).append(relative_path)
									show_unmerge("---", unmerge_desc["!empty"],
										file_type, obj)
									continue

					# Go ahead and unlink symlinks to directories here when
					# they're actually recorded as symlinks in the contents.
					# Normally, symlinks such as /lib -> lib64 are not recorded
					# as symlinks in the contents of a package.  If a package
					# installs something into ${D}/lib/, it is recorded in the
					# contents as a directory even if it happens to correspond
					# to a symlink when it's merged to the live filesystem.
					try:
						unlink(obj, lstatobj)
						show_unmerge("<<<", "", file_type, obj)
					except (OSError, IOError) as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
						show_unmerge("!!!", "", file_type, obj)
				elif pkgfiles[objkey][0] == "obj":
					if statobj is None or not stat.S_ISREG(statobj.st_mode):
						show_unmerge("---", unmerge_desc["!obj"], file_type, obj)
						continue
					mymd5 = None
					try:
						mymd5 = perf_md5(obj, calc_prelink=calc_prelink)
					except FileNotFound as e:
						# the file has disappeared between now and our stat call
						show_unmerge("---", unmerge_desc["!obj"], file_type, obj)
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != pkgfiles[objkey][2].lower():
						show_unmerge("---", unmerge_desc["!md5"], file_type, obj)
						continue
					try:
						unlink(obj, lstatobj)
					except (OSError, IOError) as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
					show_unmerge("<<<", "", file_type, obj)
				elif pkgfiles[objkey][0] == "fif":
					if not stat.S_ISFIFO(lstatobj[stat.ST_MODE]):
						show_unmerge("---", unmerge_desc["!fif"], file_type, obj)
						continue
					show_unmerge("---", "", file_type, obj)
				elif pkgfiles[objkey][0] == "dev":
					show_unmerge("---", "", file_type, obj)

			self._unmerge_dirs(mydirs, infodirs_inodes,
				protected_symlinks, unmerge_desc, unlink, os)
			mydirs.clear()

		if protected_symlinks:
			self._unmerge_protected_symlinks(others_in_slot, infodirs_inodes,
				protected_symlinks, unmerge_desc, unlink, os)

		if protected_symlinks:
			msg = "One or more symlinks to directories have been " + \
				"preserved in order to ensure that files installed " + \
				"via these symlinks remain accessible. " + \
				"This indicates that the mentioned symlink(s) may " + \
				"be obsolete remnants of an old install, and it " + \
				"may be appropriate to replace a given symlink " + \
				"with the directory that it points to."
			lines = textwrap.wrap(msg, 72)
			lines.append("")
			flat_list = set()
			flat_list.update(*protected_symlinks.values())
			flat_list = sorted(flat_list)
			for f in flat_list:
				lines.append("\t%s" % (os.path.join(real_root,
					f.lstrip(os.sep))))
			lines.append("")
			self._elog("elog", "postrm", lines)

		# Remove stale entries from config memory.
		if stale_confmem:
			for filename in stale_confmem:
				del cfgfiledict[filename]
			writedict(cfgfiledict, self.vartree.dbapi._conf_mem_file)

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

	def _unmerge_protected_symlinks(self, others_in_slot, infodirs_inodes,
		protected_symlinks, unmerge_desc, unlink, os):

		real_root = self.settings['ROOT']
		show_unmerge = self._show_unmerge
		ignored_unlink_errnos = self._ignored_unlink_errnos

		flat_list = set()
		flat_list.update(*protected_symlinks.values())
		flat_list = sorted(flat_list)

		for f in flat_list:
			for dblnk in others_in_slot:
				if dblnk.isowner(f):
					# If another package in the same slot installed
					# a file via a protected symlink, return early
					# and don't bother searching for any other owners.
					return

		msg = []
		msg.append("")
		msg.append(_("Directory symlink(s) may need protection:"))
		msg.append("")

		for f in flat_list:
			msg.append("\t%s" % \
				os.path.join(real_root, f.lstrip(os.path.sep)))

		msg.append("")
		msg.append("Use the UNINSTALL_IGNORE variable to exempt specific symlinks")
		msg.append("from the following search (see the make.conf man page).")
		msg.append("")
		msg.append(_("Searching all installed"
			" packages for files installed via above symlink(s)..."))
		msg.append("")
		self._elog("elog", "postrm", msg)

		self.lockdb()
		try:
			owners = self.vartree.dbapi._owners.get_owners(flat_list)
			self.vartree.dbapi.flush_cache()
		finally:
			self.unlockdb()

		for owner in list(owners):
			if owner.mycpv == self.mycpv:
				owners.pop(owner, None)

		if not owners:
			msg = []
			msg.append(_("The above directory symlink(s) are all "
				"safe to remove. Removing them now..."))
			msg.append("")
			self._elog("elog", "postrm", msg)
			dirs = set()
			for unmerge_syms in protected_symlinks.values():
				for relative_path in unmerge_syms:
					obj = os.path.join(real_root,
						relative_path.lstrip(os.sep))
					parent = os.path.dirname(obj)
					while len(parent) > len(self._eroot):
						try:
							lstatobj = os.lstat(parent)
						except OSError:
							break
						else:
							dirs.add((parent,
								(lstatobj.st_dev, lstatobj.st_ino)))
							parent = os.path.dirname(parent)
					try:
						unlink(obj, os.lstat(obj))
						show_unmerge("<<<", "", "sym", obj)
					except (OSError, IOError) as e:
						if e.errno not in ignored_unlink_errnos:
							raise
						del e
						show_unmerge("!!!", "", "sym", obj)

			protected_symlinks.clear()
			self._unmerge_dirs(dirs, infodirs_inodes,
				protected_symlinks, unmerge_desc, unlink, os)
			dirs.clear()

	def _unmerge_dirs(self, dirs, infodirs_inodes,
		protected_symlinks, unmerge_desc, unlink, os):

		show_unmerge = self._show_unmerge
		infodir_cleanup = self._infodir_cleanup
		ignored_unlink_errnos = self._ignored_unlink_errnos
		ignored_rmdir_errnos = self._ignored_rmdir_errnos
		real_root = self.settings['ROOT']

		dirs = sorted(dirs)
		revisit = {}

		while True:
			try:
				obj, inode_key = dirs.pop()
			except IndexError:
				break
			# Treat any directory named "info" as a candidate here,
			# since it might have been in INFOPATH previously even
			# though it may not be there now.
			if inode_key in infodirs_inodes or \
				os.path.basename(obj) == "info":
				try:
					remaining = os.listdir(obj)
				except OSError:
					pass
				else:
					cleanup_info_dir = ()
					if remaining and \
						len(remaining) <= len(infodir_cleanup):
						if not set(remaining).difference(infodir_cleanup):
							cleanup_info_dir = remaining

					for child in cleanup_info_dir:
						child = os.path.join(obj, child)
						try:
							lstatobj = os.lstat(child)
							if stat.S_ISREG(lstatobj.st_mode):
								unlink(child, lstatobj)
								show_unmerge("<<<", "", "obj", child)
						except EnvironmentError as e:
							if e.errno not in ignored_unlink_errnos:
								raise
							del e
							show_unmerge("!!!", "", "obj", child)

			try:
				parent_name = os.path.dirname(obj)
				parent_stat = os.stat(parent_name)

				if bsd_chflags:
					lstatobj = os.lstat(obj)
					if lstatobj.st_flags != 0:
						bsd_chflags.lchflags(obj, 0)

					# Use normal stat/chflags for the parent since we want to
					# follow any symlinks to the real parent directory.
					pflags = parent_stat.st_flags
					if pflags != 0:
						bsd_chflags.chflags(parent_name, 0)
				try:
					os.rmdir(obj)
				finally:
					if bsd_chflags and pflags != 0:
						# Restore the parent flags we saved before unlinking
						bsd_chflags.chflags(parent_name, pflags)

				# Record the parent directory for use in syncfs calls.
				# Note that we use a realpath and a regular stat here, since
				# we want to follow any symlinks back to the real device where
				# the real parent directory resides.
				self._merged_path(os.path.realpath(parent_name), parent_stat)

				show_unmerge("<<<", "", "dir", obj)
			except EnvironmentError as e:
				if e.errno not in ignored_rmdir_errnos:
					raise
				if e.errno != errno.ENOENT:
					show_unmerge("---", unmerge_desc["!empty"], "dir", obj)
					revisit[obj] = inode_key

				# Since we didn't remove this directory, record the directory
				# itself for use in syncfs calls, if we have removed another
				# file from the same device.
				# Note that we use a realpath and a regular stat here, since
				# we want to follow any symlinks back to the real device where
				# the real directory resides.
				try:
					dir_stat = os.stat(obj)
				except OSError:
					pass
				else:
					if dir_stat.st_dev in self._device_path_map:
						self._merged_path(os.path.realpath(obj), dir_stat)

			else:
				# When a directory is successfully removed, there's
				# no need to protect symlinks that point to it.
				unmerge_syms = protected_symlinks.pop(inode_key, None)
				if unmerge_syms is not None:
					parents = []
					for relative_path in unmerge_syms:
						obj = os.path.join(real_root,
							relative_path.lstrip(os.sep))
						try:
							unlink(obj, os.lstat(obj))
							show_unmerge("<<<", "", "sym", obj)
						except (OSError, IOError) as e:
							if e.errno not in ignored_unlink_errnos:
								raise
							del e
							show_unmerge("!!!", "", "sym", obj)
						else:
							parents.append(os.path.dirname(obj))

					if parents:
						# Revisit parents recursively (bug 640058).
						recursive_parents = []
						for parent in set(parents):
							while parent in revisit:
								recursive_parents.append(parent)
								parent = os.path.dirname(parent)
								if parent == '/':
									break

						for parent in sorted(set(recursive_parents)):
							dirs.append((parent, revisit.pop(parent)))

	def isowner(self, filename, destroot=None):
		"""
		Check if a file belongs to this package. This may
		result in a stat call for the parent directory of
		every installed file, since the inode numbers are
		used to work around the problem of ambiguous paths
		caused by symlinked directories. The results of
		stat calls are cached to optimize multiple calls
		to this method.

		@param filename:
		@type filename:
		@param destroot:
		@type destroot:
		@rtype: Boolean
		@return:
		1. True if this package owns the file.
		2. False if this package does not own the file.
		"""

		if destroot is not None and destroot != self._eroot:
			warnings.warn("The second parameter of the " + \
				"portage.dbapi.vartree.dblink.isowner()" + \
				" is now unused. Instead " + \
				"self.settings['EROOT'] will be used.",
				DeprecationWarning, stacklevel=2)

		return bool(self._match_contents(filename))

	def _match_contents(self, filename, destroot=None):
		"""
		The matching contents entry is returned, which is useful
		since the path may differ from the one given by the caller,
		due to symlinks.

		@rtype: String
		@return: the contents entry corresponding to the given path, or False
			if the file is not owned by this package.
		"""

		filename = _unicode_decode(filename,
			encoding=_encodings['content'], errors='strict')

		if destroot is not None and destroot != self._eroot:
			warnings.warn("The second parameter of the " + \
				"portage.dbapi.vartree.dblink._match_contents()" + \
				" is now unused. Instead " + \
				"self.settings['ROOT'] will be used.",
				DeprecationWarning, stacklevel=2)

		# don't use EROOT here, image already contains EPREFIX
		destroot = self.settings['ROOT']

		# The given filename argument might have a different encoding than the
		# the filenames contained in the contents, so use separate wrapped os
		# modules for each. The basename is more likely to contain non-ascii
		# characters than the directory path, so use os_filename_arg for all
		# operations involving the basename of the filename arg.
		os_filename_arg = _os_merge
		os = _os_merge

		try:
			_unicode_encode(filename,
				encoding=_encodings['merge'], errors='strict')
		except UnicodeEncodeError:
			# The package appears to have been merged with a
			# different value of sys.getfilesystemencoding(),
			# so fall back to utf_8 if appropriate.
			try:
				_unicode_encode(filename,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeEncodeError:
				pass
			else:
				os_filename_arg = portage.os

		destfile = normalize_path(
			os_filename_arg.path.join(destroot,
			filename.lstrip(os_filename_arg.path.sep)))

		if "case-insensitive-fs" in self.settings.features:
			destfile = destfile.lower()

		if self._contents.contains(destfile):
			return self._contents.unmap_key(destfile)

		if self.getcontents():
			basename = os_filename_arg.path.basename(destfile)
			if self._contents_basenames is None:

				try:
					for x in self._contents.keys():
						_unicode_encode(x,
							encoding=_encodings['merge'],
							errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						for x in self._contents.keys():
							_unicode_encode(x,
								encoding=_encodings['fs'],
								errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

				self._contents_basenames = set(
					os.path.basename(x) for x in self._contents.keys())
			if basename not in self._contents_basenames:
				# This is a shortcut that, in most cases, allows us to
				# eliminate this package as an owner without the need
				# to examine inode numbers of parent directories.
				return False

			# Use stat rather than lstat since we want to follow
			# any symlinks to the real parent directory.
			parent_path = os_filename_arg.path.dirname(destfile)
			try:
				parent_stat = os_filename_arg.stat(parent_path)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				return False
			if self._contents_inodes is None:

				if os is _os_merge:
					try:
						for x in self._contents.keys():
							_unicode_encode(x,
								encoding=_encodings['merge'],
								errors='strict')
					except UnicodeEncodeError:
						# The package appears to have been merged with a
						# different value of sys.getfilesystemencoding(),
						# so fall back to utf_8 if appropriate.
						try:
							for x in self._contents.keys():
								_unicode_encode(x,
									encoding=_encodings['fs'],
									errors='strict')
						except UnicodeEncodeError:
							pass
						else:
							os = portage.os

				self._contents_inodes = {}
				parent_paths = set()
				for x in self._contents.keys():
					p_path = os.path.dirname(x)
					if p_path in parent_paths:
						continue
					parent_paths.add(p_path)
					try:
						s = os.stat(p_path)
					except OSError:
						pass
					else:
						inode_key = (s.st_dev, s.st_ino)
						# Use lists of paths in case multiple
						# paths reference the same inode.
						p_path_list = self._contents_inodes.get(inode_key)
						if p_path_list is None:
							p_path_list = []
							self._contents_inodes[inode_key] = p_path_list
						if p_path not in p_path_list:
							p_path_list.append(p_path)

			p_path_list = self._contents_inodes.get(
				(parent_stat.st_dev, parent_stat.st_ino))
			if p_path_list:
				for p_path in p_path_list:
					x = os_filename_arg.path.join(p_path, basename)
					if self._contents.contains(x):
						return self._contents.unmap_key(x)

		return False

	def _linkmap_rebuild(self, **kwargs):
		"""
		Rebuild the self._linkmap if it's not broken due to missing
		scanelf binary. Also, return early if preserve-libs is disabled
		and the preserve-libs registry is empty.
		"""
		if self._linkmap_broken or \
			self.vartree.dbapi._linkmap is None or \
			self.vartree.dbapi._plib_registry is None or \
			("preserve-libs" not in self.settings.features and \
			not self.vartree.dbapi._plib_registry.hasEntries()):
			return
		try:
			self.vartree.dbapi._linkmap.rebuild(**kwargs)
		except CommandNotFound as e:
			self._linkmap_broken = True
			self._display_merge(_("!!! Disabling preserve-libs " \
				"due to error: Command Not Found: %s\n") % (e,),
				level=logging.ERROR, noiselevel=-1)

	def _find_libs_to_preserve(self, unmerge=False):
		"""
		Get set of relative paths for libraries to be preserved. When
		unmerge is False, file paths to preserve are selected from
		self._installed_instance. Otherwise, paths are selected from
		self.
		"""
		if self._linkmap_broken or \
			self.vartree.dbapi._linkmap is None or \
			self.vartree.dbapi._plib_registry is None or \
			(not unmerge and self._installed_instance is None) or \
			not self._preserve_libs:
			return set()

		os = _os_merge
		linkmap = self.vartree.dbapi._linkmap
		if unmerge:
			installed_instance = self
		else:
			installed_instance = self._installed_instance
		old_contents = installed_instance.getcontents()
		root = self.settings['ROOT']
		root_len = len(root) - 1
		lib_graph = digraph()
		path_node_map = {}

		def path_to_node(path):
			node = path_node_map.get(path)
			if node is None:
				node = LinkageMap._LibGraphNode(linkmap._obj_key(path))
				alt_path_node = lib_graph.get(node)
				if alt_path_node is not None:
					node = alt_path_node
				node.alt_paths.add(path)
				path_node_map[path] = node
			return node

		consumer_map = {}
		provider_nodes = set()
		# Create provider nodes and add them to the graph.
		for f_abs in old_contents:

			if os is _os_merge:
				try:
					_unicode_encode(f_abs,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						_unicode_encode(f_abs,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

			f = f_abs[root_len:]
			try:
				consumers = linkmap.findConsumers(f,
					exclude_providers=(installed_instance.isowner,))
			except KeyError:
				continue
			if not consumers:
				continue
			provider_node = path_to_node(f)
			lib_graph.add(provider_node, None)
			provider_nodes.add(provider_node)
			consumer_map[provider_node] = consumers

		# Create consumer nodes and add them to the graph.
		# Note that consumers can also be providers.
		for provider_node, consumers in consumer_map.items():
			for c in consumers:
				consumer_node = path_to_node(c)
				if installed_instance.isowner(c) and \
					consumer_node not in provider_nodes:
					# This is not a provider, so it will be uninstalled.
					continue
				lib_graph.add(provider_node, consumer_node)

		# Locate nodes which should be preserved. They consist of all
		# providers that are reachable from consumers that are not
		# providers themselves.
		preserve_nodes = set()
		for consumer_node in lib_graph.root_nodes():
			if consumer_node in provider_nodes:
				continue
			# Preserve all providers that are reachable from this consumer.
			node_stack = lib_graph.child_nodes(consumer_node)
			while node_stack:
				provider_node = node_stack.pop()
				if provider_node in preserve_nodes:
					continue
				preserve_nodes.add(provider_node)
				node_stack.extend(lib_graph.child_nodes(provider_node))

		preserve_paths = set()
		for preserve_node in preserve_nodes:
			# Preserve the library itself, and also preserve the
			# soname symlink which is the only symlink that is
			# strictly required.
			hardlinks = set()
			soname_symlinks = set()
			soname = linkmap.getSoname(next(iter(preserve_node.alt_paths)))
			have_replacement_soname_link = False
			have_replacement_hardlink = False
			for f in preserve_node.alt_paths:
				f_abs = os.path.join(root, f.lstrip(os.sep))
				try:
					if stat.S_ISREG(os.lstat(f_abs).st_mode):
						hardlinks.add(f)
						if not unmerge and self.isowner(f):
							have_replacement_hardlink = True
							if os.path.basename(f) == soname:
								have_replacement_soname_link = True
					elif os.path.basename(f) == soname:
						soname_symlinks.add(f)
						if not unmerge and self.isowner(f):
							have_replacement_soname_link = True
				except OSError:
					pass

			if have_replacement_hardlink and have_replacement_soname_link:
				continue

			if hardlinks:
				preserve_paths.update(hardlinks)
				preserve_paths.update(soname_symlinks)

		return preserve_paths

	def _add_preserve_libs_to_contents(self, preserve_paths):
		"""
		Preserve libs returned from _find_libs_to_preserve().
		"""

		if not preserve_paths:
			return

		os = _os_merge
		showMessage = self._display_merge
		root = self.settings['ROOT']

		# Copy contents entries from the old package to the new one.
		new_contents = self.getcontents().copy()
		old_contents = self._installed_instance.getcontents()
		for f in sorted(preserve_paths):
			f = _unicode_decode(f,
				encoding=_encodings['content'], errors='strict')
			f_abs = os.path.join(root, f.lstrip(os.sep))
			contents_entry = old_contents.get(f_abs)
			if contents_entry is None:
				# This will probably never happen, but it might if one of the
				# paths returned from findConsumers() refers to one of the libs
				# that should be preserved yet the path is not listed in the
				# contents. Such a path might belong to some other package, so
				# it shouldn't be preserved here.
				showMessage(_("!!! File '%s' will not be preserved "
					"due to missing contents entry\n") % (f_abs,),
					level=logging.ERROR, noiselevel=-1)
				preserve_paths.remove(f)
				continue
			new_contents[f_abs] = contents_entry
			obj_type = contents_entry[0]
			showMessage(_(">>> needed    %s %s\n") % (obj_type, f_abs),
				noiselevel=-1)
			# Add parent directories to contents if necessary.
			parent_dir = os.path.dirname(f_abs)
			while len(parent_dir) > len(root):
				new_contents[parent_dir] = ["dir"]
				prev = parent_dir
				parent_dir = os.path.dirname(parent_dir)
				if prev == parent_dir:
					break
		outfile = atomic_ofstream(os.path.join(self.dbtmpdir, "CONTENTS"))
		write_contents(new_contents, root, outfile)
		outfile.close()
		self._clear_contents_cache()

	def _find_unused_preserved_libs(self, unmerge_no_replacement):
		"""
		Find preserved libraries that don't have any consumers left.
		"""

		if self._linkmap_broken or \
			self.vartree.dbapi._linkmap is None or \
			self.vartree.dbapi._plib_registry is None or \
			not self.vartree.dbapi._plib_registry.hasEntries():
			return {}

		# Since preserved libraries can be consumers of other preserved
		# libraries, use a graph to track consumer relationships.
		plib_dict = self.vartree.dbapi._plib_registry.getPreservedLibs()
		linkmap = self.vartree.dbapi._linkmap
		lib_graph = digraph()
		preserved_nodes = set()
		preserved_paths = set()
		path_cpv_map = {}
		path_node_map = {}
		root = self.settings['ROOT']

		def path_to_node(path):
			node = path_node_map.get(path)
			if node is None:
				node = LinkageMap._LibGraphNode(linkmap._obj_key(path))
				alt_path_node = lib_graph.get(node)
				if alt_path_node is not None:
					node = alt_path_node
				node.alt_paths.add(path)
				path_node_map[path] = node
			return node

		for cpv, plibs in plib_dict.items():
			for f in plibs:
				path_cpv_map[f] = cpv
				preserved_node = path_to_node(f)
				if not preserved_node.file_exists():
					continue
				lib_graph.add(preserved_node, None)
				preserved_paths.add(f)
				preserved_nodes.add(preserved_node)
				for c in self.vartree.dbapi._linkmap.findConsumers(f):
					consumer_node = path_to_node(c)
					if not consumer_node.file_exists():
						continue
					# Note that consumers may also be providers.
					lib_graph.add(preserved_node, consumer_node)

		# Eliminate consumers having providers with the same soname as an
		# installed library that is not preserved. This eliminates
		# libraries that are erroneously preserved due to a move from one
		# directory to another.
		# Also eliminate consumers that are going to be unmerged if
		# unmerge_no_replacement is True.
		provider_cache = {}
		for preserved_node in preserved_nodes:
			soname = linkmap.getSoname(preserved_node)
			for consumer_node in lib_graph.parent_nodes(preserved_node):
				if consumer_node in preserved_nodes:
					continue
				if unmerge_no_replacement:
					will_be_unmerged = True
					for path in consumer_node.alt_paths:
						if not self.isowner(path):
							will_be_unmerged = False
							break
					if will_be_unmerged:
						# This consumer is not preserved and it is
						# being unmerged, so drop this edge.
						lib_graph.remove_edge(preserved_node, consumer_node)
						continue

				providers = provider_cache.get(consumer_node)
				if providers is None:
					providers = linkmap.findProviders(consumer_node)
					provider_cache[consumer_node] = providers
				providers = providers.get(soname)
				if providers is None:
					continue
				for provider in providers:
					if provider in preserved_paths:
						continue
					provider_node = path_to_node(provider)
					if not provider_node.file_exists():
						continue
					if provider_node in preserved_nodes:
						continue
					# An alternative provider seems to be
					# installed, so drop this edge.
					lib_graph.remove_edge(preserved_node, consumer_node)
					break

		cpv_lib_map = {}
		while lib_graph:
			root_nodes = preserved_nodes.intersection(lib_graph.root_nodes())
			if not root_nodes:
				break
			lib_graph.difference_update(root_nodes)
			unlink_list = set()
			for node in root_nodes:
				unlink_list.update(node.alt_paths)
			unlink_list = sorted(unlink_list)
			for obj in unlink_list:
				cpv = path_cpv_map.get(obj)
				if cpv is None:
					# This means that a symlink is in the preserved libs
					# registry, but the actual lib it points to is not.
					self._display_merge(_("!!! symlink to lib is preserved, "
						"but not the lib itself:\n!!! '%s'\n") % (obj,),
						level=logging.ERROR, noiselevel=-1)
					continue
				removed = cpv_lib_map.get(cpv)
				if removed is None:
					removed = set()
					cpv_lib_map[cpv] = removed
				removed.add(obj)

		return cpv_lib_map

	def _remove_preserved_libs(self, cpv_lib_map):
		"""
		Remove files returned from _find_unused_preserved_libs().
		"""

		os = _os_merge

		files_to_remove = set()
		for files in cpv_lib_map.values():
			files_to_remove.update(files)
		files_to_remove = sorted(files_to_remove)
		showMessage = self._display_merge
		root = self.settings['ROOT']

		parent_dirs = set()
		for obj in files_to_remove:
			obj = os.path.join(root, obj.lstrip(os.sep))
			parent_dirs.add(os.path.dirname(obj))
			if os.path.islink(obj):
				obj_type = _("sym")
			else:
				obj_type = _("obj")
			try:
				os.unlink(obj)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
			else:
				showMessage(_("<<< !needed  %s %s\n") % (obj_type, obj),
					noiselevel=-1)

		# Remove empty parent directories if possible.
		while parent_dirs:
			x = parent_dirs.pop()
			while True:
				try:
					os.rmdir(x)
				except OSError:
					break
				prev = x
				x = os.path.dirname(x)
				if x == prev:
					break

		self.vartree.dbapi._plib_registry.pruneNonExisting()

	def _collision_protect(self, srcroot, destroot, mypkglist,
		file_list, symlink_list):

			os = _os_merge

			real_relative_paths = {}

			collision_ignore = []
			for x in portage.util.shlex_split(
				self.settings.get("COLLISION_IGNORE", "")):
				if os.path.isdir(os.path.join(self._eroot, x.lstrip(os.sep))):
					x = normalize_path(x)
					x += "/*"
				collision_ignore.append(x)

			# For collisions with preserved libraries, the current package
			# will assume ownership and the libraries will be unregistered.
			if self.vartree.dbapi._plib_registry is None:
				# preserve-libs is entirely disabled
				plib_cpv_map = None
				plib_paths = None
				plib_inodes = {}
			else:
				plib_dict = self.vartree.dbapi._plib_registry.getPreservedLibs()
				plib_cpv_map = {}
				plib_paths = set()
				for cpv, paths in plib_dict.items():
					plib_paths.update(paths)
					for f in paths:
						plib_cpv_map[f] = cpv
				plib_inodes = self._lstat_inode_map(plib_paths)

			plib_collisions = {}

			showMessage = self._display_merge
			stopmerge = False
			collisions = []
			dirs = set()
			dirs_ro = set()
			symlink_collisions = []
			destroot = self.settings['ROOT']
			totfiles = len(file_list) + len(symlink_list)
			previous = time.monotonic()
			progress_shown = False
			report_interval = 1.7  # seconds
			falign = len("%d" % totfiles)
			showMessage(_(" %s checking %d files for package collisions\n") % \
				(colorize("GOOD", "*"), totfiles))
			for i, (f, f_type) in enumerate(chain(
				((f, "reg") for f in file_list),
				((f, "sym") for f in symlink_list))):
				current = time.monotonic()
				if current - previous > report_interval:
					showMessage(_("%3d%% done,  %*d files remaining ...\n") %
							(i * 100 / totfiles, falign, totfiles - i))
					previous = current
					progress_shown = True

				dest_path = normalize_path(os.path.join(destroot, f.lstrip(os.path.sep)))

				# Relative path with symbolic links resolved only in parent directories
				real_relative_path = os.path.join(os.path.realpath(os.path.dirname(dest_path)),
					os.path.basename(dest_path))[len(destroot):]

				real_relative_paths.setdefault(real_relative_path, []).append(f.lstrip(os.path.sep))

				parent = os.path.dirname(dest_path)
				if parent not in dirs:
					for x in iter_parents(parent):
						if x in dirs:
							break
						dirs.add(x)
						if os.path.isdir(x):
							if not os.access(x, os.W_OK):
								dirs_ro.add(x)
							break

				try:
					dest_lstat = os.lstat(dest_path)
				except EnvironmentError as e:
					if e.errno == errno.ENOENT:
						del e
						continue
					elif e.errno == errno.ENOTDIR:
						del e
						# A non-directory is in a location where this package
						# expects to have a directory.
						dest_lstat = None
						parent_path = dest_path
						while len(parent_path) > len(destroot):
							parent_path = os.path.dirname(parent_path)
							try:
								dest_lstat = os.lstat(parent_path)
								break
							except EnvironmentError as e:
								if e.errno != errno.ENOTDIR:
									raise
								del e
						if not dest_lstat:
							raise AssertionError(
								"unable to find non-directory " + \
								"parent for '%s'" % dest_path)
						dest_path = parent_path
						f = os.path.sep + dest_path[len(destroot):]
						if f in collisions:
							continue
					else:
						raise
				if f[0] != "/":
					f="/"+f

				if stat.S_ISDIR(dest_lstat.st_mode):
					if f_type == "sym":
						# This case is explicitly banned
						# by PMS (see bug #326685).
						symlink_collisions.append(f)
						collisions.append(f)
						continue

				plibs = plib_inodes.get((dest_lstat.st_dev, dest_lstat.st_ino))
				if plibs:
					for path in plibs:
						cpv = plib_cpv_map[path]
						paths = plib_collisions.get(cpv)
						if paths is None:
							paths = set()
							plib_collisions[cpv] = paths
						paths.add(path)
					# The current package will assume ownership and the
					# libraries will be unregistered, so exclude this
					# path from the normal collisions.
					continue

				isowned = False
				full_path = os.path.join(destroot, f.lstrip(os.path.sep))
				for ver in mypkglist:
					if ver.isowner(f):
						isowned = True
						break
				if not isowned and self.isprotected(full_path):
					isowned = True
				if not isowned:
					f_match = full_path[len(self._eroot)-1:]
					stopmerge = True
					for pattern in collision_ignore:
						if fnmatch.fnmatch(f_match, pattern):
							stopmerge = False
							break
					if stopmerge:
						collisions.append(f)

			internal_collisions = {}
			for real_relative_path, files in real_relative_paths.items():
				# Detect internal collisions between non-identical files.
				if len(files) >= 2:
					files.sort()
					for i in range(len(files) - 1):
						file1 = normalize_path(os.path.join(srcroot, files[i]))
						file2 = normalize_path(os.path.join(srcroot, files[i+1]))
						# Compare files, ignoring differences in times.
						differences = compare_files(file1, file2, skipped_types=("atime", "mtime", "ctime"))
						if differences:
							internal_collisions.setdefault(real_relative_path, {})[(files[i], files[i+1])] = differences

			if progress_shown:
				showMessage(_("100% done\n"))

			return collisions, internal_collisions, dirs_ro, symlink_collisions, plib_collisions

	def _lstat_inode_map(self, path_iter):
		"""
		Use lstat to create a map of the form:
		  {(st_dev, st_ino) : set([path1, path2, ...])}
		Multiple paths may reference the same inode due to hardlinks.
		All lstat() calls are relative to self.myroot.
		"""

		os = _os_merge

		root = self.settings['ROOT']
		inode_map = {}
		for f in path_iter:
			path = os.path.join(root, f.lstrip(os.sep))
			try:
				st = os.lstat(path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ENOTDIR):
					raise
				del e
				continue
			key = (st.st_dev, st.st_ino)
			paths = inode_map.get(key)
			if paths is None:
				paths = set()
				inode_map[key] = paths
			paths.add(f)
		return inode_map

	def _security_check(self, installed_instances):
		if not installed_instances:
			return 0

		os = _os_merge

		showMessage = self._display_merge

		file_paths = set()
		for dblnk in installed_instances:
			file_paths.update(dblnk.getcontents())
		inode_map = {}
		real_paths = set()
		for i, path in enumerate(file_paths):

			if os is _os_merge:
				try:
					_unicode_encode(path,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeEncodeError:
					# The package appears to have been merged with a
					# different value of sys.getfilesystemencoding(),
					# so fall back to utf_8 if appropriate.
					try:
						_unicode_encode(path,
							encoding=_encodings['fs'], errors='strict')
					except UnicodeEncodeError:
						pass
					else:
						os = portage.os

			try:
				s = os.lstat(path)
			except OSError as e:
				if e.errno not in (errno.ENOENT, errno.ENOTDIR):
					raise
				del e
				continue
			if not stat.S_ISREG(s.st_mode):
				continue
			path = os.path.realpath(path)
			if path in real_paths:
				continue
			real_paths.add(path)
			if s.st_nlink > 1 and \
				s.st_mode & (stat.S_ISUID | stat.S_ISGID):
				k = (s.st_dev, s.st_ino)
				inode_map.setdefault(k, []).append((path, s))
		suspicious_hardlinks = []
		for path_list in inode_map.values():
			path, s = path_list[0]
			if len(path_list) == s.st_nlink:
				# All hardlinks seem to be owned by this package.
				continue
			suspicious_hardlinks.append(path_list)
		if not suspicious_hardlinks:
			return 0

		msg = []
		msg.append(_("suid/sgid file(s) "
			"with suspicious hardlink(s):"))
		msg.append("")
		for path_list in suspicious_hardlinks:
			for path, s in path_list:
				msg.append("\t%s" % path)
		msg.append("")
		msg.append(_("See the Gentoo Security Handbook "
			"guide for advice on how to proceed."))

		self._eerror("preinst", msg)

		return 1

	def _eqawarn(self, phase, lines):
		self._elog("eqawarn", phase, lines)

	def _eerror(self, phase, lines):
		self._elog("eerror", phase, lines)

	def _elog(self, funcname, phase, lines):
		func = getattr(portage.elog.messages, funcname)
		if self._scheduler is None:
			for l in lines:
				func(l, phase=phase, key=self.mycpv)
		else:
			background = self.settings.get("PORTAGE_BACKGROUND") == "1"
			log_path = None
			if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
				log_path = self.settings.get("PORTAGE_LOG_FILE")
			out = io.StringIO()
			for line in lines:
				func(line, phase=phase, key=self.mycpv, out=out)
			msg = out.getvalue()
			self._scheduler.output(msg,
				background=background, log_path=log_path)

	def _elog_process(self, phasefilter=None):
		cpv = self.mycpv
		if self._pipe is None:
			elog_process(cpv, self.settings, phasefilter=phasefilter)
		else:
			logdir = os.path.join(self.settings["T"], "logging")
			ebuild_logentries = collect_ebuild_messages(logdir)
			# phasefilter is irrelevant for the above collect_ebuild_messages
			# call, since this package instance has a private logdir. However,
			# it may be relevant for the following collect_messages call.
			py_logentries = collect_messages(key=cpv, phasefilter=phasefilter).get(cpv, {})
			logentries = _merge_logentries(py_logentries, ebuild_logentries)
			funcnames = {
				"INFO": "einfo",
				"LOG": "elog",
				"WARN": "ewarn",
				"QA": "eqawarn",
				"ERROR": "eerror"
			}
			str_buffer = []
			for phase, messages in logentries.items():
				for key, lines in messages:
					funcname = funcnames[key]
					if isinstance(lines, str):
						lines = [lines]
					for line in lines:
						for line in line.split('\n'):
							fields = (funcname, phase, cpv, line)
							str_buffer.append(' '.join(fields))
							str_buffer.append('\n')
			if str_buffer:
				str_buffer = _unicode_encode(''.join(str_buffer))
				while str_buffer:
					str_buffer = str_buffer[os.write(self._pipe, str_buffer):]

	def _emerge_log(self, msg):
		emergelog(False, msg)

	def treewalk(self, srcroot, destroot, inforoot, myebuild, cleanup=0,
		mydbapi=None, prev_mtimes=None, counter=None):
		"""

		This function does the following:

		calls doebuild(mydo=instprep)
		calls get_ro_checker to retrieve a function for checking whether Portage
		will write to a read-only filesystem, then runs it against the directory list
		calls self._preserve_libs if FEATURES=preserve-libs
		calls self._collision_protect if FEATURES=collision-protect
		calls doebuild(mydo=pkg_preinst)
		Merges the package to the livefs
		unmerges old version (if required)
		calls doebuild(mydo=pkg_postinst)
		calls env_update

		@param srcroot: Typically this is ${D}
		@type srcroot: String (Path)
		@param destroot: ignored, self.settings['ROOT'] is used instead
		@type destroot: String (Path)
		@param inforoot: root of the vardb entry ?
		@type inforoot: String (Path)
		@param myebuild: path to the ebuild that we are processing
		@type myebuild: String (Path)
		@param mydbapi: dbapi which is handed to doebuild.
		@type mydbapi: portdbapi instance
		@param prev_mtimes: { Filename:mtime } mapping for env_update
		@type prev_mtimes: Dictionary
		@rtype: Boolean
		@return:
		1. 0 on success
		2. 1 on failure

		secondhand is a list of symlinks that have been skipped due to their target
		not existing; we will merge these symlinks at a later time.
		"""

		os = _os_merge

		srcroot = _unicode_decode(srcroot,
			encoding=_encodings['content'], errors='strict')
		destroot = self.settings['ROOT']
		inforoot = _unicode_decode(inforoot,
			encoding=_encodings['content'], errors='strict')
		myebuild = _unicode_decode(myebuild,
			encoding=_encodings['content'], errors='strict')

		showMessage = self._display_merge
		srcroot = normalize_path(srcroot).rstrip(os.path.sep) + os.path.sep

		if not os.path.isdir(srcroot):
			showMessage(_("!!! Directory Not Found: D='%s'\n") % srcroot,
				level=logging.ERROR, noiselevel=-1)
			return 1

		# run instprep internal phase
		doebuild_environment(myebuild, "instprep",
			settings=self.settings, db=mydbapi)
		phase = EbuildPhase(background=False, phase="instprep",
			scheduler=self._scheduler, settings=self.settings)
		phase.start()
		if phase.wait() != os.EX_OK:
			showMessage(_("!!! instprep failed\n"),
				level=logging.ERROR, noiselevel=-1)
			return 1

		is_binpkg = self.settings.get("EMERGE_FROM") == "binary"
		slot = ''
		for var_name in ('CHOST', 'SLOT'):
			try:
				with io.open(_unicode_encode(
					os.path.join(inforoot, var_name),
					encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace') as f:
					val = f.readline().strip()
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				val = ''

			if var_name == 'SLOT':
				slot = val

				if not slot.strip():
					slot = self.settings.get(var_name, '')
					if not slot.strip():
						showMessage(_("!!! SLOT is undefined\n"),
							level=logging.ERROR, noiselevel=-1)
						return 1
					write_atomic(os.path.join(inforoot, var_name), slot + '\n')

			# This check only applies when built from source, since
			# inforoot values are written just after src_install.
			if not is_binpkg and val != self.settings.get(var_name, ''):
				self._eqawarn('preinst',
					[_("QA Notice: Expected %(var_name)s='%(expected_value)s', got '%(actual_value)s'\n") % \
					{"var_name":var_name, "expected_value":self.settings.get(var_name, ''), "actual_value":val}])

		def eerror(lines):
			self._eerror("preinst", lines)

		if not os.path.exists(self.dbcatdir):
			ensure_dirs(self.dbcatdir)

		# NOTE: We use SLOT obtained from the inforoot
		#	directory, in order to support USE=multislot.
		# Use _pkg_str discard the sub-slot part if necessary.
		slot = _pkg_str(self.mycpv, slot=slot).slot
		cp = self.mysplit[0]
		slot_atom = "%s:%s" % (cp, slot)

		self.lockdb()
		try:
			# filter any old-style virtual matches
			slot_matches = [cpv for cpv in self.vartree.dbapi.match(slot_atom)
				if cpv_getkey(cpv) == cp]

			if self.mycpv not in slot_matches and \
				self.vartree.dbapi.cpv_exists(self.mycpv):
				# handle multislot or unapplied slotmove
				slot_matches.append(self.mycpv)

			others_in_slot = []
			for cur_cpv in slot_matches:
				# Clone the config in case one of these has to be unmerged,
				# since we need it to have private ${T} etc... for things
				# like elog.
				settings_clone = portage.config(clone=self.settings)
				# This reset ensures that there is no unintended leakage
				# of variables which should not be shared.
				settings_clone.reset()
				settings_clone.setcpv(cur_cpv, mydb=self.vartree.dbapi)
				if self._preserve_libs and "preserve-libs" in \
					settings_clone["PORTAGE_RESTRICT"].split():
					self._preserve_libs = False
				others_in_slot.append(dblink(self.cat, catsplit(cur_cpv)[1],
					settings=settings_clone,
					vartree=self.vartree, treetype="vartree",
					scheduler=self._scheduler, pipe=self._pipe))
		finally:
			self.unlockdb()

		# If any instance has RESTRICT=preserve-libs, then
		# restrict it for all instances.
		if not self._preserve_libs:
			for dblnk in others_in_slot:
				dblnk._preserve_libs = False

		retval = self._security_check(others_in_slot)
		if retval:
			return retval

		if slot_matches:
			# Used by self.isprotected().
			max_dblnk = None
			max_counter = -1
			for dblnk in others_in_slot:
				cur_counter = self.vartree.dbapi.cpv_counter(dblnk.mycpv)
				if cur_counter > max_counter:
					max_counter = cur_counter
					max_dblnk = dblnk
			self._installed_instance = max_dblnk

		# Apply INSTALL_MASK before collision-protect, since it may
		# be useful to avoid collisions in some scenarios.
		# We cannot detect if this is needed or not here as INSTALL_MASK can be
		# modified by bashrc files.
		phase = MiscFunctionsProcess(background=False,
			commands=["preinst_mask"], phase="preinst",
			scheduler=self._scheduler, settings=self.settings)
		phase.start()
		phase.wait()
		try:
			with io.open(_unicode_encode(os.path.join(inforoot, "INSTALL_MASK"),
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				install_mask = InstallMask(f.read())
		except EnvironmentError:
			install_mask = None

		if install_mask:
			install_mask_dir(self.settings["ED"], install_mask)
			if any(x in self.settings.features for x in ('nodoc', 'noman', 'noinfo')):
				try:
					os.rmdir(os.path.join(self.settings["ED"], 'usr', 'share'))
				except OSError:
					pass

		# We check for unicode encoding issues after src_install. However,
		# the check must be repeated here for binary packages (it's
		# inexpensive since we call os.walk() here anyway).
		unicode_errors = []
		line_ending_re = re.compile('[\n\r]')
		srcroot_len = len(srcroot)
		ed_len = len(self.settings["ED"])
		eprefix_len = len(self.settings["EPREFIX"])

		while True:

			unicode_error = False
			eagain_error = False

			filelist = []
			linklist = []
			paths_with_newlines = []
			def onerror(e):
				raise
			walk_iter = os.walk(srcroot, onerror=onerror)
			while True:
				try:
					parent, dirs, files = next(walk_iter)
				except StopIteration:
					break
				except OSError as e:
					if e.errno != errno.EAGAIN:
						raise
					# Observed with PyPy 1.8.
					eagain_error = True
					break

				try:
					parent = _unicode_decode(parent,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeDecodeError:
					new_parent = _unicode_decode(parent,
						encoding=_encodings['merge'], errors='replace')
					new_parent = _unicode_encode(new_parent,
						encoding='ascii', errors='backslashreplace')
					new_parent = _unicode_decode(new_parent,
						encoding=_encodings['merge'], errors='replace')
					os.rename(parent, new_parent)
					unicode_error = True
					unicode_errors.append(new_parent[ed_len:])
					break

				for fname in files:
					try:
						fname = _unicode_decode(fname,
							encoding=_encodings['merge'], errors='strict')
					except UnicodeDecodeError:
						fpath = portage._os.path.join(
							parent.encode(_encodings['merge']), fname)
						new_fname = _unicode_decode(fname,
							encoding=_encodings['merge'], errors='replace')
						new_fname = _unicode_encode(new_fname,
							encoding='ascii', errors='backslashreplace')
						new_fname = _unicode_decode(new_fname,
							encoding=_encodings['merge'], errors='replace')
						new_fpath = os.path.join(parent, new_fname)
						os.rename(fpath, new_fpath)
						unicode_error = True
						unicode_errors.append(new_fpath[ed_len:])
						fname = new_fname
						fpath = new_fpath
					else:
						fpath = os.path.join(parent, fname)

					relative_path = fpath[srcroot_len:]

					if line_ending_re.search(relative_path) is not None:
						paths_with_newlines.append(relative_path)

					file_mode = os.lstat(fpath).st_mode
					if stat.S_ISREG(file_mode):
						filelist.append(relative_path)
					elif stat.S_ISLNK(file_mode):
						# Note: os.walk puts symlinks to directories in the "dirs"
						# list and it does not traverse them since that could lead
						# to an infinite recursion loop.
						linklist.append(relative_path)

						myto = _unicode_decode(
							_os.readlink(_unicode_encode(fpath,
							encoding=_encodings['merge'], errors='strict')),
							encoding=_encodings['merge'], errors='replace')
						if line_ending_re.search(myto) is not None:
							paths_with_newlines.append(relative_path)

				if unicode_error:
					break

			if not (unicode_error or eagain_error):
				break

		if unicode_errors:
			self._elog("eqawarn", "preinst",
				_merge_unicode_error(unicode_errors))

		if paths_with_newlines:
			msg = []
			msg.append(_("This package installs one or more files containing line ending characters:"))
			msg.append("")
			paths_with_newlines.sort()
			for f in paths_with_newlines:
				msg.append("\t/%s" % (f.replace("\n", "\\n").replace("\r", "\\r")))
			msg.append("")
			msg.append(_("package %s NOT merged") % self.mycpv)
			msg.append("")
			eerror(msg)
			return 1

		# If there are no files to merge, and an installed package in the same
		# slot has files, it probably means that something went wrong.
		if self.settings.get("PORTAGE_PACKAGE_EMPTY_ABORT") == "1" and \
			not filelist and not linklist and others_in_slot:
			installed_files = None
			for other_dblink in others_in_slot:
				installed_files = other_dblink.getcontents()
				if not installed_files:
					continue
				from textwrap import wrap
				wrap_width = 72
				msg = []
				d = {
					"new_cpv":self.mycpv,
					"old_cpv":other_dblink.mycpv
				}
				msg.extend(wrap(_("The '%(new_cpv)s' package will not install "
					"any files, but the currently installed '%(old_cpv)s'"
					" package has the following files: ") % d, wrap_width))
				msg.append("")
				msg.extend(sorted(installed_files))
				msg.append("")
				msg.append(_("package %s NOT merged") % self.mycpv)
				msg.append("")
				msg.extend(wrap(
					_("Manually run `emerge --unmerge =%s` if you "
					"really want to remove the above files. Set "
					"PORTAGE_PACKAGE_EMPTY_ABORT=\"0\" in "
					"/etc/portage/make.conf if you do not want to "
					"abort in cases like this.") % other_dblink.mycpv,
					wrap_width))
				eerror(msg)
			if installed_files:
				return 1

		# Make sure the ebuild environment is initialized and that ${T}/elog
		# exists for logging of collision-protect eerror messages.
		if myebuild is None:
			myebuild = os.path.join(inforoot, self.pkg + ".ebuild")
		doebuild_environment(myebuild, "preinst",
			settings=self.settings, db=mydbapi)
		self.settings["REPLACING_VERSIONS"] = " ".join(
			[portage.versions.cpv_getversion(other.mycpv)
			for other in others_in_slot])
		prepare_build_dirs(settings=self.settings, cleanup=cleanup)

		# check for package collisions
		blockers = []
		for blocker in self._blockers or []:
			blocker = self.vartree.dbapi._dblink(blocker.cpv)
			# It may have been unmerged before lock(s)
			# were aquired.
			if blocker.exists():
				blockers.append(blocker)

		collisions, internal_collisions, dirs_ro, symlink_collisions, plib_collisions = \
			self._collision_protect(srcroot, destroot,
			others_in_slot + blockers, filelist, linklist)

		# Check for read-only filesystems.
		ro_checker = get_ro_checker()
		rofilesystems = ro_checker(dirs_ro)

		if rofilesystems:
			msg = _("One or more files installed to this package are "
				"set to be installed to read-only filesystems. "
				"Please mount the following filesystems as read-write "
				"and retry.")
			msg = textwrap.wrap(msg, 70)
			msg.append("")
			for f in rofilesystems:
				msg.append("\t%s" % f)
			msg.append("")
			self._elog("eerror", "preinst", msg)

			msg = _("Package '%s' NOT merged due to read-only file systems.") % \
				self.settings.mycpv
			msg += _(" If necessary, refer to your elog "
				"messages for the whole content of the above message.")
			msg = textwrap.wrap(msg, 70)
			eerror(msg)
			return 1

		if internal_collisions:
			msg = _("Package '%s' has internal collisions between non-identical files "
				"(located in separate directories in the installation image (${D}) "
				"corresponding to merged directories in the target "
				"filesystem (${ROOT})):") % self.settings.mycpv
			msg = textwrap.wrap(msg, 70)
			msg.append("")
			for k, v in sorted(internal_collisions.items(), key=operator.itemgetter(0)):
				msg.append("\t%s" % os.path.join(destroot, k.lstrip(os.path.sep)))
				for (file1, file2), differences in sorted(v.items()):
					msg.append("\t\t%s" % os.path.join(destroot, file1.lstrip(os.path.sep)))
					msg.append("\t\t%s" % os.path.join(destroot, file2.lstrip(os.path.sep)))
					msg.append("\t\t\tDifferences: %s" % ", ".join(differences))
					msg.append("")
			self._elog("eerror", "preinst", msg)

			msg = _("Package '%s' NOT merged due to internal collisions "
				"between non-identical files.") % self.settings.mycpv
			msg += _(" If necessary, refer to your elog messages for the whole "
				"content of the above message.")
			eerror(textwrap.wrap(msg, 70))
			return 1

		if symlink_collisions:
			# Symlink collisions need to be distinguished from other types
			# of collisions, in order to avoid confusion (see bug #409359).
			msg = _("Package '%s' has one or more collisions "
				"between symlinks and directories, which is explicitly "
				"forbidden by PMS section 13.4 (see bug #326685):") % \
				(self.settings.mycpv,)
			msg = textwrap.wrap(msg, 70)
			msg.append("")
			for f in symlink_collisions:
				msg.append("\t%s" % os.path.join(destroot,
					f.lstrip(os.path.sep)))
			msg.append("")
			self._elog("eerror", "preinst", msg)

		if collisions:
			collision_protect = "collision-protect" in self.settings.features
			protect_owned = "protect-owned" in self.settings.features
			msg = _("This package will overwrite one or more files that"
			" may belong to other packages (see list below).")
			if not (collision_protect or protect_owned):
				msg += _(" Add either \"collision-protect\" or"
				" \"protect-owned\" to FEATURES in"
				" make.conf if you would like the merge to abort"
				" in cases like this. See the make.conf man page for"
				" more information about these features.")
			if self.settings.get("PORTAGE_QUIET") != "1":
				msg += _(" You can use a command such as"
				" `portageq owners / <filename>` to identify the"
				" installed package that owns a file. If portageq"
				" reports that only one package owns a file then do NOT"
				" file a bug report. A bug report is only useful if it"
				" identifies at least two or more packages that are known"
				" to install the same file(s)."
				" If a collision occurs and you"
				" can not explain where the file came from then you"
				" should simply ignore the collision since there is not"
				" enough information to determine if a real problem"
				" exists. Please do NOT file a bug report at"
				" https://bugs.gentoo.org/ unless you report exactly which"
				" two packages install the same file(s). See"
				" https://wiki.gentoo.org/wiki/Knowledge_Base:Blockers"
				" for tips on how to solve the problem. And once again,"
				" please do NOT file a bug report unless you have"
				" completely understood the above message.")

			self.settings["EBUILD_PHASE"] = "preinst"
			from textwrap import wrap
			msg = wrap(msg, 70)
			if collision_protect:
				msg.append("")
				msg.append(_("package %s NOT merged") % self.settings.mycpv)
			msg.append("")
			msg.append(_("Detected file collision(s):"))
			msg.append("")

			for f in collisions:
				msg.append("\t%s" % \
					os.path.join(destroot, f.lstrip(os.path.sep)))

			eerror(msg)

			owners = None
			if collision_protect or protect_owned or symlink_collisions:
				msg = []
				msg.append("")
				msg.append(_("Searching all installed"
					" packages for file collisions..."))
				msg.append("")
				msg.append(_("Press Ctrl-C to Stop"))
				msg.append("")
				eerror(msg)

				if len(collisions) > 20:
					# get_owners is slow for large numbers of files, so
					# don't look them all up.
					collisions = collisions[:20]

				pkg_info_strs = {}
				self.lockdb()
				try:
					owners = self.vartree.dbapi._owners.get_owners(collisions)
					self.vartree.dbapi.flush_cache()

					for pkg in owners:
						pkg = self.vartree.dbapi._pkg_str(pkg.mycpv, None)
						pkg_info_str = "%s%s%s" % (pkg,
							_slot_separator, pkg.slot)
						if pkg.repo != _unknown_repo:
							pkg_info_str += "%s%s" % (_repo_separator,
								pkg.repo)
						pkg_info_strs[pkg] = pkg_info_str

				finally:
					self.unlockdb()

				for pkg, owned_files in owners.items():
					msg = []
					msg.append(pkg_info_strs[pkg.mycpv])
					for f in sorted(owned_files):
						msg.append("\t%s" % os.path.join(destroot,
							f.lstrip(os.path.sep)))
					msg.append("")
					eerror(msg)

				if not owners:
					eerror([_("None of the installed"
						" packages claim the file(s)."), ""])

			symlink_abort_msg =_("Package '%s' NOT merged since it has "
				"one or more collisions between symlinks and directories, "
				"which is explicitly forbidden by PMS section 13.4 "
				"(see bug #326685).")

			# The explanation about the collision and how to solve
			# it may not be visible via a scrollback buffer, especially
			# if the number of file collisions is large. Therefore,
			# show a summary at the end.
			abort = False
			if symlink_collisions:
				abort = True
				msg = symlink_abort_msg % (self.settings.mycpv,)
			elif collision_protect:
				abort = True
				msg = _("Package '%s' NOT merged due to file collisions.") % \
					self.settings.mycpv
			elif protect_owned and owners:
				abort = True
				msg = _("Package '%s' NOT merged due to file collisions.") % \
					self.settings.mycpv
			else:
				msg = _("Package '%s' merged despite file collisions.") % \
					self.settings.mycpv
			msg += _(" If necessary, refer to your elog "
				"messages for the whole content of the above message.")
			eerror(wrap(msg, 70))

			if abort:
				return 1

		# The merge process may move files out of the image directory,
		# which causes invalidation of the .installed flag.
		try:
			os.unlink(os.path.join(
				os.path.dirname(normalize_path(srcroot)), ".installed"))
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e

		self.dbdir = self.dbtmpdir
		self.delete()
		ensure_dirs(self.dbtmpdir)

		downgrade = False
		if self._installed_instance is not None and \
			vercmp(self.mycpv.version,
			self._installed_instance.mycpv.version) < 0:
			downgrade = True

		if self._installed_instance is not None:
			rval = self._pre_merge_backup(self._installed_instance, downgrade)
			if rval != os.EX_OK:
				showMessage(_("!!! FAILED preinst: ") +
					"quickpkg: %s\n" % rval,
					level=logging.ERROR, noiselevel=-1)
				return rval

		# run preinst script
		showMessage(_(">>> Merging %(cpv)s to %(destroot)s\n") % \
			{"cpv":self.mycpv, "destroot":destroot})
		phase = EbuildPhase(background=False, phase="preinst",
			scheduler=self._scheduler, settings=self.settings)
		phase.start()
		a = phase.wait()

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			showMessage(_("!!! FAILED preinst: ")+str(a)+"\n",
				level=logging.ERROR, noiselevel=-1)
			return a

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in os.listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# write local package counter for recording
		if counter is None:
			counter = self.vartree.dbapi.counter_tick(mycpv=self.mycpv)
		with io.open(_unicode_encode(os.path.join(self.dbtmpdir, 'COUNTER'),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace') as f:
			f.write("%s" % counter)

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		self.vartree.dbapi._fs_lock()
		try:
			# This prunes any libraries from the registry that no longer
			# exist on disk, in case they have been manually removed.
			# This has to be done prior to merge, since after merge it
			# is non-trivial to distinguish these files from files
			# that have just been merged.
			plib_registry = self.vartree.dbapi._plib_registry
			if plib_registry:
				plib_registry.lock()
				try:
					plib_registry.load()
					plib_registry.store()
				finally:
					plib_registry.unlock()

			# Always behave like --noconfmem is enabled for downgrades
			# so that people who don't know about this option are less
			# likely to get confused when doing upgrade/downgrade cycles.
			cfgfiledict = grabdict(self.vartree.dbapi._conf_mem_file)
			if "NOCONFMEM" in self.settings or downgrade:
				cfgfiledict["IGNORE"]=1
			else:
				cfgfiledict["IGNORE"]=0

			rval = self._merge_contents(srcroot, destroot, cfgfiledict)
			if rval != os.EX_OK:
				return rval
		finally:
			self.vartree.dbapi._fs_unlock()

		# These caches are populated during collision-protect and the data
		# they contain is now invalid. It's very important to invalidate
		# the contents_inodes cache so that FEATURES=unmerge-orphans
		# doesn't unmerge anything that belongs to this package that has
		# just been merged.
		for dblnk in others_in_slot:
			dblnk._clear_contents_cache()
		self._clear_contents_cache()

		linkmap = self.vartree.dbapi._linkmap
		plib_registry = self.vartree.dbapi._plib_registry
		# We initialize preserve_paths to an empty set rather
		# than None here because it plays an important role
		# in prune_plib_registry logic by serving to indicate
		# that we have a replacement for a package that's
		# being unmerged.

		preserve_paths = set()
		needed = None
		if not (self._linkmap_broken or linkmap is None or
			plib_registry is None):
			self.vartree.dbapi._fs_lock()
			plib_registry.lock()
			try:
				plib_registry.load()
				needed = os.path.join(inforoot, linkmap._needed_aux_key)
				self._linkmap_rebuild(include_file=needed)

				# Preserve old libs if they are still in use
				# TODO: Handle cases where the previous instance
				# has already been uninstalled but it still has some
				# preserved libraries in the registry that we may
				# want to preserve here.
				preserve_paths = self._find_libs_to_preserve()
			finally:
				plib_registry.unlock()
				self.vartree.dbapi._fs_unlock()

			if preserve_paths:
				self._add_preserve_libs_to_contents(preserve_paths)

		# If portage is reinstalling itself, remove the old
		# version now since we want to use the temporary
		# PORTAGE_BIN_PATH that will be removed when we return.
		reinstall_self = False
		if self.myroot == "/" and \
			match_from_list(PORTAGE_PACKAGE_ATOM, [self.mycpv]):
			reinstall_self = True

		emerge_log = self._emerge_log

		# If we have any preserved libraries then autoclean
		# is forced so that preserve-libs logic doesn't have
		# to account for the additional complexity of the
		# AUTOCLEAN=no mode.
		autoclean = self.settings.get("AUTOCLEAN", "yes") == "yes" \
			or preserve_paths

		if autoclean:
			emerge_log(_(" >>> AUTOCLEAN: %s") % (slot_atom,))

		others_in_slot.append(self)  # self has just been merged
		for dblnk in list(others_in_slot):
			if dblnk is self:
				continue
			if not (autoclean or dblnk.mycpv == self.mycpv or reinstall_self):
				continue
			showMessage(_(">>> Safely unmerging already-installed instance...\n"))
			emerge_log(_(" === Unmerging... (%s)") % (dblnk.mycpv,))
			others_in_slot.remove(dblnk) # dblnk will unmerge itself now
			dblnk._linkmap_broken = self._linkmap_broken
			dblnk.settings["REPLACED_BY_VERSION"] = portage.versions.cpv_getversion(self.mycpv)
			dblnk.settings.backup_changes("REPLACED_BY_VERSION")
			unmerge_rval = dblnk.unmerge(ldpath_mtimes=prev_mtimes,
				others_in_slot=others_in_slot, needed=needed,
				preserve_paths=preserve_paths)
			dblnk.settings.pop("REPLACED_BY_VERSION", None)

			if unmerge_rval == os.EX_OK:
				emerge_log(_(" >>> unmerge success: %s") % (dblnk.mycpv,))
			else:
				emerge_log(_(" !!! unmerge FAILURE: %s") % (dblnk.mycpv,))

			self.lockdb()
			try:
				# TODO: Check status and abort if necessary.
				dblnk.delete()
			finally:
				self.unlockdb()
			showMessage(_(">>> Original instance of package unmerged safely.\n"))

		if len(others_in_slot) > 1:
			showMessage(colorize("WARN", _("WARNING:"))
				+ _(" AUTOCLEAN is disabled.  This can cause serious"
				" problems due to overlapping packages.\n"),
				level=logging.WARN, noiselevel=-1)

		# We hold both directory locks.
		self.dbdir = self.dbpkgdir
		self.lockdb()
		try:
			self.delete()
			_movefile(self.dbtmpdir, self.dbpkgdir, mysettings=self.settings)
			self._merged_path(self.dbpkgdir, os.lstat(self.dbpkgdir))
			self.vartree.dbapi._cache_delta.recordEvent(
				"add", self.mycpv, slot, counter)
		finally:
			self.unlockdb()

		# Check for file collisions with blocking packages
		# and remove any colliding files from their CONTENTS
		# since they now belong to this package.
		self._clear_contents_cache()
		contents = self.getcontents()
		destroot_len = len(destroot) - 1
		self.lockdb()
		try:
			for blocker in blockers:
				self.vartree.dbapi.removeFromContents(blocker, iter(contents),
					relative_paths=False)
		finally:
			self.unlockdb()

		plib_registry = self.vartree.dbapi._plib_registry
		if plib_registry:
			self.vartree.dbapi._fs_lock()
			plib_registry.lock()
			try:
				plib_registry.load()

				if preserve_paths:
					# keep track of the libs we preserved
					plib_registry.register(self.mycpv, slot, counter,
						sorted(preserve_paths))

				# Unregister any preserved libs that this package has overwritten
				# and update the contents of the packages that owned them.
				plib_dict = plib_registry.getPreservedLibs()
				for cpv, paths in plib_collisions.items():
					if cpv not in plib_dict:
						continue
					has_vdb_entry = False
					if cpv != self.mycpv:
						# If we've replaced another instance with the
						# same cpv then the vdb entry no longer belongs
						# to it, so we'll have to get the slot and counter
						# from plib_registry._data instead.
						self.vartree.dbapi.lock()
						try:
							try:
								slot = self.vartree.dbapi._pkg_str(cpv, None).slot
								counter = self.vartree.dbapi.cpv_counter(cpv)
							except (KeyError, InvalidData):
								pass
							else:
								has_vdb_entry = True
								self.vartree.dbapi.removeFromContents(
									cpv, paths)
						finally:
							self.vartree.dbapi.unlock()

					if not has_vdb_entry:
						# It's possible for previously unmerged packages
						# to have preserved libs in the registry, so try
						# to retrieve the slot and counter from there.
						has_registry_entry = False
						for plib_cps, (plib_cpv, plib_counter, plib_paths) in \
							plib_registry._data.items():
							if plib_cpv != cpv:
								continue
							try:
								cp, slot = plib_cps.split(":", 1)
							except ValueError:
								continue
							counter = plib_counter
							has_registry_entry = True
							break

						if not has_registry_entry:
							continue

					remaining = [f for f in plib_dict[cpv] if f not in paths]
					plib_registry.register(cpv, slot, counter, remaining)

				plib_registry.store()
			finally:
				plib_registry.unlock()
				self.vartree.dbapi._fs_unlock()

		self.vartree.dbapi._add(self)
		contents = self.getcontents()

		#do postinst script
		self.settings["PORTAGE_UPDATE_ENV"] = \
			os.path.join(self.dbpkgdir, "environment.bz2")
		self.settings.backup_changes("PORTAGE_UPDATE_ENV")
		try:
			phase = EbuildPhase(background=False, phase="postinst",
				scheduler=self._scheduler, settings=self.settings)
			phase.start()
			a = phase.wait()
			if a == os.EX_OK:
				showMessage(_(">>> %s merged.\n") % self.mycpv)
		finally:
			self.settings.pop("PORTAGE_UPDATE_ENV", None)

		if a != os.EX_OK:
			# It's stupid to bail out here, so keep going regardless of
			# phase return code.
			self._postinst_failure = True
			self._elog("eerror", "postinst", [
				_("FAILED postinst: %s") % (a,),
			])

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(
			target_root=self.settings['ROOT'], prev_mtimes=prev_mtimes,
			contents=contents, env=self.settings,
			writemsg_level=self._display_merge, vardbapi=self.vartree.dbapi)

		# For gcc upgrades, preserved libs have to be removed after the
		# the library path has been updated.
		self._prune_plib_registry()
		self._post_merge_sync()

		return os.EX_OK

	def _new_backup_path(self, p):
		"""
		The works for any type path, such as a regular file, symlink,
		or directory. The parent directory is assumed to exist.
		The returned filename is of the form p + '.backup.' + x, where
		x guarantees that the returned path does not exist yet.
		"""
		os = _os_merge

		x = -1
		while True:
			x += 1
			backup_p = '%s.backup.%04d' % (p, x)
			try:
				os.lstat(backup_p)
			except OSError:
				break

		return backup_p

	def _merge_contents(self, srcroot, destroot, cfgfiledict):

		cfgfiledict_orig = cfgfiledict.copy()

		# open CONTENTS file (possibly overwriting old one) for recording
		# Use atomic_ofstream for automatic coercion of raw bytes to
		# unicode, in order to prevent TypeError when writing raw bytes
		# to TextIOWrapper with python2.
		outfile = atomic_ofstream(_unicode_encode(
			os.path.join(self.dbtmpdir, 'CONTENTS'),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace')

		# Don't bump mtimes on merge since some application require
		# preservation of timestamps.  This means that the unmerge phase must
		# check to see if file belongs to an installed instance in the same
		# slot.
		mymtime = None

		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		prevmask = os.umask(0)
		secondhand = []

		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		if self.mergeme(srcroot, destroot, outfile, secondhand,
			self.settings["EPREFIX"].lstrip(os.sep), cfgfiledict, mymtime):
			return 1

		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen = 0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that
			# couldn't get merged will be added to thirdhand.

			thirdhand = []
			if self.mergeme(srcroot, destroot, outfile, thirdhand,
				secondhand, cfgfiledict, mymtime):
				return 1

			#swap hands
			lastlen = len(secondhand)

			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			if self.mergeme(srcroot, destroot, outfile, None,
				secondhand, cfgfiledict, mymtime):
				return 1

		#restore umask
		os.umask(prevmask)

		#if we opened it, close it
		outfile.flush()
		outfile.close()

		# write out our collection of md5sums
		if cfgfiledict != cfgfiledict_orig:
			cfgfiledict.pop("IGNORE", None)
			try:
				writedict(cfgfiledict, self.vartree.dbapi._conf_mem_file)
			except InvalidLocation:
				self.settings._init_dirs()
				writedict(cfgfiledict, self.vartree.dbapi._conf_mem_file)

		return os.EX_OK

	def mergeme(self, srcroot, destroot, outfile, secondhand, stufftomerge, cfgfiledict, thismtime):
		"""

		This function handles actual merging of the package contents to the livefs.
		It also handles config protection.

		@param srcroot: Where are we copying files from (usually ${D})
		@type srcroot: String (Path)
		@param destroot: Typically ${ROOT}
		@type destroot: String (Path)
		@param outfile: File to log operations to
		@type outfile: File Object
		@param secondhand: A set of items to merge in pass two (usually
		or symlinks that point to non-existing files that may get merged later)
		@type secondhand: List
		@param stufftomerge: Either a diretory to merge, or a list of items.
		@type stufftomerge: String or List
		@param cfgfiledict: { File:mtime } mapping for config_protected files
		@type cfgfiledict: Dictionary
		@param thismtime: None or new mtime for merged files (expressed in seconds
		in Python <3.3 and nanoseconds in Python >=3.3)
		@type thismtime: None or Int
		@rtype: None or Boolean
		@return:
		1. True on failure
		2. None otherwise

		"""

		showMessage = self._display_merge
		writemsg = self._display_merge

		os = _os_merge
		sep = os.sep
		join = os.path.join
		srcroot = normalize_path(srcroot).rstrip(sep) + sep
		destroot = normalize_path(destroot).rstrip(sep) + sep
		calc_prelink = "prelink-checksums" in self.settings.features

		protect_if_modified = \
			"config-protect-if-modified" in self.settings.features and \
			self._installed_instance is not None

		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if isinstance(stufftomerge, str):
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist = [join(stufftomerge, child) for child in \
				os.listdir(join(srcroot, stufftomerge))]
		else:
			mergelist = stufftomerge[:]

		while mergelist:

			relative_path = mergelist.pop()
			mysrc = join(srcroot, relative_path)
			mydest = join(destroot, relative_path)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest = join(sep, relative_path)
			# stat file once, test using S_* macros many times (faster that way)
			mystat = os.lstat(mysrc)
			mymode = mystat[stat.ST_MODE]
			mymd5 = None
			myto = None

			mymtime = mystat.st_mtime_ns

			if stat.S_ISREG(mymode):
				mymd5 = perform_md5(mysrc, calc_prelink=calc_prelink)
			elif stat.S_ISLNK(mymode):
				# The file name of mysrc and the actual file that it points to
				# will have earlier been forcefully converted to the 'merge'
				# encoding if necessary, but the content of the symbolic link
				# may need to be forcefully converted here.
				myto = _os.readlink(_unicode_encode(mysrc,
					encoding=_encodings['merge'], errors='strict'))
				try:
					myto = _unicode_decode(myto,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeDecodeError:
					myto = _unicode_decode(myto, encoding=_encodings['merge'],
						errors='replace')
					myto = _unicode_encode(myto, encoding='ascii',
						errors='backslashreplace')
					myto = _unicode_decode(myto, encoding=_encodings['merge'],
						errors='replace')
					os.unlink(mysrc)
					os.symlink(myto, mysrc)

				mymd5 = md5(_unicode_encode(myto)).hexdigest()

			protected = False
			if stat.S_ISLNK(mymode) or stat.S_ISREG(mymode):
				protected = self.isprotected(mydest)

				if stat.S_ISREG(mymode) and \
					mystat.st_size == 0 and \
					os.path.basename(mydest).startswith(".keep"):
					protected = False

			destmd5 = None
			mydest_link = None
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydstat = os.lstat(mydest)
				mydmode = mydstat.st_mode
				if protected:
					if stat.S_ISLNK(mydmode):
						# Read symlink target as bytes, in case the
						# target path has a bad encoding.
						mydest_link = _os.readlink(
							_unicode_encode(mydest,
							encoding=_encodings['merge'],
							errors='strict'))
						mydest_link = _unicode_decode(mydest_link,
							encoding=_encodings['merge'],
							errors='replace')

						# For protection of symlinks, the md5
						# of the link target path string is used
						# for cfgfiledict (symlinks are
						# protected since bug #485598).
						destmd5 = md5(_unicode_encode(mydest_link)).hexdigest()

					elif stat.S_ISREG(mydmode):
						destmd5 = perform_md5(mydest,
							calc_prelink=calc_prelink)
			except (FileNotFound, OSError) as e:
				if isinstance(e, OSError) and e.errno != errno.ENOENT:
					raise
				#dest file doesn't exist
				mydstat = None
				mydmode = None
				mydest_link = None
				destmd5 = None

			moveme = True
			if protected:
				mydest, protected, moveme = self._protect(cfgfiledict,
					protect_if_modified, mymd5, myto, mydest,
					myrealdest, mydmode, destmd5, mydest_link)

			zing = "!!!"
			if not moveme:
				# confmem rejected this update
				zing = "---"

			if stat.S_ISLNK(mymode):
				# we are merging a symbolic link
				# Pass in the symlink target in order to bypass the
				# os.readlink() call inside abssymlink(), since that
				# call is unsafe if the merge encoding is not ascii
				# or utf_8 (see bug #382021).
				myabsto = abssymlink(mysrc, target=myto)

				if myabsto.startswith(srcroot):
					myabsto = myabsto[len(srcroot):]
				myabsto = myabsto.lstrip(sep)
				if self.settings and self.settings["D"]:
					if myto.startswith(self.settings["D"]):
						myto = myto[len(self.settings["D"])-1:]
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto = normalize_path(os.path.join(destroot, myabsto))
				if mydmode is not None and stat.S_ISDIR(mydmode):
					if not protected:
						# we can't merge a symlink over a directory
						newdest = self._new_backup_path(mydest)
						msg = []
						msg.append("")
						msg.append(_("Installation of a symlink is blocked by a directory:"))
						msg.append("  '%s'" % mydest)
						msg.append(_("This symlink will be merged with a different name:"))
						msg.append("  '%s'" % newdest)
						msg.append("")
						self._eerror("preinst", msg)
						mydest = newdest

				# if secondhand is None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand != None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				if moveme:
					zing = ">>>"
					mymtime = movefile(mysrc, mydest, newmtime=thismtime,
						sstat=mystat, mysettings=self.settings,
						encoding=_encodings['merge'])

				try:
					self._merged_path(mydest, os.lstat(mydest))
				except OSError:
					pass

				if mymtime != None:
					# Use lexists, since if the target happens to be a broken
					# symlink then that should trigger an independent warning.
					if not (os.path.lexists(myrealto) or
						os.path.lexists(join(srcroot, myabsto))):
						self._eqawarn('preinst',
							[_("QA Notice: Symbolic link /%s points to /%s which does not exist.")
							% (relative_path, myabsto)])

					showMessage("%s %s -> %s\n" % (zing, mydest, myto))
					outfile.write(
						self._format_contents_line(
							node_type="sym",
							abs_path=myrealdest,
							symlink_target=myto,
							mtime_ns=mymtime,
						)
					)
				else:
					showMessage(_("!!! Failed to move file.\n"),
						level=logging.ERROR, noiselevel=-1)
					showMessage("!!! %s -> %s\n" % (mydest, myto),
						level=logging.ERROR, noiselevel=-1)
					return 1
			elif stat.S_ISDIR(mymode):
				# we are merging a directory
				if mydmode != None:
					# destination exists

					if bsd_chflags:
						# Save then clear flags on dest.
						dflags = mydstat.st_flags
						if dflags != 0:
							bsd_chflags.lchflags(mydest, 0)

					if not stat.S_ISLNK(mydmode) and \
						not os.access(mydest, os.W_OK):
						pkgstuff = pkgsplit(self.pkg)
						writemsg(_("\n!!! Cannot write to '%s'.\n") % mydest, noiselevel=-1)
						writemsg(_("!!! Please check permissions and directories for broken symlinks.\n"))
						writemsg(_("!!! You may start the merge process again by using ebuild:\n"))
						writemsg("!!! ebuild "+self.settings["PORTDIR"]+"/"+self.cat+"/"+pkgstuff[0]+"/"+self.pkg+".ebuild merge\n")
						writemsg(_("!!! And finish by running this: env-update\n\n"))
						return 1

					if stat.S_ISDIR(mydmode) or \
						(stat.S_ISLNK(mydmode) and os.path.isdir(mydest)):
						# a symlink to an existing directory will work for us; keep it:
						showMessage("--- %s/\n" % mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						backup_dest = self._new_backup_path(mydest)
						msg = []
						msg.append("")
						msg.append(_("Installation of a directory is blocked by a file:"))
						msg.append("  '%s'" % mydest)
						msg.append(_("This file will be renamed to a different name:"))
						msg.append("  '%s'" % backup_dest)
						msg.append("")
						self._eerror("preinst", msg)
						if movefile(mydest, backup_dest,
							mysettings=self.settings,
							encoding=_encodings['merge']) is None:
							return 1
						showMessage(_("bak %s %s.backup\n") % (mydest, mydest),
							level=logging.ERROR, noiselevel=-1)
						#now create our directory
						try:
							if self.settings.selinux_enabled():
								_selinux_merge.mkdir(mydest, mysrc)
							else:
								os.mkdir(mydest)
						except OSError as e:
							# Error handling should be equivalent to
							# portage.util.ensure_dirs() for cases
							# like bug #187518.
							if e.errno in (errno.EEXIST,):
								pass
							elif os.path.isdir(mydest):
								pass
							else:
								raise
							del e

						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
						os.chmod(mydest, mystat[0])
						os.chown(mydest, mystat[4], mystat[5])
						showMessage(">>> %s/\n" % mydest)
				else:
					try:
						#destination doesn't exist
						if self.settings.selinux_enabled():
							_selinux_merge.mkdir(mydest, mysrc)
						else:
							os.mkdir(mydest)
					except OSError as e:
						# Error handling should be equivalent to
						# portage.util.ensure_dirs() for cases
						# like bug #187518.
						if e.errno in (errno.EEXIST,):
							pass
						elif os.path.isdir(mydest):
							pass
						else:
							raise
						del e
					os.chmod(mydest, mystat[0])
					os.chown(mydest, mystat[4], mystat[5])
					showMessage(">>> %s/\n" % mydest)

				try:
					self._merged_path(mydest, os.lstat(mydest))
				except OSError:
					pass

				outfile.write(
					self._format_contents_line(node_type="dir", abs_path=myrealdest)
				)
				# recurse and merge this directory
				mergelist.extend(join(relative_path, child) for child in
					os.listdir(join(srcroot, relative_path)))

			elif stat.S_ISREG(mymode):
				# we are merging a regular file
				if not protected and \
					mydmode is not None and stat.S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						newdest = self._new_backup_path(mydest)
						msg = []
						msg.append("")
						msg.append(_("Installation of a regular file is blocked by a directory:"))
						msg.append("  '%s'" % mydest)
						msg.append(_("This file will be merged with a different name:"))
						msg.append("  '%s'" % newdest)
						msg.append("")
						self._eerror("preinst", msg)
						mydest = newdest

				# whether config protection or not, we merge the new file the
				# same way.  Unless moveme=0 (blocking directory)
				if moveme:
					# Create hardlinks only for source files that already exist
					# as hardlinks (having identical st_dev and st_ino).
					hardlink_key = (mystat.st_dev, mystat.st_ino)

					hardlink_candidates = self._hardlink_merge_map.get(hardlink_key)
					if hardlink_candidates is None:
						hardlink_candidates = []
						self._hardlink_merge_map[hardlink_key] = hardlink_candidates

					mymtime = movefile(mysrc, mydest, newmtime=thismtime,
						sstat=mystat, mysettings=self.settings,
						hardlink_candidates=hardlink_candidates,
						encoding=_encodings['merge'])
					if mymtime is None:
						return 1
					hardlink_candidates.append(mydest)
					zing = ">>>"

					try:
						self._merged_path(mydest, os.lstat(mydest))
					except OSError:
						pass

				if mymtime != None:
					outfile.write(
						self._format_contents_line(
							node_type="obj",
							abs_path=myrealdest,
							md5_digest=mymd5,
							mtime_ns=mymtime,
						)
					)
				showMessage("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing = "!!!"
				if mydmode is None:
					# destination doesn't exist
					if movefile(mysrc, mydest, newmtime=thismtime,
						sstat=mystat, mysettings=self.settings,
						encoding=_encodings['merge']) is not None:
						zing = ">>>"

						try:
							self._merged_path(mydest, os.lstat(mydest))
						except OSError:
							pass

					else:
						return 1
				if stat.S_ISFIFO(mymode):
					outfile.write(
						self._format_contents_line(node_type="fif", abs_path=myrealdest)
					)
				else:
					outfile.write(
						self._format_contents_line(node_type="dev", abs_path=myrealdest)
					)
				showMessage(zing + " " + mydest + "\n")

	def _protect(self, cfgfiledict, protect_if_modified, src_md5,
		src_link, dest, dest_real, dest_mode, dest_md5, dest_link):

		move_me = True
		protected = True
		force = False
		k = False
		if self._installed_instance is not None:
			k = self._installed_instance._match_contents(dest_real)
		if k is not False:
			if dest_mode is None:
				# If the file doesn't exist, then it may
				# have been deleted or renamed by the
				# admin. Therefore, force the file to be
				# merged with a ._cfg name, so that the
				# admin will be prompted for this update
				# (see bug #523684).
				force = True

			elif protect_if_modified:
				data = self._installed_instance.getcontents()[k]
				if data[0] == "obj" and data[2] == dest_md5:
					protected = False
				elif data[0] == "sym" and data[2] == dest_link:
					protected = False

		if protected and dest_mode is not None:
			# we have a protection path; enable config file management.
			if src_md5 == dest_md5:
				protected = False

			elif src_md5 == cfgfiledict.get(dest_real, [None])[0]:
				# An identical update has previously been
				# merged.  Skip it unless the user has chosen
				# --noconfmem.
				move_me = protected = bool(cfgfiledict["IGNORE"])

			if protected and \
				(dest_link is not None or src_link is not None) and \
				dest_link != src_link:
				# If either one is a symlink, and they are not
				# identical symlinks, then force config protection.
				force = True

			if move_me:
				# Merging a new file, so update confmem.
				cfgfiledict[dest_real] = [src_md5]
			elif dest_md5 == cfgfiledict.get(dest_real, [None])[0]:
				# A previously remembered update has been
				# accepted, so it is removed from confmem.
				del cfgfiledict[dest_real]

		if protected and move_me:
			dest = new_protect_filename(dest,
				newmd5=(dest_link or src_md5),
				force=force)

		return dest, protected, move_me

	def _format_contents_line(
		self, node_type, abs_path, md5_digest=None, symlink_target=None, mtime_ns=None
	):
		fields = [node_type, abs_path]
		if md5_digest is not None:
			fields.append(md5_digest)
		elif symlink_target is not None:
			fields.append("-> {}".format(symlink_target))
		if mtime_ns is not None:
			fields.append(str(mtime_ns // 1000000000))
		return "{}\n".format(" ".join(fields))

	def _merged_path(self, path, lstatobj, exists=True):
		previous_path = self._device_path_map.get(lstatobj.st_dev)
		if previous_path is None or previous_path is False or \
			(exists and len(path) < len(previous_path)):
			if exists:
				self._device_path_map[lstatobj.st_dev] = path
			else:
				# This entry is used to indicate that we've unmerged
				# a file from this device, and later, this entry is
				# replaced by a parent directory.
				self._device_path_map[lstatobj.st_dev] = False

	def _post_merge_sync(self):
		"""
		Call this after merge or unmerge, in order to sync relevant files to
		disk and avoid data-loss in the event of a power failure. This method
		does nothing if FEATURES=merge-sync is disabled.
		"""
		if not self._device_path_map or \
			"merge-sync" not in self.settings.features:
			return

		returncode = None
		if platform.system() == "Linux":

			paths = []
			for path in self._device_path_map.values():
				if path is not False:
					paths.append(path)
			paths = tuple(paths)

			proc = SyncfsProcess(paths=paths,
				scheduler=(self._scheduler or asyncio._safe_loop()))
			proc.start()
			returncode = proc.wait()

		if returncode is None or returncode != os.EX_OK:
			try:
				proc = subprocess.Popen(["sync"])
			except EnvironmentError:
				pass
			else:
				proc.wait()

	@_slot_locked
	def merge(self, mergeroot, inforoot, myroot=None, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None, counter=None):
		"""
		@param myroot: ignored, self._eroot is used instead
		"""
		myroot = None
		retval = -1
		parallel_install = "parallel-install" in self.settings.features
		if not parallel_install:
			self.lockdb()
		self.vartree.dbapi._bump_mtime(self.mycpv)
		if self._scheduler is None:
			self._scheduler = SchedulerInterface(asyncio._safe_loop())
		try:
			retval = self.treewalk(mergeroot, myroot, inforoot, myebuild,
				cleanup=cleanup, mydbapi=mydbapi, prev_mtimes=prev_mtimes,
				counter=counter)

			# If PORTAGE_BUILDDIR doesn't exist, then it probably means
			# fail-clean is enabled, and the success/die hooks have
			# already been called by EbuildPhase.
			if os.path.isdir(self.settings['PORTAGE_BUILDDIR']):

				if retval == os.EX_OK:
					phase = 'success_hooks'
				else:
					phase = 'die_hooks'

				ebuild_phase = MiscFunctionsProcess(
					background=False, commands=[phase],
					scheduler=self._scheduler, settings=self.settings)
				ebuild_phase.start()
				ebuild_phase.wait()
				self._elog_process()

				if 'noclean' not in self.settings.features and \
					(retval == os.EX_OK or \
					'fail-clean' in self.settings.features):
					if myebuild is None:
						myebuild = os.path.join(inforoot, self.pkg + ".ebuild")

					doebuild_environment(myebuild, "clean",
						settings=self.settings, db=mydbapi)
					phase = EbuildPhase(background=False, phase="clean",
						scheduler=self._scheduler, settings=self.settings)
					phase.start()
					phase.wait()
		finally:
			self.settings.pop('REPLACING_VERSIONS', None)
			if self.vartree.dbapi._linkmap is None:
				# preserve-libs is entirely disabled
				pass
			else:
				self.vartree.dbapi._linkmap._clear_cache()
			self.vartree.dbapi._bump_mtime(self.mycpv)
			if not parallel_install:
				self.unlockdb()

		if retval == os.EX_OK and self._postinst_failure:
			retval = portage.const.RETURNCODE_POSTINST_FAILURE

		return retval

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		with io.open(
			_unicode_encode(os.path.join(self.dbdir, name),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			) as f:
			mydata = f.read().split()
		return " ".join(mydata)

	def copyfile(self,fname):
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))

	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		with io.open(_unicode_encode(os.path.join(self.dbdir, fname),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			) as f:
			return f.read()

	def setfile(self,fname,data):
		kwargs = {}
		if fname == 'environment.bz2' or not isinstance(data, str):
			kwargs['mode'] = 'wb'
		else:
			kwargs['mode'] = 'w'
			kwargs['encoding'] = _encodings['repo.content']
		write_atomic(os.path.join(self.dbdir, fname), data, **kwargs)

	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return []
		with io.open(_unicode_encode(
			os.path.join(self.dbdir, ename),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace'
			) as f:
			mylines = f.readlines()
		myreturn = []
		for x in mylines:
			for y in x[:-1].split():
				myreturn.append(y)
		return myreturn

	def setelements(self,mylist,ename):
		with io.open(_unicode_encode(
			os.path.join(self.dbdir, ename),
			encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace') as f:
			for x in mylist:
				f.write("%s\n" % x)

	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(os.path.join(self.dbdir, "CATEGORY"))

	def _pre_merge_backup(self, backup_dblink, downgrade):

		if ("unmerge-backup" in self.settings.features or
			(downgrade and "downgrade-backup" in self.settings.features)):
			return self._quickpkg_dblink(backup_dblink, False, None)

		return os.EX_OK

	def _pre_unmerge_backup(self, background):

		if "unmerge-backup" in self.settings.features :
			logfile = None
			if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
				logfile = self.settings.get("PORTAGE_LOG_FILE")
			return self._quickpkg_dblink(self, background, logfile)

		return os.EX_OK

	def _quickpkg_dblink(self, backup_dblink, background, logfile):

		build_time = backup_dblink.getfile('BUILD_TIME')
		try:
			build_time = int(build_time.strip())
		except ValueError:
			build_time = 0

		trees = QueryCommand.get_db()[self.settings["EROOT"]]
		bintree = trees["bintree"]

		for binpkg in reversed(
			bintree.dbapi.match('={}'.format(backup_dblink.mycpv))):
			if binpkg.build_time == build_time:
				return os.EX_OK

		self.lockdb()
		try:

			if not backup_dblink.exists():
				# It got unmerged by a concurrent process.
				return os.EX_OK

			# Call quickpkg for support of QUICKPKG_DEFAULT_OPTS and stuff.
			quickpkg_binary = os.path.join(self.settings["PORTAGE_BIN_PATH"],
				"quickpkg")

			if not os.access(quickpkg_binary, os.X_OK):
				# If not running from the source tree, use PATH.
				quickpkg_binary = find_binary("quickpkg")
				if quickpkg_binary is None:
					self._display_merge(
						_("%s: command not found") % "quickpkg",
						level=logging.ERROR, noiselevel=-1)
					return 127

			# Let quickpkg inherit the global vartree config's env.
			env = dict(self.vartree.settings.items())
			env["__PORTAGE_INHERIT_VARDB_LOCK"] = "1"

			pythonpath = [x for x in env.get('PYTHONPATH', '').split(":") if x]
			if not pythonpath or \
				not os.path.samefile(pythonpath[0], portage._pym_path):
				pythonpath.insert(0, portage._pym_path)
			env['PYTHONPATH'] = ":".join(pythonpath)

			quickpkg_proc = SpawnProcess(
				args=[portage._python_interpreter, quickpkg_binary,
					"=%s" % (backup_dblink.mycpv,)],
				background=background, env=env,
				scheduler=self._scheduler, logfile=logfile)
			quickpkg_proc.start()

			return quickpkg_proc.wait()

		finally:
			self.unlockdb()

def merge(mycat, mypkg, pkgloc, infloc,
	myroot=None, settings=None, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None, blockers=None,
	scheduler=None, fd_pipes=None):
	"""
	@param myroot: ignored, settings['EROOT'] is used instead
	"""
	myroot = None
	if settings is None:
		raise TypeError("settings argument is required")
	if not os.access(settings['EROOT'], os.W_OK):
		writemsg(_("Permission denied: access('%s', W_OK)\n") % settings['EROOT'],
			noiselevel=-1)
		return errno.EACCES
	background = (settings.get('PORTAGE_BACKGROUND') == '1')
	merge_task = MergeProcess(
		mycat=mycat, mypkg=mypkg, settings=settings,
		treetype=mytree, vartree=vartree,
		scheduler=(scheduler or asyncio._safe_loop()),
		background=background, blockers=blockers, pkgloc=pkgloc,
		infloc=infloc, myebuild=myebuild, mydbapi=mydbapi,
		prev_mtimes=prev_mtimes, logfile=settings.get('PORTAGE_LOG_FILE'),
		fd_pipes=fd_pipes)
	merge_task.start()
	retcode = merge_task.wait()
	return retcode

def unmerge(cat, pkg, myroot=None, settings=None,
	mytrimworld=None, vartree=None,
	ldpath_mtimes=None, scheduler=None):
	"""
	@param myroot: ignored, settings['EROOT'] is used instead
	@param mytrimworld: ignored
	"""
	myroot = None
	if settings is None:
		raise TypeError("settings argument is required")
	mylink = dblink(cat, pkg, settings=settings, treetype="vartree",
		vartree=vartree, scheduler=scheduler)
	vartree = mylink.vartree
	parallel_install = "parallel-install" in settings.features
	if not parallel_install:
		mylink.lockdb()
	try:
		if mylink.exists():
			retval = mylink.unmerge(ldpath_mtimes=ldpath_mtimes)
			if retval == os.EX_OK:
				mylink.lockdb()
				try:
					mylink.delete()
				finally:
					mylink.unlockdb()
			return retval
		return os.EX_OK
	finally:
		if vartree.dbapi._linkmap is None:
			# preserve-libs is entirely disabled
			pass
		else:
			vartree.dbapi._linkmap._clear_cache()
		if not parallel_install:
			mylink.unlockdb()

def write_contents(contents, root, f):
	"""
	Write contents to any file like object. The file will be left open.
	"""
	root_len = len(root) - 1
	for filename in sorted(contents):
		entry_data = contents[filename]
		entry_type = entry_data[0]
		relative_filename = filename[root_len:]
		if entry_type == "obj":
			entry_type, mtime, md5sum = entry_data
			line = "%s %s %s %s\n" % \
				(entry_type, relative_filename, md5sum, mtime)
		elif entry_type == "sym":
			entry_type, mtime, link = entry_data
			line = "%s %s -> %s %s\n" % \
				(entry_type, relative_filename, link, mtime)
		else: # dir, dev, fif
			line = "%s %s\n" % (entry_type, relative_filename)
		f.write(line)

def tar_contents(contents, root, tar, protect=None, onProgress=None,
	xattrs=False):
	os = _os_merge
	encoding = _encodings['merge']

	try:
		for x in contents:
			_unicode_encode(x,
				encoding=_encodings['merge'],
				errors='strict')
	except UnicodeEncodeError:
		# The package appears to have been merged with a
		# different value of sys.getfilesystemencoding(),
		# so fall back to utf_8 if appropriate.
		try:
			for x in contents:
				_unicode_encode(x,
					encoding=_encodings['fs'],
					errors='strict')
		except UnicodeEncodeError:
			pass
		else:
			os = portage.os
			encoding = _encodings['fs']

	tar.encoding = encoding
	root = normalize_path(root).rstrip(os.path.sep) + os.path.sep
	id_strings = {}
	maxval = len(contents)
	curval = 0
	if onProgress:
		onProgress(maxval, 0)
	paths = list(contents)
	paths.sort()
	for path in paths:
		curval += 1
		try:
			lst = os.lstat(path)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			if onProgress:
				onProgress(maxval, curval)
			continue
		contents_type = contents[path][0]
		if path.startswith(root):
			arcname = "./" + path[len(root):]
		else:
			raise ValueError("invalid root argument: '%s'" % root)
		live_path = path
		if 'dir' == contents_type and \
			not stat.S_ISDIR(lst.st_mode) and \
			os.path.isdir(live_path):
			# Even though this was a directory in the original ${D}, it exists
			# as a symlink to a directory in the live filesystem.  It must be
			# recorded as a real directory in the tar file to ensure that tar
			# can properly extract it's children.
			live_path = os.path.realpath(live_path)
			lst = os.lstat(live_path)

		# Since os.lstat() inside TarFile.gettarinfo() can trigger a
		# UnicodeEncodeError when python has something other than utf_8
		# return from sys.getfilesystemencoding() (as in bug #388773),
		# we implement the needed functionality here, using the result
		# of our successful lstat call. An alternative to this would be
		# to pass in the fileobj argument to TarFile.gettarinfo(), so
		# that it could use fstat instead of lstat. However, that would
		# have the unwanted effect of dereferencing symlinks.

		tarinfo = tar.tarinfo()
		tarinfo.name = arcname
		tarinfo.mode = lst.st_mode
		tarinfo.uid = lst.st_uid
		tarinfo.gid = lst.st_gid
		tarinfo.size = 0
		tarinfo.mtime = lst.st_mtime
		tarinfo.linkname = ""
		if stat.S_ISREG(lst.st_mode):
			inode = (lst.st_ino, lst.st_dev)
			if (lst.st_nlink > 1 and
				inode in tar.inodes and
				arcname != tar.inodes[inode]):
				tarinfo.type = tarfile.LNKTYPE
				tarinfo.linkname = tar.inodes[inode]
			else:
				tar.inodes[inode] = arcname
				tarinfo.type = tarfile.REGTYPE
				tarinfo.size = lst.st_size
		elif stat.S_ISDIR(lst.st_mode):
			tarinfo.type = tarfile.DIRTYPE
		elif stat.S_ISLNK(lst.st_mode):
			tarinfo.type = tarfile.SYMTYPE
			tarinfo.linkname = os.readlink(live_path)
		else:
			continue
		try:
			tarinfo.uname = pwd.getpwuid(tarinfo.uid)[0]
		except KeyError:
			pass
		try:
			tarinfo.gname = grp.getgrgid(tarinfo.gid)[0]
		except KeyError:
			pass

		if stat.S_ISREG(lst.st_mode):
			if protect and protect(path):
				# Create an empty file as a place holder in order to avoid
				# potential collision-protect issues.
				f = tempfile.TemporaryFile()
				f.write(_unicode_encode(
					"# empty file because --include-config=n " + \
					"when `quickpkg` was used\n"))
				f.flush()
				f.seek(0)
				tarinfo.size = os.fstat(f.fileno()).st_size
				tar.addfile(tarinfo, f)
				f.close()
			else:
				path_bytes = _unicode_encode(path,
					encoding=encoding,
					errors='strict')

				if xattrs:
					# Compatible with GNU tar, which saves the xattrs
					# under the SCHILY.xattr namespace.
					for k in xattr.list(path_bytes):
						tarinfo.pax_headers['SCHILY.xattr.' +
							_unicode_decode(k)] = _unicode_decode(
							xattr.get(path_bytes, _unicode_encode(k)))

				with open(path_bytes, 'rb') as f:
					tar.addfile(tarinfo, f)

		else:
			tar.addfile(tarinfo)
		if onProgress:
			onProgress(maxval, curval)
