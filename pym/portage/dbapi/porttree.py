# Copyright 1998-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

__all__ = [
	"close_portdbapi_caches", "FetchlistDict", "portagetree", "portdbapi"
]

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.checksum',
	'portage.data:portage_gid,secpass',
	'portage.dbapi.dep_expand:dep_expand',
	'portage.dep:Atom,dep_getkey,match_from_list,use_reduce,_match_slot',
	'portage.package.ebuild.doebuild:doebuild',
	'portage.util:ensure_dirs,shlex_split,writemsg,writemsg_level',
	'portage.util.listdir:listdir',
	'portage.versions:best,catsplit,catpkgsplit,_pkgsplit@pkgsplit,ver_regexp,_pkg_str',
)

from portage.cache import volatile
from portage.cache.cache_errors import CacheError
from portage.cache.mappings import Mapping
from portage.dbapi import dbapi
from portage.exception import PortageException, PortageKeyError, \
	FileNotFound, InvalidAtom, InvalidData, \
	InvalidDependString, InvalidPackageName
from portage.localization import _

from portage import eclass_cache, \
	eapi_is_supported, \
	_eapi_is_deprecated
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import OrderedDict
from portage.util._eventloop.EventLoop import EventLoop
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.EbuildMetadataPhase import EbuildMetadataPhase

import os as _os
import sys
import traceback
import warnings
import errno
import collections
import functools

try:
	from urllib.parse import urlparse
except ImportError:
	from urlparse import urlparse

if sys.hexversion >= 0x3000000:
	# pylint: disable=W0622
	basestring = str
	long = int

def close_portdbapi_caches():
	# The python interpreter does _not_ guarantee that destructors are
	# called for objects that remain when the interpreter exits, so we
	# use an atexit hook to call destructors for any global portdbapi
	# instances that may have been constructed.
	try:
		portage._legacy_globals_constructed
	except AttributeError:
		pass
	else:
		if "db" in portage._legacy_globals_constructed:
			try:
				db = portage.db
			except AttributeError:
				pass
			else:
				if isinstance(db, dict):
					for x in db.values():
						try:
							if "porttree" in x.lazy_items:
								continue
						except (AttributeError, TypeError):
							continue
						try:
							x = x.pop("porttree").dbapi
						except (AttributeError, KeyError):
							continue
						if not isinstance(x, portdbapi):
							continue
						x.close_caches()

portage.process.atexit_register(close_portdbapi_caches)

# It used to be necessary for API consumers to remove portdbapi instances
# from portdbapi_instances, in order to avoid having accumulated instances
# consume memory. Now, portdbapi_instances is just an empty dummy list, so
# for backward compatibility, ignore ValueError for removal on non-existent
# items.
class _dummy_list(list):
	def remove(self, item):
		# TODO: Trigger a DeprecationWarning here, after stable portage
		# has dummy portdbapi_instances.
		try:
			list.remove(self, item)
		except ValueError:
			pass


class _better_cache(object):

	"""
	The purpose of better_cache is to locate catpkgs in repositories using ``os.listdir()`` as much as possible, which
	is less expensive IO-wise than exhaustively doing a stat on each repo for a particular catpkg. better_cache stores a
	list of repos in which particular catpkgs appear. Various dbapi methods use better_cache to locate repositories of
	interest related to particular catpkg rather than performing an exhaustive scan of all repos/overlays.

	Better_cache.items data may look like this::

	  { "sys-apps/portage" : [ repo1, repo2 ] }

	Without better_cache, Portage will get slower and slower (due to excessive IO) as more overlays are added.

	Also note that it is OK if this cache has some 'false positive' catpkgs in it. We use it to search for specific
	catpkgs listed in ebuilds. The likelihood of a false positive catpkg in our cache causing a problem is extremely
	low, because the user of our cache is passing us a catpkg that came from somewhere and has already undergone some
	validation, and even then will further interrogate the short-list of repos we return to gather more information
	on the catpkg.

	Thus, the code below is optimized for speed rather than painstaking correctness. I have added a note to
	``dbapi.getRepositories()`` to ensure that developers are aware of this just in case.

	The better_cache has been redesigned to perform on-demand scans -- it will only scan a category at a time, as
	needed. This should further optimize IO performance by not scanning category directories that are not needed by
	Portage.
	"""

	def __init__(self, repositories):
		self._items = collections.defaultdict(list)
		self._scanned_cats = set()

		# ordered list of all portree locations we'll scan:
		self._repo_list = [repo for repo in reversed(list(repositories))
			if repo.location is not None]

	def __getitem__(self, catpkg):
		result = self._items.get(catpkg)
		if result is not None:
			return result

		cat, pkg = catsplit(catpkg)
		if cat not in self._scanned_cats:
			self._scan_cat(cat)
		return self._items[catpkg]

	def _scan_cat(self, cat):
		for repo in self._repo_list:
			cat_dir = repo.location + "/" + cat
			try:
				pkg_list = os.listdir(cat_dir)
			except OSError as e:
				if e.errno not in (errno.ENOTDIR, errno.ENOENT, errno.ESTALE):
					raise
				continue
			for p in pkg_list:
				if os.path.isdir(cat_dir + "/" + p):
					self._items[cat + "/" + p].append(repo)
		self._scanned_cats.add(cat)


