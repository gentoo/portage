# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

import portage
from portage import os
from _emerge.Package import Package
from _emerge.PackageVirtualDbapi import PackageVirtualDbapi
from portage.const import VDB_PATH
from portage.dbapi.vartree import vartree
from portage.update import grab_updates, parse_updates, update_dbentries

if sys.hexversion >= 0x3000000:
	long = int

class FakeVardbapi(PackageVirtualDbapi):
	"""
	Implements the vardbapi.getpath() method which is used in error handling
	code for the Package class and vartree.get_provide().
	"""
	def getpath(self, cpv, filename=None):
		path = os.path.join(self.settings['EROOT'], VDB_PATH, cpv)
		if filename is not None:
			path =os.path.join(path, filename)
		return path

class FakeVartree(vartree):
	"""This is implements an in-memory copy of a vartree instance that provides
	all the interfaces required for use by the depgraph.  The vardb is locked
	during the constructor call just long enough to read a copy of the
	installed package information.  This allows the depgraph to do it's
	dependency calculations without holding a lock on the vardb.  It also
	allows things like vardb global updates to be done in memory so that the
	user doesn't necessarily need write access to the vardb in cases where
	global updates are necessary (updates are performed when necessary if there
	is not a matching ebuild in the tree). Instances of this class are not
	populated until the sync() method is called."""
	def __init__(self, root_config, pkg_cache=None, pkg_root_config=None):
		self._root_config = root_config
		if pkg_root_config is None:
			pkg_root_config = self._root_config
		self._pkg_root_config = pkg_root_config
		if pkg_cache is None:
			pkg_cache = {}
		real_vartree = root_config.trees["vartree"]
		self._real_vardb = real_vartree.dbapi
		portdb = root_config.trees["porttree"].dbapi
		self.root = real_vartree.root
		self.settings = real_vartree.settings
		mykeys = list(real_vartree.dbapi._aux_cache_keys)
		if "_mtime_" not in mykeys:
			mykeys.append("_mtime_")
		self._db_keys = mykeys
		self._pkg_cache = pkg_cache
		self.dbapi = FakeVardbapi(real_vartree.settings)

		# Initialize variables needed for lazy cache pulls of the live ebuild
		# metadata.  This ensures that the vardb lock is released ASAP, without
		# being delayed in case cache generation is triggered.
		self._aux_get = self.dbapi.aux_get
		self.dbapi.aux_get = self._aux_get_wrapper
		self._match = self.dbapi.match
		self.dbapi.match = self._match_wrapper
		self._aux_get_history = set()
		self._portdb_keys = ["EAPI", "DEPEND", "RDEPEND", "PDEPEND"]
		self._portdb = portdb
		self._global_updates = None

	def _match_wrapper(self, cpv, use_cache=1):
		"""
		Make sure the metadata in Package instances gets updated for any
		cpv that is returned from a match() call, since the metadata can
		be accessed directly from the Package instance instead of via
		aux_get().
		"""
		matches = self._match(cpv, use_cache=use_cache)
		for cpv in matches:
			if cpv in self._aux_get_history:
				continue
			self._aux_get_wrapper(cpv, [])
		return matches

	def _aux_get_wrapper(self, pkg, wants):
		if pkg in self._aux_get_history:
			return self._aux_get(pkg, wants)
		self._aux_get_history.add(pkg)
		try:
			# Use the live ebuild metadata if possible.
			live_metadata = dict(zip(self._portdb_keys,
				self._portdb.aux_get(pkg, self._portdb_keys)))
			if not portage.eapi_is_supported(live_metadata["EAPI"]):
				raise KeyError(pkg)
			self.dbapi.aux_update(pkg, live_metadata)
		except (KeyError, portage.exception.PortageException):
			if self._global_updates is None:
				self._global_updates = \
					grab_global_updates(self._portdb)
			perform_global_updates(
				pkg, self.dbapi, self._global_updates)
		return self._aux_get(pkg, wants)

	def cpv_discard(self, pkg):
		"""
		Discard a package from the fake vardb if it exists.
		"""
		old_pkg = self.dbapi.get(pkg)
		if old_pkg is not None:
			self.dbapi.cpv_remove(old_pkg)
			self._pkg_cache.pop(old_pkg, None)
			self._aux_get_history.discard(old_pkg.cpv)

	def sync(self, acquire_lock=1):
		"""
		Call this method to synchronize state with the real vardb
		after one or more packages may have been installed or
		uninstalled.
		"""
		vdb_path = os.path.join(self.settings['EROOT'], portage.VDB_PATH)
		try:
			# At least the parent needs to exist for the lock file.
			portage.util.ensure_dirs(vdb_path)
		except portage.exception.PortageException:
			pass
		vdb_lock = None
		try:
			if acquire_lock and os.access(vdb_path, os.W_OK):
				vdb_lock = portage.locks.lockdir(vdb_path)
			self._sync()
		finally:
			if vdb_lock:
				portage.locks.unlockdir(vdb_lock)

		# Populate the old-style virtuals using the cached values.
		# Skip the aux_get wrapper here, to avoid unwanted
		# cache generation.
		try:
			self.dbapi.aux_get = self._aux_get
			self.settings._populate_treeVirtuals_if_needed(self)
		finally:
			self.dbapi.aux_get = self._aux_get_wrapper

	def _sync(self):

		real_vardb = self._root_config.trees["vartree"].dbapi
		current_cpv_set = frozenset(real_vardb.cpv_all())
		pkg_vardb = self.dbapi
		pkg_cache = self._pkg_cache
		aux_get_history = self._aux_get_history

		# Remove any packages that have been uninstalled.
		for pkg in list(pkg_vardb):
			if pkg.cpv not in current_cpv_set:
				self.cpv_discard(pkg)

		# Validate counters and timestamps.
		slot_counters = {}
		root = self.root
		validation_keys = ["COUNTER", "_mtime_"]
		for cpv in current_cpv_set:

			pkg_hash_key = ("installed", root, cpv, "nomerge")
			pkg = pkg_vardb.get(pkg_hash_key)
			if pkg is not None:
				counter, mtime = real_vardb.aux_get(cpv, validation_keys)
				try:
					counter = long(counter)
				except ValueError:
					counter = 0

				if counter != pkg.counter or \
					mtime != pkg.mtime:
					self.cpv_discard(pkg)
					pkg = None

			if pkg is None:
				pkg = self._pkg(cpv)

			other_counter = slot_counters.get(pkg.slot_atom)
			if other_counter is not None:
				if other_counter > pkg.counter:
					continue

			slot_counters[pkg.slot_atom] = pkg.counter
			pkg_vardb.cpv_inject(pkg)

		real_vardb.flush_cache()

	def _pkg(self, cpv):
		"""
		The RootConfig instance that will become the Package.root_config
		attribute can be overridden by the FakeVartree pkg_root_config
		constructory argument, since we want to be consistent with the
		depgraph._pkg() method which uses a specially optimized
		RootConfig that has a FakeVartree instead of a real vartree.
		"""
		pkg = Package(cpv=cpv, built=True, installed=True,
			metadata=zip(self._db_keys,
			self._real_vardb.aux_get(cpv, self._db_keys)),
			root_config=self._pkg_root_config,
			type_name="installed")

		try:
			mycounter = long(pkg.metadata["COUNTER"])
		except ValueError:
			mycounter = 0
			pkg.metadata["COUNTER"] = str(mycounter)

		self._pkg_cache[pkg] = pkg
		return pkg

