from portage.checksum import perform_md5
from portage.const import CACHE_PATH, CONFIG_MEMORY_FILE, PORTAGE_BIN_PATH, \
	PRIVATE_PATH, VDB_PATH
from portage.data import portage_gid, portage_uid, secpass
from portage.dbapi import dbapi
from portage.dep import dep_getslot, use_reduce, paren_reduce, isvalidatom, \
	isjustname, dep_getkey, match_from_list
from portage.elog import elog_process
from portage.exception import InvalidPackageName, InvalidAtom, \
	UnsupportedAPIException, FileNotFound
from portage.locks import lockdir, unlockdir
from portage.output import bold, red, green
from portage.update import fixdbentries
from portage.util import apply_secpass_permissions, ConfigProtect, ensure_dirs, \
	writemsg, writemsg_stdout, write_atomic, atomic_ofstream, writedict, \
	grabfile, grabdict, normalize_path, new_protect_filename
from portage.versions import pkgsplit, catpkgsplit, catsplit, best, pkgcmp

from portage import listdir, dep_expand, config, flatten, key_expand, \
	doebuild_environment, doebuild, env_update, dircache, \
	abssymlink, movefile, bsd_chflags

import os, sys, stat, errno, commands, copy, time
from itertools import izip

try:
	import cPickle
except ImportError:
	import pickle as cPickle

class PreservedLibsRegistry(object):
	""" This class handles the tracking of preserved library objects """
	def __init__(self, filename, autocommit=True):
		""" @param filename: absolute path for saving the preserved libs records
		    @type filename: String
			@param autocommit: determines if the file is written after every update
			@type autocommit: Boolean
		"""
		self._filename = filename
		self._autocommit = autocommit
		self.load()
	
	def load(self):
		""" Reload the registry data from file """
		try:
			self._data = cPickle.load(open(self._filename, "r"))
		except IOError, e:
			if e.errno == errno.ENOENT:
				self._data = {}
			else:
				raise e
		
	def store(self):
		""" Store the registry data to file. No need to call this if autocommit
		    was enabled.
		"""
		cPickle.dump(self._data, open(self._filename, "w"))
	
	def register(self, cpv, slot, counter, paths):
		""" Register new objects in the registry. If there is a record with the
			same packagename (internally derived from cpv) and slot it is 
			overwritten with the new data.
			@param cpv: package instance that owns the objects
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
			@param counter: vdb counter value for the package instace
			@type counter: Integer
			@param paths: absolute paths of objects that got preserved during an update
			@type paths: List
		"""
		cp = "/".join(catpkgsplit(cpv)[:2])
		cps = cp+":"+slot
		if len(paths) == 0 and self._data.has_key(cps) \
				and self._data[cps][0] == cpv and int(self._data[cps][1]) == int(counter):
			del self._data[cps]
		elif len(paths) > 0:
			self._data[cps] = (cpv, counter, paths)
		if self._autocommit:
			self.store()
	
	def unregister(self, cpv, slot, counter):
		""" Remove a previous registration of preserved objects for the given package.
			@param cpv: package instance whose records should be removed
			@type cpv: CPV (as String)
			@param slot: the value of SLOT of the given package instance
			@type slot: String
		"""
		self.register(cpv, slot, counter, [])
	
	def pruneNonExisting(self):
		""" Remove all records for objects that no longer exist on the filesystem. """
		for cps in self._data.keys():
			cpv, counter, paths = self._data[cps]
			paths = [f for f in paths if os.path.exists(f)]
			if len(paths) > 0:
				self._data[cps] = (cpv, counter, paths)
			else:
				del self._data[cps]
		if self._autocommit:
			self.store()
	
	def hasEntries(self):
		""" Check if this registry contains any records. """
		return (len(self._data.keys()) > 0)
	
	def getPreservedLibs(self):
		""" Return a mapping of packages->preserved objects.
			@returns mapping of package instances to preserved objects
			@rtype Dict cpv->list-of-paths
		"""
		rValue = {}
		for cps in self._data.keys():
			rValue[self._data[cps][0]] = self._data[cps][2]
		return rValue

class LibraryPackageMap(object):
	""" This class provides a library->consumer mapping generated from VDB data """
	def __init__(self, filename, vardbapi):
		self._filename = filename
		self._dbapi = vardbapi

	def get(self):
		""" Read the global library->consumer map for the given vdb instance.
		    @returns mapping of library objects (just basenames) to consumers (absolute paths)
			@rtype filename->list-of-paths
		"""
		if not os.path.exists(self._filename):
			self.update()
		rValue = {}
		for l in open(self._filename, "r").read().split("\n"):
			mysplit = l.split()
			if len(mysplit) > 1:
				rValue[mysplit[0]] = mysplit[1].split(",")
		return rValue

	def update(self):
		""" Update the global library->consumer map for the given vdb instance. """
		obj_dict = {}
		for cpv in self._dbapi.cpv_all():
			needed_list = self._dbapi.aux_get(cpv, ["NEEDED"])[0]
			for l in needed_list.split("\n"):
				mysplit = l.split()
				if len(mysplit) < 2:
					continue
				libs = mysplit[1].split(",")
				for lib in libs:
					if not obj_dict.has_key(lib):
						obj_dict[lib] = [mysplit[0]]
					else:
						obj_dict[lib].append(mysplit[0])
		mapfile = open(self._filename, "w")
		for lib in obj_dict.keys():
			mapfile.write(lib+" "+",".join(obj_dict[lib])+"\n")
		mapfile.close()