class portdbapi(dbapi):
	"""this tree will scan a portage directory located at root (passed to init)"""
	portdbapi_instances = _dummy_list()
	_use_mutable = True

	@property
	def _categories(self):
		return self.settings.categories

	@property
	def porttree_root(self):
		warnings.warn("portage.dbapi.porttree.portdbapi.porttree_root is deprecated in favor of portage.repository.config.RepoConfig.location "
			"(available as repositories[repo_name].location attribute of instances of portage.dbapi.porttree.portdbapi class)",
			DeprecationWarning, stacklevel=2)
		return self.settings.repositories.mainRepoLocation()

	@property
	def eclassdb(self):
		warnings.warn("portage.dbapi.porttree.portdbapi.eclassdb is deprecated in favor of portage.repository.config.RepoConfig.eclass_db "
			"(available as repositories[repo_name].eclass_db attribute of instances of portage.dbapi.porttree.portdbapi class)",
			DeprecationWarning, stacklevel=2)
		main_repo = self.repositories.mainRepo()
		if main_repo is None:
			return None
		return main_repo.eclass_db

	def __init__(self, _unused_param=DeprecationWarning, mysettings=None):
		"""
		@param _unused_param: deprecated, use mysettings['PORTDIR'] instead
		@type _unused_param: None
		@param mysettings: an immutable config instance
		@type mysettings: portage.config
		"""

		from portage import config
		if mysettings:
			self.settings = mysettings
		else:
			from portage import settings
			self.settings = config(clone=settings)

		if _unused_param is not DeprecationWarning:
			warnings.warn("The first parameter of the " + \
				"portage.dbapi.porttree.portdbapi" + \
				" constructor is unused since portage-2.1.8. " + \
				"mysettings['PORTDIR'] is used instead.",
				DeprecationWarning, stacklevel=2)

		self.repositories = self.settings.repositories
		self.treemap = self.repositories.treemap

		# This is strictly for use in aux_get() doebuild calls when metadata
		# is generated by the depend phase.  It's safest to use a clone for
		# this purpose because doebuild makes many changes to the config
		# instance that is passed in.
		self.doebuild_settings = config(clone=self.settings)
		self.depcachedir = os.path.realpath(self.settings.depcachedir)
		
		if os.environ.get("SANDBOX_ON") == "1":
			# Make api consumers exempt from sandbox violations
			# when doing metadata cache updates.
			sandbox_write = os.environ.get("SANDBOX_WRITE", "").split(":")
			if self.depcachedir not in sandbox_write:
				sandbox_write.append(self.depcachedir)
				os.environ["SANDBOX_WRITE"] = \
					":".join(filter(None, sandbox_write))

		self.porttrees = list(self.settings.repositories.repoLocationList())

		# This is used as sanity check for aux_get(). If there is no
		# root eclass dir, we assume that PORTDIR is invalid or
		# missing. This check allows aux_get() to detect a missing
		# portage tree and return early by raising a KeyError.
		self._have_root_eclass_dir = os.path.isdir(
			os.path.join(self.settings.repositories.mainRepoLocation(), "eclass"))

		#if the portdbapi is "frozen", then we assume that we can cache everything (that no updates to it are happening)
		self.xcache = {}
		self.frozen = 0

		#Keep a list of repo names, sorted by priority (highest priority first).
		self._ordered_repo_name_list = tuple(reversed(self.repositories.prepos_order))

		self.auxdbmodule = self.settings.load_best_module("portdbapi.auxdbmodule")
		self.auxdb = {}
		self._pregen_auxdb = {}
		# If the current user doesn't have depcachedir write permission,
		# then the depcachedir cache is kept here read-only access.
		self._ro_auxdb = {}
		self._init_cache_dirs()
		try:
			depcachedir_st = os.stat(self.depcachedir)
			depcachedir_w_ok = os.access(self.depcachedir, os.W_OK)
		except OSError:
			depcachedir_st = None
			depcachedir_w_ok = False

		cache_kwargs = {}

		depcachedir_unshared = False
		if portage.data.secpass < 1 and \
			depcachedir_w_ok and \
			depcachedir_st is not None and \
			os.getuid() == depcachedir_st.st_uid and \
			os.getgid() == depcachedir_st.st_gid:
			# If this user owns depcachedir and is not in the
			# portage group, then don't bother to set permissions
			# on cache entries. This makes it possible to run
			# egencache without any need to be a member of the
			# portage group.
			depcachedir_unshared = True
		else:
			cache_kwargs.update({
				'gid'     : portage_gid,
				'perms'   : 0o664
			})

		# If secpass < 1, we don't want to write to the cache
		# since then we won't be able to apply group permissions
		# to the cache entries/directories.
		if (secpass < 1 and not depcachedir_unshared) or not depcachedir_w_ok:
			for x in self.porttrees:
				self.auxdb[x] = volatile.database(
					self.depcachedir, x, self._known_keys,
					**cache_kwargs)
				try:
					self._ro_auxdb[x] = self.auxdbmodule(self.depcachedir, x,
						self._known_keys, readonly=True, **cache_kwargs)
				except CacheError:
					pass
		else:
			for x in self.porttrees:
				if x in self.auxdb:
					continue
				# location, label, auxdbkeys
				self.auxdb[x] = self.auxdbmodule(
					self.depcachedir, x, self._known_keys, **cache_kwargs)
		if "metadata-transfer" not in self.settings.features:
			for x in self.porttrees:
				if x in self._pregen_auxdb:
					continue
				cache = self._create_pregen_cache(x)
				if cache is not None:
					self._pregen_auxdb[x] = cache
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(
			["BDEPEND", "DEPEND", "EAPI", "HDEPEND",
			"INHERITED", "IUSE", "KEYWORDS", "LICENSE",
			"PDEPEND", "PROPERTIES", "RDEPEND", "repository",
			"RESTRICT", "SLOT", "DEFINED_PHASES", "REQUIRED_USE"])

		self._aux_cache = {}
		self._better_cache = None
		self._broken_ebuilds = set()

	@property
	def _event_loop(self):
		if portage._internal_caller:
			# For internal portage usage, the global_event_loop is safe.
			return global_event_loop()
		else:
			# For external API consumers, use a local EventLoop, since
			# we don't want to assume that it's safe to override the
			# global SIGCHLD handler.
			return EventLoop(main=False)

	def _create_pregen_cache(self, tree):
		conf = self.repositories.get_repo_for_location(tree)
		cache = conf.get_pregenerated_cache(
			self._known_keys, readonly=True)
		if cache is not None:
			try:
				cache.ec = self.repositories.get_repo_for_location(tree).eclass_db
			except AttributeError:
				pass

			if not cache.complete_eclass_entries:
				warnings.warn(
					("Repository '%s' used deprecated 'pms' cache format. "
					"Please migrate to 'md5-dict' format.") % (conf.name,),
					DeprecationWarning)

		return cache

	def _init_cache_dirs(self):
		"""Create /var/cache/edb/dep and adjust permissions for the portage
		group."""

		dirmode  = 0o2070
		modemask =    0o2

		try:
			ensure_dirs(self.depcachedir, gid=portage_gid,
				mode=dirmode, mask=modemask)
		except PortageException:
			pass

	def close_caches(self):
		if not hasattr(self, "auxdb"):
			# unhandled exception thrown from constructor
			return
		for x in self.auxdb:
			self.auxdb[x].sync()
		self.auxdb.clear()

	def flush_cache(self):
		for x in self.auxdb.values():
			x.sync()

	def findLicensePath(self, license_name):
		for x in reversed(self.porttrees):
			license_path = os.path.join(x, "licenses", license_name)
			if os.access(license_path, os.R_OK):
				return license_path
		return None

	def findname(self,mycpv, mytree = None, myrepo = None):
		return self.findname2(mycpv, mytree, myrepo)[0]

	def getRepositoryPath(self, repository_id):
		"""
		This function is required for GLEP 42 compliance; given a valid repository ID
		it must return a path to the repository
		TreeMap = { id:path }
		"""
		return self.treemap.get(repository_id)

	def getRepositoryName(self, canonical_repo_path):
		"""
		This is the inverse of getRepositoryPath().
		@param canonical_repo_path: the canonical path of a repository, as
			resolved by os.path.realpath()
		@type canonical_repo_path: String
		@return: The repo_name for the corresponding repository, or None
			if the path does not correspond a known repository
		@rtype: String or None
		"""
		try:
			return self.repositories.get_name_for_location(canonical_repo_path)
		except KeyError:
			return None

	def getRepositories(self, catpkg=None):

		"""
		With catpkg=None, this will return a complete list of repositories in this dbapi. With catpkg set to a value,
		this method will return a short-list of repositories that contain this catpkg. Use this second approach if
		possible, to avoid exhaustively searching all repos for a particular catpkg. It's faster for this method to
		find the catpkg than for you do it yourself. When specifying catpkg, you should have reasonable assurance that
		the category is valid and PMS-compliant as the caching mechanism we use does not perform validation checks for
		categories.

		This function is required for GLEP 42 compliance.

		@param catpkg: catpkg for which we want a list of repositories; we'll get a list of all repos containing this
		  catpkg; if None, return a list of all Repositories that contain a particular catpkg.
		@return: a list of repositories.
		"""

		if catpkg is not None and self._better_cache is not None:
			return [repo.name for repo in self._better_cache[catpkg]]
		return self._ordered_repo_name_list

	def getMissingRepoNames(self):
		"""
		Returns a list of repository paths that lack profiles/repo_name.
		"""
		return self.settings.repositories.missing_repo_names

	def getIgnoredRepos(self):
		"""
		Returns a list of repository paths that have been ignored, because
		another repo with the same name exists.
		"""
		return self.settings.repositories.ignored_repos

	def findname2(self, mycpv, mytree=None, myrepo=None):
		""" 
		Returns the location of the CPV, and what overlay it was in.
		Searches overlays first, then PORTDIR; this allows us to return the first
		matching file.  As opposed to starting in portdir and then doing overlays
		second, we would have to exhaustively search the overlays until we found
		the file we wanted.
		If myrepo is not None it will find packages from this repository(overlay)
		"""
		if not mycpv:
			return (None, 0)

		if myrepo is not None:
			mytree = self.treemap.get(myrepo)
			if mytree is None:
				return (None, 0)

		mysplit = mycpv.split("/")
		psplit = pkgsplit(mysplit[1])
		if psplit is None or len(mysplit) != 2:
			raise InvalidPackageName(mycpv)

		try:
			cp = mycpv.cp
		except AttributeError:
			cp = mysplit[0] + "/" + psplit[0]

		if self._better_cache is None:
			if mytree:
				mytrees = [mytree]
			else:
				mytrees = reversed(self.porttrees)
		else:
			try:
				repos = self._better_cache[cp]
			except KeyError:
				return (None, 0)

			mytrees = []
			for repo in repos:
				if mytree is not None and mytree != repo.location:
					continue
				mytrees.append(repo.location)

		# For optimal performace in this hot spot, we do manual unicode
		# handling here instead of using the wrapped os module.
		encoding = _encodings['fs']
		errors = 'strict'

		relative_path = mysplit[0] + _os.sep + psplit[0] + _os.sep + \
			mysplit[1] + ".ebuild"

		for x in mytrees:
			filename = x + _os.sep + relative_path
			if _os.access(_unicode_encode(filename,
				encoding=encoding, errors=errors), _os.R_OK):
				return (filename, x)
		return (None, 0)

	def _write_cache(self, cpv, repo_path, metadata, ebuild_hash):

		try:
			cache = self.auxdb[repo_path]
			chf = cache.validation_chf
			metadata['_%s_' % chf] = getattr(ebuild_hash, chf)
		except CacheError:
			# Normally this shouldn't happen, so we'll show
			# a traceback for debugging purposes.
			traceback.print_exc()
			cache = None

		if cache is not None:
			try:
				cache[cpv] = metadata
			except CacheError:
				# Normally this shouldn't happen, so we'll show
				# a traceback for debugging purposes.
				traceback.print_exc()

	def _pull_valid_cache(self, cpv, ebuild_path, repo_path):
		try:
			ebuild_hash = eclass_cache.hashed_path(ebuild_path)
			# snag mtime since we use it later, and to trigger stat failure
			# if it doesn't exist
			ebuild_hash.mtime
		except FileNotFound:
			writemsg(_("!!! aux_get(): ebuild for " \
				"'%s' does not exist at:\n") % (cpv,), noiselevel=-1)
			writemsg("!!!            %s\n" % ebuild_path, noiselevel=-1)
			raise PortageKeyError(cpv)

		# Pull pre-generated metadata from the metadata/cache/
		# directory if it exists and is valid, otherwise fall
		# back to the normal writable cache.
		auxdbs = []
		pregen_auxdb = self._pregen_auxdb.get(repo_path)
		if pregen_auxdb is not None:
			auxdbs.append(pregen_auxdb)
		ro_auxdb = self._ro_auxdb.get(repo_path)
		if ro_auxdb is not None:
			auxdbs.append(ro_auxdb)
		auxdbs.append(self.auxdb[repo_path])
		eclass_db = self.repositories.get_repo_for_location(repo_path).eclass_db

		for auxdb in auxdbs:
			try:
				metadata = auxdb[cpv]
			except KeyError:
				continue
			except CacheError:
				if not auxdb.readonly:
					try:
						del auxdb[cpv]
					except (KeyError, CacheError):
						pass
				continue
			eapi = metadata.get('EAPI', '').strip()
			if not eapi:
				eapi = '0'
				metadata['EAPI'] = eapi
			if not eapi_is_supported(eapi):
				# Since we're supposed to be able to efficiently obtain the
				# EAPI from _parse_eapi_ebuild_head, we disregard cache entries
				# for unsupported EAPIs.
				continue
			if auxdb.validate_entry(metadata, ebuild_hash, eclass_db):
				break
		else:
			metadata = None

		return (metadata, ebuild_hash)

	def aux_get(self, mycpv, mylist, mytree=None, myrepo=None):
		"stub code for returning auxilliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or raise PortageKeyError if error'
		# For external API consumers, self._event_loop returns a new event
		# loop on each access, so a local reference is needed in order
		# to avoid instantiating more than one.
		loop = self._event_loop
		return loop.run_until_complete(
			self.async_aux_get(mycpv, mylist, mytree=mytree,
			myrepo=myrepo, loop=loop))

	def async_aux_get(self, mycpv, mylist, mytree=None, myrepo=None, loop=None):
		"""
		Asynchronous form form of aux_get.

		@param mycpv: cpv for an ebuild
		@type mycpv: str
		@param mylist: list of metadata keys
		@type mylist: list
		@param mytree: The canonical path of the tree in which the ebuild
			is located, or None for automatic lookup
		@type mytree: str
		@param myrepo: name of the repo in which the ebuild is located,
			or None for automatic lookup
		@type myrepo: str
		@param loop: event loop (defaults to global event loop)
		@type loop: EventLoop
		@return: list of metadata values
		@rtype: asyncio.Future (or compatible)
		"""
		# Don't default to self._event_loop here, since that creates a
		# local event loop for thread safety, and that could easily lead
		# to simultaneous instantiation of multiple event loops here.
		# Callers of this method certainly want the same event loop to
		# be used for all calls.
		loop = loop or global_event_loop()
		future = loop.create_future()
		cache_me = False
		if myrepo is not None:
			mytree = self.treemap.get(myrepo)
			if mytree is None:
				future.set_exception(PortageKeyError(myrepo))
				return future

		if mytree is not None and len(self.porttrees) == 1 \
			and mytree == self.porttrees[0]:
			# mytree matches our only tree, so it's safe to
			# ignore mytree and cache the result
			mytree = None
			myrepo = None

		if mytree is None:
			cache_me = True
		if mytree is None and not self._known_keys.intersection(
			mylist).difference(self._aux_cache_keys):
			aux_cache = self._aux_cache.get(mycpv)
			if aux_cache is not None:
				future.set_result([aux_cache.get(x, "") for x in mylist])
				return future
			cache_me = True

		try:
			cat, pkg = mycpv.split("/", 1)
		except ValueError:
			# Missing slash. Can't find ebuild so raise PortageKeyError.
			future.set_exception(PortageKeyError(mycpv))
			return future

		myebuild, mylocation = self.findname2(mycpv, mytree)

		if not myebuild:
			writemsg("!!! aux_get(): %s\n" % \
				_("ebuild not found for '%s'") % mycpv, noiselevel=1)
			future.set_exception(PortageKeyError(mycpv))
			return future

		mydata, ebuild_hash = self._pull_valid_cache(mycpv, myebuild, mylocation)

		if mydata is not None:
			self._aux_get_return(
				future, mycpv, mylist, myebuild, ebuild_hash,
				mydata, mylocation, cache_me, None)
			return future

		if myebuild in self._broken_ebuilds:
			future.set_exception(PortageKeyError(mycpv))
			return future

		proc = EbuildMetadataPhase(cpv=mycpv,
			ebuild_hash=ebuild_hash, portdb=self,
			repo_path=mylocation, scheduler=loop,
			settings=self.doebuild_settings)

		proc.addExitListener(functools.partial(self._aux_get_return,
			future, mycpv, mylist, myebuild, ebuild_hash, mydata, mylocation,
			cache_me))
		future.add_done_callback(functools.partial(self._aux_get_cancel, proc))
		proc.start()
		return future

	@staticmethod
	def _aux_get_cancel(proc, future):
		if future.cancelled() and proc.returncode is None:
			proc.cancel()

	def _aux_get_return(self, future, mycpv, mylist, myebuild, ebuild_hash,
		mydata, mylocation, cache_me, proc):
		if future.cancelled():
			return
		if proc is not None:
			if proc.returncode != os.EX_OK:
				self._broken_ebuilds.add(myebuild)
				future.set_exception(PortageKeyError(mycpv))
				return
			mydata = proc.metadata
		mydata["repository"] = self.repositories.get_name_for_location(mylocation)
		mydata["_mtime_"] = ebuild_hash.mtime
		eapi = mydata.get("EAPI")
		if not eapi:
			eapi = "0"
			mydata["EAPI"] = eapi
		if eapi_is_supported(eapi):
			mydata["INHERITED"] = " ".join(mydata.get("_eclasses_", []))

		#finally, we look at our internal cache entry and return the requested data.
		returnme = [mydata.get(x, "") for x in mylist]

		if cache_me and self.frozen:
			aux_cache = {}
			for x in self._aux_cache_keys:
				aux_cache[x] = mydata.get(x, "")
			self._aux_cache[mycpv] = aux_cache

		future.set_result(returnme)

	def getFetchMap(self, mypkg, useflags=None, mytree=None):
		"""
		Get the SRC_URI metadata as a dict which maps each file name to a
		set of alternative URIs.

		@param mypkg: cpv for an ebuild
		@type mypkg: String
		@param useflags: a collection of enabled USE flags, for evaluation of
			conditionals
		@type useflags: set, or None to enable all conditionals
		@param mytree: The canonical path of the tree in which the ebuild
			is located, or None for automatic lookup
		@type mypkg: String
		@return: A dict which maps each file name to a set of alternative
			URIs.
		@rtype: dict
		"""

		try:
			eapi, myuris = self.aux_get(mypkg,
				["EAPI", "SRC_URI"], mytree=mytree)
		except KeyError:
			# Convert this to an InvalidDependString exception since callers
			# already handle it.
			raise portage.exception.InvalidDependString(
				"getFetchMap(): aux_get() error reading "+mypkg+"; aborting.")

		if not eapi_is_supported(eapi):
			# Convert this to an InvalidDependString exception
			# since callers already handle it.
			raise portage.exception.InvalidDependString(
				"getFetchMap(): '%s' has unsupported EAPI: '%s'" % \
				(mypkg, eapi))

		return _parse_uri_map(mypkg, {'EAPI':eapi,'SRC_URI':myuris},
			use=useflags)

	def getfetchsizes(self, mypkg, useflags=None, debug=0, myrepo=None):
		# returns a filename:size dictionnary of remaining downloads
		myebuild, mytree = self.findname2(mypkg, myrepo=myrepo)
		if myebuild is None:
			raise AssertionError(_("ebuild not found for '%s'") % mypkg)
		pkgdir = os.path.dirname(myebuild)
		mf = self.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(pkgdir))).load_manifest(
				pkgdir, self.settings["DISTDIR"])
		checksums = mf.getDigests()
		if not checksums:
			if debug: 
				writemsg(_("[empty/missing/bad digest]: %s\n") % (mypkg,))
			return {}
		filesdict={}
		myfiles = self.getFetchMap(mypkg, useflags=useflags, mytree=mytree)
		#XXX: maybe this should be improved: take partial downloads
		# into account? check checksums?
		for myfile in myfiles:
			try:
				fetch_size = int(checksums[myfile]["size"])
			except (KeyError, ValueError):
				if debug:
					writemsg(_("[bad digest]: missing %(file)s for %(pkg)s\n") % {"file":myfile, "pkg":mypkg})
				continue
			file_path = os.path.join(self.settings["DISTDIR"], myfile)
			mystat = None
			try:
				mystat = os.stat(file_path)
			except OSError:
				pass
			if mystat is None:
				existing_size = 0
				ro_distdirs = self.settings.get("PORTAGE_RO_DISTDIRS")
				if ro_distdirs is not None:
					for x in shlex_split(ro_distdirs):
						try:
							mystat = os.stat(os.path.join(x, myfile))
						except OSError:
							pass
						else:
							if mystat.st_size == fetch_size:
								existing_size = fetch_size
								break
			else:
				existing_size = mystat.st_size
			remaining_size = fetch_size - existing_size
			if remaining_size > 0:
				# Assume the download is resumable.
				filesdict[myfile] = remaining_size
			elif remaining_size < 0:
				# The existing file is too large and therefore corrupt.
				filesdict[myfile] = int(checksums[myfile]["size"])
		return filesdict

	def fetch_check(self, mypkg, useflags=None, mysettings=None, all=False, myrepo=None):
		"""
		TODO: account for PORTAGE_RO_DISTDIRS
		"""
		if all:
			useflags = None
		elif useflags is None:
			if mysettings:
				useflags = mysettings["USE"].split()
		if myrepo is not None:
			mytree = self.treemap.get(myrepo)
			if mytree is None:
				return False
		else:
			mytree = None

		myfiles = self.getFetchMap(mypkg, useflags=useflags, mytree=mytree)
		myebuild = self.findname(mypkg, myrepo=myrepo)
		if myebuild is None:
			raise AssertionError(_("ebuild not found for '%s'") % mypkg)
		pkgdir = os.path.dirname(myebuild)
		mf = self.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(pkgdir)))
		mf = mf.load_manifest(pkgdir, self.settings["DISTDIR"])
		mysums = mf.getDigests()

		failures = {}
		for x in myfiles:
			if not mysums or x not in mysums:
				ok     = False
				reason = _("digest missing")
			else:
				try:
					ok, reason = portage.checksum.verify_all(
						os.path.join(self.settings["DISTDIR"], x), mysums[x])
				except FileNotFound as e:
					ok = False
					reason = _("File Not Found: '%s'") % (e,)
			if not ok:
				failures[x] = reason
		if failures:
			return False
		return True

	def cpv_exists(self, mykey, myrepo=None):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		cps2 = mykey.split("/")
		cps = catpkgsplit(mykey, silent=0)
		if not cps:
			#invalid cat/pkg-v
			return 0
		if self.findname(cps[0] + "/" + cps2[1], myrepo=myrepo):
			return 1
		else:
			return 0

	def cp_all(self, categories=None, trees=None, reverse=False, sort=True):
		"""
		This returns a list of all keys in our tree or trees
		@param categories: optional list of categories to search or 
			defaults to self.settings.categories
		@param trees: optional list of trees to search the categories in or
			defaults to self.porttrees
		@param reverse: reverse sort order (default is False)
		@param sort: return sorted results (default is True)
		@rtype list of [cat/pkg,...]
		"""
		d = {}
		if categories is None:
			categories = self.settings.categories
		if trees is None:
			trees = self.porttrees
		for x in categories:
			for oroot in trees:
				for y in listdir(oroot+"/"+x, EmptyOnError=1, ignorecvs=1, dirsonly=1):
					try:
						atom = Atom("%s/%s" % (x, y))
					except InvalidAtom:
						continue
					if atom != atom.cp:
						continue
					d[atom.cp] = None
		l = list(d)
		if sort:
			l.sort(reverse=reverse)
		return l

	def cp_list(self, mycp, use_cache=1, mytree=None):
		# NOTE: Cache can be safely shared with the match cache, since the
		# match cache uses the result from dep_expand for the cache_key.
		if self.frozen and mytree is not None \
			and len(self.porttrees) == 1 \
			and mytree == self.porttrees[0]:
			# mytree matches our only tree, so it's safe to
			# ignore mytree and cache the result
			mytree = None

		if self.frozen and mytree is None:
			cachelist = self.xcache["cp-list"].get(mycp)
			if cachelist is not None:
				# Try to propagate this to the match-all cache here for
				# repoman since he uses separate match-all caches for each
				# profile (due to differences in _get_implicit_iuse).
				self.xcache["match-all"][(mycp, mycp)] = cachelist
				return cachelist[:]
		mysplit = mycp.split("/")
		invalid_category = mysplit[0] not in self._categories
		d={}
		if mytree is not None:
			if isinstance(mytree, basestring):
				mytrees = [mytree]
			else:
				# assume it's iterable
				mytrees = mytree
		elif self._better_cache is None:
			mytrees = self.porttrees
		else:
			mytrees = [repo.location for repo in self._better_cache[mycp]]
		for oroot in mytrees:
			try:
				file_list = os.listdir(os.path.join(oroot, mycp))
			except OSError:
				continue
			for x in file_list:
				pf = None
				if x[-7:] == '.ebuild':
					pf = x[:-7]

				if pf is not None:
					ps = pkgsplit(pf)
					if not ps:
						writemsg(_("\nInvalid ebuild name: %s\n") % \
							os.path.join(oroot, mycp, x), noiselevel=-1)
						continue
					if ps[0] != mysplit[1]:
						writemsg(_("\nInvalid ebuild name: %s\n") % \
							os.path.join(oroot, mycp, x), noiselevel=-1)
						continue
					ver_match = ver_regexp.match("-".join(ps[1:]))
					if ver_match is None or not ver_match.groups():
						writemsg(_("\nInvalid ebuild version: %s\n") % \
							os.path.join(oroot, mycp, x), noiselevel=-1)
						continue
					d[_pkg_str(mysplit[0]+"/"+pf)] = None
		if invalid_category and d:
			writemsg(_("\n!!! '%s' has a category that is not listed in " \
				"%setc/portage/categories\n") % \
				(mycp, self.settings["PORTAGE_CONFIGROOT"]), noiselevel=-1)
			mylist = []
		else:
			mylist = list(d)
		# Always sort in ascending order here since it's handy
		# and the result can be easily cached and reused.
		self._cpv_sort_ascending(mylist)
		if self.frozen and mytree is None:
			cachelist = mylist[:]
			self.xcache["cp-list"][mycp] = cachelist
			self.xcache["match-all"][(mycp, mycp)] = cachelist
		return mylist

	def freeze(self):
		for x in ("bestmatch-visible", "cp-list", "match-all",
			"match-all-cpv-only", "match-visible", "minimum-all",
			"minimum-all-ignore-profile", "minimum-visible"):
			self.xcache[x]={}
		self.frozen=1
		self._better_cache = _better_cache(self.repositories)

	def melt(self):
		self.xcache = {}
		self._aux_cache = {}
		self._better_cache = None
		self.frozen = 0

	def xmatch(self,level,origdep,mydep=None,mykey=None,mylist=None):
		"caching match function; very trick stuff"
		if level == "list-visible":
			level = "match-visible"
			warnings.warn("The 'list-visible' mode of "
				"portage.dbapi.porttree.portdbapi.xmatch "
				"has been renamed to match-visible",
				DeprecationWarning, stacklevel=2)

		if mydep is None:
			#this stuff only runs on first call of xmatch()
			#create mydep, mykey from origdep
			mydep = dep_expand(origdep, mydb=self, settings=self.settings)
			mykey = mydep.cp

		#if no updates are being made to the tree, we can consult our xcache...
		cache_key = None
		if self.frozen:
			cache_key = (mydep, mydep.unevaluated_atom)
			try:
				return self.xcache[level][cache_key][:]
			except KeyError:
				pass

		myval = None
		mytree = None
		if mydep.repo is not None:
			mytree = self.treemap.get(mydep.repo)
			if mytree is None:
				if level.startswith("match-"):
					myval = []
				else:
					myval = ""

		if myval is not None:
			# Unknown repo, empty result.
			pass
		elif level == "match-all-cpv-only":
			# match *all* packages, only against the cpv, in order
			# to bypass unnecessary cache access for things like IUSE
			# and SLOT.
			if mydep == mykey:
				# Share cache with match-all/cp_list when the result is the
				# same. Note that this requires that mydep.repo is None and
				# thus mytree is also None.
				level = "match-all"
				myval = self.cp_list(mykey, mytree=mytree)
			else:
				myval = match_from_list(mydep,
					self.cp_list(mykey, mytree=mytree))

		elif level in ("bestmatch-visible", "match-all",
			"match-visible", "minimum-all", "minimum-all-ignore-profile",
			"minimum-visible"):
			# Find the minimum matching visible version. This is optimized to
			# minimize the number of metadata accesses (improves performance
			# especially in cases where metadata needs to be generated).
			if mydep == mykey:
				mylist = self.cp_list(mykey, mytree=mytree)
			else:
				mylist = match_from_list(mydep,
					self.cp_list(mykey, mytree=mytree))

			ignore_profile = level in ("minimum-all-ignore-profile",)
			visibility_filter = level not in ("match-all",
				"minimum-all", "minimum-all-ignore-profile")
			single_match = level not in ("match-all", "match-visible")
			myval = []
			aux_keys = list(self._aux_cache_keys)
			if level == "bestmatch-visible":
				iterfunc = reversed
			else:
				iterfunc = iter

			if mydep.repo is not None:
				repos = [mydep.repo]
			else:
				# We iterate over self.porttrees, since it's common to
				# tweak this attribute in order to adjust match behavior.
				repos = []
				for tree in reversed(self.porttrees):
					repos.append(self.repositories.get_name_for_location(tree))

			for cpv in iterfunc(mylist):
				for repo in repos:
					try:
						metadata = dict(zip(aux_keys,
							self.aux_get(cpv, aux_keys, myrepo=repo)))
					except KeyError:
						# ebuild not in this repo, or masked by corruption
						continue

					try:
						pkg_str = _pkg_str(cpv, metadata=metadata,
							settings=self.settings)
					except InvalidData:
						continue

					if visibility_filter and not self._visible(pkg_str, metadata):
						continue

					if mydep.slot is not None and \
						not _match_slot(mydep, pkg_str):
						continue

					if mydep.unevaluated_atom.use is not None and \
						not self._match_use(mydep, pkg_str, metadata,
						ignore_profile=ignore_profile):
						continue

					myval.append(pkg_str)
					# only yield a given cpv once
					break

				if myval and single_match:
					break

			if single_match:
				if myval:
					myval = myval[0]
				else:
					myval = ""

		elif level == "bestmatch-list":
			#dep match -- find best match but restrict search to sublist
			warnings.warn("The 'bestmatch-list' mode of "
				"portage.dbapi.porttree.portdbapi.xmatch is deprecated",
				DeprecationWarning, stacklevel=2)
			myval = best(list(self._iter_match(mydep, mylist)))
		elif level == "match-list":
			#dep match -- find all matches but restrict search to sublist (used in 2nd half of visible())
			warnings.warn("The 'match-list' mode of "
				"portage.dbapi.porttree.portdbapi.xmatch is deprecated",
				DeprecationWarning, stacklevel=2)
			myval = list(self._iter_match(mydep, mylist))
		else:
			raise AssertionError(
				"Invalid level argument: '%s'" % level)

		if self.frozen:
			xcache_this_level = self.xcache.get(level)
			if xcache_this_level is not None:
				xcache_this_level[cache_key] = myval
				if not isinstance(myval, _pkg_str):
					myval = myval[:]

		return myval

	def match(self, mydep, use_cache=1):
		return self.xmatch("match-visible", mydep)

	def gvisible(self, mylist):
		warnings.warn("The 'gvisible' method of "
			"portage.dbapi.porttree.portdbapi "
			"is deprecated",
			DeprecationWarning, stacklevel=2)
		return list(self._iter_visible(iter(mylist)))

	def visible(self, cpv_iter):
		warnings.warn("The 'visible' method of "
			"portage.dbapi.porttree.portdbapi "
			"is deprecated",
			DeprecationWarning, stacklevel=2)
		if cpv_iter is None:
			return []
		return list(self._iter_visible(iter(cpv_iter)))

	def _iter_visible(self, cpv_iter, myrepo=None):
		"""
		Return a new list containing only visible packages.
		"""
		aux_keys = list(self._aux_cache_keys)
		metadata = {}

		if myrepo is not None:
			repos = [myrepo]
		else:
			# We iterate over self.porttrees, since it's common to
			# tweak this attribute in order to adjust match behavior.
			repos = []
			for tree in reversed(self.porttrees):
				repos.append(self.repositories.get_name_for_location(tree))

		for mycpv in cpv_iter:
			for repo in repos:
				metadata.clear()
				try:
					metadata.update(zip(aux_keys,
						self.aux_get(mycpv, aux_keys, myrepo=repo)))
				except KeyError:
					continue
				except PortageException as e:
					writemsg("!!! Error: aux_get('%s', %s)\n" %
						(mycpv, aux_keys), noiselevel=-1)
					writemsg("!!! %s\n" % (e,), noiselevel=-1)
					del e
					continue

				if not self._visible(mycpv, metadata):
					continue

				yield mycpv
				# only yield a given cpv once
				break

	def _visible(self, cpv, metadata):
		eapi = metadata["EAPI"]
		if not eapi_is_supported(eapi):
			return False
		if _eapi_is_deprecated(eapi):
			return False
		if not metadata["SLOT"]:
			return False

		settings = self.settings
		if settings._getMaskAtom(cpv, metadata):
			return False
		if settings._getMissingKeywords(cpv, metadata):
			return False
		if settings.local_config:
			metadata['CHOST'] = settings.get('CHOST', '')
			if not settings._accept_chost(cpv, metadata):
				return False
			metadata["USE"] = ""
			if "?" in metadata["LICENSE"] or \
				"?" in metadata["PROPERTIES"]:
				self.doebuild_settings.setcpv(cpv, mydb=metadata)
				metadata['USE'] = self.doebuild_settings['PORTAGE_USE']
			try:
				if settings._getMissingLicenses(cpv, metadata):
					return False
				if settings._getMissingProperties(cpv, metadata):
					return False
				if settings._getMissingRestrict(cpv, metadata):
					return False
			except InvalidDependString:
				return False

		return True