def grab_global_updates(portdb):
	retupdates = {}

	for repo_name in portdb.getRepositories():
		repo = portdb.getRepositoryPath(repo_name)
		updpath = os.path.join(repo, "profiles", "updates")
		if not os.path.isdir(updpath):
			continue

		try:
			rawupdates = grab_updates(updpath)
		except portage.exception.DirectoryNotFound:
			rawupdates = []
		upd_commands = []
		for mykey, mystat, mycontent in rawupdates:
			commands, errors = parse_updates(mycontent)
			upd_commands.extend(commands)
		retupdates[repo_name] = upd_commands

	master_repo = portdb.getRepositoryName(portdb.porttree_root)
	if master_repo in retupdates:
		retupdates['DEFAULT'] = retupdates[master_repo]

	return retupdates

def perform_global_updates(mycpv, mydb, myupdates):
	aux_keys = ["DEPEND", "RDEPEND", "PDEPEND", 'repository']
	aux_dict = dict(zip(aux_keys, mydb.aux_get(mycpv, aux_keys)))
	repository = aux_dict.pop('repository')
	try:
		mycommands = myupdates[repository]
	except KeyError:
		try:
			mycommands = myupdates['DEFAULT']
		except KeyError:
			return

	if not mycommands:
		return

	updates = update_dbentries(mycommands, aux_dict)
	if updates:
		mydb.aux_update(mycpv, updates)