class vardbapi(dbapi):
	def __init__(self, root, categories=None, settings=None, vartree=None):
		self.root = root[:]

		#cache for category directory mtimes
		self.mtdircache = {}

		#cache for dependency checks
		self.matchcache = {}

		#cache for cp_list results
		self.cpcache = {}

		self.blockers = None
		if settings is None:
			from portage import settings
		self.settings = settings
		if categories is None:
			categories = settings.categories
		self.categories = categories[:]
		if vartree is None:
			from portage import db
			vartree = db[root]["vartree"]
		self.vartree = vartree
		self._aux_cache_keys = set(["SLOT", "COUNTER", "PROVIDE", "USE",
			"IUSE", "DEPEND", "RDEPEND", "PDEPEND", "NEEDED"])
		self._aux_cache = None
		self._aux_cache_version = "1"
		self._aux_cache_filename = os.path.join(self.root,
			CACHE_PATH.lstrip(os.path.sep), "vdb_metadata.pickle")

		self.libmap = LibraryPackageMap(os.path.join(self.root, CACHE_PATH, "library_consumers"), self)
		self.plib_registry = PreservedLibsRegistry(os.path.join(self.root, CACHE_PATH, "preserved_libs_registry"))

	def getpath(self, mykey, filename=None):
		rValue = os.path.join(self.root, VDB_PATH, mykey)
		if filename != None:
			rValue = os.path.join(rValue, filename)
		return rValue

	def cpv_exists(self, mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.getpath(mykey))

	def cpv_counter(self, mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		try:
			return long(self.aux_get(mycpv, ["COUNTER"])[0])
		except (KeyError, ValueError):
			pass
		cdir = self.getpath(mycpv)
		cpath = self.getpath(mycpv, filename="COUNTER")

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption on XFS (unexpected reboot.)
		corrupted = 0
		if os.path.exists(cpath):
			cfile = open(cpath, "r")
			try:
				counter = long(cfile.readline())
			except ValueError:
				print "portage: COUNTER for", mycpv, "was corrupted; resetting to value of 0"
				counter = long(0)
				corrupted = 1
			cfile.close()
		elif os.path.exists(cdir):
			mys = pkgsplit(mycpv)
			myl = self.match(mys[0], use_cache=0)
			print mys, myl
			if len(myl) == 1:
				try:
					# Only one package... Counter doesn't matter.
					write_atomic(cpath, "1")
					counter = 1
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
						noiselevel=-1)
					writemsg("!!! Please run %s/fix-db.py or\n" % PORTAGE_BIN_PATH,
						noiselevel=-1)
					writemsg("!!! unmerge this exact version.\n", noiselevel=-1)
					writemsg("!!! %s\n" % e, noiselevel=-1)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
					noiselevel=-1)
				writemsg("!!! Please run %s/fix-db.py or\n" % PORTAGE_BIN_PATH,
					noiselevel=-1)
				writemsg("!!! remerge the package.\n", noiselevel=-1)
				sys.exit(1)
		else:
			counter = long(0)
		if corrupted:
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

	def cpv_inject(self, mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		os.makedirs(self.getpath(mycpv))
		counter = self.counter_tick(self.root, mycpv=mycpv)
		# write local package counter so that emerge clean does the right thing
		write_atomic(self.getpath(mycpv, filename="COUNTER"), str(counter))

	def isInjected(self, mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.getpath(mycpv, filename="INJECTED")):
				return True
			if not os.path.exists(self.getpath(mycpv, filename="CONTENTS")):
				return True
		return False

	def move_ent(self, mylist):
		origcp = mylist[1]
		newcp = mylist[2]

		# sanity check
		for cp in [origcp, newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise InvalidPackageName(cp)
		origmatches = self.match(origcp, use_cache=0)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			mycpsplit = catpkgsplit(mycpv)
			mynewcpv = newcp + "-" + mycpsplit[2]
			mynewcat = newcp.split("/")[0]
			if mycpsplit[3] != "r0":
				mynewcpv += "-" + mycpsplit[3]
			mycpsplit_new = catpkgsplit(mynewcpv)
			origpath = self.getpath(mycpv)
			if not os.path.exists(origpath):
				continue
			moves += 1
			if not os.path.exists(self.getpath(mynewcat)):
				#create the directory
				os.makedirs(self.getpath(mynewcat))
			newpath = self.getpath(mynewcpv)
			if os.path.exists(newpath):
				#dest already exists; keep this puppy where it is.
				continue
			os.rename(origpath, newpath)

			# We need to rename the ebuild now.
			old_pf = catsplit(mycpv)[1]
			new_pf = catsplit(mynewcpv)[1]
			if new_pf != old_pf:
				try:
					os.rename(os.path.join(newpath, old_pf + ".ebuild"),
						os.path.join(newpath, new_pf + ".ebuild"))
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
				write_atomic(os.path.join(newpath, "PF"), new_pf+"\n")

			write_atomic(os.path.join(newpath, "CATEGORY"), mynewcat+"\n")
			fixdbentries([mylist], newpath)
		return moves

	def cp_list(self, mycp, use_cache=1):
		mysplit=catsplit(mycp)
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat = os.stat(self.getpath(mysplit[0]))[stat.ST_MTIME]
		except OSError:
			mystat = 0
		if use_cache and self.cpcache.has_key(mycp):
			cpc = self.cpcache[mycp]
			if cpc[0] == mystat:
				return cpc[1]
		list = listdir(self.getpath(mysplit[0]), EmptyOnError=1)

		if (list is None):
			return []
		returnme = []
		for x in list:
			if x.startswith("."):
				continue
			if x[0] == '-':
				#writemsg(red("INCOMPLETE MERGE:")+str(x[len("-MERGING-"):])+"\n")
				continue
			ps = pkgsplit(x)
			if not ps:
				self.invalidentry(os.path.join(self.getpath(mysplit[0]), x))
				continue
			if len(mysplit) > 1:
				if ps[0] == mysplit[1]:
					returnme.append(mysplit[0]+"/"+x)
		if use_cache:
			self.cpcache[mycp] = [mystat,returnme]
		elif self.cpcache.has_key(mycp):
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self, use_cache=1):
		returnme = []
		basepath = os.path.join(self.root, VDB_PATH) + os.path.sep
		for x in self.categories:
			for y in listdir(basepath + x, EmptyOnError=1):
				if y.startswith("."):
					continue
				subpath = x + "/" + y
				# -MERGING- should never be a cpv, nor should files.
				if os.path.isdir(basepath + subpath) and (pkgsplit(y) is not None):
					returnme += [subpath]
		return returnme

	def cp_all(self, use_cache=1):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			mysplit = catpkgsplit(y)
			if not mysplit:
				self.invalidentry(self.getpath(y))
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return d.keys()

	def checkblockers(self, origdep):
		pass

	def match(self, origdep, use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		mykey = dep_getkey(mydep)
		mycat = catsplit(mykey)[0]
		if not use_cache:
			if self.matchcache.has_key(mycat):
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			mymatch = match_from_list(mydep,
				self.cp_list(mykey, use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			return mymatch
		try:
			curmtime = os.stat(self.root+VDB_PATH+"/"+mycat)[stat.ST_MTIME]
		except (IOError, OSError):
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat] = curmtime
			self.matchcache[mycat] = {}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch = match_from_list(mydep, self.cp_list(mykey, use_cache=use_cache))
			myslot = dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			self.matchcache[mycat][mydep] = mymatch
		return self.matchcache[mycat][mydep][:]

	def findname(self, mycpv):
		return self.getpath(str(mycpv), filename=catsplit(mycpv)[1]+".ebuild")

	def flush_cache(self):
		"""If the current user has permission and the internal aux_get cache has
		been updated, save it to disk and mark it unmodified.  This is called
		by emerge after it has loaded the full vdb for use in dependency
		calculations.  Currently, the cache is only written if the user has
		superuser privileges (since that's required to obtain a lock), but all
		users have read access and benefit from faster metadata lookups (as
		long as at least part of the cache is still valid)."""
		if self._aux_cache is not None and \
			self._aux_cache["modified"] and \
			secpass >= 2:
			valid_nodes = set(self.cpv_all())
			for cpv in self._aux_cache["packages"].keys():
				if cpv not in valid_nodes:
					del self._aux_cache["packages"][cpv]
			del self._aux_cache["modified"]
			try:
				f = atomic_ofstream(self._aux_cache_filename)
				cPickle.dump(self._aux_cache, f, -1)
				f.close()
				apply_secpass_permissions(
					self._aux_cache_filename, gid=portage_gid, mode=0644)
			except (IOError, OSError), e:
				pass
			self._aux_cache["modified"] = False

	def aux_get(self, mycpv, wants):
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
		if not self._aux_cache_keys.intersection(wants):
			return self._aux_get(mycpv, wants)
		if self._aux_cache is None:
			try:
				f = open(self._aux_cache_filename)
				mypickle = cPickle.Unpickler(f)
				mypickle.find_global = None
				self._aux_cache = mypickle.load()
				f.close()
				del f
			except (IOError, OSError, EOFError, cPickle.UnpicklingError):
				pass
			if not self._aux_cache or \
				not isinstance(self._aux_cache, dict) or \
				self._aux_cache.get("version") != self._aux_cache_version or \
				not self._aux_cache.get("packages"):
				self._aux_cache = {"version": self._aux_cache_version}
				self._aux_cache["packages"] = {}
			self._aux_cache["modified"] = False
		mydir = self.getpath(mycpv)
		mydir_stat = None
		try:
			mydir_stat = os.stat(mydir)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			raise KeyError(mycpv)
		mydir_mtime = long(mydir_stat.st_mtime)
		pkg_data = self._aux_cache["packages"].get(mycpv)
		mydata = {}
		cache_valid = False
		if pkg_data:
			cache_mtime, metadata = pkg_data
			cache_valid = cache_mtime == mydir_mtime
		if cache_valid:
			cache_incomplete = self._aux_cache_keys.difference(metadata)
			if cache_incomplete:
				# Allow self._aux_cache_keys to change without a cache version
				# bump and efficiently recycle partial cache whenever possible.
				cache_valid = False
				pull_me = cache_incomplete.union(wants)
			else:
				pull_me = set(wants).difference(self._aux_cache_keys)
			mydata.update(metadata)
		else:
			pull_me = self._aux_cache_keys.union(wants)
		if pull_me:
			# pull any needed data and cache it
			aux_keys = list(pull_me)
			for k, v in izip(aux_keys, self._aux_get(mycpv, aux_keys)):
				mydata[k] = v
			if not cache_valid:
				cache_data = {}
				for aux_key in self._aux_cache_keys:
					cache_data[aux_key] = mydata[aux_key]
				self._aux_cache["packages"][mycpv] = (mydir_mtime, cache_data)
				self._aux_cache["modified"] = True
		return [mydata[x] for x in wants]

	def _aux_get(self, mycpv, wants):
		mydir = self.getpath(mycpv)
		try:
			if not stat.S_ISDIR(os.stat(mydir).st_mode):
				raise KeyError(mycpv)
		except OSError, e:
			if e.errno == errno.ENOENT:
				raise KeyError(mycpv)
			del e
			raise
		results = []
		for x in wants:
			try:
				myf = open(os.path.join(mydir, x), "r")
				try:
					myd = myf.read()
				finally:
					myf.close()
				myd = " ".join(myd.split())
			except IOError:
				myd = ""
			if x == "EAPI" and not myd:
				results.append("0")
			else:
				results.append(myd)
		return results

	def aux_update(self, cpv, values):
		cat, pkg = catsplit(cpv)
		mylink = dblink(cat, pkg, self.root, self.settings,
		treetype="vartree", vartree=self.vartree)
		if not mylink.exists():
			raise KeyError(cpv)
		for k, v in values.iteritems():
			if v:
				mylink.setfile(k, v)
			else:
				try:
					os.unlink(os.path.join(self.getpath(cpv), k))
				except EnvironmentError:
					pass

	def counter_tick(self, myroot, mycpv=None):
		return self.counter_tick_core(myroot, incrementing=1, mycpv=mycpv)

	def get_counter_tick_core(self, myroot, mycpv=None):
		return self.counter_tick_core(myroot, incrementing=0, mycpv=mycpv) + 1

	def counter_tick_core(self, myroot, incrementing=1, mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		cpath = os.path.join(myroot, CACHE_PATH.lstrip(os.sep), "counter")
		changed = 0
		min_counter = 0
		if mycpv:
			mysplit = pkgsplit(mycpv)
			for x in self.match(mysplit[0], use_cache=0):
				if x == mycpv:
					continue
				try:
					old_counter = long(self.aux_get(x, ["COUNTER"])[0])
					writemsg("COUNTER '%d' '%s'\n" % (old_counter, x), 1)
				except (ValueError, KeyError): # valueError from long(), KeyError from aux_get
					old_counter = 0
					writemsg("!!! BAD COUNTER in '%s'\n" % (x), noiselevel=-1)
				if old_counter > min_counter:
					min_counter = old_counter

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption.
		find_counter = ("find '%s' -type f -name COUNTER | " + \
			"while read f; do echo $(<\"${f}\"); done | " + \
			"sort -n | tail -n1") % os.path.join(self.root, VDB_PATH)
		if os.path.exists(cpath):
			cfile = open(cpath, "r")
			try:
				counter = long(cfile.readline())
			except (ValueError,OverflowError):
				try:
					counter = long(commands.getoutput(find_counter).strip())
					writemsg("!!! COUNTER was corrupted; resetting to value of %d\n" % counter,
						noiselevel=-1)
					changed=1
				except (ValueError, OverflowError):
					writemsg("!!! COUNTER data is corrupt in pkg db. The values need to be\n",
						noiselevel=-1)
					writemsg("!!! corrected/normalized so that portage can operate properly.\n",
						noiselevel=-1)
					writemsg("!!! A simple solution is not yet available so try #gentoo on IRC.\n")
					sys.exit(2)
			cfile.close()
		else:
			try:
				counter = long(commands.getoutput(find_counter).strip())
				writemsg("!!! Global counter missing. Regenerated from counter files to: %s\n" % counter,
					noiselevel=-1)
			except ValueError: # Value Error for long(), probably others for commands.getoutput
				writemsg("!!! Initializing global counter.\n", noiselevel=-1)
				counter = long(0)
			changed = 1

		if counter < min_counter:
			counter = min_counter + 1000
			changed = 1

		if incrementing or changed:

			#increment counter
			counter += 1
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

class vartree(object):
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self, root="/", virtual=None, clone=None, categories=None,
		settings=None):
		if clone:
			writemsg("vartree.__init__(): deprecated " + \
				"use of clone parameter\n", noiselevel=-1)
			self.root = clone.root[:]
			self.dbapi = copy.deepcopy(clone.dbapi)
			self.populated = 1
			self.settings = config(clone=clone.settings)
		else:
			self.root = root[:]
			if settings is None:
				from portage import settings
			self.settings = settings # for key_expand calls
			if categories is None:
				categories = settings.categories
			self.dbapi = vardbapi(self.root, categories=categories,
				settings=settings, vartree=self)
			self.populated = 1

	def getpath(self, mykey, filename=None):
		rValue = self.getpath(mykey)
		if filename != None:
			rValue = os.path.join(rValue, filename)
		return rValue

	def zap(self, mycpv):
		return

	def inject(self, mycpv):
		return

	def get_provide(self, mycpv):
		myprovides = []
		mylines = None
		try:
			mylines, myuse = self.dbapi.aux_get(mycpv, ["PROVIDE", "USE"])
			if mylines:
				myuse = myuse.split()
				mylines = flatten(use_reduce(paren_reduce(mylines), uselist=myuse))
				for myprovide in mylines:
					mys = catpkgsplit(myprovide)
					if not mys:
						mys = myprovide.split("/")
					myprovides += [mys[0] + "/" + mys[1]]
			return myprovides
		except SystemExit, e:
			raise
		except Exception, e:
			mydir = self.getpath(mycpv)
			writemsg("\nParse Error reading PROVIDE and USE in '%s'\n" % mydir,
				noiselevel=-1)
			if mylines:
				writemsg("Possibly Invalid: '%s'\n" % str(mylines),
					noiselevel=-1)
			writemsg("Exception: %s\n\n" % str(e), noiselevel=-1)
			return []

	def get_all_provides(self):
		myprovides = {}
		for node in self.getallcpv():
			for mykey in self.get_provide(node):
				if myprovides.has_key(mykey):
					myprovides[mykey] += [node]
				else:
					myprovides[mykey] = [node]
		return myprovides

	def dep_bestmatch(self, mydep, use_cache=1):
		"compatibility method -- all matches, not just visible ones"
		#mymatch=best(match(dep_expand(mydep,self.dbapi),self.dbapi))
		mymatch = best(self.dbapi.match(
			dep_expand(mydep, mydb=self.dbapi, settings=self.settings),
			use_cache=use_cache))
		if mymatch is None:
			return ""
		else:
			return mymatch

	def dep_match(self, mydep, use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch = match(mydep,self.dbapi)
		mymatch = self.dbapi.match(mydep, use_cache=use_cache)
		if mymatch is None:
			return []
		else:
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

	def exists_specific_cat(self, cpv, use_cache=1):
		cpv = key_expand(cpv, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		a = catpkgsplit(cpv)
		if not a:
			return 0
		mylist = listdir(self.getpath(a[0]), EmptyOnError=1)
		for x in mylist:
			b = pkgsplit(x)
			if not b:
				self.dbapi.invalidentry(self.getpath(a[0], filename=x))
				continue
			if a[1] == b[0]:
				return 1
		return 0

	def getebuildpath(self, fullpackage):
		cat, package = catsplit(fullpackage)
		return self.getpath(fullpackage, filename=package+".ebuild")

	def getnode(self, mykey, use_cache=1):
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		if not mykey:
			return []
		mysplit = catsplit(mykey)
		mydirlist = listdir(self.getpath(mysplit[0]),EmptyOnError=1)
		returnme = []
		for x in mydirlist:
			mypsplit = pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.getpath(mysplit[0], filename=x))
				continue
			if mypsplit[0] == mysplit[1]:
				appendme = [mysplit[0]+"/"+x, [mysplit[0], mypsplit[0], mypsplit[1], mypsplit[2]]]
				returnme.append(appendme)
		return returnme


	def getslot(self, mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			return self.dbapi.aux_get(mycatpkg, ["SLOT"])[0]
		except KeyError:
			return ""

	def hasnode(self, mykey, use_cache):
		"""Does the particular node (cat/pkg key) exist?"""
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		mysplit = catsplit(mykey)
		mydirlist = listdir(self.getpath(mysplit[0]), EmptyOnError=1)
		for x in mydirlist:
			mypsplit = pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.getpath(mysplit[0], filename=x))
				continue
			if mypsplit[0] == mysplit[1]:
				return 1
		return 0

	def populate(self):
		self.populated=1

class dblink(object):
	"""
	This class provides an interface to the installed package database
	At present this is implemented as a text backend in /var/db/pkg.
	"""
	def __init__(self, cat, pkg, myroot, mysettings, treetype=None,
		vartree=None):
		"""
		Creates a DBlink object for a given CPV.
		The given CPV may not be present in the database already.
		
		@param cat: Category
		@type cat: String
		@param pkg: Package (PV)
		@type pkg: String
		@param myroot: Typically ${ROOT}
		@type myroot: String (Path)
		@param mysettings: Typically portage.config
		@type mysettings: An instance of portage.config
		@param treetype: one of ['porttree','bintree','vartree']
		@type treetype: String
		@param vartree: an instance of vartree corresponding to myroot.
		@type vartree: vartree
		"""
		
		self.cat = cat
		self.pkg = pkg
		self.mycpv = self.cat + "/" + self.pkg
		self.mysplit = pkgsplit(self.mycpv)
		self.treetype = treetype
		if vartree is None:
			from portage import db
			vartree = db[myroot]["vartree"]
		self.vartree = vartree

		self.dbroot = normalize_path(os.path.join(myroot, VDB_PATH))
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir = self.dbpkgdir

		self._lock_vdb = None

		self.settings = mysettings
		if self.settings == 1:
			raise ValueError

		self.myroot=myroot
		protect_obj = ConfigProtect(myroot,
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split())
		self.updateprotect = protect_obj.updateprotect
		self._config_protect = protect_obj
		self._installed_instance = None
		self.contentscache=[]
		self._contents_inodes = None

	def lockdb(self):
		if self._lock_vdb:
			raise AssertionError("Lock already held.")
		# At least the parent needs to exist for the lock file.
		ensure_dirs(self.dbroot)
		self._lock_vdb = lockdir(self.dbroot)

	def unlockdb(self):
		if self._lock_vdb:
			unlockdir(self._lock_vdb)
			self._lock_vdb = None

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
		if not os.path.exists(self.dbdir):
			return
		try:
			for x in listdir(self.dbdir):
				os.unlink(self.dbdir+"/"+x)
			os.rmdir(self.dbdir)
		except OSError, e:
			print "!!! Unable to remove db entry for this package."
			print "!!! It is possible that a directory is in this one. Portage will still"
			print "!!! register this package as installed as long as this directory exists."
			print "!!! You may delete this directory with 'rm -Rf "+self.dbdir+"'"
			print "!!! "+str(e)
			print
			sys.exit(1)

	def clearcontents(self):
		"""
		For a given db entry (self), erase the CONTENTS values.
		"""
		if os.path.exists(self.dbdir+"/CONTENTS"):
			os.unlink(self.dbdir+"/CONTENTS")

	def getcontents(self):
		"""
		Get the installed files of a given package (aka what that package installed)
		"""
		contents_file = os.path.join(self.dbdir, "CONTENTS")
		if not os.path.exists(contents_file):
			return None
		if self.contentscache != []:
			return self.contentscache
		pkgfiles = {}
		myc = open(contents_file,"r")
		mylines = myc.readlines()
		myc.close()
		null_byte = "\0"
		pos = 0
		for line in mylines:
			pos += 1
			if null_byte in line:
				# Null bytes are a common indication of corruption.
				writemsg("!!! Null byte found in contents " + \
					"file, line %d: '%s'\n" % (pos, contents_file),
					noiselevel=-1)
				continue
			mydat = line.split()
			# we do this so we can remove from non-root filesystems
			# (use the ROOT var to allow maintenance on other partitions)
			try:
				mydat[1] = normalize_path(os.path.join(
					self.myroot, mydat[1].lstrip(os.path.sep)))
				if mydat[0] == "obj":
					#format: type, mtime, md5sum
					pkgfiles[" ".join(mydat[1:-2])] = [mydat[0], mydat[-1], mydat[-2]]
				elif mydat[0] == "dir":
					#format: type
					pkgfiles[" ".join(mydat[1:])] = [mydat[0] ]
				elif mydat[0] == "sym":
					#format: type, mtime, dest
					x = len(mydat) - 1
					if (x >= 13) and (mydat[-1][-1] == ')'): # Old/Broken symlink entry
						mydat = mydat[:-10] + [mydat[-10:][stat.ST_MTIME][:-1]]
						writemsg("FIXED SYMLINK LINE: %s\n" % mydat, 1)
						x = len(mydat) - 1
					splitter = -1
					while (x >= 0):
						if mydat[x] == "->":
							splitter = x
							break
						x = x - 1
					if splitter == -1:
						return None
					pkgfiles[" ".join(mydat[1:splitter])] = [mydat[0], mydat[-1], " ".join(mydat[(splitter+1):-1])]
				elif mydat[0] == "dev":
					#format: type
					pkgfiles[" ".join(mydat[1:])] = [mydat[0] ]
				elif mydat[0]=="fif":
					#format: type
					pkgfiles[" ".join(mydat[1:])] = [mydat[0]]
				else:
					return None
			except (KeyError, IndexError):
				print "portage: CONTENTS line", pos, "corrupt!"
		self.contentscache = pkgfiles
		return pkgfiles

	def unmerge(self, pkgfiles=None, trimworld=1, cleanup=1,
		ldpath_mtimes=None):
		"""
		Calls prerm
		Unmerges a given package (CPV)
		calls postrm
		calls cleanrm
		calls env_update
		
		@param pkgfiles: files to unmerge (generally self.getcontents() )
		@type pkgfiles: Dictionary
		@param trimworld: Remove CPV from world file if True, not if False
		@type trimworld: Boolean
		@param cleanup: cleanup to pass to doebuild (see doebuild)
		@type cleanup: Boolean
		@param ldpath_mtimes: mtimes to pass to env_update (see env_update)
		@type ldpath_mtimes: Dictionary
		@rtype: Integer
		@returns:
		1. os.EX_OK if everything went well.
		2. return code of the failed phase (for prerm, postrm, cleanrm)
		
		Notes:
		The caller must ensure that lockdb() and unlockdb() are called
		before and after this method.
		"""

		contents = self.getcontents()
		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath = None
		mystuff = listdir(self.dbdir, EmptyOnError=1)
		for x in mystuff:
			if x.endswith(".ebuild"):
				myebuildpath = os.path.join(self.dbdir, self.pkg + ".ebuild")
				if x[:-7] != self.pkg:
					# Clean up after vardbapi.move_ent() breakage in
					# portage versions before 2.1.2
					os.rename(os.path.join(self.dbdir, x), myebuildpath)
					write_atomic(os.path.join(self.dbdir, "PF"), self.pkg+"\n")
				break

		self.settings.load_infodir(self.dbdir)
		if myebuildpath:
			try:
				doebuild_environment(myebuildpath, "prerm", self.myroot,
					self.settings, 0, 0, self.vartree.dbapi)
			except UnsupportedAPIException, e:
				# Sometimes this happens due to corruption of the EAPI file.
				writemsg("!!! FAILED prerm: %s\n" % \
					os.path.join(self.dbdir, "EAPI"), noiselevel=-1)
				writemsg("%s\n" % str(e), noiselevel=-1)
				return 1
			catdir = os.path.dirname(self.settings["PORTAGE_BUILDDIR"])
			ensure_dirs(os.path.dirname(catdir),
				uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		builddir_lock = None
		catdir_lock = None
		try:
			if myebuildpath:
				catdir_lock = lockdir(catdir)
				ensure_dirs(catdir,
					uid=portage_uid, gid=portage_gid,
					mode=070, mask=0)
				builddir_lock = lockdir(
					self.settings["PORTAGE_BUILDDIR"])
				try:
					unlockdir(catdir_lock)
				finally:
					catdir_lock = None
				# Eventually, we'd like to pass in the saved ebuild env here...
				retval = doebuild(myebuildpath, "prerm", self.myroot,
					self.settings, cleanup=cleanup, use_cache=0,
					mydbapi=self.vartree.dbapi, tree="vartree",
					vartree=self.vartree)
				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					writemsg("!!! FAILED prerm: %s\n" % retval, noiselevel=-1)
					return retval

			self._unmerge_pkgfiles(pkgfiles)
			
			# Remove the registration of preserved libs for this pkg instance
			self.vartree.dbapi.plib_registry.unregister(self.mycpv, self.settings["SLOT"], self.settings["COUNTER"])

			if myebuildpath:
				retval = doebuild(myebuildpath, "postrm", self.myroot,
					 self.settings, use_cache=0, tree="vartree",
					 mydbapi=self.vartree.dbapi, vartree=self.vartree)

				# process logs created during pre/postrm
				elog_process(self.mycpv, self.settings)

				# XXX: Decide how to handle failures here.
				if retval != os.EX_OK:
					writemsg("!!! FAILED postrm: %s\n" % retval, noiselevel=-1)
					return retval
				doebuild(myebuildpath, "cleanrm", self.myroot, self.settings,
					tree="vartree", mydbapi=self.vartree.dbapi,
					vartree=self.vartree)
			
			# regenerate reverse NEEDED map
			self.vartree.dbapi.libmap.update()

		finally:
			if builddir_lock:
				unlockdir(builddir_lock)
			try:
				if myebuildpath and not catdir_lock:
					# Lock catdir for removal if empty.
					catdir_lock = lockdir(catdir)
			finally:
				if catdir_lock:
					try:
						os.rmdir(catdir)
					except OSError, e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					unlockdir(catdir_lock)
		env_update(target_root=self.myroot, prev_mtimes=ldpath_mtimes,
			contents=contents)
		return os.EX_OK

	def _unmerge_pkgfiles(self, pkgfiles):
		"""
		
		Unmerges the contents of a package from the liveFS
		Removes the VDB entry for self
		
		@param pkgfiles: typically self.getcontents()
		@type pkgfiles: Dictionary { filename: [ 'type', '?', 'md5sum' ] }
		@rtype: None
		"""
		global dircache
		dircache={}

		if not pkgfiles:
			writemsg_stdout("No package files given... Grabbing a set.\n")
			pkgfiles = self.getcontents()

		if pkgfiles:
			mykeys = pkgfiles.keys()
			mykeys.sort()
			mykeys.reverse()

			#process symlinks second-to-last, directories last.
			mydirs = []
			modprotect = "/lib/modules/"
			for objkey in mykeys:
				obj = normalize_path(objkey)
				if obj[:2] == "//":
					obj = obj[1:]
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
				if statobj is None:
					if not islink:
						#we skip this if we're dealing with a symlink
						#because os.stat() will operate on the
						#link target rather than the link itself.
						writemsg_stdout("--- !found " + str(pkgfiles[objkey][0]) + " %s\n" % obj)
						continue
				# next line includes a tweak to protect modules from being unmerged,
				# but we don't protect modules from being overwritten if they are
				# upgraded. We effectively only want one half of the config protection
				# functionality for /lib/modules. For portage-ng both capabilities
				# should be able to be independently specified.
				if obj.startswith(modprotect):
					writemsg_stdout("--- cfgpro %s %s\n" % (pkgfiles[objkey][0], obj))
					continue

				lmtime = str(lstatobj[stat.ST_MTIME])
				if (pkgfiles[objkey][0] not in ("dir", "fif", "dev")) and (lmtime != pkgfiles[objkey][1]):
					writemsg_stdout("--- !mtime %s %s\n" % (pkgfiles[objkey][0], obj))
					continue

				if pkgfiles[objkey][0] == "dir":
					if statobj is None or not stat.S_ISDIR(statobj.st_mode):
						writemsg_stdout("--- !dir   %s %s\n" % ("dir", obj))
						continue
					mydirs.append(obj)
				elif pkgfiles[objkey][0] == "sym":
					if not islink:
						writemsg_stdout("--- !sym   %s %s\n" % ("sym", obj))
						continue
					try:
						os.unlink(obj)
						writemsg_stdout("<<<        %s %s\n" % ("sym", obj))
					except (OSError, IOError),e:
						writemsg_stdout("!!!        %s %s\n" % ("sym", obj))
				elif pkgfiles[objkey][0] == "obj":
					if statobj is None or not stat.S_ISREG(statobj.st_mode):
						writemsg_stdout("--- !obj   %s %s\n" % ("obj", obj))
						continue
					mymd5 = None
					try:
						mymd5 = perform_md5(obj, calc_prelink=1)
					except FileNotFound, e:
						# the file has disappeared between now and our stat call
						writemsg_stdout("--- !obj   %s %s\n" % ("obj", obj))
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != pkgfiles[objkey][2].lower():
						writemsg_stdout("--- !md5   %s %s\n" % ("obj", obj))
						continue
					try:
						if statobj.st_mode & (stat.S_ISUID | stat.S_ISGID):
							# Always blind chmod 0 before unlinking to avoid race conditions.
							os.chmod(obj, 0000)
							if statobj.st_nlink > 1:
								writemsg("setXid: "+str(statobj.st_nlink-1)+ \
									" hardlinks to '%s'\n" % obj)
						os.unlink(obj)
					except (OSError, IOError), e:
						pass
					writemsg_stdout("<<<        %s %s\n" % ("obj", obj))
				elif pkgfiles[objkey][0] == "fif":
					if not stat.S_ISFIFO(lstatobj[stat.ST_MODE]):
						writemsg_stdout("--- !fif   %s %s\n" % ("fif", obj))
						continue
					writemsg_stdout("---        %s %s\n" % ("fif", obj))
				elif pkgfiles[objkey][0] == "dev":
					writemsg_stdout("---        %s %s\n" % ("dev", obj))

			mydirs.sort()
			mydirs.reverse()

			for obj in mydirs:
				try:
					os.rmdir(obj)
					writemsg_stdout("<<<        %s %s\n" % ("dir", obj))
				except (OSError, IOError):
					writemsg_stdout("--- !empty dir %s\n" % obj)

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

	def isowner(self,filename, destroot):
		""" 
		Check if filename is a new file or belongs to this package
		(for this or a previous version)
		
		@param filename:
		@type filename:
		@param destroot:
		@type destroot:
		@rtype: Boolean
		@returns:
		1. True if this package owns the file.
		2. False if this package does not own the file.
		"""
		destfile = normalize_path(
			os.path.join(destroot, filename.lstrip(os.path.sep)))
		try:
			mylstat = os.lstat(destfile)
		except (OSError, IOError):
			return True

		pkgfiles = self.getcontents()
		if pkgfiles and filename in pkgfiles:
			return True
		if pkgfiles:
			if self._contents_inodes is None:
				self._contents_inodes = set()
				for x in pkgfiles:
					try:
						lstat = os.lstat(x)
						self._contents_inodes.add((lstat.st_dev, lstat.st_ino))
					except OSError:
						pass
			if (mylstat.st_dev, mylstat.st_ino) in self._contents_inodes:
				 return True

		return False

	def isprotected(self, filename):
		"""In cases where an installed package in the same slot owns a
		protected file that will be merged, bump the mtime on the installed
		file in order to ensure that it isn't unmerged."""
		if not self._config_protect.isprotected(filename):
			return False
		if self._installed_instance is None:
			return True
		mydata = self._installed_instance.getcontents().get(filename, None)
		if mydata is None:
			return True

		# Bump the mtime in order to ensure that the old config file doesn't
		# get unmerged.  The user will have an opportunity to merge the new
		# config with the old one.
		try:
			os.utime(filename, None)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
			del e
			# The file has disappeared, so it's not protected.
			return False
		return True


	def _preserve_libs(self, srcroot, destroot, mycontents, counter):
		# read global reverse NEEDED map
		libmap = self.vartree.dbapi.libmap.get()

		# get list of libraries from old package instance
		old_contents = self._installed_instance.getcontents().keys()
		old_libs = set([os.path.basename(x) for x in old_contents]).intersection(libmap.keys())

		# get list of libraries from new package instance
		mylibs = set([os.path.basename(x) for x in mycontents]).intersection(libmap.keys())

		# check which libs are present in the old, but not the new package instance
		preserve_libs = old_libs.difference(mylibs)

		# ignore any libs that are only internally used by the package
		def has_external_consumers(lib, contents, otherlibs):
			consumers = set(libmap[lib])
			contents_without_libs = [x for x in contents if not os.path.basename(x) in otherlibs]
			
			# just used by objects that will be autocleaned
			if len(consumers.difference(contents_without_libs)) == 0:
				return False
			# used by objects that are referenced as well, need to check those 
			# recursively to break any reference cycles
			elif len(consumers.difference(contents)) == 0:
				otherlibs = set(otherlibs)
				for ol in otherlibs.intersection(consumers):
					if has_external_consumers(ol, contents, otherlibs.difference([lib])):
						return True
				return False
			# used by external objects directly
			else:
				return True

		for lib in list(preserve_libs):
			if not has_external_consumers(lib, old_contents, preserve_libs):
				preserve_libs.remove(lib)						
			
		# get the real paths for the libs
		preserve_paths = [x for x in old_contents if os.path.basename(x) in preserve_libs]
		del old_contents, old_libs, mylibs, preserve_libs
			
		# inject files that should be preserved into our image dir
		import shutil
		for x in preserve_paths:
			print "injecting %s into %s" % (x, srcroot)
			mydir = os.path.join(srcroot, os.path.dirname(x))
			if not os.path.exists(mydir):
				os.makedirs(mydir)

			# resolve symlinks and extend preserve list
			# NOTE: we're extending the list in the loop to emulate recursion to
			#       also get indirect symlinks
			if os.path.islink(x):
				linktarget = os.readlink(x)
				os.symlink(linktarget, os.path.join(srcroot, x.lstrip(os.sep)))
				if linktarget[0] != os.sep:
					linktarget = os.path.join(os.path.dirname(x), linktarget)
				preserve_paths.append(linktarget)
			else:
				shutil.copy2(os.path.join(destroot, x), os.path.join(srcroot, x.lstrip(os.sep)))

		# keep track of the libs we preserved
		self.vartree.dbapi.plib_registry.register(self.mycpv, self.settings["SLOT"], counter, preserve_paths)

		del preserve_paths
	
	def _collision_protect(self, srcroot, destroot, otherversions, mycontents, mysymlinks):
			collision_ignore = set([normalize_path(myignore) for myignore in \
				self.settings.get("COLLISION_IGNORE", "").split()])

			# the linkcheck only works if we are in srcroot
			mycwd = os.getcwd()
			os.chdir(srcroot)


			mysymlinked_directories = [s + os.path.sep for s in mysymlinks]
			del mysymlinks

			stopmerge = False
			i=0

			otherpkg=[]
			mypkglist=[]

			if self.pkg in otherversions:
				otherversions.remove(self.pkg)	# we already checked this package

			myslot = self.settings["SLOT"]
			for v in otherversions:
				# only allow versions with same slot to overwrite files
				if myslot == self.vartree.dbapi.aux_get("/".join((self.cat, v)), ["SLOT"])[0]:
					mypkglist.append(
						dblink(self.cat, v, destroot, self.settings,
							vartree=self.vartree))

			collisions = []

			print green("*")+" checking "+str(len(mycontents))+" files for package collisions"
			for f in mycontents:
				nocheck = False
				# listdir isn't intelligent enough to exclude symlinked dirs,
				# so we have to do it ourself
				for s in mysymlinked_directories:
					if f.startswith(s):
						nocheck = True
						break
				if nocheck:
					continue
				i = i + 1
				if i % 1000 == 0:
					print str(i)+" files checked ..."
				if f[0] != "/":
					f="/"+f
				isowned = False
				for ver in [self] + mypkglist:
					if (ver.isowner(f, destroot) or ver.isprotected(f)):
						isowned = True
						break
				if not isowned:
					collisions.append(f)
					print "existing file "+f+" is not owned by this package"
					stopmerge = True
					if collision_ignore:
						if f in collision_ignore:
							stopmerge = False
						else:
							for myignore in collision_ignore:
								if f.startswith(myignore + os.path.sep):
									stopmerge = False
									break
			if stopmerge:
				print red("*")+" This package is blocked because it wants to overwrite"
				print red("*")+" files belonging to other packages (see messages above)."
				print red("*")+" If you have no clue what this is all about report it "
				print red("*")+" as a bug for this package on http://bugs.gentoo.org"
				print
				print red("package "+self.cat+"/"+self.pkg+" NOT merged")
				print
				print
				print "Searching all installed packages for file collisions..."
				print "Press Ctrl-C to Stop"
				print
				""" Note: The isowner calls result in a stat call for *every*
				single installed file, since the inode numbers are used to work
				around the problem of ambiguous paths caused by symlinked files
				and/or directories.  Though it is slow, it is as accurate as
				possible."""
				found_owner = False
				for cpv in self.vartree.dbapi.cpv_all():
					cat, pkg = catsplit(cpv)
					mylink = dblink(cat, pkg, destroot, self.settings,
						vartree=self.vartree)
					mycollisions = []
					for f in collisions:
						if mylink.isowner(f, destroot):
							mycollisions.append(f)
					if mycollisions:
						found_owner = True
						print " * %s:" % cpv
						print
						for f in mycollisions:
							print "     '%s'" % \
								os.path.join(destroot, f.lstrip(os.path.sep))
						print
				if not found_owner:
					print "None of the installed packages claim the above file(s)."
					print
				sys.exit(1)
			try:
				os.chdir(mycwd)
			except OSError:
				pass

	def treewalk(self, srcroot, destroot, inforoot, myebuild, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		"""
		
		This function does the following:
		
		calls self._preserve_libs if FEATURES=preserve-libs
		calls self._collision_protect if FEATURES=collision-protect
		calls doebuild(mydo=pkg_preinst)
		Merges the package to the livefs
		unmerges old version (if required)
		calls doebuild(mydo=pkg_postinst)
		calls env_update
		calls elog_process
		
		@param srcroot: Typically this is ${D}
		@type srcroot: String (Path)
		@param destroot: Path to merge to (usually ${ROOT})
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
		@returns:
		1. 0 on success
		2. 1 on failure
		
		secondhand is a list of symlinks that have been skipped due to their target
		not existing; we will merge these symlinks at a later time.
		"""
		if not os.path.isdir(srcroot):
			writemsg("!!! Directory Not Found: D='%s'\n" % srcroot,
				noiselevel=-1)
			return 1

		if not os.path.exists(self.dbcatdir):
			os.makedirs(self.dbcatdir)

		otherversions = []
		for v in self.vartree.dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		slot_matches = self.vartree.dbapi.match(
			"%s:%s" % (self.mysplit[0], self.settings["SLOT"]))
		if slot_matches:
			# Used by self.isprotected().
			self._installed_instance = dblink(self.cat,
				catsplit(slot_matches[0])[1], destroot, self.settings,
				vartree=self.vartree)

		# get current counter value (counter_tick also takes care of incrementing it)
		# XXX Need to make this destroot, but it needs to be initialized first. XXX
		# XXX bis: leads to some invalidentry() call through cp_all().
		# Note: The counter is generated here but written later because preserve_libs
		#       needs the counter value but has to be before dbtmpdir is made (which
		#       has to be before the counter is written) - genone
		counter = self.vartree.dbapi.counter_tick(self.myroot, mycpv=self.mycpv)

		myfilelist = None
		mylinklist = None

		# Preserve old libs if they are still in use
		if slot_matches and "preserve-libs" in self.settings.features:
			myfilelist = listdir(srcroot, recursive=1, filesonly=1, followSymlinks=False)
			mylinklist = filter(os.path.islink, [os.path.join(srcroot, x) for x in listdir(srcroot, recursive=1, filesonly=0, followSymlinks=False)])
			mylinklist = [x[len(srcroot):] for x in mylinklist]
			self._preserve_libs(srcroot, destroot, myfilelist+mylinklist, counter)

		# check for package collisions
		if "collision-protect" in self.settings.features:
			if myfilelist == None:
				myfilelist = listdir(srcroot, recursive=1, filesonly=1, followSymlinks=False)
			if mylinklist == None:
				mylinklist = filter(os.path.islink, [os.path.join(srcroot, x) for x in listdir(srcroot, recursive=1, filesonly=0, followSymlinks=False)])
				mylinklist = [x[len(srcroot):] for x in mylinklist]
			self._collision_protect(srcroot, destroot, otherversions, myfilelist+mylinklist, mylinklist)

		if os.stat(srcroot).st_dev == os.stat(destroot).st_dev:
			""" The merge process may move files out of the image directory,
			which causes invalidation of the .installed flag."""
			try:
				os.unlink(os.path.join(
					os.path.dirname(normalize_path(srcroot)), ".installed"))
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e

		# get old contents info for later unmerging
		oldcontents = self.getcontents()

		self.dbdir = self.dbtmpdir
		self.delete()
		if not os.path.exists(self.dbtmpdir):
			os.makedirs(self.dbtmpdir)

		writemsg_stdout(">>> Merging %s %s %s\n" % (self.mycpv,"to",destroot))

		# run preinst script
		if myebuild is None:
			myebuild = os.path.join(inforoot, self.pkg + ".ebuild")
		a = doebuild(myebuild, "preinst", destroot, self.settings, cleanup=cleanup,
			use_cache=0, tree=self.treetype, mydbapi=mydbapi,
			vartree=self.vartree)

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			writemsg("!!! FAILED preinst: "+str(a)+"\n", noiselevel=-1)
			return a

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# write local package counter for recording
		lcfile = open(os.path.join(self.dbtmpdir, "COUNTER"),"w")
		lcfile.write(str(counter))
		lcfile.close()

		# open CONTENTS file (possibly overwriting old one) for recording
		outfile = open(os.path.join(self.dbtmpdir, "CONTENTS"),"w")

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		conf_mem_file = os.path.join(destroot, CONFIG_MEMORY_FILE)
		cfgfiledict = grabdict(conf_mem_file)
		if self.settings.has_key("NOCONFMEM"):
			cfgfiledict["IGNORE"]=1
		else:
			cfgfiledict["IGNORE"]=0

		# Timestamp for files being merged.  Use time() - 1 in order to prevent
		# a collision with timestamps that are bumped by the utime() call
		# inside isprotected().  This ensures that the new and old config have
		# different timestamps (for the benefit of programs like rsync that
		# that need distiguishable timestamps to detect file changes).
		mymtime = long(time.time() - 1)

		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		prevmask = os.umask(0)
		secondhand = []

		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		if self.mergeme(srcroot, destroot, outfile, secondhand, "", cfgfiledict, mymtime):
			return 1

		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen = 0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that
			# couldn't get merged will be added to thirdhand.

			thirdhand = []
			self.mergeme(srcroot, destroot, outfile, thirdhand, secondhand, cfgfiledict, mymtime)

			#swap hands
			lastlen = len(secondhand)

			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			self.mergeme(srcroot, destroot, outfile, None, secondhand, cfgfiledict, mymtime)

		#restore umask
		os.umask(prevmask)

		#if we opened it, close it
		outfile.flush()
		outfile.close()

		if os.path.exists(self.dbpkgdir):
			writemsg_stdout(">>> Safely unmerging already-installed instance...\n")
			self.dbdir = self.dbpkgdir
			self.unmerge(oldcontents, trimworld=0, ldpath_mtimes=prev_mtimes)
			self.dbdir = self.dbtmpdir
			writemsg_stdout(">>> Original instance of package unmerged safely.\n")

		# We hold both directory locks.
		self.dbdir = self.dbpkgdir
		self.delete()
		movefile(self.dbtmpdir, self.dbpkgdir, mysettings=self.settings)
		contents = self.getcontents()

		#write out our collection of md5sums
		if cfgfiledict.has_key("IGNORE"):
			del cfgfiledict["IGNORE"]

		my_private_path = os.path.join(destroot, PRIVATE_PATH)
		if not os.path.exists(my_private_path):
			os.makedirs(my_private_path)
			os.chown(my_private_path, os.getuid(), portage_gid)
			os.chmod(my_private_path, 02770)

		writedict(cfgfiledict, conf_mem_file)
		del conf_mem_file

		# regenerate reverse NEEDED map
		self.vartree.dbapi.libmap.update()

		#do postinst script
		a = doebuild(myebuild, "postinst", destroot, self.settings, use_cache=0,
			tree=self.treetype, mydbapi=mydbapi, vartree=self.vartree)

		# XXX: Decide how to handle failures here.
		if a != os.EX_OK:
			writemsg("!!! FAILED postinst: "+str(a)+"\n", noiselevel=-1)
			return a

		downgrade = False
		for v in otherversions:
			if pkgcmp(catpkgsplit(self.pkg)[1:], catpkgsplit(v)[1:]) < 0:
				downgrade = True

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=(not downgrade),
			target_root=self.settings["ROOT"], prev_mtimes=prev_mtimes,
			contents=contents)
		#dircache may break autoclean because it remembers the -MERGING-pkg file
		global dircache
		if dircache.has_key(self.dbcatdir):
			del dircache[self.dbcatdir]
		writemsg_stdout(">>> %s %s\n" % (self.mycpv,"merged."))

		# Process ebuild logfiles
		elog_process(self.mycpv, self.settings)
		if "noclean" not in self.settings.features:
			doebuild(myebuild, "clean", destroot, self.settings,
				tree=self.treetype, mydbapi=mydbapi, vartree=self.vartree)
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
		@param thismtime: The current time (typically long(time.time())
		@type thismtime: Long
		@rtype: None or Boolean
		@returns:
		1. True on failure
		2. None otherwise
		
		"""
		from os.path import sep, join
		srcroot = normalize_path(srcroot).rstrip(sep) + sep
		destroot = normalize_path(destroot).rstrip(sep) + sep
		
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if isinstance(stufftomerge, basestring):
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist = listdir(join(srcroot, stufftomerge))
			offset = stufftomerge
		else:
			mergelist = stufftomerge
			offset = ""
		for x in mergelist:
			mysrc = join(srcroot, offset, x)
			mydest = join(destroot, offset, x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest = join(sep, offset, x)
			# stat file once, test using S_* macros many times (faster that way)
			try:
				mystat = os.lstat(mysrc)
			except OSError, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: There appears to be ")+bold("FILE SYSTEM CORRUPTION.")+red(" A file that is listed\n"))
				writemsg(red("!!!        as existing is not capable of being stat'd. If you are using an\n"))
				writemsg(red("!!!        experimental kernel, please boot into a stable one, force an fsck,\n"))
				writemsg(red("!!!        and ensure your filesystem is in a sane state. ")+bold("'shutdown -Fr now'\n"))
				writemsg(red("!!!        File:  ")+str(mysrc)+"\n", noiselevel=-1)
				writemsg(red("!!!        Error: ")+str(e)+"\n", noiselevel=-1)
				sys.exit(1)
			except Exception, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: An unknown error has occurred during the merge process.\n"))
				writemsg(red("!!!        A stat call returned the following error for the following file:"))
				writemsg(    "!!!        Please ensure that your filesystem is intact, otherwise report\n")
				writemsg(    "!!!        this as a portage bug at bugs.gentoo.org. Append 'emerge info'.\n")
				writemsg(    "!!!        File:  "+str(mysrc)+"\n", noiselevel=-1)
				writemsg(    "!!!        Error: "+str(e)+"\n", noiselevel=-1)
				sys.exit(1)


			mymode = mystat[stat.ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydmode = os.lstat(mydest).st_mode
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				#dest file doesn't exist
				mydmode = None

			if stat.S_ISLNK(mymode):
				# we are merging a symbolic link
				myabsto = abssymlink(mysrc)
				if myabsto.startswith(srcroot):
					myabsto = myabsto[len(srcroot):]
				myabsto = myabsto.lstrip(sep)
				myto = os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.startswith(self.settings["D"]):
						myto = myto[len(self.settings["D"]):]
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto = normalize_path(os.path.join(destroot, myabsto))
				if mydmode!=None:
					#destination exists
					if not stat.S_ISLNK(mydmode):
						if stat.S_ISDIR(mydmode):
							# directory in the way: we can't merge a symlink over a directory
							# we won't merge this, continue with next file...
							continue

						if os.path.exists(mysrc) and stat.S_ISDIR(os.stat(mysrc)[stat.ST_MODE]):
							# Kill file blocking installation of symlink to dir #71787
							pass
						elif self.isprotected(mydest):
							# Use md5 of the target in ${D} if it exists...
							try:
								newmd5 = perform_md5(join(srcroot, myabsto))
							except FileNotFound:
								# Maybe the target is merged already.
								try:
									newmd5 = perform_md5(myrealto)
								except FileNotFound:
									newmd5 = None
							mydest = new_protect_filename(mydest, newmd5=newmd5)

				# if secondhand is None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand != None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				mymtime = movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings)
				if mymtime != None:
					writemsg_stdout(">>> %s -> %s\n" % (mydest, myto))
					outfile.write("sym "+myrealdest+" -> "+myto+" "+str(mymtime)+"\n")
				else:
					print "!!! Failed to move file."
					print "!!!", mydest, "->", myto
					sys.exit(1)
			elif stat.S_ISDIR(mymode):
				# we are merging a directory
				if mydmode != None:
					# destination exists

					if bsd_chflags:
						# Save then clear flags on dest.
						dflags = os.lstat(mydest).st_flags
						if dflags != 0:
							bsd_chflags.lchflags(mydest, 0)

					if not os.access(mydest, os.W_OK):
						pkgstuff = pkgsplit(self.pkg)
						writemsg("\n!!! Cannot write to '"+mydest+"'.\n", noiselevel=-1)
						writemsg("!!! Please check permissions and directories for broken symlinks.\n")
						writemsg("!!! You may start the merge process again by using ebuild:\n")
						writemsg("!!! ebuild "+self.settings["PORTDIR"]+"/"+self.cat+"/"+pkgstuff[0]+"/"+self.pkg+".ebuild merge\n")
						writemsg("!!! And finish by running this: env-update\n\n")
						return 1

					if stat.S_ISLNK(mydmode) or stat.S_ISDIR(mydmode):
						# a symlink to an existing directory will work for us; keep it:
						writemsg_stdout("--- %s/\n" % mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
					else:
						# a non-directory and non-symlink-to-directory.  Won't work for us.  Move out of the way.
						if movefile(mydest, mydest+".backup", mysettings=self.settings) is None:
							sys.exit(1)
						print "bak", mydest, mydest+".backup"
						#now create our directory
						if self.settings.selinux_enabled():
							import selinux
							sid = selinux.get_sid(mysrc)
							selinux.secure_mkdir(mydest,sid)
						else:
							os.mkdir(mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
						os.chmod(mydest, mystat[0])
						os.chown(mydest, mystat[4], mystat[5])
						writemsg_stdout(">>> %s/\n" % mydest)
				else:
					#destination doesn't exist
					if self.settings.selinux_enabled():
						import selinux
						sid = selinux.get_sid(mysrc)
						selinux.secure_mkdir(mydest, sid)
					else:
						os.mkdir(mydest)
					os.chmod(mydest, mystat[0])
					os.chown(mydest, mystat[4], mystat[5])
					writemsg_stdout(">>> %s/\n" % mydest)
				outfile.write("dir "+myrealdest+"\n")
				# recurse and merge this directory
				if self.mergeme(srcroot, destroot, outfile, secondhand,
					join(offset, x), cfgfiledict, thismtime):
					return 1
			elif stat.S_ISREG(mymode):
				# we are merging a regular file
				mymd5 = perform_md5(mysrc, calc_prelink=1)
				# calculate config file protection stuff
				mydestdir = os.path.dirname(mydest)
				moveme = 1
				zing = "!!!"
				if mydmode != None:
					# destination file exists
					if stat.S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						moveme = 0
						writemsg_stdout("!!! %s\n" % mydest)
					elif stat.S_ISREG(mydmode) or (stat.S_ISLNK(mydmode) and os.path.exists(mydest) and stat.S_ISREG(os.stat(mydest)[stat.ST_MODE])):
						cfgprot = 0
						# install of destination is blocked by an existing regular file,
						# or by a symlink to an existing regular file;
						# now, config file management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if self.isprotected(mydest):
							# we have a protection path; enable config file management.
							destmd5 = perform_md5(mydest, calc_prelink=1)
							if mymd5 == destmd5:
								#file already in place; simply update mtimes of destination
								os.utime(mydest, (thismtime, thismtime))
								zing = "---"
								moveme = 0
							else:
								if mymd5 == cfgfiledict.get(myrealdest, [None])[0]:
									""" An identical update has previously been
									merged.  Skip it unless the user has chosen
									--noconfmem."""
									zing = "-o-"
									moveme = cfgfiledict["IGNORE"]
									cfgprot = cfgfiledict["IGNORE"]
								else:
									moveme = 1
									cfgprot = 1
							if moveme:
								# Merging a new file, so update confmem.
								cfgfiledict[myrealdest] = [mymd5]
							elif destmd5 == cfgfiledict.get(myrealdest, [None])[0]:
								"""A previously remembered update has been
								accepted, so it is removed from confmem."""
								del cfgfiledict[myrealdest]
						if cfgprot:
							mydest = new_protect_filename(mydest, newmd5=mymd5)

				# whether config protection or not, we merge the new file the
				# same way.  Unless moveme=0 (blocking directory)
				if moveme:
					mymtime = movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings)
					if mymtime is None:
						sys.exit(1)
					zing = ">>>"
				else:
					mymtime = long(time.time())
					# We need to touch the destination so that on --update the
					# old package won't yank the file with it. (non-cfgprot related)
					os.utime(mydest, (mymtime, mymtime))
					zing = "---"
				if self.settings["USERLAND"] == "Darwin" and myrealdest[-2:] == ".a":

					# XXX kludge, can be killed when portage stops relying on
					# md5+mtime, and uses refcounts
					# alright, we've fooled w/ mtime on the file; this pisses off static archives
					# basically internal mtime != file's mtime, so the linker (falsely) thinks
					# the archive is stale, and needs to have it's toc rebuilt.

					myf = open(mydest, "r+")

					# ar mtime field is digits padded with spaces, 12 bytes.
					lms = str(thismtime+5).ljust(12)
					myf.seek(0)
					magic = myf.read(8)
					if magic != "!<arch>\n":
						# not an archive (dolib.a from portage.py makes it here fex)
						myf.close()
					else:
						st = os.stat(mydest)
						while myf.tell() < st.st_size - 12:
							# skip object name
							myf.seek(16, 1)

							# update mtime
							myf.write(lms)

							# skip uid/gid/mperm
							myf.seek(20, 1)

							# read the archive member's size
							x = long(myf.read(10))

							# skip the trailing newlines, and add the potential
							# extra padding byte if it's not an even size
							myf.seek(x + 2 + (x % 2),1)

						# and now we're at the end. yay.
						myf.close()
						mymd5 = perform_md5(mydest, calc_prelink=1)
					os.utime(mydest, (thismtime, thismtime))

				if mymtime != None:
					zing = ">>>"
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				writemsg_stdout("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing = "!!!"
				if mydmode is None:
					# destination doesn't exist
					if movefile(mysrc, mydest, newmtime=thismtime, sstat=mystat, mysettings=self.settings) != None:
						zing = ">>>"
					else:
						sys.exit(1)
				if stat.S_ISFIFO(mymode):
					outfile.write("fif %s\n" % myrealdest)
				else:
					outfile.write("dev %s\n" % myrealdest)
				writemsg_stdout(zing + " " + mydest + "\n")

	def merge(self, mergeroot, inforoot, myroot, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		try:
			self.lockdb()
			return self.treewalk(mergeroot, myroot, inforoot, myebuild,
				cleanup=cleanup, mydbapi=mydbapi, prev_mtimes=prev_mtimes)
		finally:
			self.unlockdb()

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		myfile = open(self.dbdir+"/"+name,"r")
		mydata = myfile.read().split()
		myfile.close()
		return " ".join(mydata)

	def copyfile(self,fname):
		import shutil
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))

	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		myfile = open(self.dbdir+"/"+fname,"r")
		mydata = myfile.read()
		myfile.close()
		return mydata

	def setfile(self,fname,data):
		write_atomic(os.path.join(self.dbdir, fname), data)

	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return []
		myelement = open(self.dbdir+"/"+ename,"r")
		mylines = myelement.readlines()
		myreturn = []
		for x in mylines:
			for y in x[:-1].split():
				myreturn.append(y)
		myelement.close()
		return myreturn

	def setelements(self,mylist,ename):
		myelement = open(self.dbdir+"/"+ename,"w")
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()

	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(os.path.join(self.dbdir, "CATEGORY"))