class portagetree(object):
	def __init__(self, root=DeprecationWarning, virtual=DeprecationWarning,
		settings=None):
		"""
		Constructor for a PortageTree
		
		@param root: deprecated, defaults to settings['ROOT']
		@type root: String/Path
		@param virtual: UNUSED
		@type virtual: No Idea
		@param settings: Portage Configuration object (portage.settings)
		@type settings: Instance of portage.config
		"""

		if settings is None:
			settings = portage.settings
		self.settings = settings

		if root is not DeprecationWarning:
			warnings.warn("The root parameter of the " + \
				"portage.dbapi.porttree.portagetree" + \
				" constructor is now unused. Use " + \
				"settings['ROOT'] instead.",
				DeprecationWarning, stacklevel=2)

		if virtual is not DeprecationWarning:
			warnings.warn("The 'virtual' parameter of the "
				"portage.dbapi.porttree.portagetree"
				" constructor is unused",
				DeprecationWarning, stacklevel=2)

		self.portroot = settings["PORTDIR"]
		self.__virtual = virtual
		self.dbapi = portdbapi(mysettings=settings)

	@property
	def root(self):
		warnings.warn("The root attribute of " + \
			"portage.dbapi.porttree.portagetree" + \
			" is deprecated. Use " + \
			"settings['ROOT'] instead.",
			DeprecationWarning, stacklevel=3)
		return self.settings['ROOT']

	@property
	def virtual(self):
		warnings.warn("The 'virtual' attribute of " + \
			"portage.dbapi.porttree.portagetree" + \
			" is deprecated.",
			DeprecationWarning, stacklevel=3)
		return self.__virtual

	def dep_bestmatch(self,mydep):
		"compatibility method"
		mymatch = self.dbapi.xmatch("bestmatch-visible",mydep)
		if mymatch is None:
			return ""
		return mymatch

	def dep_match(self,mydep):
		"compatibility method"
		mymatch = self.dbapi.xmatch("match-visible",mydep)
		if mymatch is None:
			return []
		return mymatch

	def exists_specific(self,cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def getname(self, pkgname):
		"returns file location for this particular package (DEPRECATED)"
		if not pkgname:
			return ""
		mysplit = pkgname.split("/")
		psplit = pkgsplit(mysplit[1])
		return "/".join([self.portroot, mysplit[0], psplit[0], mysplit[1]])+".ebuild"

	def getslot(self,mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		myslot = ""
		try:
			myslot = self.dbapi._pkg_str(mycatpkg, None).slot
		except KeyError:
			pass
		return myslot

class FetchlistDict(Mapping):
	"""
	This provide a mapping interface to retrieve fetch lists. It's used
	to allow portage.manifest.Manifest to access fetch lists via a standard
	mapping interface rather than use the dbapi directly.
	"""
	def __init__(self, pkgdir, settings, mydbapi):
		"""pkgdir is a directory containing ebuilds and settings is passed into
		portdbapi.getfetchlist for __getitem__ calls."""
		self.pkgdir = pkgdir
		self.cp = os.sep.join(pkgdir.split(os.sep)[-2:])
		self.settings = settings
		self.mytree = os.path.realpath(os.path.dirname(os.path.dirname(pkgdir)))
		self.portdb = mydbapi

	def __getitem__(self, pkg_key):
		"""Returns the complete fetch list for a given package."""
		return list(self.portdb.getFetchMap(pkg_key, mytree=self.mytree))

	def __contains__(self, cpv):
		return cpv in self.__iter__()

	def has_key(self, pkg_key):
		"""Returns true if the given package exists within pkgdir."""
		warnings.warn("portage.dbapi.porttree.FetchlistDict.has_key() is "
			"deprecated, use the 'in' operator instead",
			DeprecationWarning, stacklevel=2)
		return pkg_key in self

	def __iter__(self):
		return iter(self.portdb.cp_list(self.cp, mytree=self.mytree))

	def __len__(self):
		"""This needs to be implemented in order to avoid
		infinite recursion in some cases."""
		return len(self.portdb.cp_list(self.cp, mytree=self.mytree))

	def keys(self):
		"""Returns keys for all packages within pkgdir"""
		return self.portdb.cp_list(self.cp, mytree=self.mytree)

	if sys.hexversion >= 0x3000000:
		keys = __iter__

def _parse_uri_map(cpv, metadata, use=None):

	myuris = use_reduce(metadata.get('SRC_URI', ''),
		uselist=use, matchall=(use is None),
		is_src_uri=True,
		eapi=metadata['EAPI'])

	uri_map = OrderedDict()

	myuris.reverse()
	while myuris:
		uri = myuris.pop()
		if myuris and myuris[-1] == "->":
			myuris.pop()
			distfile = myuris.pop()
		else:
			distfile = os.path.basename(uri)
			if not distfile:
				raise portage.exception.InvalidDependString(
					("getFetchMap(): '%s' SRC_URI has no file " + \
					"name: '%s'") % (cpv, uri))

		uri_set = uri_map.get(distfile)
		if uri_set is None:
			# Use OrderedDict to preserve order from SRC_URI
			# while ensuring uniqueness.
			uri_set = OrderedDict()
			uri_map[distfile] = uri_set

		# SRC_URI may contain a file name with no scheme, and in
		# this case it does not belong in uri_set.
		if urlparse(uri).scheme:
			uri_set[uri] = True

	# Convert OrderedDicts to tuples.
	for k, v in uri_map.items():
		uri_map[k] = tuple(v)

	return uri_map
