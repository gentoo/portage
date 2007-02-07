# portage.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


VERSION="$Rev$"[6:-2] + "-svn"

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

try:
	import sys
except ImportError:
	print "Failed to import sys! Something is _VERY_ wrong with python."
	raise

try:
	import copy, errno, os, re, shutil, time, types
	try:
		import cPickle
	except ImportError:
		import pickle as cPickle

	import stat
	import commands
	from time import sleep
	from random import shuffle
	import UserDict
	if getattr(__builtins__, "set", None) is None:
		from sets import Set as set
	from itertools import chain, izip
except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. These are internal modules for\n")
	sys.stderr.write("!!! python and failure here indicates that you have a problem with python\n")
	sys.stderr.write("!!! itself and thus portage is not able to continue processing.\n\n")

	sys.stderr.write("!!! You might consider starting python with verbose flags to see what has\n")
	sys.stderr.write("!!! gone wrong. Here is the information we got for this exception:\n")
	sys.stderr.write("    "+str(e)+"\n\n");
	raise

bsd_chflags = None
if os.uname()[0] in ["FreeBSD"]:
	try:
		import freebsd as bsd_chflags
	except ImportError:
		pass

try:
	from portage.cache.cache_errors import CacheError
	import portage.cvstree
	import portage.xpak
	import portage.getbinpkg
	import portage.dep
	from portage.dep import dep_getcpv, dep_getkey, get_operator, \
		isjustname, isspecific, isvalidatom, \
		match_from_list, match_to_list, best_match_to_list

	# XXX: This needs to get cleaned up.
	import portage.output
	from portage.output import bold, colorize, green, red, yellow

	import portage.const
	from portage.const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
	  USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
	  PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
	  EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
	  MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
	  DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
	  INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
	  INCREMENTALS, EAPI, MISC_SH_BINARY, REPO_NAME_LOC, REPO_NAME_FILE

	from portage.data import ostype, lchown, userland, secpass, uid, wheelgid, \
	                         portage_uid, portage_gid, userpriv_groups
	from portage.manifest import Manifest

	import portage.util
	from portage.util import atomic_ofstream, apply_secpass_permissions, apply_recursive_permissions, \
		dump_traceback, getconfig, grabdict, grabdict_package, grabfile, grabfile_package, \
		map_dictlist_vals, new_protect_filename, normalize_path, \
		pickle_read, pickle_write, stack_dictlist, stack_dicts, stack_lists, \
		unique_array, varexpand, writedict, writemsg, writemsg_stdout, write_atomic
	import portage.exception
	import portage.gpg
	import portage.locks
	import portage.process
	from portage.process import atexit_register, run_exitfuncs
	from portage.locks import unlockfile,unlockdir,lockfile,lockdir
	import portage.checksum
	from portage.checksum import perform_md5,perform_checksum,prelink_capable
	import portage.eclass_cache
	from portage.localization import _
	from portage.update import dep_transform, fixdbentries, grab_updates, \
		parse_updates, update_config_files, update_dbentries

	# Need these functions directly in portage namespace to not break every external tool in existence
	from portage.versions import best, catpkgsplit, catsplit, pkgcmp, \
		pkgsplit, vercmp, ververify

	# endversion and endversion_keys are for backward compatibility only.
	from portage.versions import endversion_keys
	from portage.versions import suffix_value as endversion

except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the\n")
	sys.stderr.write("!!! portage tree under '/usr/portage/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise


try:
	import portage.selinux as selinux
except OSError, e:
	writemsg("!!! SELinux not loaded: %s\n" % str(e), noiselevel=-1)
	del e
except ImportError:
	pass

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================


def load_mod(name):
	modname = ".".join(name.split(".")[:-1])
	mod = __import__(modname)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def best_from_dict(key, top_dict, key_order, EmptyOnError=1, FullCopy=1, AllowEmpty=1):
	for x in key_order:
		if top_dict.has_key(x) and top_dict[x].has_key(key):
			if FullCopy:
				return copy.deepcopy(top_dict[x][key])
			else:
				return top_dict[x][key]
	if EmptyOnError:
		return ""
	else:
		raise KeyError, "Key not found in list; '%s'" % key

def getcwd():
	"this fixes situations where the current directory doesn't exist"
	try:
		return os.getcwd()
	except OSError: #dir doesn't exist
		os.chdir("/")
		return "/"
getcwd()

def abssymlink(symlink):
	"This reads symlinks, resolving the relative symlinks, and returning the absolute."
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)

dircache = {}
cacheHit=0
cacheMiss=0
cacheStale=0
def cacheddir(my_original_path, ignorecvs, ignorelist, EmptyOnError, followSymlinks=True):
	global cacheHit,cacheMiss,cacheStale
	mypath = normalize_path(my_original_path)
	if dircache.has_key(mypath):
		cacheHit += 1
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cacheMiss += 1
		cached_mtime, list, ftype = -1, [], []
	try:
		pathstat = os.stat(mypath)
		if stat.S_ISDIR(pathstat[stat.ST_MODE]):
			mtime = pathstat[stat.ST_MTIME]
		else:
			raise portage.exception.DirectoryNotFound(mypath)
	except (IOError,OSError,portage.exception.PortageException):
		if EmptyOnError:
			return [], []
		return None, None
	# Python retuns mtime in seconds, so if it was changed in the last few seconds, it could be invalid
	if mtime != cached_mtime or time.time() - mtime < 4:
		if dircache.has_key(mypath):
			cacheStale += 1
		list = os.listdir(mypath)
		ftype = []
		for x in list:
			try:
				if followSymlinks:
					pathstat = os.stat(mypath+"/"+x)
				else:
					pathstat = os.lstat(mypath+"/"+x)

				if stat.S_ISREG(pathstat[stat.ST_MODE]):
					ftype.append(0)
				elif stat.S_ISDIR(pathstat[stat.ST_MODE]):
					ftype.append(1)
				elif stat.S_ISLNK(pathstat[stat.ST_MODE]):
					ftype.append(2)
				else:
					ftype.append(3)
			except (IOError, OSError):
				ftype.append(3)
		dircache[mypath] = mtime, list, ftype

	ret_list = []
	ret_ftype = []
	for x in range(0, len(list)):
		if(ignorecvs and (len(list[x]) > 2) and (list[x][:2]!=".#")):
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])
		elif (list[x] not in ignorelist):
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])

	writemsg("cacheddirStats: H:%d/M:%d/S:%d\n" % (cacheHit, cacheMiss, cacheStale),10)
	return ret_list, ret_ftype

def listdir(mypath, recursive=False, filesonly=False, ignorecvs=False, ignorelist=[], followSymlinks=True,
	EmptyOnError=False, dirsonly=False):
	"""
	Portage-specific implementation of os.listdir

	@param mypath: Path whose contents you wish to list
	@type mypath: String
	@param recursive: Recursively scan directories contained within mypath
	@type recursive: Boolean
	@param filesonly; Only return files, not more directories
	@type filesonly: Boolean
	@param ignorecvs: Ignore CVS directories ('CVS','.svn','SCCS')
	@type ignorecvs: Boolean
	@param ignorelist: List of filenames/directories to exclude
	@type ignorelist: List
	@param followSymlinks: Follow Symlink'd files and directories
	@type followSymlinks: Boolean
	@param EmptyOnError: Return [] if an error occurs.
	@type EmptyOnError: Boolean
	@param dirsonly: Only return directories.
	@type dirsonly: Boolean
	@rtype: List
	@returns: A list of files and directories (or just files or just directories) or an empty list.
	"""

	list, ftype = cacheddir(mypath, ignorecvs, ignorelist, EmptyOnError, followSymlinks)

	if list is None:
		list=[]
	if ftype is None:
		ftype=[]

	if not (filesonly or dirsonly or recursive):
		return list

	if recursive:
		x=0
		while x<len(ftype):
			if ftype[x]==1 and not (ignorecvs and os.path.basename(list[x]) in ('CVS','.svn','SCCS')):
				l,f = cacheddir(mypath+"/"+list[x], ignorecvs, ignorelist, EmptyOnError,
					followSymlinks)

				l=l[:]
				for y in range(0,len(l)):
					l[y]=list[x]+"/"+l[y]
				list=list+l
				ftype=ftype+f
			x+=1
	if filesonly:
		rlist=[]
		for x in range(0,len(ftype)):
			if ftype[x]==0:
				rlist=rlist+[list[x]]
	elif dirsonly:
		rlist = []
		for x in range(0, len(ftype)):
			if ftype[x] == 1:
				rlist = rlist + [list[x]]	
	else:
		rlist=list

	return rlist

def flatten(mytokens):
	"""this function now turns a [1,[2,3]] list into
	a [1,2,3] list and returns it."""
	newlist=[]
	for x in mytokens:
		if type(x)==types.ListType:
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist

#beautiful directed graph object

class digraph:
	def __init__(self):
		"""Create an empty digraph"""
		
		# { node : ( { child : priority } , { parent : priority } ) }
		self.nodes = {}
		self.order = []

	def add(self, node, parent, priority=0):
		"""Adds the specified node with the specified parent.
		
		If the dep is a soft-dep and the node already has a hard
		relationship to the parent, the relationship is left as hard."""
		
		if node not in self.nodes:
			self.nodes[node] = ({}, {})
			self.order.append(node)
		
		if not parent:
			return
		
		if parent not in self.nodes:
			self.nodes[parent] = ({}, {})
			self.order.append(parent)
		
		if parent in self.nodes[node][1]:
			if priority > self.nodes[node][1][parent]:
				self.nodes[node][1][parent] = priority
		else:
			self.nodes[node][1][parent] = priority
		
		if node in self.nodes[parent][0]:
			if priority > self.nodes[parent][0][node]:
				self.nodes[parent][0][node] = priority
		else:
			self.nodes[parent][0][node] = priority

	def remove(self, node):
		"""Removes the specified node from the digraph, also removing
		and ties to other nodes in the digraph. Raises KeyError if the
		node doesn't exist."""
		
		if node not in self.nodes:
			raise KeyError(node)
		
		for parent in self.nodes[node][1]:
			del self.nodes[parent][0][node]
		for child in self.nodes[node][0]:
			del self.nodes[child][1][node]
		
		del self.nodes[node]
		self.order.remove(node)

	def contains(self, node):
		"""Checks if the digraph contains mynode"""
		return node in self.nodes

	def all_nodes(self):
		"""Return a list of all nodes in the graph"""
		return self.order[:]

	def child_nodes(self, node, ignore_priority=None):
		"""Return all children of the specified node"""
		if ignore_priority is None:
			return self.nodes[node][0].keys()
		children = []
		for child, priority in self.nodes[node][0].iteritems():
			if priority > ignore_priority:
				children.append(child)
		return children

	def parent_nodes(self, node):
		"""Return all parents of the specified node"""
		return self.nodes[node][1].keys()

	def leaf_nodes(self, ignore_priority=None):
		"""Return all nodes that have no children
		
		If ignore_soft_deps is True, soft deps are not counted as
		children in calculations."""
		
		leaf_nodes = []
		for node in self.order:
			is_leaf_node = True
			for child in self.nodes[node][0]:
				if self.nodes[node][0][child] > ignore_priority:
					is_leaf_node = False
					break
			if is_leaf_node:
				leaf_nodes.append(node)
		return leaf_nodes

	def root_nodes(self, ignore_priority=None):
		"""Return all nodes that have no parents.
		
		If ignore_soft_deps is True, soft deps are not counted as
		parents in calculations."""
		
		root_nodes = []
		for node in self.order:
			is_root_node = True
			for parent in self.nodes[node][1]:
				if self.nodes[node][1][parent] > ignore_priority:
					is_root_node = False
					break
			if is_root_node:
				root_nodes.append(node)
		return root_nodes

	def is_empty(self):
		"""Checks if the digraph is empty"""
		return len(self.nodes) == 0

	def clone(self):
		clone = digraph()
		clone.nodes = copy.deepcopy(self.nodes)
		clone.order = self.order[:]
		return clone

	# Backward compatibility
	addnode = add
	allnodes = all_nodes
	allzeros = leaf_nodes
	hasnode = contains
	empty = is_empty
	copy = clone

	def delnode(self, node):
		try:
			self.remove(node)
		except KeyError:
			pass

	def firstzero(self):
		leaf_nodes = self.leaf_nodes()
		if leaf_nodes:
			return leaf_nodes[0]
		return None

	def hasallzeros(self, ignore_priority=None):
		return len(self.leaf_nodes(ignore_priority=ignore_priority)) == \
			len(self.order)

	def debug_print(self):
		for node in self.nodes:
			print node,
			if self.nodes[node][0]:
				print "depends on"
			else:
				print "(no children)"
			for child in self.nodes[node][0]:
				print "  ",child,
				print "(%s)" % self.nodes[node][0][child]


_elog_atexit_handlers = []
def elog_process(cpv, mysettings):
	mylogfiles = listdir(mysettings["T"]+"/logging/")
	# shortcut for packages without any messages
	if len(mylogfiles) == 0:
		return
	# exploit listdir() file order so we process log entries in chronological order
	mylogfiles.reverse()
	all_logentries = {}
	for f in mylogfiles:
		msgfunction, msgtype = f.split(".")
		if msgfunction not in portage.const.EBUILD_PHASES:
			writemsg("!!! can't process invalid log file: %s\n" % f,
				noiselevel=-1)
			continue
		if not msgfunction in all_logentries:
			all_logentries[msgfunction] = []
		msgcontent = open(mysettings["T"]+"/logging/"+f, "r").readlines()
		all_logentries[msgfunction].append((msgtype, msgcontent))

	def filter_loglevels(logentries, loglevels):
		# remove unwanted entries from all logentries
		rValue = {}
		loglevels = map(str.upper, loglevels)
		for phase in logentries.keys():
			for msgtype, msgcontent in logentries[phase]:
				if msgtype.upper() in loglevels or "*" in loglevels:
					if not rValue.has_key(phase):
						rValue[phase] = []
					rValue[phase].append((msgtype, msgcontent))
		return rValue
	
	my_elog_classes = set(mysettings.get("PORTAGE_ELOG_CLASSES", "").split())
	default_logentries = filter_loglevels(all_logentries, my_elog_classes)

	# in case the filters matched all messages and no module overrides exist
	if len(default_logentries) == 0 and (not ":" in mysettings.get("PORTAGE_ELOG_SYSTEM", "")):
		return

	def combine_logentries(logentries):
		# generate a single string with all log messages
		rValue = ""
		for phase in portage.const.EBUILD_PHASES:
			if not phase in logentries:
				continue
			for msgtype,msgcontent in logentries[phase]:
				rValue += "%s: %s\n" % (msgtype, phase)
				for line in msgcontent:
					rValue += line
				rValue += "\n"
		return rValue
	
	default_fulllog = combine_logentries(default_logentries)

	# pass the processing to the individual modules
	logsystems = mysettings["PORTAGE_ELOG_SYSTEM"].split()
	for s in logsystems:
		# allow per module overrides of PORTAGE_ELOG_CLASSES
		if ":" in s:
			s, levels = s.split(":", 1)
			levels = levels.split(",")
			mod_logentries = filter_loglevels(all_logentries, levels)
			mod_fulllog = combine_logentries(mod_logentries)
		else:
			mod_logentries = default_logentries
			mod_fulllog = default_fulllog
		if len(mod_logentries) == 0:
			continue
		# - is nicer than _ for module names, so allow people to use it.
		s = s.replace("-", "_")
		try:
			# FIXME: ugly ad.hoc import code
			# TODO:  implement a common portage module loader
			logmodule = __import__("portage.elog_modules.mod_"+s)
			m = getattr(logmodule, "mod_"+s)
			def timeout_handler(signum, frame):
				raise portage.exception.PortageException(
					"Timeout in elog_process for system '%s'" % s)
			import signal
			signal.signal(signal.SIGALRM, timeout_handler)
			# Timeout after one minute (in case something like the mail
			# module gets hung).
			signal.alarm(60)
			try:
				m.process(mysettings, cpv, mod_logentries, mod_fulllog)
			finally:
				signal.alarm(0)
			if hasattr(m, "finalize") and not m.finalize in _elog_atexit_handlers:
				_elog_atexit_handlers.append(m.finalize)
				atexit_register(m.finalize, mysettings)
		except (ImportError, AttributeError), e:
			writemsg("!!! Error while importing logging modules " + \
				"while loading \"mod_%s\":\n" % str(s))
			writemsg("%s\n" % str(e), noiselevel=-1)
		except portage.exception.PortageException, e:
			writemsg("%s\n" % str(e), noiselevel=-1)

	# clean logfiles to avoid repetitions
	for f in mylogfiles:
		try:
			os.unlink(os.path.join(mysettings["T"], "logging", f))
		except OSError:
			pass

#parse /etc/env.d and generate /etc/profile.env

def env_update(makelinks=1, target_root=None, prev_mtimes=None, contents=None):
	if target_root is None:
		global root
		target_root = root
	if prev_mtimes is None:
		global mtimedb
		prev_mtimes = mtimedb["ldpath"]
	envd_dir = os.path.join(target_root, "etc", "env.d")
	portage.util.ensure_dirs(envd_dir, mode=0755)
	fns = listdir(envd_dir, EmptyOnError=1)
	fns.sort()
	templist = []
	for x in fns:
		if len(x) < 3:
			continue
		if not x[0].isdigit() or not x[1].isdigit():
			continue
		if x.startswith(".") or x.endswith("~") or x.endswith(".bak"):
			continue
		templist.append(x)
	fns = templist
	del templist

	space_separated = set(["CONFIG_PROTECT", "CONFIG_PROTECT_MASK"])
	colon_separated = set(["ADA_INCLUDE_PATH", "ADA_OBJECTS_PATH",
		"CLASSPATH", "INFODIR", "INFOPATH", "KDEDIRS", "LDPATH", "MANPATH",
		  "PATH", "PKG_CONFIG_PATH", "PRELINK_PATH", "PRELINK_PATH_MASK",
		  "PYTHONPATH", "ROOTPATH"])

	config_list = []

	for x in fns:
		file_path = os.path.join(envd_dir, x)
		try:
			myconfig = getconfig(file_path, expand=False)
		except portage.exception.ParseError, e:
			writemsg("!!! '%s'\n" % str(e), noiselevel=-1)
			del e
			continue
		if myconfig is None:
			# broken symlink or file removed by a concurrent process
			writemsg("!!! File Not Found: '%s'\n" % file_path, noiselevel=-1)
			continue
		config_list.append(myconfig)
		if "SPACE_SEPARATED" in myconfig:
			space_separated.update(myconfig["SPACE_SEPARATED"].split())
			del myconfig["SPACE_SEPARATED"]
		if "COLON_SEPARATED" in myconfig:
			colon_separated.update(myconfig["COLON_SEPARATED"].split())
			del myconfig["COLON_SEPARATED"]

	env = {}
	specials = {}
	for var in space_separated:
		mylist = []
		for myconfig in config_list:
			if var in myconfig:
				mylist.extend(filter(None, myconfig[var].split()))
				del myconfig[var] # prepare for env.update(myconfig)
		if mylist:
			env[var] = " ".join(mylist)
		specials[var] = mylist

	for var in colon_separated:
		mylist = []
		for myconfig in config_list:
			if var in myconfig:
				mylist.extend(filter(None, myconfig[var].split(":")))
				del myconfig[var] # prepare for env.update(myconfig)
		if mylist:
			env[var] = ":".join(mylist)
		specials[var] = mylist

	for myconfig in config_list:
		"""Cumulative variables have already been deleted from myconfig so that
		they won't be overwritten by this dict.update call."""
		env.update(myconfig)

	ldsoconf_path = os.path.join(target_root, "etc", "ld.so.conf")
	try:
		myld = open(ldsoconf_path)
		myldlines=myld.readlines()
		myld.close()
		oldld=[]
		for x in myldlines:
			#each line has at least one char (a newline)
			if x[0]=="#":
				continue
			oldld.append(x[:-1])
	except (IOError, OSError), e:
		if e.errno != errno.ENOENT:
			raise
		oldld = None

	ld_cache_update=False

	newld = specials["LDPATH"]
	if (oldld!=newld):
		#ld.so.conf needs updating and ldconfig needs to be run
		myfd = atomic_ofstream(ldsoconf_path)
		myfd.write("# ld.so.conf autogenerated by env-update; make all changes to\n")
		myfd.write("# contents of /etc/env.d directory\n")
		for x in specials["LDPATH"]:
			myfd.write(x+"\n")
		myfd.close()
		ld_cache_update=True

	# Update prelink.conf if we are prelink-enabled
	if prelink_capable:
		newprelink = atomic_ofstream(
			os.path.join(target_root, "etc", "prelink.conf"))
		newprelink.write("# prelink.conf autogenerated by env-update; make all changes to\n")
		newprelink.write("# contents of /etc/env.d directory\n")

		for x in ["/bin","/sbin","/usr/bin","/usr/sbin","/lib","/usr/lib"]:
			newprelink.write("-l "+x+"\n");
		for x in specials["LDPATH"]+specials["PATH"]+specials["PRELINK_PATH"]:
			if not x:
				continue
			if x[-1]!='/':
				x=x+"/"
			plmasked=0
			for y in specials["PRELINK_PATH_MASK"]:
				if not y:
					continue
				if y[-1]!='/':
					y=y+"/"
				if y==x[0:len(y)]:
					plmasked=1
					break
			if not plmasked:
				newprelink.write("-h "+x+"\n")
		for x in specials["PRELINK_PATH_MASK"]:
			newprelink.write("-b "+x+"\n")
		newprelink.close()

	mtime_changed = False
	lib_dirs = set()
	for lib_dir in portage.util.unique_array(specials["LDPATH"]+['usr/lib','usr/lib64','usr/lib32','lib','lib64','lib32']):
		x = os.path.join(target_root, lib_dir.lstrip(os.sep))
		try:
			newldpathtime = os.stat(x)[stat.ST_MTIME]
			lib_dirs.add(normalize_path(x))
		except OSError, oe:
			if oe.errno == errno.ENOENT:
				try:
					del prev_mtimes[x]
				except KeyError:
					pass
				# ignore this path because it doesn't exist
				continue
			raise
		if x in prev_mtimes:
			if prev_mtimes[x] == newldpathtime:
				pass
			else:
				prev_mtimes[x] = newldpathtime
				mtime_changed = True
		else:
			prev_mtimes[x] = newldpathtime
			mtime_changed = True

	if mtime_changed:
		ld_cache_update = True

	if makelinks and \
		not ld_cache_update and \
		contents is not None:
		libdir_contents_changed = False
		for mypath, mydata in contents.iteritems():
			if mydata[0] not in ("obj","sym"):
				continue
			head, tail = os.path.split(mypath)
			if head in lib_dirs:
				libdir_contents_changed = True
				break
		if not libdir_contents_changed:
			makelinks = False

	# Only run ldconfig as needed
	if (ld_cache_update or makelinks):
		# ldconfig has very different behaviour between FreeBSD and Linux
		if ostype=="Linux" or ostype.lower().endswith("gnu"):
			# We can't update links if we haven't cleaned other versions first, as
			# an older package installed ON TOP of a newer version will cause ldconfig
			# to overwrite the symlinks we just made. -X means no links. After 'clean'
			# we can safely create links.
			writemsg(">>> Regenerating %setc/ld.so.cache...\n" % target_root)
			if makelinks:
				commands.getstatusoutput("cd / ; /sbin/ldconfig -r '%s'" % target_root)
			else:
				commands.getstatusoutput("cd / ; /sbin/ldconfig -X -r '%s'" % target_root)
		elif ostype in ("FreeBSD","DragonFly"):
			writemsg(">>> Regenerating %svar/run/ld-elf.so.hints...\n" % target_root)
			commands.getstatusoutput(
				"cd / ; /sbin/ldconfig -elf -i -f '%svar/run/ld-elf.so.hints' '%setc/ld.so.conf'" % \
				(target_root, target_root))

	del specials["LDPATH"]

	penvnotice  = "# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.\n"
	penvnotice += "# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES\n"
	cenvnotice  = penvnotice[:]
	penvnotice += "# GO INTO /etc/profile NOT /etc/profile.env\n\n"
	cenvnotice += "# GO INTO /etc/csh.cshrc NOT /etc/csh.env\n\n"

	#create /etc/profile.env for bash support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "profile.env"))
	outfile.write(penvnotice)

	env_keys = [ x for x in env if x != "LDPATH" ]
	env_keys.sort()
	for x in env_keys:
		outfile.write("export %s='%s'\n" % (x, env[x]))
	outfile.close()

	#create /etc/csh.env for (t)csh support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "csh.env"))
	outfile.write(cenvnotice)
	for x in env_keys:
		outfile.write("setenv %s '%s'\n" % (x, env[x]))
	outfile.close()

def ExtractKernelVersion(base_dir):
	"""
	Try to figure out what kernel version we are running
	@param base_dir: Path to sources (usually /usr/src/linux)
	@type base_dir: string
	@rtype: tuple( version[string], error[string])
	@returns:
	1. tuple( version[string], error[string])
	Either version or error is populated (but never both)

	"""
	lines = []
	pathname = os.path.join(base_dir, 'Makefile')
	try:
		f = open(pathname, 'r')
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))

	try:
		for i in range(4):
			lines.append(f.readline())
	except OSError, details:
		return (None, str(details))
	except IOError, details:
		return (None, str(details))

	lines = [l.strip() for l in lines]

	version = ''

	#XXX: The following code relies on the ordering of vars within the Makefile
	for line in lines:
		# split on the '=' then remove annoying whitespace
		items = line.split("=")
		items = [i.strip() for i in items]
		if items[0] == 'VERSION' or \
			items[0] == 'PATCHLEVEL':
			version += items[1]
			version += "."
		elif items[0] == 'SUBLEVEL':
			version += items[1]
		elif items[0] == 'EXTRAVERSION' and \
			items[-1] != items[0]:
			version += items[1]

	# Grab a list of files named localversion* and sort them
	localversions = os.listdir(base_dir)
	for x in range(len(localversions)-1,-1,-1):
		if localversions[x][:12] != "localversion":
			del localversions[x]
	localversions.sort()

	# Append the contents of each to the version string, stripping ALL whitespace
	for lv in localversions:
		version += "".join( " ".join( grabfile( base_dir+ "/" + lv ) ).split() )

	# Check the .config for a CONFIG_LOCALVERSION and append that too, also stripping whitespace
	kernelconfig = getconfig(base_dir+"/.config")
	if kernelconfig and kernelconfig.has_key("CONFIG_LOCALVERSION"):
		version += "".join(kernelconfig["CONFIG_LOCALVERSION"].split())

	return (version,None)

def autouse(myvartree, use_cache=1, mysettings=None):
	"""
	autuse returns a list of USE variables auto-enabled to packages being installed

	@param myvartree: Instance of the vartree class (from /var/db/pkg...)
	@type myvartree: vartree
	@param use_cache: read values from cache
	@type use_cache: Boolean
	@param mysettings: Instance of config
	@type mysettings: config
	@rtype: string
	@returns: A string containing a list of USE variables that are enabled via use.defaults
	"""
	if mysettings is None:
		global settings
		mysettings = settings
	if mysettings.profile_path is None:
		return ""
	myusevars=""
	usedefaults = mysettings.use_defs
	for myuse in usedefaults:
		dep_met = True
		for mydep in usedefaults[myuse]:
			if not myvartree.dep_match(mydep,use_cache=True):
				dep_met = False
				break
		if dep_met:
			myusevars += " "+myuse
	return myusevars

def check_config_instance(test):
	if not test or (str(test.__class__) != 'portage.config'):
		raise TypeError, "Invalid type for config object: %s" % test.__class__

class config:
	"""
	This class encompasses the main portage configuration.  Data is pulled from
	ROOT/PORTDIR/profiles/, from ROOT/etc/make.profile incrementally through all 
	parent profiles as well as from ROOT/PORTAGE_CONFIGROOT/* for user specified
	overrides.
	
	Generally if you need data like USE flags, FEATURES, environment variables,
	virtuals ...etc you look in here.
	"""
	
	def __init__(self, clone=None, mycpv=None, config_profile_path=None,
		config_incrementals=None, config_root=None, target_root=None,
		local_config=True):
		"""
		@param clone: If provided, init will use deepcopy to copy by value the instance.
		@type clone: Instance of config class.
		@param mycpv: CPV to load up (see setcpv), this is the same as calling init with mycpv=None
		and then calling instance.setcpv(mycpv).
		@type mycpv: String
		@param config_profile_path: Configurable path to the profile (usually PROFILE_PATH from portage.const)
		@type config_profile_path: String
		@param config_incrementals: List of incremental variables (usually portage.const.INCREMENTALS)
		@type config_incrementals: List
		@param config_root: path to read local config from (defaults to "/", see PORTAGE_CONFIGROOT)
		@type config_root: String
		@param target_root: __init__ override of $ROOT env variable.
		@type target_root: String
		@param local_config: Enables loading of local config (/etc/portage); used most by repoman to
		ignore local config (keywording and unmasking)
		@type local_config: Boolean
		"""

		debug = os.environ.get("PORTAGE_DEBUG") == "1"

		self.already_in_regenerate = 0

		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []
		self.uvlist = []

		self.virtuals = {}
		self.virts_p = {}
		self.dirVirtuals = None
		self.v_count  = 0

		# Virtuals obtained from the vartree
		self.treeVirtuals = {}
		# Virtuals by user specification. Includes negatives.
		self.userVirtuals = {}
		# Virtual negatives from user specifications.
		self.negVirtuals  = {}

		self.user_profile_dir = None
		self.local_config = local_config

		if clone:
			self.incrementals = copy.deepcopy(clone.incrementals)
			self.profile_path = copy.deepcopy(clone.profile_path)
			self.user_profile_dir = copy.deepcopy(clone.user_profile_dir)
			self.local_config = copy.deepcopy(clone.local_config)

			self.module_priority = copy.deepcopy(clone.module_priority)
			self.modules         = copy.deepcopy(clone.modules)

			self.depcachedir = copy.deepcopy(clone.depcachedir)

			self.packages = copy.deepcopy(clone.packages)
			self.virtuals = copy.deepcopy(clone.virtuals)

			self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
			self.userVirtuals = copy.deepcopy(clone.userVirtuals)
			self.negVirtuals  = copy.deepcopy(clone.negVirtuals)

			self.use_defs = copy.deepcopy(clone.use_defs)
			self.usemask  = copy.deepcopy(clone.usemask)
			self.usemask_list = copy.deepcopy(clone.usemask_list)
			self.pusemask_list = copy.deepcopy(clone.pusemask_list)
			self.useforce      = copy.deepcopy(clone.useforce)
			self.useforce_list = copy.deepcopy(clone.useforce_list)
			self.puseforce_list = copy.deepcopy(clone.puseforce_list)
			self.puse     = copy.deepcopy(clone.puse)
			self.make_defaults_use = copy.deepcopy(clone.make_defaults_use)
			self.pkgprofileuse = copy.deepcopy(clone.pkgprofileuse)
			self.mycpv    = copy.deepcopy(clone.mycpv)

			self.configlist = copy.deepcopy(clone.configlist)
			self.lookuplist = self.configlist[:]
			self.lookuplist.reverse()
			self.configdict = {
				"env.d":     self.configlist[0],
				"pkginternal": self.configlist[1],
				"globals":     self.configlist[2],
				"defaults":    self.configlist[3],
				"conf":        self.configlist[4],
				"pkg":         self.configlist[5],
				"auto":        self.configlist[6],
				"backupenv":   self.configlist[7],
				"env":         self.configlist[8] }
			self.profiles = copy.deepcopy(clone.profiles)
			self.backupenv  = self.configdict["backupenv"]
			self.pusedict   = copy.deepcopy(clone.pusedict)
			self.categories = copy.deepcopy(clone.categories)
			self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
			self.pmaskdict = copy.deepcopy(clone.pmaskdict)
			self.punmaskdict = copy.deepcopy(clone.punmaskdict)
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.pprovideddict = copy.deepcopy(clone.pprovideddict)
			self.dirVirtuals = copy.deepcopy(clone.dirVirtuals)
			self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
			self.features = copy.deepcopy(clone.features)
		else:

			# backupenv is for calculated incremental variables.
			self.backupenv = os.environ.copy()

			def check_var_directory(varname, var):
				if not os.path.isdir(var):
					writemsg(("!!! Error: %s='%s' is not a directory. " + \
						"Please correct this.\n") % (varname, var),
						noiselevel=-1)
					raise portage.exception.DirectoryNotFound(var)

			if config_root is None:
				config_root = "/"

			config_root = \
				normalize_path(config_root).rstrip(os.path.sep) + os.path.sep

			check_var_directory("PORTAGE_CONFIGROOT", config_root)

			self.depcachedir = DEPCACHE_PATH

			if not config_profile_path:
				config_profile_path = \
					os.path.join(config_root, PROFILE_PATH.lstrip(os.path.sep))
				if os.path.isdir(config_profile_path):
					self.profile_path = config_profile_path
				else:
					self.profile_path = None
			else:
				self.profile_path = config_profile_path[:]

			if not config_incrementals:
				writemsg("incrementals not specified to class config\n")
				self.incrementals = copy.deepcopy(portage.const.INCREMENTALS)
			else:
				self.incrementals = copy.deepcopy(config_incrementals)

			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"] = getconfig(
				os.path.join(config_root, MODULES_FILE_PATH.lstrip(os.path.sep)))
			if self.modules["user"] is None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "portage.cache.metadata.database",
				"portdbapi.auxdbmodule":  "portage.cache.flat_hash.database",
			}

			self.usemask=[]
			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ env.d, globals, defaults, conf, pkg, auto, backupenv, env ]
			self.configlist.append({})
			self.configdict["env.d"] = self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkginternal"] = self.configlist[-1]

			# The symlink might not exist or might not be a symlink.
			if self.profile_path is None:
				self.profiles = []
			else:
				self.profiles = []
				def addProfile(currentPath):
					parentsFile = os.path.join(currentPath, "parent")
					if os.path.exists(parentsFile):
						parents = grabfile(parentsFile)
						if not parents:
							raise portage.exception.ParseError(
								"Empty parent file: '%s'" % parents_file)
						for parentPath in parents:
							parentPath = normalize_path(os.path.join(
								currentPath, parentPath))
							if os.path.exists(parentPath):
								addProfile(parentPath)
							else:
								raise portage.exception.ParseError(
									"Parent '%s' not found: '%s'" %  \
									(parentPath, parentsFile))
					self.profiles.append(currentPath)
				addProfile(os.path.realpath(self.profile_path))
			if local_config:
				custom_prof = os.path.join(
					config_root, CUSTOM_PROFILE_PATH.lstrip(os.path.sep))
				if os.path.exists(custom_prof):
					self.user_profile_dir = custom_prof
					self.profiles.append(custom_prof)
				del custom_prof

			self.packages_list = [grabfile_package(os.path.join(x, "packages")) for x in self.profiles]
			self.packages      = stack_lists(self.packages_list, incremental=1)
			del self.packages_list
			#self.packages = grab_stacked("packages", self.profiles, grabfile, incremental_lines=1)

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				mycatpkg=dep_getkey(x)
				if not self.prevmaskdict.has_key(mycatpkg):
					self.prevmaskdict[mycatpkg]=[x]
				else:
					self.prevmaskdict[mycatpkg].append(x)

			# get profile-masked use flags -- INCREMENTAL Child over parent
			self.usemask_list = [grabfile(os.path.join(x, "use.mask")) \
				for x in self.profiles]
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			use_defs_lists = [grabdict(os.path.join(x, "use.defaults")) for x in self.profiles]
			self.use_defs  = stack_dictlist(use_defs_lists, incremental=True)
			del use_defs_lists

			self.pusemask_list = []
			rawpusemask = [grabdict_package(
				os.path.join(x, "package.use.mask")) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawpusemask[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.pusemask_list.append(cpdict)
			del rawpusemask

			self.pkgprofileuse = []
			rawprofileuse = [grabdict_package(
				os.path.join(x, "package.use"), juststrings=True) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawprofileuse[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.pkgprofileuse.append(cpdict)
			del rawprofileuse

			self.useforce_list = [grabfile(os.path.join(x, "use.force")) \
				for x in self.profiles]
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))

			self.puseforce_list = []
			rawpuseforce = [grabdict_package(
				os.path.join(x, "package.use.force")) \
				for x in self.profiles]
			for i in xrange(len(self.profiles)):
				cpdict = {}
				for k, v in rawpuseforce[i].iteritems():
					cpdict.setdefault(dep_getkey(k), {})[k] = v
				self.puseforce_list.append(cpdict)
			del rawpuseforce

			try:
				self.mygcfg   = getconfig(os.path.join(config_root, "etc", "make.globals"))

				if self.mygcfg is None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				if debug:
					raise
				writemsg("!!! %s\n" % (e), noiselevel=-1)
				if not isinstance(e, EnvironmentError):
					writemsg("!!! Incorrect multiline literals can cause " + \
						"this. Do not use them.\n", noiselevel=-1)
				sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.make_defaults_use = []
			self.mygcfg = {}
			if self.profiles:
				try:
					mygcfg_dlists = [getconfig(os.path.join(x, "make.defaults")) for x in self.profiles]
					for cfg in mygcfg_dlists:
						if cfg:
							self.make_defaults_use.append(cfg.get("USE", ""))
						else:
							self.make_defaults_use.append("")
					self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=portage.const.INCREMENTALS, ignore_none=1)
					#self.mygcfg = grab_stacked("make.defaults", self.profiles, getconfig)
					if self.mygcfg is None:
						self.mygcfg = {}
				except SystemExit, e:
					raise
				except Exception, e:
					if debug:
						raise
					writemsg("!!! %s\n" % (e), noiselevel=-1)
					if not isinstance(e, EnvironmentError):
						writemsg("!!! 'rm -Rf /usr/portage/profiles; " + \
							"emerge sync' may fix this. If it does\n",
							noiselevel=-1)
						writemsg("!!! not then please report this to " + \
							"bugs.gentoo.org and, if possible, a dev\n",
								noiselevel=-1)
						writemsg("!!! on #gentoo (irc.freenode.org)\n",
							noiselevel=-1)
					sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			try:
				self.mygcfg = getconfig(
					os.path.join(config_root, MAKE_CONF_FILE.lstrip(os.path.sep)),
					allow_sourcing=True)
				if self.mygcfg is None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				if debug:
					raise
				writemsg("!!! %s\n" % (e), noiselevel=-1)
				if not isinstance(e, EnvironmentError):
					writemsg("!!! Incorrect multiline literals can cause " + \
						"this. Do not use them.\n", noiselevel=-1)
				sys.exit(1)

			# Allow ROOT setting to come from make.conf if it's not overridden
			# by the constructor argument (from the calling environment).  As a
			# special exception for a very common use case, config_root == "/"
			# implies that ROOT in make.conf should be ignored.  That way, the
			# user can chroot into $ROOT and the ROOT setting in make.conf will
			# be automatically ignored (unless config_root is other than "/").
			if config_root != "/" and \
				target_root is None and "ROOT" in self.mygcfg:
				target_root = self.mygcfg["ROOT"]
			
			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

			self.configlist.append(self.backupenv) # XXX Why though?
			self.configdict["backupenv"]=self.configlist[-1]

			self.configlist.append(os.environ.copy())
			self.configdict["env"]=self.configlist[-1]


			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			# Blacklist vars that could interfere with portage internals.
			for blacklisted in ["PKGUSE", "PORTAGE_CONFIGROOT", "ROOT"]:
				for cfg in self.lookuplist:
					try:
						del cfg[blacklisted]
					except KeyError:
						pass
			del blacklisted, cfg

			if target_root is None:
				target_root = "/"

			target_root = \
				normalize_path(target_root).rstrip(os.path.sep) + os.path.sep

			check_var_directory("ROOT", target_root)

			env_d = getconfig(
				os.path.join(target_root, "etc", "profile.env"), expand=False)
			# env_d will be None if profile.env doesn't exist.
			if env_d:
				self.configdict["env.d"].update(env_d)
				# Remove duplicate values so they don't override updated
				# profile.env values later (profile.env is reloaded in each
				# call to self.regenerate).
				for cfg in (self.configdict["backupenv"],
					self.configdict["env"]):
					for k, v in env_d.iteritems():
						try:
							if cfg[k] == v:
								del cfg[k]
						except KeyError:
							pass
				del cfg, k, v

			self["PORTAGE_CONFIGROOT"] = config_root
			self.backup_changes("PORTAGE_CONFIGROOT")
			self["ROOT"] = target_root
			self.backup_changes("ROOT")

			self.pusedict = {}
			self.pkeywordsdict = {}
			self.punmaskdict = {}
			abs_user_config = os.path.join(config_root,
				USER_CONFIG_PATH.lstrip(os.path.sep))

			# locations for "categories" and "arch.list" files
			locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations.extend(self.profiles)

			""" repoman controls PORTDIR_OVERLAY via the environment, so no
			special cases are needed here."""
			overlay_profiles = []
			for ov in self["PORTDIR_OVERLAY"].split():
				ov = normalize_path(ov)
				profiles_dir = os.path.join(ov, "profiles")
				if os.path.isdir(profiles_dir):
					overlay_profiles.append(profiles_dir)
			locations += overlay_profiles
			
			pmask_locations.extend(overlay_profiles)

			if local_config:
				locations.append(abs_user_config)
				pmask_locations.append(abs_user_config)
				pusedict = grabdict_package(
					os.path.join(abs_user_config, "package.use"), recursive=1)
				for key in pusedict.keys():
					cp = dep_getkey(key)
					if not self.pusedict.has_key(cp):
						self.pusedict[cp] = {}
					self.pusedict[cp][key] = pusedict[key]

				#package.keywords
				pkgdict = grabdict_package(
					os.path.join(abs_user_config, "package.keywords"),
					recursive=1)
				for key in pkgdict.keys():
					# default to ~arch if no specific keyword is given
					if not pkgdict[key]:
						mykeywordlist = []
						if self.configdict["defaults"] and self.configdict["defaults"].has_key("ACCEPT_KEYWORDS"):
							groups = self.configdict["defaults"]["ACCEPT_KEYWORDS"].split()
						else:
							groups = []
						for keyword in groups:
							if not keyword[0] in "~-":
								mykeywordlist.append("~"+keyword)
						pkgdict[key] = mykeywordlist
					cp = dep_getkey(key)
					if not self.pkeywordsdict.has_key(cp):
						self.pkeywordsdict[cp] = {}
					self.pkeywordsdict[cp][key] = pkgdict[key]

				#package.unmask
				pkgunmasklines = grabfile_package(
					os.path.join(abs_user_config, "package.unmask"),
					recursive=1)
				for x in pkgunmasklines:
					mycatpkg=dep_getkey(x)
					if self.punmaskdict.has_key(mycatpkg):
						self.punmaskdict[mycatpkg].append(x)
					else:
						self.punmaskdict[mycatpkg]=[x]

			#getting categories from an external file now
			categories = [grabfile(os.path.join(x, "categories")) for x in locations]
			self.categories = stack_lists(categories, incremental=1)
			del categories

			archlist = [grabfile(os.path.join(x, "arch.list")) for x in locations]
			archlist = stack_lists(archlist, incremental=1)
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = " ".join(archlist)

			#package.mask
			pkgmasklines = []
			for x in pmask_locations:
				pkgmasklines.append(grabfile_package(
					os.path.join(x, "package.mask"), recursive=1))
			pkgmasklines = stack_lists(pkgmasklines, incremental=1)

			self.pmaskdict = {}
			for x in pkgmasklines:
				mycatpkg=dep_getkey(x)
				if self.pmaskdict.has_key(mycatpkg):
					self.pmaskdict[mycatpkg].append(x)
				else:
					self.pmaskdict[mycatpkg]=[x]

			pkgprovidedlines = [grabfile(os.path.join(x, "package.provided")) for x in self.profiles]
			pkgprovidedlines = stack_lists(pkgprovidedlines, incremental=1)
			has_invalid_data = False
			for x in range(len(pkgprovidedlines)-1, -1, -1):
				myline = pkgprovidedlines[x]
				if not isvalidatom("=" + myline):
					writemsg("Invalid package name in package.provided:" + \
						" %s\n" % myline, noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
				cpvr = catpkgsplit(pkgprovidedlines[x])
				if not cpvr or cpvr[0] == "null":
					writemsg("Invalid package name in package.provided: "+pkgprovidedlines[x]+"\n",
						noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
				if cpvr[0] == "virtual":
					writemsg("Virtual package in package.provided: %s\n" % \
						myline, noiselevel=-1)
					has_invalid_data = True
					del pkgprovidedlines[x]
					continue
			if has_invalid_data:
				writemsg("See portage(5) for correct package.provided usage.\n",
					noiselevel=-1)
			self.pprovideddict = {}
			for x in pkgprovidedlines:
				cpv=catpkgsplit(x)
				if not x:
					continue
				mycatpkg=dep_getkey(x)
				if self.pprovideddict.has_key(mycatpkg):
					self.pprovideddict[mycatpkg].append(x)
				else:
					self.pprovideddict[mycatpkg]=[x]

			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			if "USE_ORDER" not in self:
				self.backupenv["USE_ORDER"] = "env:pkg:conf:defaults:pkginternal"

			self["PORTAGE_GID"] = str(portage_gid)
			self.backup_changes("PORTAGE_GID")

			if self.get("PORTAGE_DEPCACHEDIR", None):
				self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			self["PORTAGE_DEPCACHEDIR"] = self.depcachedir
			self.backup_changes("PORTAGE_DEPCACHEDIR")

			overlays = self.get("PORTDIR_OVERLAY","").split()
			if overlays:
				new_ov = []
				for ov in overlays:
					ov = normalize_path(ov)
					if os.path.isdir(ov):
						new_ov.append(ov)
					else:
						writemsg("!!! Invalid PORTDIR_OVERLAY" + \
							" (not a dir): '%s'\n" % ov, noiselevel=-1)
				self["PORTDIR_OVERLAY"] = " ".join(new_ov)
				self.backup_changes("PORTDIR_OVERLAY")

			if "CBUILD" not in self and "CHOST" in self:
				self["CBUILD"] = self["CHOST"]
				self.backup_changes("CBUILD")

			self["PORTAGE_BIN_PATH"] = PORTAGE_BIN_PATH
			self.backup_changes("PORTAGE_BIN_PATH")
			self["PORTAGE_PYM_PATH"] = PORTAGE_PYM_PATH
			self.backup_changes("PORTAGE_PYM_PATH")

			for var in ("PORTAGE_INST_UID", "PORTAGE_INST_GID"):
				try:
					self[var] = str(int(self.get(var, "0")))
				except ValueError:
					writemsg(("!!! %s='%s' is not a valid integer.  " + \
						"Falling back to '0'.\n") % (var, self[var]),
						noiselevel=-1)
					self[var] = "0"
				self.backup_changes(var)

			self.regenerate()
			self.features = portage.util.unique_array(self["FEATURES"].split())

			if "gpg" in self.features:
				if not os.path.exists(self["PORTAGE_GPG_DIR"]) or \
					not os.path.isdir(self["PORTAGE_GPG_DIR"]):
					writemsg(colorize("BAD", "PORTAGE_GPG_DIR is invalid." + \
						" Removing gpg from FEATURES.\n"), noiselevel=-1)
					self.features.remove("gpg")

			if not portage.process.sandbox_capable and \
				("sandbox" in self.features or "usersandbox" in self.features):
				if self.profile_path is not None and \
					os.path.realpath(self.profile_path) == \
					os.path.realpath(PROFILE_PATH):
					""" Don't show this warning when running repoman and the
					sandbox feature came from a profile that doesn't belong to
					the user."""
					writemsg(colorize("BAD", "!!! Problem with sandbox" + \
						" binary. Disabling...\n\n"), noiselevel=-1)
				if "sandbox" in self.features:
					self.features.remove("sandbox")
				if "usersandbox" in self.features:
					self.features.remove("usersandbox")

			self.features.sort()
			self["FEATURES"] = " ".join(self.features)
			self.backup_changes("FEATURES")

			self._init_dirs()

		if mycpv:
			self.setcpv(mycpv)

	def _init_dirs(self):
		"""
		Create a few directories that are critical to portage operation
		"""
		if not os.access(self["ROOT"], os.W_OK):
			return

		dir_mode_map = {
			"tmp"             :(-1,          01777, 0),
			"var/tmp"         :(-1,          01777, 0),
			"var/lib/portage" :(portage_gid, 02750, 02),
			"var/cache/edb"   :(portage_gid,  0755, 02)
		}

		for mypath, (gid, mode, modemask) in dir_mode_map.iteritems():
			try:
				mydir = os.path.join(self["ROOT"], mypath)
				portage.util.ensure_dirs(mydir, gid=gid, mode=mode, mask=modemask)
			except portage.exception.PortageException, e:
				writemsg("!!! Directory initialization failed: '%s'\n" % mydir,
					noiselevel=-1)
				writemsg("!!! %s\n" % str(e),
					noiselevel=-1)

	def validate(self):
		"""Validate miscellaneous settings and display warnings if necessary.
		(This code was previously in the global scope of portage.py)"""

		groups = self["ACCEPT_KEYWORDS"].split()
		archlist = self.archlist()
		if not archlist:
			writemsg("--- 'profiles/arch.list' is empty or not available. Empty portage tree?\n")
		else:
			for group in groups:
				if group not in archlist and group[0] != '-':
					writemsg("!!! INVALID ACCEPT_KEYWORDS: %s\n" % str(group),
						noiselevel=-1)

		abs_profile_path = os.path.join(self["PORTAGE_CONFIGROOT"],
			PROFILE_PATH.lstrip(os.path.sep))
		if not os.path.islink(abs_profile_path) and \
			not os.path.exists(os.path.join(abs_profile_path, "parent")) and \
			os.path.exists(os.path.join(self["PORTDIR"], "profiles")):
			writemsg("\a\n\n!!! %s is not a symlink and will probably prevent most merges.\n" % abs_profile_path,
				noiselevel=-1)
			writemsg("!!! It should point into a profile within %s/profiles/\n" % self["PORTDIR"])
			writemsg("!!! (You can safely ignore this message when syncing. It's harmless.)\n\n\n")

		abs_user_virtuals = os.path.join(self["PORTAGE_CONFIGROOT"],
			USER_VIRTUALS_FILE.lstrip(os.path.sep))
		if os.path.exists(abs_user_virtuals):
			writemsg("\n!!! /etc/portage/virtuals is deprecated in favor of\n")
			writemsg("!!! /etc/portage/profile/virtuals. Please move it to\n")
			writemsg("!!! this new location.\n\n")

	def loadVirtuals(self,root):
		"""Not currently used by portage."""
		writemsg("DEPRECATED: portage.config.loadVirtuals\n")
		self.getvirtuals(root)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		try:
			mod = load_mod(best_mod)
		except ImportError:
			dump_traceback(red("Error: Failed to import module '%s'") % best_mod, noiselevel=0)
			sys.exit(1)
		return mod

	def lock(self):
		self.locked = 1

	def unlock(self):
		self.locked = 0

	def modifying(self):
		if self.locked:
			raise Exception, "Configuration is locked."

	def backup_changes(self,key=None):
		self.modifying()
		if key and self.configdict["env"].has_key(key):
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError, "No such key defined in environment: %s" % key

	def reset(self,keeping_pkg=0,use_cache=1):
		"""
		Restore environment from self.backupenv, call self.regenerate()
		@param keeping_pkg: Should we keep the set_cpv() data or delete it.
		@type keeping_pkg: Boolean
		@param use_cache: Should self.regenerate use the cache or not
		@type use_cache: Boolean
		@rype: None
		"""
		self.modifying()
		self.configdict["env"].clear()
		self.configdict["env"].update(self.backupenv)

		self.modifiedkeys = []
		if not keeping_pkg:
			self.mycpv = None
			self.puse = ""
			self.configdict["pkg"].clear()
			self.configdict["pkginternal"].clear()
			self.configdict["defaults"]["USE"] = \
				" ".join(self.make_defaults_use)
			self.usemask  = set(stack_lists(
				self.usemask_list, incremental=True))
			self.useforce  = set(stack_lists(
				self.useforce_list, incremental=True))
		self.regenerate(use_cache=use_cache)

	def load_infodir(self,infodir):
		self.modifying()
		if self.configdict.has_key("pkg"):
			for x in self.configdict["pkg"].keys():
				del self.configdict["pkg"][x]
		else:
			writemsg("No pkg setup for settings instance?\n",
				noiselevel=-1)
			sys.exit(17)

		if os.path.exists(infodir):
			if os.path.exists(infodir+"/environment"):
				self.configdict["pkg"]["PORT_ENV_FILE"] = infodir+"/environment"

			myre = re.compile('^[A-Z]+$')
			null_byte = "\0"
			for filename in listdir(infodir,filesonly=1,EmptyOnError=1):
				if myre.match(filename):
					try:
						file_path = os.path.join(infodir, filename)
						mydata = open(file_path).read().strip()
						if len(mydata) < 2048 or filename == "USE":
							if null_byte in mydata:
								writemsg("!!! Null byte found in metadata " + \
									"file: '%s'\n" % file_path, noiselevel=-1)
								continue
							if filename == "USE":
								binpkg_flags = "-* " + mydata
								self.configdict["pkg"][filename] = binpkg_flags
								self.configdict["env"][filename] = mydata
							else:
								self.configdict["pkg"][filename] = mydata
								self.configdict["env"][filename] = mydata
						# CATEGORY is important because it's used in doebuild
						# to infer the cpv.  If it's corrupted, it leads to
						# strange errors later on, so we'll validate it and
						# print a warning if necessary.
						if filename == "CATEGORY":
							matchobj = re.match("[-a-zA-Z0-9_.+]+", mydata)
							if not matchobj or matchobj.start() != 0 or \
								matchobj.end() != len(mydata):
								writemsg("!!! CATEGORY file is corrupt: %s\n" % \
									os.path.join(infodir, filename), noiselevel=-1)
					except (OSError, IOError):
						writemsg("!!! Unable to read file: %s\n" % infodir+"/"+filename,
							noiselevel=-1)
						pass
			return 1
		return 0

	def setcpv(self, mycpv, use_cache=1, mydb=None):
		"""
		Load a particular CPV into the config, this lets us see the
		Default USE flags for a particular ebuild as well as the USE
		flags from package.use.

		@param mycpv: A cpv to load
		@type mycpv: string
		@param use_cache: Enables caching
		@type use_cache: Boolean
		@param mydb: a dbapi instance that supports aux_get with the IUSE key.
		@type mydb: dbapi or derivative.
		@rtype: None
		"""

		self.modifying()
		if self.mycpv == mycpv:
			return
		has_changed = False
		self.mycpv = mycpv
		cp = dep_getkey(mycpv)
		pkginternaluse = ""
		if mydb:
			pkginternaluse = " ".join([x[1:] \
				for x in mydb.aux_get(mycpv, ["IUSE"])[0].split() \
				if x.startswith("+")])
		if pkginternaluse != self.configdict["pkginternal"].get("USE", ""):
			self.configdict["pkginternal"]["USE"] = pkginternaluse
			has_changed = True
		defaults = []
		for i in xrange(len(self.profiles)):
			defaults.append(self.make_defaults_use[i])
			cpdict = self.pkgprofileuse[i].get(cp, None)
			if cpdict:
				best_match = best_match_to_list(self.mycpv, cpdict.keys())
				if best_match:
					defaults.append(cpdict[best_match])
		defaults = " ".join(defaults)
		if defaults != self.configdict["defaults"].get("USE",""):
			self.configdict["defaults"]["USE"] = defaults
			has_changed = True
		useforce = []
		for i in xrange(len(self.profiles)):
			useforce.append(self.useforce_list[i])
			cpdict = self.puseforce_list[i].get(cp, None)
			if cpdict:
				best_match = best_match_to_list(self.mycpv, cpdict.keys())
				if best_match:
					useforce.append(cpdict[best_match])
		useforce = set(stack_lists(useforce, incremental=True))
		if useforce != self.useforce:
			self.useforce = useforce
			has_changed = True
		usemask = []
		for i in xrange(len(self.profiles)):
			usemask.append(self.usemask_list[i])
			cpdict = self.pusemask_list[i].get(cp, None)
			if cpdict:
				best_match = best_match_to_list(self.mycpv, cpdict.keys())
				if best_match:
					usemask.append(cpdict[best_match])
		usemask = set(stack_lists(usemask, incremental=True))
		if usemask != self.usemask:
			self.usemask = usemask
			has_changed = True
		oldpuse = self.puse
		self.puse = ""
		if self.pusedict.has_key(cp):
			self.pusekey = best_match_to_list(self.mycpv, self.pusedict[cp].keys())
			if self.pusekey:
				self.puse = " ".join(self.pusedict[cp][self.pusekey])
		if oldpuse != self.puse:
			has_changed = True
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE
		# CATEGORY is essential for doebuild calls
		self.configdict["pkg"]["CATEGORY"] = mycpv.split("/")[0]
		if has_changed:
			self.reset(keeping_pkg=1,use_cache=use_cache)

	def setinst(self,mycpv,mydbapi):
		self.modifying()
		if len(self.virtuals) == 0:
			self.getvirtuals()
		# Grab the virtuals this package provides and add them into the tree virtuals.
		provides = mydbapi.aux_get(mycpv, ["PROVIDE"])[0]
		if isinstance(mydbapi, portdbapi):
			myuse = self["USE"]
		else:
			myuse = mydbapi.aux_get(mycpv, ["USE"])[0]
		virts = flatten(portage.dep.use_reduce(portage.dep.paren_reduce(provides), uselist=myuse.split()))

		cp = dep_getkey(mycpv)
		for virt in virts:
			virt = dep_getkey(virt)
			if not self.treeVirtuals.has_key(virt):
				self.treeVirtuals[virt] = []
			# XXX: Is this bad? -- It's a permanent modification
			if cp not in self.treeVirtuals[virt]:
				self.treeVirtuals[virt].append(cp)

		self.virtuals = self.__getvirtuals_compile()


	def regenerate(self,useonly=0,use_cache=1):
		"""
		Regenerate settings
		This involves regenerating valid USE flags, re-expanding USE_EXPAND flags
		re-stacking USE flags (-flag and -*), as well as any other INCREMENTAL
		variables.  This also updates the env.d configdict; useful in case an ebuild
		changes the environment.

		If FEATURES has already stacked, it is not stacked twice.

		@param useonly: Only regenerate USE flags (not any other incrementals)
		@type useonly: Boolean
		@param use_cache: Enable Caching (only for autouse)
		@type use_cache: Boolean
		@rtype: None
		"""

		self.modifying()
		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		# We grab the latest profile.env here since it changes frequently.
		self.configdict["env.d"].clear()
		env_d = getconfig(
			os.path.join(self["ROOT"], "etc", "profile.env"), expand=False)
		if env_d:
			# env_d will be None if profile.env doesn't exist.
			self.configdict["env.d"].update(env_d)

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals = self.incrementals
		myincrementals = set(myincrementals)
		# If self.features exists, it has already been stacked and may have
		# been mutated, so don't stack it again or else any mutations will be
		# reverted.
		if "FEATURES" in myincrementals and hasattr(self, "features"):
			myincrementals.remove("FEATURES")

		if "USE" in myincrementals:
			# Process USE last because it depends on USE_EXPAND which is also
			# an incremental!
			myincrementals.remove("USE")

		for mykey in myincrementals:

			mydbs=self.configlist[:-1]

			myflags=[]
			for curdb in mydbs:
				if mykey not in curdb:
					continue
				#variables are already expanded
				mysplit = curdb[mykey].split()

				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags = []
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(red("USE flags should not start with a '+': %s\n" % x),
							noiselevel=-1)
						x=x[1:]
						if not x:
							continue

					if (x[0]=="-"):
						if (x[1:] in myflags):
							# Unset/Remove it.
							del myflags[myflags.index(x[1:])]
						continue

					# We got here, so add it now.
					if x not in myflags:
						myflags.append(x)

			myflags.sort()
			#store setting in last element of configlist, the original environment:
			if myflags or mykey in self:
				self.configlist[-1][mykey] = " ".join(myflags)
			del myflags

		# Do the USE calculation last because it depends on USE_EXPAND.
		if "auto" in self["USE_ORDER"].split(":"):
			self.configdict["auto"]["USE"] = autouse(
				vartree(root=self["ROOT"], categories=self.categories,
					settings=self),
				use_cache=use_cache, mysettings=self)
		else:
			self.configdict["auto"]["USE"] = ""

		use_expand_protected = []
		use_expand = self.get("USE_EXPAND", "").split()
		for var in use_expand:
			var_lower = var.lower()
			for x in self.get(var, "").split():
				# Any incremental USE_EXPAND variables have already been
				# processed, so leading +/- operators are invalid here.
				if x[0] == "+":
					writemsg(colorize("BAD", "Invalid '+' operator in " + \
						"non-incremental variable '%s': '%s'\n" % (var, x)),
						noiselevel=-1)
					x = x[1:]
				if x[0] == "-":
					writemsg(colorize("BAD", "Invalid '-' operator in " + \
						"non-incremental variable '%s': '%s'\n" % (var, x)),
						noiselevel=-1)
					continue
				mystr = var_lower + "_" + x
				if mystr not in use_expand_protected:
					use_expand_protected.append(mystr)

		if not self.uvlist:
			for x in self["USE_ORDER"].split(":"):
				if x in self.configdict:
					self.uvlist.append(self.configdict[x])
			self.uvlist.reverse()

		myflags = use_expand_protected[:]
		for curdb in self.uvlist:
			if "USE" not in curdb:
				continue
			mysplit = curdb["USE"].split()
			for x in mysplit:
				if x == "-*":
					myflags = use_expand_protected[:]
					continue

				if x[0] == "+":
					writemsg(colorize("BAD", "USE flags should not start " + \
						"with a '+': %s\n" % x), noiselevel=-1)
					x = x[1:]
					if not x:
						continue

				if x[0] == "-":
					try:
						myflags.remove(x[1:])
					except ValueError:
						pass
					continue

				if x not in myflags:
					myflags.append(x)

		myflags = set(myflags)
		myflags.update(self.useforce)

		# FEATURES=test should imply USE=test
		if "test" in self.configlist[-1].get("FEATURES","").split():
			myflags.add("test")

		usesplit = [ x for x in myflags if \
			x not in self.usemask]

		usesplit.sort()

		# Use the calculated USE flags to regenerate the USE_EXPAND flags so
		# that they are consistent.
		for var in use_expand:
			prefix = var.lower() + "_"
			prefix_len = len(prefix)
			expand_flags = set([ x[prefix_len:] for x in usesplit \
				if x.startswith(prefix) ])
			var_split = self.get(var, "").split()
			# Preserve the order of var_split because it can matter for things
			# like LINGUAS.
			var_split = [ x for x in var_split if x in expand_flags ]
			var_split.extend(expand_flags.difference(var_split))
			if var_split or var in self:
				# Don't export empty USE_EXPAND vars unless the user config
				# exports them as empty.  This is required for vars such as
				# LINGUAS, where unset and empty have different meanings.
				self[var] = " ".join(var_split)

		# Pre-Pend ARCH variable to USE settings so '-*' in env doesn't kill arch.
		if self.configdict["defaults"].has_key("ARCH"):
			if self.configdict["defaults"]["ARCH"]:
				if self.configdict["defaults"]["ARCH"] not in usesplit:
					usesplit.insert(0,self.configdict["defaults"]["ARCH"])

		self.configlist[-1]["USE"]= " ".join(usesplit)

		self.already_in_regenerate = 0

	def get_virts_p(self, myroot):
		if self.virts_p:
			return self.virts_p
		virts = self.getvirtuals(myroot)
		if virts:
			myvkeys = virts.keys()
			for x in myvkeys:
				vkeysplit = x.split("/")
				if not self.virts_p.has_key(vkeysplit[1]):
					self.virts_p[vkeysplit[1]] = virts[x]
		return self.virts_p

	def getvirtuals(self, myroot=None):
		"""myroot is now ignored because, due to caching, it has always been
		broken for all but the first call."""
		myroot = self["ROOT"]
		if self.virtuals:
			return self.virtuals

		virtuals_list = []
		for x in self.profiles:
			virtuals_file = os.path.join(x, "virtuals")
			virtuals_dict = grabdict(virtuals_file)
			for k in virtuals_dict.keys():
				if not isvalidatom(k) or dep_getkey(k) != k:
					writemsg("--- Invalid virtuals atom in %s: %s\n" % \
						(virtuals_file, k), noiselevel=-1)
					del virtuals_dict[k]
					continue
				myvalues = virtuals_dict[k]
				for x in myvalues:
					myatom = x
					if x.startswith("-"):
						# allow incrementals
						myatom = x[1:]
					if not isvalidatom(myatom):
						writemsg("--- Invalid atom in %s: %s\n" % \
							(virtuals_file, x), noiselevel=-1)
						myvalues.remove(x)
				if not myvalues:
					del virtuals_dict[k]
			if virtuals_dict:
				virtuals_list.append(virtuals_dict)

		self.dirVirtuals = stack_dictlist(virtuals_list, incremental=True)
		del virtuals_list

		for virt in self.dirVirtuals:
			# Preference for virtuals decreases from left to right.
			self.dirVirtuals[virt].reverse()

		# Repoman does not use user or tree virtuals.
		if self.local_config and not self.treeVirtuals:
			temp_vartree = vartree(myroot, None,
				categories=self.categories, settings=self)
			# Reduce the provides into a list by CP.
			self.treeVirtuals = map_dictlist_vals(getCPFromCPV,temp_vartree.get_all_provides())

		self.virtuals = self.__getvirtuals_compile()
		return self.virtuals

	def __getvirtuals_compile(self):
		"""Stack installed and profile virtuals.  Preference for virtuals
		decreases from left to right.
		Order of preference:
		1. installed and in profile
		2. installed only
		3. profile only
		"""

		# Virtuals by profile+tree preferences.
		ptVirtuals   = {}

		for virt, installed_list in self.treeVirtuals.iteritems():
			profile_list = self.dirVirtuals.get(virt, None)
			if not profile_list:
				continue
			for cp in installed_list:
				if cp in profile_list:
					ptVirtuals.setdefault(virt, [])
					ptVirtuals[virt].append(cp)

		virtuals = stack_dictlist([ptVirtuals, self.treeVirtuals,
			self.dirVirtuals])
		return virtuals

	def __delitem__(self,mykey):
		self.modifying()
		for x in self.lookuplist:
			if x != None:
				if mykey in x:
					del x[mykey]

	def __getitem__(self,mykey):
		match = ''
		for x in self.lookuplist:
			if x is None:
				writemsg("!!! lookuplist is null.\n")
			elif x.has_key(mykey):
				match = x[mykey]
				break
		return match

	def has_key(self,mykey):
		for x in self.lookuplist:
			if x.has_key(mykey):
				return 1
		return 0

	def __contains__(self, mykey):
		"""Called to implement membership test operators (in and not in)."""
		return bool(self.has_key(mykey))

	def setdefault(self, k, x=None):
		if k in self:
			return self[k]
		else:
			self[k] = x
			return x

	def get(self, k, x=None):
		if k in self:
			return self[k]
		else:
			return x

	def keys(self):
		return unique_array(flatten([x.keys() for x in self.lookuplist]))

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		if type(myvalue) != types.StringType:
			raise ValueError("Invalid type being used as a value: '%s': '%s'" % (str(mykey),str(myvalue)))
		self.modifying()
		self.modifiedkeys += [mykey]
		self.configdict["env"][mykey]=myvalue

	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		for x in self.keys():
			myvalue = self[x]
			if not isinstance(myvalue, basestring):
				writemsg("!!! Non-string value in config: %s=%s\n" % \
					(x, myvalue), noiselevel=-1)
				continue
			mydict[x] = myvalue
		if not mydict.has_key("HOME") and mydict.has_key("BUILD_PREFIX"):
			writemsg("*** HOME not set. Setting to "+mydict["BUILD_PREFIX"]+"\n")
			mydict["HOME"]=mydict["BUILD_PREFIX"][:]

		return mydict

	def thirdpartymirrors(self):
		if getattr(self, "_thirdpartymirrors", None) is None:
			profileroots = [os.path.join(self["PORTDIR"], "profiles")]
			for x in self["PORTDIR_OVERLAY"].split():
				profileroots.insert(0, os.path.join(x, "profiles"))
			thirdparty_lists = [grabdict(os.path.join(x, "thirdpartymirrors")) for x in profileroots]
			self._thirdpartymirrors = stack_dictlist(thirdparty_lists, incremental=True)
		return self._thirdpartymirrors

	def archlist(self):
		return flatten([[myarch, "~" + myarch] \
			for myarch in self["PORTAGE_ARCHLIST"].split()])

	def selinux_enabled(self):
		if getattr(self, "_selinux_enabled", None) is None:
			self._selinux_enabled = 0
			if "selinux" in self["USE"].split():
				if "selinux" in globals():
					if selinux.is_selinux_enabled() == 1:
						self._selinux_enabled = 1
					else:
						self._selinux_enabled = 0
				else:
					writemsg("!!! SELinux module not found. Please verify that it was installed.\n",
						noiselevel=-1)
					self._selinux_enabled = 0
			if self._selinux_enabled == 0:
				try:	
					del sys.modules["selinux"]
				except KeyError:
					pass
		return self._selinux_enabled

# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring, mysettings, debug=0, free=0, droppriv=0, sesandbox=0, **keywords):
	"""
	Spawn a subprocess with extra portage-specific options.
	Optiosn include:

	Sandbox: Sandbox means the spawned process will be limited in its ability t
	read and write files (normally this means it is restricted to ${IMAGE}/)
	SElinux Sandbox: Enables sandboxing on SElinux
	Reduced Privileges: Drops privilages such that the process runs as portage:portage
	instead of as root.

	Notes: os.system cannot be used because it messes with signal handling.  Instead we
	use the portage.process spawn* family of functions.

	This function waits for the process to terminate.

	@param mystring: Command to run
	@type mystring: String
	@param mysettings: Either a Dict of Key,Value pairs or an instance of portage.config
	@type mysettings: Dictionary or config instance
	@param debug: Ignored
	@type debug: Boolean
	@param free: Enable sandboxing for this process
	@type free: Boolean
	@param droppriv: Drop to portage:portage when running this command
	@type droppriv: Boolean
	@param sesandbox: Enable SELinux Sandboxing (toggles a context switch)
	@type sesandbox: Boolean
	@param keywords: Extra options encoded as a dict, to be passed to spawn
	@type keywords: Dictionary
	@rtype: Integer
	@returns:
	1. The return code of the spawned process.
	"""

	if type(mysettings) == types.DictType:
		env=mysettings
		keywords["opt_name"]="[ %s ]" % "portage"
	else:
		check_config_instance(mysettings)
		env=mysettings.environ()
		keywords["opt_name"]="[%s]" % mysettings["PF"]

	# The default policy for the sesandbox domain only allows entry (via exec)
	# from shells and from binaries that belong to portage (the number of entry
	# points is minimized).  The "tee" binary is not among the allowed entry
	# points, so it is spawned outside of the sesandbox domain and reads from a
	# pipe between two domains.
	logfile = keywords.get("logfile")
	mypids = []
	pw = None
	if logfile:
		del keywords["logfile"]
		fd_pipes = keywords.get("fd_pipes")
		if fd_pipes is None:
			fd_pipes = {0:0, 1:1, 2:2}
		elif 1 not in fd_pipes or 2 not in fd_pipes:
			raise ValueError(fd_pipes)
		pr, pw = os.pipe()
		mypids.extend(portage.process.spawn(('tee', '-i', '-a', logfile),
			 returnpid=True, fd_pipes={0:pr, 1:fd_pipes[1], 2:fd_pipes[2]}))
		os.close(pr)
		fd_pipes[1] = pw
		fd_pipes[2] = pw
		keywords["fd_pipes"] = fd_pipes

	features = mysettings.features
	# XXX: Negative RESTRICT word
	droppriv=(droppriv and ("userpriv" in features) and not \
		(("nouserpriv" in mysettings["RESTRICT"].split()) or \
		 ("userpriv" in mysettings["RESTRICT"].split())))

	if droppriv and not uid and portage_gid and portage_uid:
		keywords.update({"uid":portage_uid,"gid":portage_gid,"groups":userpriv_groups,"umask":002})

	if not free:
		free=((droppriv and "usersandbox" not in features) or \
			(not droppriv and "sandbox" not in features and "usersandbox" not in features))

	if free:
		keywords["opt_name"] += " bash"
		spawn_func = portage.process.spawn_bash
	else:
		keywords["opt_name"] += " sandbox"
		spawn_func = portage.process.spawn_sandbox

	if sesandbox:
		con = selinux.getcontext()
		con = con.replace(mysettings["PORTAGE_T"], mysettings["PORTAGE_SANDBOX_T"])
		selinux.setexec(con)

	returnpid = keywords.get("returnpid")
	keywords["returnpid"] = True
	try:
		mypids.extend(spawn_func(mystring, env=env, **keywords))
	finally:
		if pw:
			os.close(pw)
		if sesandbox:
			selinux.setexec(None)

	if returnpid:
		return mypids

	while mypids:
		pid = mypids.pop(0)
		retval = os.waitpid(pid, 0)[1]
		portage.process.spawned_pids.remove(pid)
		if retval != os.EX_OK:
			for pid in mypids:
				if os.waitpid(pid, os.WNOHANG) == (0,0):
					os.kill(pid, signal.SIGTERM)
					os.waitpid(pid, 0)
				portage.process.spawned_pids.remove(pid)
			if retval & 0xff:
				return (retval & 0xff) << 8
			return retval >> 8
	return os.EX_OK

def fetch(myuris, mysettings, listonly=0, fetchonly=0, locks_in_subdir=".locks",use_locks=1, try_mirrors=1):
	"fetch files.  Will use digest file if available."

	features = mysettings.features
	# 'nomirror' is bad/negative logic. You Restrict mirroring, not no-mirroring.
	if ("mirror" in mysettings["RESTRICT"].split()) or \
	   ("nomirror" in mysettings["RESTRICT"].split()):
		if ("mirror" in features) and ("lmirror" not in features):
			# lmirror should allow you to bypass mirror restrictions.
			# XXX: This is not a good thing, and is temporary at best.
			print ">>> \"mirror\" mode desired and \"mirror\" restriction found; skipping fetch."
			return 1

	thirdpartymirrors = mysettings.thirdpartymirrors()

	check_config_instance(mysettings)

	custommirrors = grabdict(os.path.join(mysettings["PORTAGE_CONFIGROOT"],
		CUSTOM_MIRRORS_FILE.lstrip(os.path.sep)), recursive=1)

	mymirrors=[]

	if listonly or ("distlocks" not in features):
		use_locks = 0

	fetch_to_ro = 0
	if "skiprocheck" in features:
		fetch_to_ro = 1

	if not os.access(mysettings["DISTDIR"],os.W_OK) and fetch_to_ro:
		if use_locks:
			writemsg(red("!!! For fetching to a read-only filesystem, " + \
				"locking should be turned off.\n"), noiselevel=-1)
			writemsg("!!! This can be done by adding -distlocks to " + \
				"FEATURES in /etc/make.conf\n", noiselevel=-1)
#			use_locks = 0

	# local mirrors are always added
	if custommirrors.has_key("local"):
		mymirrors += custommirrors["local"]

	if ("nomirror" in mysettings["RESTRICT"].split()) or \
	   ("mirror"   in mysettings["RESTRICT"].split()):
		# We don't add any mirrors.
		pass
	else:
		if try_mirrors:
			mymirrors += [x.rstrip("/") for x in mysettings["GENTOO_MIRRORS"].split() if x]

	mydigests = Manifest(
		mysettings["O"], mysettings["DISTDIR"]).getTypeDigests("DIST")

	fsmirrors = []
	for x in range(len(mymirrors)-1,-1,-1):
		if mymirrors[x] and mymirrors[x][0]=='/':
			fsmirrors += [mymirrors[x]]
			del mymirrors[x]

	restrict_fetch = "fetch" in mysettings["RESTRICT"].split()
	custom_local_mirrors = custommirrors.get("local", [])
	if restrict_fetch:
		# With fetch restriction, a normal uri may only be fetched from
		# custom local mirrors (if available).  A mirror:// uri may also
		# be fetched from specific mirrors (effectively overriding fetch
		# restriction, but only for specific mirrors).
		locations = custom_local_mirrors
	else:
		locations = mymirrors

	filedict={}
	primaryuri_indexes={}
	for myuri in myuris:
		myfile=os.path.basename(myuri)
		if not filedict.has_key(myfile):
			filedict[myfile]=[]
			for y in range(0,len(locations)):
				filedict[myfile].append(locations[y]+"/distfiles/"+myfile)
		if myuri[:9]=="mirror://":
			eidx = myuri.find("/", 9)
			if eidx != -1:
				mirrorname = myuri[9:eidx]

				# Try user-defined mirrors first
				if custommirrors.has_key(mirrorname):
					for cmirr in custommirrors[mirrorname]:
						filedict[myfile].append(cmirr+"/"+myuri[eidx+1:])
						# remove the mirrors we tried from the list of official mirrors
						if cmirr.strip() in thirdpartymirrors[mirrorname]:
							thirdpartymirrors[mirrorname].remove(cmirr)
				# now try the official mirrors
				if thirdpartymirrors.has_key(mirrorname):
					shuffle(thirdpartymirrors[mirrorname])

					for locmirr in thirdpartymirrors[mirrorname]:
						filedict[myfile].append(locmirr+"/"+myuri[eidx+1:])

				if not filedict[myfile]:
					writemsg("No known mirror by the name: %s\n" % (mirrorname))
			else:
				writemsg("Invalid mirror definition in SRC_URI:\n", noiselevel=-1)
				writemsg("  %s\n" % (myuri), noiselevel=-1)
		else:
			if restrict_fetch:
				# Only fetch from specific mirrors is allowed.
				continue
			if "primaryuri" in mysettings["RESTRICT"].split():
				# Use the source site first.
				if primaryuri_indexes.has_key(myfile):
					primaryuri_indexes[myfile] += 1
				else:
					primaryuri_indexes[myfile] = 0
				filedict[myfile].insert(primaryuri_indexes[myfile], myuri)
			else:
				filedict[myfile].append(myuri)

	can_fetch=True

	if listonly:
		can_fetch = False

	for var_name in ("FETCHCOMMAND", "RESUMECOMMAND"):
		if not mysettings.get(var_name, None):
			can_fetch = False

	if can_fetch:
		dirmode  = 02070
		filemode =   060
		modemask =    02
		distdir_dirs = [""]
		if "distlocks" in features:
			distdir_dirs.append(".locks")
		try:
			
			for x in distdir_dirs:
				mydir = os.path.join(mysettings["DISTDIR"], x)
				if portage.util.ensure_dirs(mydir, gid=portage_gid, mode=dirmode, mask=modemask):
					writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage.exception.OperationNotPermitted(
							"Failed to apply recursive permissions for the portage group.")
		except portage.exception.PortageException, e:
			if not os.path.isdir(mysettings["DISTDIR"]):
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Directory Not Found: DISTDIR='%s'\n" % mysettings["DISTDIR"], noiselevel=-1)
				writemsg("!!! Fetching will fail!\n", noiselevel=-1)

	if can_fetch and \
		not fetch_to_ro and \
		not os.access(mysettings["DISTDIR"], os.W_OK):
		writemsg("!!! No write access to '%s'\n" % mysettings["DISTDIR"],
			noiselevel=-1)
		can_fetch = False

	if can_fetch and use_locks and locks_in_subdir:
			distlocks_subdir = os.path.join(mysettings["DISTDIR"], locks_in_subdir)
			if not os.access(distlocks_subdir, os.W_OK):
				writemsg("!!! No write access to write to %s.  Aborting.\n" % distlocks_subdir,
					noiselevel=-1)
				return 0
			del distlocks_subdir
	for myfile in filedict.keys():
		"""
		fetched  status
		0        nonexistent
		1        partially downloaded
		2        completely downloaded
		"""
		myfile_path = os.path.join(mysettings["DISTDIR"], myfile)
		fetched=0
		file_lock = None
		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		else:
			if use_locks and can_fetch:
				if locks_in_subdir:
					file_lock = portage.locks.lockfile(mysettings["DISTDIR"]+"/"+locks_in_subdir+"/"+myfile,wantnewlockfile=1)
				else:
					file_lock = portage.locks.lockfile(mysettings["DISTDIR"]+"/"+myfile,wantnewlockfile=1)
		try:
			if not listonly:
				if fsmirrors and not os.path.exists(myfile_path):
					for mydir in fsmirrors:
						mirror_file = os.path.join(mydir, myfile)
						try:
							shutil.copyfile(mirror_file, myfile_path)
							writemsg(_("Local mirror has file:" + \
								" %(file)s\n" % {"file":myfile}))
							break
						except (IOError, OSError), e:
							if e.errno != errno.ENOENT:
								raise
							del e

				try:
					mystat = os.stat(myfile_path)
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
				else:
					try:
						apply_secpass_permissions(
							myfile_path, gid=portage_gid, mode=0664, mask=02,
							stat_cached=mystat)
					except portage.exception.PortageException, e:
						if not os.access(myfile_path, os.R_OK):
							writemsg("!!! Failed to adjust permissions:" + \
								" %s\n" % str(e), noiselevel=-1)
					if myfile not in mydigests:
						# We don't have a digest, but the file exists.  We must
						# assume that it is fully downloaded.
						continue
					else:
						if mystat.st_size < mydigests[myfile]["size"] and \
							not restrict_fetch:
							fetched = 1 # Try to resume this download.
						else:
							verified_ok, reason = portage.checksum.verify_all(
								myfile_path, mydigests[myfile])
							if not verified_ok:
								writemsg("!!! Previously fetched" + \
									" file: '%s'\n" % myfile, noiselevel=-1)
								writemsg("!!! Reason: %s\n" % reason[0],
									noiselevel=-1)
								writemsg(("!!! Got:      %s\n" + \
									"!!! Expected: %s\n") % \
									(reason[1], reason[2]), noiselevel=-1)
								if can_fetch and not restrict_fetch:
									writemsg("Refetching...\n\n",
										noiselevel=-1)
									os.unlink(myfile_path)
							else:
								eout = portage.output.EOutput()
								eout.quiet = \
									mysettings.get("PORTAGE_QUIET", None) == "1"
								for digest_name in mydigests[myfile]:
									eout.ebegin(
										"%s %s ;-)" % (myfile, digest_name))
									eout.eend(0)
								continue # fetch any remaining files

			for loc in filedict[myfile]:
				if listonly:
					writemsg_stdout(loc+" ", noiselevel=-1)
					continue
				# allow different fetchcommands per protocol
				protocol = loc[0:loc.find("://")]
				if mysettings.has_key("FETCHCOMMAND_"+protocol.upper()):
					fetchcommand=mysettings["FETCHCOMMAND_"+protocol.upper()]
				else:
					fetchcommand=mysettings["FETCHCOMMAND"]
				if mysettings.has_key("RESUMECOMMAND_"+protocol.upper()):
					resumecommand=mysettings["RESUMECOMMAND_"+protocol.upper()]
				else:
					resumecommand=mysettings["RESUMECOMMAND"]

				fetchcommand=fetchcommand.replace("${DISTDIR}",mysettings["DISTDIR"])
				resumecommand=resumecommand.replace("${DISTDIR}",mysettings["DISTDIR"])

				if not can_fetch:
					if fetched != 2:
						if fetched == 0:
							writemsg("!!! File %s isn't fetched but unable to get it.\n" % myfile,
								noiselevel=-1)
						else:
							writemsg("!!! File %s isn't fully fetched, but unable to complete it\n" % myfile,
								noiselevel=-1)
						for var_name in ("FETCHCOMMAND", "RESUMECOMMAND"):
							if not mysettings.get(var_name, None):
								writemsg(("!!! %s is unset.  It should " + \
								"have been defined in /etc/make.globals.\n") \
								 % var_name, noiselevel=-1)
						return 0
					else:
						continue

				if fetched != 2:
					#we either need to resume or start the download
					#you can't use "continue" when you're inside a "try" block
					if fetched==1:
						#resume mode:
						writemsg(">>> Resuming download...\n")
						locfetch=resumecommand
					else:
						#normal mode:
						locfetch=fetchcommand
					writemsg_stdout(">>> Downloading '%s'\n" % \
						re.sub(r'//(.+):.+@(.+)/',r'//\1:*password*@\2/', loc))
					myfetch=locfetch.replace("${URI}",loc)
					myfetch=myfetch.replace("${FILE}",myfile)

					spawn_keywords = {}
					if "userfetch" in mysettings.features and \
						os.getuid() == 0 and portage_gid and portage_uid:
						spawn_keywords.update({
							"uid"    : portage_uid,
							"gid"    : portage_gid,
							"groups" : userpriv_groups,
							"umask"  : 002})

					try:

						if mysettings.selinux_enabled():
							con = selinux.getcontext()
							con = con.replace(mysettings["PORTAGE_T"], mysettings["PORTAGE_FETCH_T"])
							selinux.setexec(con)

						myret = portage.process.spawn_bash(myfetch,
							env=mysettings.environ(), **spawn_keywords)

						if mysettings.selinux_enabled():
							selinux.setexec(None)

					finally:
						try:
							apply_secpass_permissions(myfile_path,
								gid=portage_gid, mode=0664, mask=02)
						except portage.exception.FileNotFound, e:
							pass
						except portage.exception.PortageException, e:
							if not os.access(myfile_path, os.R_OK):
								writemsg("!!! Failed to adjust permissions:" + \
									" %s\n" % str(e), noiselevel=-1)

					if mydigests!=None and mydigests.has_key(myfile):
						try:
							mystat = os.stat(myfile_path)
						except OSError, e:
							if e.errno != errno.ENOENT:
								raise
							del e
							fetched = 0
						else:
							# no exception?  file exists. let digestcheck() report
							# an appropriately for size or checksum errors
							if (mystat[stat.ST_SIZE]<mydigests[myfile]["size"]):
								# Fetch failed... Try the next one... Kill 404 files though.
								if (mystat[stat.ST_SIZE]<100000) and (len(myfile)>4) and not ((myfile[-5:]==".html") or (myfile[-4:]==".htm")):
									html404=re.compile("<title>.*(not found|404).*</title>",re.I|re.M)
									if html404.search(open(mysettings["DISTDIR"]+"/"+myfile).read()):
										try:
											os.unlink(mysettings["DISTDIR"]+"/"+myfile)
											writemsg(">>> Deleting invalid distfile. (Improper 404 redirect from server.)\n")
											fetched = 0
											continue
										except (IOError, OSError):
											pass
								fetched = 1
								continue
							if not fetchonly:
								fetched=2
								break
							else:
								# File is the correct size--check the checksums for the fetched
								# file NOW, for those users who don't have a stable/continuous
								# net connection. This way we have a chance to try to download
								# from another mirror...
								verified_ok,reason = portage.checksum.verify_all(mysettings["DISTDIR"]+"/"+myfile, mydigests[myfile])
								if not verified_ok:
									print reason
									writemsg("!!! Fetched file: "+str(myfile)+" VERIFY FAILED!\n",
										noiselevel=-1)
									writemsg("!!! Reason: "+reason[0]+"\n",
										noiselevel=-1)
									writemsg("!!! Got:      %s\n!!! Expected: %s\n" % \
										(reason[1], reason[2]), noiselevel=-1)
									writemsg("Removing corrupt distfile...\n", noiselevel=-1)
									os.unlink(mysettings["DISTDIR"]+"/"+myfile)
									fetched=0
								else:
									eout = portage.output.EOutput()
									eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
									for x_key in mydigests[myfile].keys():
										eout.ebegin("%s %s ;-)" % (myfile, x_key))
										eout.eend(0)
									fetched=2
									break
					else:
						if not myret:
							fetched=2
							break
						elif mydigests!=None:
							writemsg("No digest file available and download failed.\n\n",
								noiselevel=-1)
		finally:
			if use_locks and file_lock:
				portage.locks.unlockfile(file_lock)

		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		if fetched != 2:
			if restrict_fetch:
				print "\n!!!", mysettings["CATEGORY"] + "/" + \
					mysettings["PF"], "has fetch restriction turned on."
				print "!!! This probably means that this " + \
					"ebuild's files must be downloaded"
				print "!!! manually.  See the comments in" + \
					" the ebuild for more information.\n"
				spawn(EBUILD_SH_BINARY + " nofetch", mysettings)
			elif listonly:
				continue
			elif not filedict[myfile]:
				writemsg("Warning: No mirrors available for file" + \
					" '%s'\n" % (myfile), noiselevel=-1)
			else:
				writemsg("!!! Couldn't download '%s'. Aborting.\n" % myfile,
					noiselevel=-1)
			return 0
	return 1

def digestgen(myarchives, mysettings, overwrite=1, manifestonly=0, myportdb=None):
	"""
	Generates a digest file if missing.  Assumes all files are available.
	DEPRECATED: this now only is a compability wrapper for 
	            portage.manifest.Manifest()
	NOTE: manifestonly and overwrite are useless with manifest2 and
	      are therefore ignored."""
	if myportdb is None:
		writemsg("Warning: myportdb not specified to digestgen\n")
		global portdb
		myportdb = portdb
	global _doebuild_manifest_exempt_depend
	try:
		_doebuild_manifest_exempt_depend += 1
		distfiles_map = {}
		fetchlist_dict = FetchlistDict(mysettings["O"], mysettings, myportdb)
		for cpv in fetchlist_dict:
			try:
				for myfile in fetchlist_dict[cpv]:
					distfiles_map.setdefault(myfile, []).append(cpv)
			except portage_exception.InvalidDependString, e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Invalid SRC_URI for '%s'.\n" % cpv, noiselevel=-1)
				del e
				return 0
		mf = Manifest(mysettings["O"], mysettings["DISTDIR"],
			fetchlist_dict=fetchlist_dict)
		# Don't require all hashes since that can trigger excessive
		# fetches when sufficient digests already exist.  To ease transition
		# while Manifest 1 is being removed, only require hashes that will
		# exist before and after the transition.
		required_hash_types = set(portage.const.MANIFEST1_HASH_FUNCTIONS
			).intersection(portage.const.MANIFEST2_HASH_FUNCTIONS)
		required_hash_types.add(portage.const.MANIFEST2_REQUIRED_HASH)
		required_hash_types.add("size")
		dist_hashes = mf.fhashdict.get("DIST", {})
		missing_hashes = set()
		for myfile in distfiles_map:
			myhashes = dist_hashes.get(myfile)
			if not myhashes:
				missing_hashes.add(myfile)
				continue
			if required_hash_types.difference(myhashes):
				missing_hashes.add(myfile)
		if missing_hashes:
			missing_files = []
			for myfile in missing_hashes:
				try:
					os.stat(os.path.join(mysettings["DISTDIR"], myfile))
				except OSError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
					missing_files.append(myfile)
			if missing_files:
				mytree = os.path.realpath(os.path.dirname(
					os.path.dirname(mysettings["O"])))
				fetch_settings = config(clone=mysettings)
				debug = mysettings.get("PORTAGE_DEBUG") == "1"
				for myfile in missing_files:
					success = False
					for cpv in distfiles_map[myfile]:
						myebuild = os.path.join(mysettings["O"],
							catsplit(cpv)[1] + ".ebuild")
						# for RESTRICT=fetch, mirror, etc...
						doebuild_environment(myebuild, "fetch",
							mysettings["ROOT"], fetch_settings,
							debug, 1, myportdb)
						alluris, aalist = myportdb.getfetchlist(
							cpv, mytree=mytree, all=True,
							mysettings=fetch_settings)
						myuris = [uri for uri in alluris \
							if os.path.basename(uri) == myfile]
						if fetch(myuris, fetch_settings):
							success = True
							break
					if not success:
						writemsg(("!!! File %s doesn't exist, can't update " + \
							"Manifest\n") % myfile, noiselevel=-1)
						return 0
		writemsg_stdout(">>> Creating Manifest for %s\n" % mysettings["O"])
		try:
			mf.create(requiredDistfiles=myarchives,
				assumeDistHashesSometimes=True,
				assumeDistHashesAlways=(
				"assume-digests" in mysettings.features))
		except portage.exception.FileNotFound, e:
			writemsg(("!!! File %s doesn't exist, can't update " + \
				"Manifest\n") % e, noiselevel=-1)
			return 0
		mf.write(sign=False)
		if "assume-digests" not in mysettings.features:
			distlist = mf.fhashdict.get("DIST", {}).keys()
			distlist.sort()
			auto_assumed = []
			for filename in distlist:
				if not os.path.exists(
					os.path.join(mysettings["DISTDIR"], filename)):
					auto_assumed.append(filename)
			if auto_assumed:
				mytree = os.path.realpath(
					os.path.dirname(os.path.dirname(mysettings["O"])))
				cp = os.path.sep.join(mysettings["O"].split(os.path.sep)[-2:])
				pkgs = myportdb.cp_list(cp, mytree=mytree)
				pkgs.sort()
				writemsg_stdout("  digest.assumed" + portage.output.colorize("WARN",
					str(len(auto_assumed)).rjust(18)) + "\n")
				for pkg_key in pkgs:
					fetchlist = myportdb.getfetchlist(pkg_key,
						mysettings=mysettings, all=True, mytree=mytree)[1]
					pv = pkg_key.split("/")[1]
					for filename in auto_assumed:
						if filename in fetchlist:
							writemsg_stdout(
								"   digest-%s::%s\n" % (pv, filename))
		return 1
	finally:
		_doebuild_manifest_exempt_depend -= 1

def digestParseFile(myfilename, mysettings=None):
	"""(filename) -- Parses a given file for entries matching:
	<checksumkey> <checksum_hex_string> <filename> <filesize>
	Ignores lines that don't start with a valid checksum identifier
	and returns a dict with the filenames as keys and {checksumkey:checksum}
	as the values.
	DEPRECATED: this function is now only a compability wrapper for
	            portage.manifest.Manifest()."""

	mysplit = myfilename.split(os.sep)
	if mysplit[-2] == "files" and mysplit[-1].startswith("digest-"):
		pkgdir = os.sep + os.sep.join(mysplit[:-2]).strip(os.sep)
	elif mysplit[-1] == "Manifest":
		pkgdir = os.sep + os.sep.join(mysplit[:-1]).strip(os.sep)

	if mysettings is None:
		global settings
		mysettings = config(clone=settings)

	return Manifest(pkgdir, mysettings["DISTDIR"]).getDigests()

def digestcheck(myfiles, mysettings, strict=0, justmanifest=0):
	"""Verifies checksums.  Assumes all files have been downloaded.
	DEPRECATED: this is now only a compability wrapper for 
	            portage.manifest.Manifest()."""
	if not strict:
		return 1
	pkgdir = mysettings["O"]
	manifest_path = os.path.join(pkgdir, "Manifest")
	if not os.path.exists(manifest_path):
		writemsg("!!! Manifest file not found: '%s'\n" % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
	mf = Manifest(pkgdir, mysettings["DISTDIR"])
	eout = portage.output.EOutput()
	eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
	try:
		eout.ebegin("checking ebuild checksums ;-)")
		mf.checkTypeHashes("EBUILD")
		eout.eend(0)
		eout.ebegin("checking auxfile checksums ;-)")
		mf.checkTypeHashes("AUX")
		eout.eend(0)
		eout.ebegin("checking miscfile checksums ;-)")
		mf.checkTypeHashes("MISC", ignoreMissingFiles=True)
		eout.eend(0)
		for f in myfiles:
			eout.ebegin("checking %s ;-)" % f)
			mf.checkFileHashes(mf.findFile(f), f)
			eout.eend(0)
	except KeyError, e:
		eout.eend(1)
		writemsg("\n!!! Missing digest for %s\n" % str(e), noiselevel=-1)
		return 0
	except portage.exception.FileNotFound, e:
		eout.eend(1)
		writemsg("\n!!! A file listed in the Manifest could not be found: %s\n" % str(e),
			noiselevel=-1)
		return 0
	except portage.exception.DigestException, e:
		eout.eend(1)
		writemsg("\n!!! Digest verification failed:\n", noiselevel=-1)
		writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
		writemsg("!!! Reason: %s\n" % e.value[1], noiselevel=-1)
		writemsg("!!! Got: %s\n" % e.value[2], noiselevel=-1)
		writemsg("!!! Expected: %s\n" % e.value[3], noiselevel=-1)
		return 0
	# Make sure that all of the ebuilds are actually listed in the Manifest.
	for f in os.listdir(pkgdir):
		if f.endswith(".ebuild") and not mf.hasFile("EBUILD", f):
			writemsg("!!! A file is not listed in the Manifest: '%s'\n" % \
				os.path.join(pkgdir, f), noiselevel=-1)
			return 0
	""" epatch will just grab all the patches out of a directory, so we have to
	make sure there aren't any foreign files that it might grab."""
	filesdir = os.path.join(pkgdir, "files")
	for parent, dirs, files in os.walk(filesdir):
		for d in dirs:
			if d.startswith(".") or d == "CVS":
				dirs.remove(d)
		for f in files:
			if f.startswith("."):
				continue
			f = os.path.join(parent, f)[len(filesdir) + 1:]
			file_type = mf.findFile(f)
			if file_type != "AUX" and not f.startswith("digest-"):
				writemsg("!!! A file is not listed in the Manifest: '%s'\n" % \
					os.path.join(filesdir, f), noiselevel=-1)
				return 0
	return 1

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo,actionmap,mysettings,debug,alwaysdep=0,logfile=None):
	if alwaysdep or "noauto" not in mysettings.features:
		# process dependency first
		if "dep" in actionmap[mydo].keys():
			retval=spawnebuild(actionmap[mydo]["dep"],actionmap,mysettings,debug,alwaysdep=alwaysdep,logfile=logfile)
			if retval:
				return retval
	kwargs = actionmap[mydo]["args"]
	mysettings["EBUILD_PHASE"] = mydo
	phase_retval = spawn(actionmap[mydo]["cmd"] % mydo, mysettings, debug=debug, logfile=logfile, **kwargs)
	mysettings["EBUILD_PHASE"] = ""

	if not kwargs["droppriv"] and secpass >= 2:
		""" Privileged phases may have left files that need to be made
		writable to a less privileged user."""
		apply_recursive_permissions(mysettings["T"],
			uid=portage_uid, gid=portage_gid, dirmode=070, dirmask=0,
			filemode=060, filemask=0)

	if phase_retval == os.EX_OK:
		if mydo == "install":
			# User and group bits that match the "portage" user or group are
			# automatically mapped to PORTAGE_INST_UID and PORTAGE_INST_GID if
			# necessary.  The chown system call may clear S_ISUID and S_ISGID
			# bits, so those bits are restored if necessary.
			inst_uid = int(mysettings["PORTAGE_INST_UID"])
			inst_gid = int(mysettings["PORTAGE_INST_GID"])
			for parent, dirs, files in os.walk(mysettings["D"]):
				for fname in chain(dirs, files):
					fpath = os.path.join(parent, fname)
					mystat = os.lstat(fpath)
					if mystat.st_uid != portage_uid and \
						mystat.st_gid != portage_gid:
						continue
					myuid = -1
					mygid = -1
					if mystat.st_uid == portage_uid:
						myuid = inst_uid
					if mystat.st_gid == portage_gid:
						mygid = inst_gid
					apply_secpass_permissions(fpath, uid=myuid, gid=mygid,
						mode=mystat.st_mode, stat_cached=mystat,
						follow_links=False)
			mycommand = " ".join([MISC_SH_BINARY, "install_qa_check", "install_symlink_html_docs"])
			qa_retval = spawn(mycommand, mysettings, debug=debug, logfile=logfile, **kwargs)
			if qa_retval:
				writemsg("!!! install_qa_check failed; exiting.\n",
					noiselevel=-1)
			return qa_retval
	return phase_retval


def eapi_is_supported(eapi):
	return str(eapi).strip() == str(portage.const.EAPI).strip()

def doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, mydbapi):

	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if mysettings.configdict["pkg"].has_key("CATEGORY"):
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(normalize_path(os.path.join(pkg_dir, "..")))
	mypv = os.path.basename(ebuild_path)[:-7]	
	mycpv = cat+"/"+mypv
	mysplit=pkgsplit(mypv,silent=0)
	if mysplit is None:
		raise portage.exception.IncorrectParameter(
			"Invalid ebuild path: '%s'" % myebuild)

	if mydo != "depend":
		"""For performance reasons, setcpv only triggers reset when it
		detects a package-specific change in config.  For the ebuild
		environment, a reset call is forced in order to ensure that the
		latest env.d variables are used."""
		mysettings.reset(use_cache=use_cache)
		mysettings.setcpv(mycpv, use_cache=use_cache, mydb=mydbapi)

	mysettings["EBUILD_PHASE"] = mydo

	mysettings["PORTAGE_MASTER_PID"] = str(os.getpid())

	# We are disabling user-specific bashrc files.
	mysettings["BASH_ENV"] = INVALID_ENV_FILE

	if debug: # Otherwise it overrides emerge's settings.
		# We have no other way to set debug... debug can't be passed in
		# due to how it's coded... Don't overwrite this so we can use it.
		mysettings["PORTAGE_DEBUG"] = "1"

	mysettings["ROOT"]     = myroot
	mysettings["STARTDIR"] = getcwd()

	mysettings["EBUILD"]   = ebuild_path
	mysettings["O"]        = pkg_dir
	mysettings.configdict["pkg"]["CATEGORY"] = cat
	mysettings["FILESDIR"] = pkg_dir+"/files"
	mysettings["PF"]       = mypv

	mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"
	mysettings["SANDBOX_LOG"] = mycpv.replace("/", "_-_")

	mysettings["PROFILE_PATHS"] = "\n".join(mysettings.profiles)+"\n"+CUSTOM_PROFILE_PATH
	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if portage.util.noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mydo != "depend":
		eapi, mysettings["INHERITED"], mysettings["SLOT"], mysettings["RESTRICT"]  = \
			mydbapi.aux_get(mycpv, ["EAPI", "INHERITED", "SLOT", "RESTRICT"])
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise portage.exception.UnsupportedAPIException(mycpv, eapi)
		mysettings["PORTAGE_RESTRICT"] = " ".join(flatten(
			portage.dep.use_reduce(portage.dep.paren_reduce(
			mysettings["RESTRICT"]), uselist=mysettings["USE"].split())))

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	if mysettings.has_key("PATH"):
		mysplit=mysettings["PATH"].split(":")
	else:
		mysplit=[]
	if PORTAGE_BIN_PATH not in mysplit:
		mysettings["PATH"]=PORTAGE_BIN_PATH+":"+mysettings["PATH"]

	# Sandbox needs cannonical paths.
	mysettings["PORTAGE_TMPDIR"] = os.path.realpath(
		mysettings["PORTAGE_TMPDIR"])
	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/binpkgs"
	
	# Package {pre,post}inst and {pre,post}rm may overlap, so they must have separate
	# locations in order to prevent interference.
	if mydo in ("unmerge", "prerm", "postrm", "cleanrm"):
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(
			mysettings["PKG_TMPDIR"],
			mysettings["CATEGORY"], mysettings["PF"])
	else:
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(
			mysettings["BUILD_PREFIX"],
			mysettings["CATEGORY"], mysettings["PF"])

	mysettings["HOME"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "homedir")
	mysettings["WORKDIR"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "work")
	mysettings["D"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "image") + os.sep
	mysettings["T"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "temp")

	mysettings["PORTAGE_BASHRC"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_FILE.lstrip(os.path.sep))

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if (mydo!="depend") or not mysettings.has_key("KV"):
		mykv,err1=ExtractKernelVersion(os.path.join(myroot, "usr/src/linux"))
		if mykv:
			# Regular source tree
			mysettings["KV"]=mykv
		else:
			mysettings["KV"]=""

	if (mydo!="depend") or not mysettings.has_key("KVERS"):
		myso=os.uname()[2]
		mysettings["KVERS"]=myso[1]

	# Allow color.map to control colors associated with einfo, ewarn, etc...
	mycolors = []
	for c in ("GOOD", "WARN", "BAD", "HILITE", "BRACKET"):
		mycolors.append("%s=$'%s'" % (c, portage.output.codes[c]))
	mysettings["PORTAGE_COLORMAP"] = "\n".join(mycolors)

def prepare_build_dirs(myroot, mysettings, cleanup):

	clean_dirs = [mysettings["HOME"]]

	# We enable cleanup when we want to make sure old cruft (such as the old
	# environment) doesn't interfere with the current phase.
	if cleanup:
		clean_dirs.append(mysettings["T"])

	for clean_dir in clean_dirs:
		try:
			shutil.rmtree(clean_dir)
		except OSError, oe:
			if errno.ENOENT == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg("Operation Not Permitted: rmtree('%s')\n" % \
					clean_dir, noiselevel=-1)
				return 1
			else:
				raise

	def makedirs(dir_path):
		try:
			os.makedirs(dir_path)
		except OSError, oe:
			if errno.EEXIST == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg("Operation Not Permitted: makedirs('%s')\n" % \
					dir_path, noiselevel=-1)
				return False
			else:
				raise
		return True

	mysettings["PKG_LOGDIR"] = os.path.join(mysettings["T"], "logging")

	mydirs = [os.path.dirname(mysettings["PORTAGE_BUILDDIR"])]
	mydirs.append(os.path.dirname(mydirs[-1]))

	try:
		for mydir in mydirs:
			portage.util.ensure_dirs(mydir)
			portage.util.apply_secpass_permissions(mydir,
				gid=portage_gid, uid=portage_uid, mode=070, mask=0)
		for dir_key in ("PORTAGE_BUILDDIR", "HOME", "PKG_LOGDIR", "T"):
			"""These directories don't necessarily need to be group writable.
			However, the setup phase is commonly run as a privileged user prior
			to the other phases being run by an unprivileged user.  Currently,
			we use the portage group to ensure that the unprivleged user still
			has write access to these directories in any case."""
			portage.util.ensure_dirs(mysettings[dir_key], mode=0775)
			portage.util.apply_secpass_permissions(mysettings[dir_key],
				uid=portage_uid, gid=portage_gid)
	except portage.exception.PermissionDenied, e:
		writemsg("Permission Denied: %s\n" % str(e), noiselevel=-1)
		return 1
	except portage.exception.OperationNotPermitted, e:
		writemsg("Operation Not Permitted: %s\n" % str(e), noiselevel=-1)
		return 1
	except portage.exception.FileNotFound, e:
		writemsg("File Not Found: '%s'\n" % str(e), noiselevel=-1)
		return 1

	features_dirs = {
		"ccache":{
			"basedir_var":"CCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "ccache"),
			"always_recurse":False},
		"confcache":{
			"basedir_var":"CONFCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "confcache"),
			"always_recurse":True},
		"distcc":{
			"basedir_var":"DISTCC_DIR",
			"default_dir":os.path.join(mysettings["BUILD_PREFIX"], ".distcc"),
			"subdirs":("lock", "state"),
			"always_recurse":True}
	}
	dirmode  = 02070
	filemode =   060
	modemask =    02
	for myfeature, kwargs in features_dirs.iteritems():
		if myfeature in mysettings.features:
			basedir = mysettings[kwargs["basedir_var"]]
			if basedir == "":
				basedir = kwargs["default_dir"]
				mysettings[kwargs["basedir_var"]] = basedir
			try:
				mydirs = [mysettings[kwargs["basedir_var"]]]
				if "subdirs" in kwargs:
					for subdir in kwargs["subdirs"]:
						mydirs.append(os.path.join(basedir, subdir))
				for mydir in mydirs:
					modified = portage.util.ensure_dirs(mydir,
						gid=portage_gid, mode=dirmode, mask=modemask)
					# To avoid excessive recursive stat calls, we trigger
					# recursion when the top level directory does not initially
					# match our permission requirements.
					if modified or kwargs["always_recurse"]:
						if modified:
							writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
								noiselevel=-1)
						def onerror(e):
							raise	# The feature is disabled if a single error
									# occurs during permissions adjustment.
						if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
							raise portage.exception.OperationNotPermitted(
								"Failed to apply recursive permissions for the portage group.")
			except portage.exception.PortageException, e:
				mysettings.features.remove(myfeature)
				mysettings["FEATURES"] = " ".join(mysettings.features)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Failed resetting perms on %s='%s'\n" % \
					(kwargs["basedir_var"], basedir), noiselevel=-1)
				writemsg("!!! Disabled FEATURES='%s'\n" % myfeature,
					noiselevel=-1)
				time.sleep(5)

	workdir_mode = 0700
	try:
		mode = mysettings["PORTAGE_WORKDIR_MODE"]
		if mode.isdigit():
			parsed_mode = int(mode, 8)
		elif mode == "":
			raise KeyError()
		else:
			raise ValueError()
		if parsed_mode & 07777 != parsed_mode:
			raise ValueError("Invalid file mode: %s" % mode)
		else:
			workdir_mode = parsed_mode
	except KeyError, e:
		writemsg("!!! PORTAGE_WORKDIR_MODE is unset, using %s.\n" % oct(workdir_mode))
	except ValueError, e:
		if len(str(e)) > 0:
			writemsg("%s\n" % e)
		writemsg("!!! Unable to parse PORTAGE_WORKDIR_MODE='%s', using %s.\n" % \
		(mysettings["PORTAGE_WORKDIR_MODE"], oct(workdir_mode)))
	mysettings["PORTAGE_WORKDIR_MODE"] = oct(workdir_mode)
	try:
		apply_secpass_permissions(mysettings["WORKDIR"],
		uid=portage_uid, gid=portage_gid, mode=workdir_mode)
	except portage.exception.FileNotFound:
		pass # ebuild.sh will create it

	if mysettings.get("PORT_LOGDIR", "") == "":
		while "PORT_LOGDIR" in mysettings:
			del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		try:
			portage.util.ensure_dirs(mysettings["PORT_LOGDIR"],
				uid=portage_uid, gid=portage_gid, mode=02770)
		except portage.exception.PortageException, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! Permission issues with PORT_LOGDIR='%s'\n" % \
				mysettings["PORT_LOGDIR"], noiselevel=-1)
			writemsg("!!! Disabling logging.\n", noiselevel=-1)
			while "PORT_LOGDIR" in mysettings:
				del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		logid_path = os.path.join(mysettings["PORTAGE_BUILDDIR"], ".logid")
		if not os.path.exists(logid_path):
			f = open(logid_path, "w")
			f.close()
			del f
		logid_time = time.strftime("%Y%m%d-%H%M%S",
			time.gmtime(os.stat(logid_path).st_mtime))
		mysettings["PORTAGE_LOG_FILE"] = os.path.join(
			mysettings["PORT_LOGDIR"], "%s:%s:%s.log" % \
			(mysettings["CATEGORY"], mysettings["PF"], logid_time))
		del logid_path, logid_time
	else:
		# When sesandbox is enabled, only log if PORT_LOGDIR is explicitly
		# enabled since it is possible that local SELinux security policies
		# do not allow ouput to be piped out of the sesandbox domain.
		if not (mysettings.selinux_enabled() and \
			"sesandbox" in mysettings.features):
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				mysettings["T"], "build.log")

_doebuild_manifest_exempt_depend = 0
_doebuild_manifest_checked = None

def doebuild(myebuild, mydo, myroot, mysettings, debug=0, listonly=0,
	fetchonly=0, cleanup=0, dbkey=None, use_cache=1, fetchall=0, tree=None,
	mydbapi=None, vartree=None, prev_mtimes=None):
	
	"""
	Wrapper function that invokes specific ebuild phases through the spawning
	of ebuild.sh
	
	@param myebuild: name of the ebuild to invoke the phase on (CPV)
	@type myebuild: String
	@param mydo: Phase to run
	@type mydo: String
	@param myroot: $ROOT (usually '/', see man make.conf)
	@type myroot: String
	@param mysettings: Portage Configuration
	@type mysettings: instance of portage.config
	@param debug: Turns on various debug information (eg, debug for spawn)
	@type debug: Boolean
	@param listonly: Used to wrap fetch(); passed such that fetch only lists files required.
	@type listonly: Boolean
	@param fetchonly: Used to wrap fetch(); passed such that files are only fetched (no other actions)
	@type fetchonly: Boolean
	@param cleanup: Passed to prepare_build_dirs (TODO: what does it do?)
	@type cleanup: Boolean
	@param dbkey: A dict (usually keys and values from the depend phase, such as KEYWORDS, USE, etc..)
	@type dbkey: Dict or String
	@param use_cache: Enables the cache
	@type use_cache: Boolean
	@param fetchall: Used to wrap fetch(), fetches all URI's (even ones invalid due to USE conditionals)
	@type fetchall: Boolean
	@param tree: Which tree to use ('vartree','porttree','bintree', etc..), defaults to 'porttree'
	@type tree: String
	@param mydbapi: a dbapi instance to pass to various functions; this should be a portdbapi instance.
	@type mydbapi: portdbapi instance
	@param vartree: A instance of vartree; used for aux_get calls, defaults to db[myroot]['vartree']
	@type vartree: vartree instance
	@param prev_mtimes: A dict of { filename:mtime } keys used by merge() to do config_protection
	@type prev_mtimes: dictionary
	@rtype: Boolean
	@returns:
	1. 0 for success
	2. 1 for error
	
	Most errors have an accompanying error message.
	
	listonly and fetchonly are only really necessary for operations involving 'fetch'
	prev_mtimes are only necessary for merge operations.
	Other variables may not be strictly required, many have defaults that are set inside of doebuild.
	
	"""
	
	if not tree:
		writemsg("Warning: tree not specified to doebuild\n")
		tree = "porttree"
	global db
	
	# chunked out deps for each phase, so that ebuild binary can use it 
	# to collapse targets down.
	actionmap_deps={
	"depend": [],
	"setup":  [],
	"unpack": ["setup"],
	"compile":["unpack"],
	"test":   ["compile"],
	"install":["test"],
	"rpm":    ["install"],
	"package":["install"],
	}
	
	if mydbapi is None:
		mydbapi = db[myroot][tree].dbapi

	if vartree is None and mydo in ("merge", "qmerge", "unmerge"):
		vartree = db[myroot]["vartree"]

	features = mysettings.features

	validcommands = ["help","clean","prerm","postrm","cleanrm","preinst","postinst",
	                "config","setup","depend","fetch","digest",
	                "unpack","compile","test","install","rpm","qmerge","merge",
	                "package","unmerge", "manifest"]

	if mydo not in validcommands:
		validcommands.sort()
		writemsg("!!! doebuild: '%s' is not one of the following valid commands:" % mydo,
			noiselevel=-1)
		for vcount in range(len(validcommands)):
			if vcount%6 == 0:
				writemsg("\n!!! ", noiselevel=-1)
			writemsg(validcommands[vcount].ljust(11), noiselevel=-1)
		writemsg("\n", noiselevel=-1)
		return 1

	if not os.path.exists(myebuild):
		writemsg("!!! doebuild: %s not found for %s\n" % (myebuild, mydo),
			noiselevel=-1)
		return 1

	global _doebuild_manifest_exempt_depend

	if "strict" in features and \
		"digest" not in features and \
		tree == "porttree" and \
		mydo not in ("digest", "manifest", "help") and \
		not _doebuild_manifest_exempt_depend:
		# Always verify the ebuild checksums before executing it.
		pkgdir = os.path.dirname(myebuild)
		manifest_path = os.path.join(pkgdir, "Manifest")
		global _doebuild_manifest_checked
		# Avoid checking the same Manifest several times in a row during a
		# regen with an empty cache.
		if _doebuild_manifest_checked != manifest_path:
			if not os.path.exists(manifest_path):
				writemsg("!!! Manifest file not found: '%s'\n" % manifest_path,
					noiselevel=-1)
				return 1
			mf = Manifest(pkgdir, mysettings["DISTDIR"])
			try:
				mf.checkTypeHashes("EBUILD")
			except portage.exception.FileNotFound, e:
				writemsg("!!! A file listed in the Manifest " + \
					"could not be found: %s\n" % str(e), noiselevel=-1)
				return 1
			except portage.exception.DigestException, e:
				writemsg("!!! Digest verification failed:\n", noiselevel=-1)
				writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
				writemsg("!!! Reason: %s\n" % e.value[1], noiselevel=-1)
				writemsg("!!! Got: %s\n" % e.value[2], noiselevel=-1)
				writemsg("!!! Expected: %s\n" % e.value[3], noiselevel=-1)
				return 1
			# Make sure that all of the ebuilds are actually listed in the
			# Manifest.
			for f in os.listdir(pkgdir):
				if f.endswith(".ebuild") and not mf.hasFile("EBUILD", f):
					writemsg("!!! A file is not listed in the " + \
					"Manifest: '%s'\n" % os.path.join(pkgdir, f),
					noiselevel=-1)
					return 1
			_doebuild_manifest_checked = manifest_path

	logfile=None
	builddir_lock = None
	try:
		if mydo in ("digest", "manifest", "help"):
			# Temporarily exempt the depend phase from manifest checks, in case
			# aux_get calls trigger cache generation.
			_doebuild_manifest_exempt_depend += 1

		doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
			use_cache, mydbapi)

		# get possible slot information from the deps file
		if mydo == "depend":
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
			if isinstance(dbkey, dict):
				mysettings["dbkey"] = ""
				pr, pw = os.pipe()
				fd_pipes = {0:0, 1:1, 2:2, 9:pw}
				mypids = spawn(EBUILD_SH_BINARY + " depend", mysettings,
					fd_pipes=fd_pipes, returnpid=True)
				os.close(pw) # belongs exclusively to the child process now
				maxbytes = 1024
				mybytes = []
				while True:
					mybytes.append(os.read(pr, maxbytes))
					if not mybytes[-1]:
						break
				os.close(pr)
				mybytes = "".join(mybytes)
				global auxdbkeys
				for k, v in izip(auxdbkeys, mybytes.splitlines()):
					dbkey[k] = v
				retval = os.waitpid(mypids[0], 0)[1]
				portage.process.spawned_pids.remove(mypids[0])
				# If it got a signal, return the signal that was sent, but
				# shift in order to distinguish it from a return value. (just
				# like portage.process.spawn() would do).
				if retval & 0xff:
					return (retval & 0xff) << 8
				# Otherwise, return its exit code.
				return retval >> 8
			elif dbkey:
				mysettings["dbkey"] = dbkey
			else:
				mysettings["dbkey"] = \
					os.path.join(mysettings.depcachedir, "aux_db_key_temp")

			return spawn(EBUILD_SH_BINARY + " depend", mysettings)

		# Validate dependency metadata here to ensure that ebuilds with invalid
		# data are never installed (even via the ebuild command).
		invalid_dep_exempt_phases = \
			set(["clean", "cleanrm", "help", "prerm", "postrm"])
		mycpv = mysettings["CATEGORY"] + "/" + mysettings["PF"]
		dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
		metadata = dict(izip(dep_keys, mydbapi.aux_get(mycpv, dep_keys)))
		class FakeTree(object):
			def __init__(self, mydb):
				self.dbapi = mydb
		dep_check_trees = {myroot:{}}
		dep_check_trees[myroot]["porttree"] = \
			FakeTree(fakedbapi(settings=mysettings))
		for dep_type in dep_keys:
			mycheck = dep_check(metadata[dep_type], None, mysettings,
				myuse="all", myroot=myroot, trees=dep_check_trees)
			if not mycheck[0]:
				writemsg("%s: %s\n%s\n" % (
					dep_type, metadata[dep_type], mycheck[1]), noiselevel=-1)
				if mydo not in invalid_dep_exempt_phases:
					return 1
			del dep_type, mycheck
		del mycpv, dep_keys, metadata, FakeTree, dep_check_trees

		if "PORTAGE_TMPDIR" not in mysettings or \
			not os.path.isdir(mysettings["PORTAGE_TMPDIR"]):
			writemsg("The directory specified in your " + \
				"PORTAGE_TMPDIR variable, '%s',\n" % \
				mysettings.get("PORTAGE_TMPDIR", ""), noiselevel=-1)
			writemsg("does not exist.  Please create this directory or " + \
				"correct your PORTAGE_TMPDIR setting.\n", noiselevel=-1)
			return 1

		# Build directory creation isn't required for any of these.
		if mydo not in ("digest", "fetch", "help", "manifest"):
			mystatus = prepare_build_dirs(myroot, mysettings, cleanup)
			if mystatus:
				return mystatus
			# PORTAGE_LOG_FILE is set above by the prepare_build_dirs() call.
			logfile = mysettings.get("PORTAGE_LOG_FILE", None)
		if mydo == "unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		# if any of these are being called, handle them -- running them out of
		# the sandbox -- and stop now.
		if mydo in ["clean","cleanrm"]:
			return spawn(EBUILD_SH_BINARY + " clean", mysettings,
				debug=debug, free=1, logfile=None)
		elif mydo == "help":
			return spawn(EBUILD_SH_BINARY + " " + mydo, mysettings,
				debug=debug, free=1, logfile=logfile)
		elif mydo == "setup":
			infodir = os.path.join(
				mysettings["PORTAGE_BUILDDIR"], "build-info")
			if os.path.isdir(infodir):
				"""Load USE flags for setup phase of a binary package.
				Ideally, the environment.bz2 would be used instead."""
				mysettings.load_infodir(infodir)
			retval = spawn(EBUILD_SH_BINARY + " " + mydo, mysettings,
				debug=debug, free=1, logfile=logfile)
			if secpass >= 2:
				""" Privileged phases may have left files that need to be made
				writable to a less privileged user."""
				apply_recursive_permissions(mysettings["T"],
					uid=portage_uid, gid=portage_gid, dirmode=070, dirmask=0,
					filemode=060, filemask=0)
			return retval
		elif mydo == "preinst":
			mysettings["IMAGE"] = mysettings["D"]
			phase_retval = spawn(" ".join((EBUILD_SH_BINARY, mydo)),
				mysettings, debug=debug, free=1, logfile=logfile)
			if phase_retval == os.EX_OK:
				# Post phase logic and tasks that have been factored out of
				# ebuild.sh.
				myargs = [MISC_SH_BINARY, "preinst_bsdflags", "preinst_mask",
					"preinst_sfperms", "preinst_selinux_labels",
					"preinst_suid_scan"]
				mysettings["EBUILD_PHASE"] = ""
				phase_retval = spawn(" ".join(myargs),
					mysettings, debug=debug, free=1, logfile=logfile)
				if phase_retval != os.EX_OK:
					writemsg("!!! post preinst failed; exiting.\n",
						noiselevel=-1)
			del mysettings["IMAGE"]
			return phase_retval
		elif mydo == "postinst":
			mysettings.load_infodir(mysettings["O"])
			phase_retval = spawn(" ".join((EBUILD_SH_BINARY, mydo)),
				mysettings, debug=debug, free=1, logfile=logfile)
			if phase_retval == os.EX_OK:
				# Post phase logic and tasks that have been factored out of
				# ebuild.sh.
				myargs = [MISC_SH_BINARY, "postinst_bsdflags"]
				mysettings["EBUILD_PHASE"] = ""
				phase_retval = spawn(" ".join(myargs),
					mysettings, debug=debug, free=1, logfile=logfile)
				if phase_retval != os.EX_OK:
					writemsg("!!! post postinst failed; exiting.\n",
						noiselevel=-1)
			return phase_retval
		elif mydo in ["prerm","postrm","config"]:
			mysettings.load_infodir(mysettings["O"])
			return spawn(EBUILD_SH_BINARY + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)

		mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))

		# Make sure we get the correct tree in case there are overlays.
		mytree = os.path.realpath(
			os.path.dirname(os.path.dirname(mysettings["O"])))
		newuris, alist = mydbapi.getfetchlist(
			mycpv, mytree=mytree, mysettings=mysettings)
		alluris, aalist = mydbapi.getfetchlist(
			mycpv, mytree=mytree, all=True, mysettings=mysettings)
		mysettings["A"] = " ".join(alist)
		mysettings["AA"] = " ".join(aalist)
		if ("mirror" in features) or fetchall:
			fetchme = alluris[:]
			checkme = aalist[:]
		elif mydo == "digest":
			fetchme = alluris[:]
			checkme = aalist[:]
			# Skip files that we already have digests for.
			mf = Manifest(mysettings["O"], mysettings["DISTDIR"])
			mydigests = mf.getTypeDigests("DIST")
			for filename, hashes in mydigests.iteritems():
				if len(hashes) == len(mf.hashes):
					checkme = [i for i in checkme if i != filename]
					fetchme = [i for i in fetchme \
						if os.path.basename(i) != filename]
				del filename, hashes
		else:
			fetchme = newuris[:]
			checkme = alist[:]

		# Only try and fetch the files if we are going to need them ...
		# otherwise, if user has FEATURES=noauto and they run `ebuild clean
		# unpack compile install`, we will try and fetch 4 times :/
		need_distfiles = (mydo in ("fetch", "unpack") or \
			mydo not in ("digest", "manifest") and "noauto" not in features)
		if need_distfiles and not fetch(
			fetchme, mysettings, listonly=listonly, fetchonly=fetchonly):
			return 1

		if mydo == "fetch" and listonly:
			return 0

		try:
			if mydo == "manifest":
				return not digestgen(aalist, mysettings, overwrite=1,
					manifestonly=1, myportdb=mydbapi)
			elif mydo == "digest":
				return not digestgen(aalist, mysettings, overwrite=1,
					myportdb=mydbapi)
			elif "digest" in mysettings.features:
				digestgen(aalist, mysettings, overwrite=0, myportdb=mydbapi)
		except portage.exception.PermissionDenied, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			if mydo in ("digest", "manifest"):
				return 1

		# See above comment about fetching only when needed
		if not digestcheck(checkme, mysettings, ("strict" in features),
			(mydo not in ["digest","fetch","unpack"] and \
			mysettings.get("PORTAGE_CALLER", None) == "ebuild" and \
			"noauto" in features)):
			return 1

		if mydo == "fetch":
			return 0

		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		if (mydo != "setup" and "noauto" not in features) or mydo == "unpack":
			orig_distdir = mysettings["DISTDIR"]
			mysettings["PORTAGE_ACTUAL_DISTDIR"] = orig_distdir
			edpath = mysettings["DISTDIR"] = \
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "distdir")
			if os.path.exists(edpath):
				try:
					if os.path.isdir(edpath) and not os.path.islink(edpath):
						shutil.rmtree(edpath)
					else:
						os.unlink(edpath)
				except OSError:
					print "!!! Failed reseting ebuild distdir path, " + edpath
					raise
			os.mkdir(edpath)
			apply_secpass_permissions(edpath, uid=portage_uid, mode=0755)
			try:
				for file in aalist:
					os.symlink(os.path.join(orig_distdir, file),
						os.path.join(edpath, file))
			except OSError:
				print "!!! Failed symlinking in '%s' to ebuild distdir" % file
				raise

		#initial dep checks complete; time to process main commands

		nosandbox = (("userpriv" in features) and \
			("usersandbox" not in features) and \
			("userpriv" not in mysettings["RESTRICT"]) and \
			("nouserpriv" not in mysettings["RESTRICT"]))
		if nosandbox and ("userpriv" not in features or \
			"userpriv" in mysettings["RESTRICT"] or \
			"nouserpriv" in mysettings["RESTRICT"]):
			nosandbox = ("sandbox" not in features and \
				"usersandbox" not in features)

		sesandbox = mysettings.selinux_enabled() and \
			"sesandbox" in mysettings.features
		ebuild_sh = EBUILD_SH_BINARY + " %s"
		misc_sh = MISC_SH_BINARY + " dyn_%s"

		# args are for the to spawn function
		actionmap = {
"depend": {"cmd":ebuild_sh, "args":{"droppriv":1, "free":0,         "sesandbox":0}},
"setup":  {"cmd":ebuild_sh, "args":{"droppriv":0, "free":1,         "sesandbox":0}},
"unpack": {"cmd":ebuild_sh, "args":{"droppriv":1, "free":0,         "sesandbox":sesandbox}},
"compile":{"cmd":ebuild_sh, "args":{"droppriv":1, "free":nosandbox, "sesandbox":sesandbox}},
"test":   {"cmd":ebuild_sh, "args":{"droppriv":1, "free":nosandbox, "sesandbox":sesandbox}},
"install":{"cmd":ebuild_sh, "args":{"droppriv":0, "free":0,         "sesandbox":sesandbox}},
"rpm":    {"cmd":misc_sh,   "args":{"droppriv":0, "free":0,         "sesandbox":0}},
"package":{"cmd":misc_sh,   "args":{"droppriv":0, "free":0,         "sesandbox":0}},
		}

		# merge the deps in so we have again a 'full' actionmap
		# be glad when this can die.
		for x in actionmap.keys():
			if len(actionmap_deps.get(x, [])):
				actionmap[x]["dep"] = ' '.join(actionmap_deps[x])

		if mydo in actionmap.keys():
			if mydo=="package":
				portage.util.ensure_dirs(
					os.path.join(mysettings["PKGDIR"], mysettings["CATEGORY"]))
				portage.util.ensure_dirs(
					os.path.join(mysettings["PKGDIR"], "All"))
			retval = spawnebuild(mydo,
				actionmap, mysettings, debug, logfile=logfile)
		elif mydo=="qmerge":
			# check to ensure install was run.  this *only* pops up when users
			# forget it and are using ebuild
			if not os.path.exists(
				os.path.join(mysettings["PORTAGE_BUILDDIR"], ".installed")):
				writemsg("!!! mydo=qmerge, but install phase hasn't been ran\n",
					noiselevel=-1)
				return 1
			# qmerge is a special phase that implies noclean.
			if "noclean" not in mysettings.features:
				mysettings.features.append("noclean")
			#qmerge is specifically not supposed to do a runtime dep check
			retval = merge(
				mysettings["CATEGORY"], mysettings["PF"], mysettings["D"],
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "build-info"),
				myroot, mysettings, myebuild=mysettings["EBUILD"], mytree=tree,
				mydbapi=mydbapi, vartree=vartree, prev_mtimes=prev_mtimes)
		elif mydo=="merge":
			retval = spawnebuild("install", actionmap, mysettings, debug,
				alwaysdep=1, logfile=logfile)
			if retval == os.EX_OK:
				retval = merge(mysettings["CATEGORY"], mysettings["PF"],
					mysettings["D"], os.path.join(mysettings["PORTAGE_BUILDDIR"],
					"build-info"), myroot, mysettings,
					myebuild=mysettings["EBUILD"], mytree=tree, mydbapi=mydbapi,
					vartree=vartree, prev_mtimes=prev_mtimes)
		else:
			print "!!! Unknown mydo:",mydo
			return 1

		if retval != os.EX_OK and tree == "porttree":
			for i in xrange(len(mydbapi.porttrees)-1):
				t = mydbapi.porttrees[i+1]
				if myebuild.startswith(t):
					# Display the non-cannonical path, in case it's different, to
					# prevent confusion.
					overlays = mysettings["PORTDIR_OVERLAY"].split()
					try:
						writemsg("!!! This ebuild is from an overlay: '%s'\n" % \
							overlays[i], noiselevel=-1)
					except IndexError:
						pass
					break
		return retval

	finally:
		if builddir_lock:
			portage.locks.unlockdir(builddir_lock)

		# Make sure that DISTDIR is restored to it's normal value before we return!
		if "PORTAGE_ACTUAL_DISTDIR" in mysettings:
			mysettings["DISTDIR"] = mysettings["PORTAGE_ACTUAL_DISTDIR"]
			del mysettings["PORTAGE_ACTUAL_DISTDIR"]

		if logfile:
			try:
				if os.stat(logfile).st_size == 0:
					os.unlink(logfile)
			except OSError:
				pass

		if mydo in ("digest", "manifest", "help"):
			# If necessary, depend phase has been triggered by aux_get calls
			# and the exemption is no longer needed.
			_doebuild_manifest_exempt_depend -= 1

expandcache={}

def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	global lchown
	if mysettings is None:
		global settings
		mysettings = settings
	selinux_enabled = mysettings.selinux_enabled()
	try:
		if not sstat:
			sstat=os.lstat(src)

	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except (OSError, IOError):
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if bsd_chflags:
		if destexists and dstat.st_flags != 0:
			bsd_chflags.lchflags(dest, 0)
		pflags = os.stat(os.path.dirname(dest)).st_flags
		if pflags != 0:
			bsd_chflags.lchflags(os.path.dirname(dest), 0)

	if destexists:
		if stat.S_ISLNK(dstat[stat.ST_MODE]):
			try:
				os.unlink(dest)
				destexists=0
			except SystemExit, e:
				raise
			except Exception, e:
				pass

	if stat.S_ISLNK(sstat[stat.ST_MODE]):
		try:
			target=os.readlink(src)
			if mysettings and mysettings["D"]:
				if target.find(mysettings["D"])==0:
					target=target[len(mysettings["D"]):]
			if destexists and not stat.S_ISDIR(dstat[stat.ST_MODE]):
				os.unlink(dest)
			if selinux_enabled:
				sid = selinux.get_lsid(src)
				selinux.secure_symlink(target,dest,sid)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			return os.lstat(dest)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! failed to properly create symlink:"
			print "!!!",dest,"->",target
			print "!!!",e
			return None

	renamefailed=1
	if sstat[stat.ST_DEV]==dstat[stat.ST_DEV] or selinux_enabled:
		try:
			if selinux_enabled:
				ret=selinux.secure_rename(src,dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except SystemExit, e:
			raise
		except Exception, e:
			if e[0]!=errno.EXDEV:
				# Some random error.
				print "!!! Failed to move",src,"to",dest
				print "!!!",e
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		didcopy=0
		if stat.S_ISREG(sstat[stat.ST_MODE]):
			try: # For safety copy then move it over.
				if selinux_enabled:
					selinux.secure_copy(src,dest+"#new")
					selinux.secure_rename(dest+"#new",dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except SystemExit, e:
				raise
			except Exception, e:
				print '!!! copy',src,'->',dest,'failed.'
				print "!!!",e
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			if selinux_enabled:
				a=commands.getstatusoutput(MOVE_BINARY+" -c -f "+"'"+src+"' '"+dest+"'")
			else:
				a=commands.getstatusoutput(MOVE_BINARY+" -f "+"'"+src+"' '"+dest+"'")
				if a[0]!=0:
					print "!!! Failed to move special file:"
					print "!!! '"+src+"' to '"+dest+"'"
					print "!!!",a
					return None # failure
		try:
			if didcopy:
				if stat.S_ISLNK(sstat[stat.ST_MODE]):
					lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				else:
					os.chown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				os.chmod(dest, stat.S_IMODE(sstat[stat.ST_MODE])) # Sticky is reset on chown
				os.unlink(src)
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! Failed to chown/chmod/unlink in movefile()"
			print "!!!",dest
			print "!!!",e
			return None

	if newmtime:
		os.utime(dest,(newmtime,newmtime))
	else:
		os.utime(dest, (sstat[stat.ST_ATIME], sstat[stat.ST_MTIME]))
		newmtime=sstat[stat.ST_MTIME]

	if bsd_chflags:
		# Restore the flags we saved before moving
		if pflags:
			bsd_chflags.lchflags(os.path.dirname(dest), pflags)

	return newmtime

def merge(mycat, mypkg, pkgloc, infloc, myroot, mysettings, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None):
	if not os.access(myroot, os.W_OK):
		writemsg("Permission denied: access('%s', W_OK)\n" % myroot,
			noiselevel=-1)
		return errno.EACCES
	mylink = dblink(mycat, mypkg, myroot, mysettings, treetype=mytree,
		vartree=vartree)
	return mylink.merge(pkgloc, infloc, myroot, myebuild,
		mydbapi=mydbapi, prev_mtimes=prev_mtimes)

def unmerge(cat, pkg, myroot, mysettings, mytrimworld=1, vartree=None, ldpath_mtimes=None):
	mylink = dblink(
		cat, pkg, myroot, mysettings, treetype="vartree", vartree=vartree)
	try:
		mylink.lockdb()
		if mylink.exists():
			retval = mylink.unmerge(trimworld=mytrimworld, cleanup=1,
				ldpath_mtimes=ldpath_mtimes)
			if retval == os.EX_OK:
				mylink.delete()
			return retval
		return os.EX_OK
	finally:
		mylink.unlockdb()

def getCPFromCPV(mycpv):
	"""Calls pkgsplit on a cpv and returns only the cp."""
	return pkgsplit(mycpv)[0]

def dep_virtual(mysplit, mysettings):
	"Does virtual dependency conversion"
	newsplit=[]
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if type(x)==types.ListType:
			newsplit.append(dep_virtual(x, mysettings))
		else:
			mykey=dep_getkey(x)
			mychoices = myvirtuals.get(mykey, None)
			if mychoices:
				if len(mychoices) == 1:
					a = x.replace(mykey, mychoices[0])
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in mychoices:
						a.append(x.replace(mykey, y))
				newsplit.append(a)
			else:
				newsplit.append(x)
	return newsplit

def _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings, myroot="/",
	trees=None, **kwargs):
	"""Recursively expand new-style virtuals so as to collapse one or more
	levels of indirection.  In dep_zapdeps, new-style virtuals will be assigned
	zero cost regardless of whether or not they are currently installed. Virtual
	blockers are supported but only when the virtual expands to a single
	atom because it wouldn't necessarily make sense to block all the components
	of a compound virtual.  When more than one new-style virtual is matched,
	the matches are sorted from highest to lowest versions and the atom is
	expanded to || ( highest match ... lowest match )."""
	newsplit = []
	# According to GLEP 37, RDEPEND is the only dependency type that is valid
	# for new-style virtuals.  Repoman should enforce this.
	dep_keys = ["RDEPEND", "DEPEND", "PDEPEND"]
	def compare_pkgs(a, b):
		return pkgcmp(b[1], a[1])
	portdb = trees[myroot]["porttree"].dbapi
	if kwargs["use_binaries"]:
		portdb = trees[myroot]["bintree"].dbapi
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			newsplit.append(_expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, **kwargs))
			continue
		if portage.dep._dep_check_strict and \
			not isvalidatom(x, allow_blockers=True):
			raise portage.exception.ParseError(
				"invalid atom: '%s'" % x)
		mykey = dep_getkey(x)
		if not mykey.startswith("virtual/"):
			newsplit.append(x)
			continue
		mychoices = myvirtuals.get(mykey, [])
		isblocker = x.startswith("!")
		match_atom = x
		if isblocker:
			match_atom = x[1:]
		pkgs = {}
		for cpv in portdb.match(match_atom):
			# only use new-style matches
			if cpv.startswith("virtual/"):
				pkgs[cpv] = (cpv, pkgsplit(cpv), portdb)
		if kwargs["use_binaries"] and "vartree" in trees[myroot]:
			vardb = trees[myroot]["vartree"].dbapi
			for cpv in vardb.match(match_atom):
				# only use new-style matches
				if cpv.startswith("virtual/"):
					if cpv in pkgs:
						continue
					pkgs[cpv] = (cpv, pkgsplit(cpv), vardb)
		if not (pkgs or mychoices):
			# This one couldn't be expanded as a new-style virtual.  Old-style
			# virtuals have already been expanded by dep_virtual, so this one
			# is unavailable and dep_zapdeps will identify it as such.  The
			# atom is not eliminated here since it may still represent a
			# dependency that needs to be satisfied.
			newsplit.append(x)
			continue
		if not pkgs and len(mychoices) == 1:
			newsplit.append(x.replace(mykey, mychoices[0]))
			continue
		pkgs = pkgs.values()
		pkgs.sort(compare_pkgs) # Prefer higher versions.
		if isblocker:
			a = []
		else:
			a = ['||']
		for y in pkgs:
			depstring = " ".join(y[2].aux_get(y[0], dep_keys))
			if edebug:
				print "Virtual Parent:   ", y[0]
				print "Virtual Depstring:", depstring
			mycheck = dep_check(depstring, mydbapi, mysettings, myroot=myroot,
				trees=trees, **kwargs)
			if not mycheck[0]:
				raise portage.exception.ParseError(
					"%s: %s '%s'" % (y[0], mycheck[1], depstring))
			if isblocker:
				virtual_atoms = [atom for atom in mycheck[1] \
					if not atom.startswith("!")]
				if len(virtual_atoms) == 1:
					# It wouldn't make sense to block all the components of a
					# compound virtual, so only a single atom block is allowed.
					a.append("!" + virtual_atoms[0])
			else:
				mycheck[1].append("="+y[0]) # pull in the new-style virtual
				a.append(mycheck[1])
		# Plain old-style virtuals.  New-style virtuals are preferred.
		for y in mychoices:
			a.append(x.replace(mykey, y))
		if isblocker and not a:
			# Probably a compound virtual.  Pass the atom through unprocessed.
			newsplit.append(x)
			continue
		newsplit.append(a)
	return newsplit

def dep_eval(deplist):
	if not deplist:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if type(x)==types.ListType:
				if dep_eval(x)==1:
					return 1
			elif x==1:
					return 1
		#XXX: unless there's no available atoms in the list
		#in which case we need to assume that everything is
		#okay as some ebuilds are relying on an old bug.
		if len(deplist) == 1:
			return 1
		return 0
	else:
		for x in deplist:
			if type(x)==types.ListType:
				if dep_eval(x)==0:
					return 0
			elif x==0 or x==2:
				return 0
		return 1

def dep_zapdeps(unreduced, reduced, myroot, use_binaries=0, trees=None):
	"""Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies."""
	if trees is None:
		global db
		trees = db
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if not reduced or unreduced == ["||"] or dep_eval(reduced):
		return []

	if unreduced[0] != "||":
		unresolved = []
		for dep, satisfied in izip(unreduced, reduced):
			if isinstance(dep, list):
				unresolved += dep_zapdeps(dep, satisfied, myroot,
					use_binaries=use_binaries, trees=trees)
			elif not satisfied:
				unresolved.append(dep)
		return unresolved

	# We're at a ( || atom ... ) type level and need to make a choice
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	# Our preference order is for an the first item that:
	# a) contains all unmasked packages with the same key as installed packages
	# b) contains all unmasked packages
	# c) contains masked installed packages
	# d) is the first item

	preferred = []
	possible_upgrades = []
	other = []

	# Alias the trees we'll be checking availability against
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	# Sort the deps into preferred (installed) and other
	# with values of [[required_atom], availablility]
	for dep, satisfied in izip(deps, satisfieds):
		if isinstance(dep, list):
			atoms = dep_zapdeps(dep, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [dep]

		all_available = True
		for atom in atoms:
			if not mydbapi.match(atom):
				# With --usepkgonly, count installed packages as "available".
				# Note that --usepkgonly currently has no package.mask support.
				# See bug #149816.
				if use_binaries and vardb and vardb.match(atom):
					continue
				all_available = False
				break

		if not vardb:
			# called by repoman
			preferred.append((atoms, None, all_available))
			continue

		""" The package names rather than the exact atoms are used for an
		initial rough match against installed packages.  More specific
		preference selection is handled later via slot and version comparison."""
		all_installed = True
		for atom in set([dep_getkey(atom) for atom in atoms]):
			# New-style virtuals have zero cost to install.
			if not vardb.match(atom) and not atom.startswith("virtual/"):
				all_installed = False
				break

		# Check if the set of atoms will result in a downgrade of
		# an installed package. If they will then don't prefer them
		# over other atoms.
		has_downgrade = False
		versions = {}
		if all_installed or all_available:
			for atom in atoms:
				mykey = dep_getkey(atom)
				avail_pkg = best(mydbapi.match(atom))
				if not avail_pkg:
					continue
				avail_slot = "%s:%s" % (mykey,
					mydbapi.aux_get(avail_pkg, ["SLOT"])[0])
				versions[avail_slot] = avail_pkg
				inst_pkg = vardb.match(avail_slot)
				if not inst_pkg:
					continue
				# emerge guarantees 1 package per slot here (highest counter)
				inst_pkg = inst_pkg[0]
				if avail_pkg != inst_pkg and \
					avail_pkg != best([avail_pkg, inst_pkg]):
					has_downgrade = True
					break

		this_choice = (atoms, versions, all_available)
		if not has_downgrade:
			if all_installed:
				preferred.append(this_choice)
				continue
			elif all_available:
				possible_upgrades.append(this_choice)
				continue
		other.append(this_choice)

	# Compare the "all_installed" choices against the "all_available" choices
	# for possible missed upgrades.  The main purpose of this code is to find
	# upgrades of new-style virtuals since _expand_new_virtuals() expands them
	# into || ( highest version ... lowest version ).  We want to prefer the
	# highest all_available version of the new-style virtual when there is a
	# lower all_installed version.
	for possible_upgrade in list(possible_upgrades):
		atoms, versions, all_available = possible_upgrade
		myslots = set(versions)
		for other_choice in preferred:
			o_atoms, o_versions, o_all_available = other_choice
			intersecting_slots = myslots.intersection(o_versions)
			if not intersecting_slots:
				continue
			has_upgrade = False
			has_downgrade = False
			for myslot in intersecting_slots:
				myversion = versions[myslot]
				o_version = o_versions[myslot]
				if myversion != o_version:
					if myversion == best([myversion, o_version]):
						has_upgrade = True
					else:
						has_downgrade = True
						break
			if has_upgrade and not has_downgrade:
				o_index = preferred.index(other_choice)
				preferred.insert(o_index, possible_upgrade)
				possible_upgrades.remove(possible_upgrade)
				break
	preferred.extend(possible_upgrades)

	# preferred now contains a) and c) from the order above with
	# the masked flag differentiating the two. other contains b)
	# and d) so adding other to preferred will give us a suitable
	# list to iterate over.
	preferred.extend(other)

	for allow_masked in (False, True):
		for atoms, versions, all_available in preferred:
			if all_available or allow_masked:
				return atoms

	assert(False) # This point should not be reachable


def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	orig_dep = mydep
	mydep = dep_getcpv(orig_dep)
	myindex = orig_dep.index(mydep)
	prefix = orig_dep[:myindex]
	postfix = orig_dep[myindex+len(mydep):]
	return prefix + cpv_expand(
		mydep, mydb=mydb, use_cache=use_cache, settings=settings) + postfix

def dep_check(depstring, mydbapi, mysettings, use="yes", mode=None, myuse=None,
	use_cache=1, use_binaries=0, myroot="/", trees=None):
	"""Takes a depend string and parses the condition."""
	edebug = mysettings.get("PORTAGE_DEBUG", None) == "1"
	#check_config_instance(mysettings)
	if trees is None:
		trees = globals()["db"]
	if use=="yes":
		if myuse is None:
			#default behavior
			myusesplit = mysettings["USE"].split()
		else:
			myusesplit = myuse
			# We've been given useflags to use.
			#print "USE FLAGS PASSED IN."
			#print myuse
			#if "bindist" in myusesplit:
			#	print "BINDIST is set!"
			#else:
			#	print "BINDIST NOT set."
	else:
		#we are being run by autouse(), don't consult USE vars yet.
		# WE ALSO CANNOT USE SETTINGS
		myusesplit=[]

	#convert parenthesis to sublists
	mysplit = portage.dep.paren_reduce(depstring)

	mymasks = set()
	useforce = set()
	useforce.add(mysettings["ARCH"])
	if use == "all":
		# This masking/forcing is only for repoman.  In other cases, relevant
		# masking/forcing should have already been applied via
		# config.regenerate().  Also, binary or installed packages may have
		# been built with flags that are now masked, and it would be
		# inconsistent to mask them now.  Additionally, myuse may consist of
		# flags from a parent package that is being merged to a $ROOT that is
		# different from the one that mysettings represents.
		mymasks.update(mysettings.usemask)
		mymasks.update(mysettings.archlist())
		mymasks.discard(mysettings["ARCH"])
		useforce.update(mysettings.useforce)
		useforce.difference_update(mymasks)
	try:
		mysplit = portage.dep.use_reduce(mysplit, uselist=myusesplit,
			masklist=mymasks, matchall=(use=="all"), excludeall=useforce)
	except portage.exception.InvalidDependString, e:
		return [0, str(e)]

	# Do the || conversions
	mysplit=portage.dep.dep_opconvert(mysplit)

	if mysplit == []:
		#dependencies were reduced to nothing
		return [1,[]]

	# Recursively expand new-style virtuals so as to
	# collapse one or more levels of indirection.
	try:
		mysplit = _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings,
			use=use, mode=mode, myuse=myuse, use_cache=use_cache,
			use_binaries=use_binaries, myroot=myroot, trees=trees)
	except portage.exception.ParseError, e:
		return [0, str(e)]

	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0,"Invalid token"]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	myzaps = dep_zapdeps(mysplit, mysplit2, myroot,
		use_binaries=use_binaries, trees=trees)
	mylist = flatten(myzaps)
	writemsg("myzaps:   %s\n" % (myzaps), 1)
	writemsg("mylist:   %s\n" % (mylist), 1)
	#remove duplicates
	mydict={}
	for x in mylist:
		mydict[x]=1
	writemsg("mydict:   %s\n" % (mydict), 1)
	return [1,mydict.keys()]

def dep_wordreduce(mydeplist,mysettings,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	deplist=mydeplist[:]
	for mypos in xrange(len(deplist)):
		if type(deplist[mypos])==types.ListType:
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mysettings,mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		else:
			mykey = dep_getkey(deplist[mypos])
			if mysettings and mysettings.pprovideddict.has_key(mykey) and \
			        match_from_list(deplist[mypos], mysettings.pprovideddict[mykey]):
				deplist[mypos]=True
			elif mydbapi is None:
				# Assume nothing is satisfied.  This forces dep_zapdeps to
				# return all of deps the deps that have been selected
				# (excluding those satisfied by package.provided).
				deplist[mypos] = False
			else:
				if mode:
					mydep=mydbapi.xmatch(mode,deplist[mypos])
				else:
					mydep=mydbapi.match(deplist[mypos],use_cache=use_cache)
				if mydep!=None:
					tmp=(len(mydep)>=1)
					if deplist[mypos][0]=="!":
						tmp=False
					deplist[mypos]=tmp
				else:
					#encountered invalid string
					return None
	return deplist

def cpv_getkey(mycpv):
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	mylen=len(myslash)
	if mylen==2:
		return myslash[0]+"/"+mysplit[0]
	elif mylen==1:
		return mysplit[0]
	else:
		return mysplit

def key_expand(mykey, mydb=None, use_cache=1, settings=None):
	mysplit=mykey.split("/")
	if settings is None:
		settings = globals()["settings"]
	virts = settings.getvirtuals("/")
	virts_p = settings.get_virts_p("/")
	if len(mysplit)==1:
		if mydb and type(mydb)==types.InstanceType:
			for x in settings.categories:
				if mydb.cp_list(x+"/"+mykey,use_cache=use_cache):
					return x+"/"+mykey
			if virts_p.has_key(mykey):
				return(virts_p[mykey][0])
		return "null/"+mykey
	elif mydb:
		if type(mydb)==types.InstanceType:
			if (not mydb.cp_list(mykey,use_cache=use_cache)) and virts and virts.has_key(mykey):
				return virts[mykey][0]
		return mykey

def cpv_expand(mycpv, mydb=None, use_cache=1, settings=None):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
	if settings is None:
		settings = globals()["settings"]
	virts = settings.getvirtuals("/")
	virts_p = settings.get_virts_p("/")
	if len(myslash)>2:
		# this is illegal case.
		mysplit=[]
		mykey=mycpv
	elif len(myslash)==2:
		if mysplit:
			mykey=myslash[0]+"/"+mysplit[0]
		else:
			mykey=mycpv
		if mydb and virts and mykey in virts:
			writemsg("mydb.__class__: %s\n" % (mydb.__class__), 1)
			if type(mydb)==types.InstanceType:
				if not mydb.cp_list(mykey, use_cache=use_cache):
					writemsg("virts[%s]: %s\n" % (str(mykey),virts[mykey]), 1)
					mykey_orig = mykey[:]
					for vkey in virts[mykey]:
						if mydb.cp_list(vkey,use_cache=use_cache):
							mykey = vkey
							writemsg("virts chosen: %s\n" % (mykey), 1)
							break
					if mykey == mykey_orig:
						mykey=virts[mykey][0]
						writemsg("virts defaulted: %s\n" % (mykey), 1)
			#we only perform virtual expansion if we are passed a dbapi
	else:
		#specific cpv, no category, ie. "foo-1.0"
		if mysplit:
			myp=mysplit[0]
		else:
			# "foo" ?
			myp=mycpv
		mykey=None
		matches=[]
		if mydb:
			for x in settings.categories:
				if mydb.cp_list(x+"/"+myp,use_cache=use_cache):
					matches.append(x+"/"+myp)
		if len(matches) > 1:
			virtual_name_collision = False
			if len(matches) == 2:
				for x in matches:
					if not x.startswith("virtual/"):
						# Assume that the non-virtual is desired.  This helps
						# avoid the ValueError for invalid deps that come from
						# installed packages (during reverse blocker detection,
						# for example).
						mykey = x
					else:
						virtual_name_collision = True
			if not virtual_name_collision:
				raise ValueError, matches
		elif matches:
			mykey=matches[0]

		if not mykey and type(mydb)!=types.ListType:
			if virts_p.has_key(myp):
				mykey=virts_p[myp][0]
			#again, we only perform virtual expansion if we have a dbapi (not a list)
		if not mykey:
			mykey="null/"+myp
	if mysplit:
		if mysplit[2]=="r0":
			return mykey+"-"+mysplit[1]
		else:
			return mykey+"-"+mysplit[1]+"-"+mysplit[2]
	else:
		return mykey

def getmaskingreason(mycpv, settings=None, portdb=None):
	from portage.util import grablines
	if settings is None:
		settings = globals()["settings"]
	if portdb is None:
		portdb = globals()["portdb"]
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if not portdb.cpv_exists(mycpv):
		raise KeyError("CPV %s does not exist" % mycpv)
	mycp=mysplit[0]+"/"+mysplit[1]

	# XXX- This is a temporary duplicate of code from the config constructor.
	locations = [os.path.join(settings["PORTDIR"], "profiles")]
	locations.extend(settings.profiles)
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(normalize_path(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH.lstrip(os.path.sep)))
	locations.reverse()
	pmasklists = [grablines(os.path.join(x, "package.mask"), recursive=1) for x in locations]
	pmasklines = []
	while pmasklists: # stack_lists doesn't preserve order so it can't be used
		pmasklines.extend(pmasklists.pop(0))
	del pmasklists

	if settings.pmaskdict.has_key(mycp):
		for x in settings.pmaskdict[mycp]:
			if mycpv in portdb.xmatch("match-all", x):
				comment = ""
				l = "\n"
				comment_valid = -1
				for i in xrange(len(pmasklines)):
					l = pmasklines[i].strip()
					if l == "":
						comment = ""
						comment_valid = -1
					elif l[0] == "#":
						comment += (l+"\n")
						comment_valid = i + 1
					elif l == x:
						if comment_valid != i:
							comment = ""
						return comment
					elif comment_valid != -1:
						# Apparently this comment applies to muliple masks, so
						# it remains valid until a blank line is encountered.
						comment_valid += 1
	return None

def getmaskingstatus(mycpv, settings=None, portdb=None):
	if settings is None:
		settings = globals()["settings"]
	if portdb is None:
		portdb = globals()["portdb"]
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if not portdb.cpv_exists(mycpv):
		raise KeyError("CPV %s does not exist" % mycpv)
	mycp=mysplit[0]+"/"+mysplit[1]

	rValue = []

	# profile checking
	revmaskdict=settings.prevmaskdict
	if revmaskdict.has_key(mycp):
		for x in revmaskdict[mycp]:
			if x[0]=="*":
				myatom = x[1:]
			else:
				myatom = x
			if not match_to_list(mycpv, [myatom]):
				rValue.append("profile")
				break

	# package.mask checking
	maskdict=settings.pmaskdict
	unmaskdict=settings.punmaskdict
	if maskdict.has_key(mycp):
		for x in maskdict[mycp]:
			if mycpv in portdb.xmatch("match-all", x):
				unmask=0
				if unmaskdict.has_key(mycp):
					for z in unmaskdict[mycp]:
						if mycpv in portdb.xmatch("match-all",z):
							unmask=1
							break
				if unmask==0:
					rValue.append("package.mask")

	# keywords checking
	try:
		mygroups, eapi = portdb.aux_get(mycpv, ["KEYWORDS", "EAPI"])
	except KeyError:
		# The "depend" phase apparently failed for some reason.  An associated
		# error message will have already been printed to stderr.
		return ["corruption"]
	if not eapi_is_supported(eapi):
		return ["required EAPI %s, supported EAPI %s" % (eapi, portage.const.EAPI)]
	mygroups = mygroups.split()
	pgroups = settings["ACCEPT_KEYWORDS"].split()
	myarch = settings["ARCH"]
	if pgroups and myarch not in pgroups:
		"""For operating systems other than Linux, ARCH is not necessarily a
		valid keyword."""
		myarch = pgroups[0].lstrip("~")
	pkgdict = settings.pkeywordsdict

	cp = dep_getkey(mycpv)
	if pkgdict.has_key(cp):
		matches = match_to_list(mycpv, pkgdict[cp].keys())
		for match in matches:
			pgroups.extend(pkgdict[cp][match])
		if matches:
			inc_pgroups = []
			for x in pgroups:
				if x != "-*" and x.startswith("-"):
					try:
						inc_pgroups.remove(x[1:])
					except ValueError:
						pass
				if x not in inc_pgroups:
					inc_pgroups.append(x)
			pgroups = inc_pgroups
			del inc_pgroups

	kmask = "missing"

	for keyword in pgroups:
		if keyword in mygroups:
			kmask=None

	if kmask:
		fallback = None
		for gp in mygroups:
			if gp=="*":
				kmask=None
				break
			elif gp=="-"+myarch:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch:
				kmask="~"+myarch
				break

	if kmask:
		rValue.append(kmask+" keyword")
	return rValue

class portagetree:
	def __init__(self, root="/", virtual=None, clone=None, settings=None):
		"""
		Constructor for a PortageTree
		
		@param root: ${ROOT}, defaults to '/', see make.conf(5)
		@type root: String/Path
		@param virtual: UNUSED
		@type virtual: No Idea
		@param clone: Set this if you want a copy of Clone
		@type clone: Existing portagetree Instance
		@param settings: Portage Configuration object (portage.settings)
		@type settings: Instance of portage.config
		"""

		if clone:
			self.root = clone.root
			self.portroot = clone.portroot
			self.pkglines = clone.pkglines
		else:
			self.root = root
			if settings is None:
				settings = globals()["settings"]
			self.settings = settings
			self.portroot = settings["PORTDIR"]
			self.virtual = virtual
			self.dbapi = portdbapi(
				settings["PORTDIR"], mysettings=settings)

	def dep_bestmatch(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("bestmatch-visible",mydep)
		if mymatch is None:
			return ""
		return mymatch

	def dep_match(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("match-visible",mydep)
		if mymatch is None:
			return []
		return mymatch

	def exists_specific(self,cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def getname(self,pkgname):
		"returns file location for this particular package (DEPRECATED)"
		if not pkgname:
			return ""
		mysplit=pkgname.split("/")
		psplit=pkgsplit(mysplit[1])
		return self.portroot+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"

	def resolve_specific(self,myspec):
		cps=catpkgsplit(myspec)
		if not cps:
			return None
		mykey = key_expand(cps[0]+"/"+cps[1], mydb=self.dbapi,
			settings=self.settings)
		mykey=mykey+"-"+cps[2]
		if cps[3]!="r0":
			mykey=mykey+"-"+cps[3]
		return mykey

	def depcheck(self,mycheck,use="yes",myusesplit=None):
		return dep_check(mycheck,self.dbapi,use=use,myuse=myusesplit)

	def getslot(self,mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		myslot = ""
		try:
			myslot=self.dbapi.aux_get(mycatpkg,["SLOT"])[0]
		except SystemExit, e:
			raise
		except Exception, e:
			pass
		return myslot


class dbapi:
	def __init__(self):
		pass

	def close_caches(self):
		pass

	def cp_list(self,cp,use_cache=1):
		return

	def cpv_all(self):
		cpv_list = []
		for cp in self.cp_all():
			cpv_list.extend(self.cp_list(cp))
		return cpv_list

	def aux_get(self,mycpv,mylist):
		"stub code for returning auxiliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		raise NotImplementedError

	def match(self,origdep,use_cache=1):
		mydep = dep_expand(origdep, mydb=self, settings=self.settings)
		mykey=dep_getkey(mydep)
		mylist = match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
		myslot = portage.dep.dep_getslot(mydep)
		if myslot is not None:
			mylist = [cpv for cpv in mylist \
				if self.aux_get(cpv, ["SLOT"])[0] == myslot]
		return mylist

	def match2(self,mydep,mykey,mylist):
		writemsg("DEPRECATED: dbapi.match2\n")
		match_from_list(mydep,mylist)

	def invalidentry(self, mypath):
		if re.search("portage_lockfile$",mypath):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				portage.locks.unlockfile((mypath,None,None))
			else:
				# Nothing we can do about it. We're probably sandboxed.
				pass
		elif re.search(".*/-MERGING-(.*)",mypath):
			if os.path.exists(mypath):
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n", noiselevel=-1)
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath, noiselevel=-1)



class fakedbapi(dbapi):
	"This is a dbapi to use for the emptytree function.  It's empty, but things can be added to it."
	def __init__(self, settings=None):
		self.cpvdict={}
		self.cpdict={}
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings
		self._match_cache = {}

	def _clear_cache(self):
		if self._match_cache:
			self._match_cache = {}

	def match(self, origdep, use_cache=1):
		result = self._match_cache.get(origdep, None)
		if result is not None:
			return result[:]
		result = dbapi.match(self, origdep, use_cache=use_cache)
		self._match_cache[origdep] = result
		return result[:]

	def cpv_exists(self,mycpv):
		return self.cpvdict.has_key(mycpv)

	def cp_list(self,mycp,use_cache=1):
		if not self.cpdict.has_key(mycp):
			return []
		else:
			return self.cpdict[mycp]

	def cp_all(self):
		returnme=[]
		for x in self.cpdict.keys():
			returnme.extend(self.cpdict[x])
		return returnme

	def cpv_all(self):
		return self.cpvdict.keys()

	def cpv_inject(self, mycpv, metadata=None):
		"""Adds a cpv from the list of available packages."""
		self._clear_cache()
		mycp=cpv_getkey(mycpv)
		self.cpvdict[mycpv] = metadata
		myslot = None
		if metadata:
			myslot = metadata.get("SLOT", None)
		if myslot and mycp in self.cpdict:
			# If necessary, remove another package in the same SLOT.
			for cpv in self.cpdict[mycp]:
				if mycpv != cpv:
					other_metadata = self.cpvdict[cpv]
					if other_metadata:
						if myslot == other_metadata.get("SLOT", None):
							self.cpv_remove(cpv)
							break
		if mycp not in self.cpdict:
			self.cpdict[mycp] = []
		if not mycpv in self.cpdict[mycp]:
			self.cpdict[mycp].append(mycpv)

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		self._clear_cache()
		mycp=cpv_getkey(mycpv)
		if self.cpvdict.has_key(mycpv):
			del	self.cpvdict[mycpv]
		if not self.cpdict.has_key(mycp):
			return
		while mycpv in self.cpdict[mycp]:
			del self.cpdict[mycp][self.cpdict[mycp].index(mycpv)]
		if not len(self.cpdict[mycp]):
			del self.cpdict[mycp]

	def aux_get(self, mycpv, wants):
		if not self.cpv_exists(mycpv):
			raise KeyError(mycpv)
		metadata = self.cpvdict[mycpv]
		if not metadata:
			return ["" for x in wants]
		return [metadata.get(x, "") for x in wants]

	def aux_update(self, cpv, values):
		self._clear_cache()
		self.cpvdict[cpv].update(values)

class bindbapi(fakedbapi):
	def __init__(self, mybintree=None, settings=None):
		self.bintree = mybintree
		self.cpvdict={}
		self.cpdict={}
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings
		self._match_cache = {}
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(["SLOT"])
		self._aux_cache = {}

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def aux_get(self,mycpv,wants):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		cache_me = False
		if not set(wants).difference(self._aux_cache_keys):
			aux_cache = self._aux_cache.get(mycpv)
			if aux_cache is not None:
				return [aux_cache[x] for x in wants]
			cache_me = True
		mysplit = mycpv.split("/")
		mylist  = []
		tbz2name = mysplit[1]+".tbz2"
		if self.bintree and not self.bintree.isremote(mycpv):
			tbz2 = portage.xpak.tbz2(self.bintree.getname(mycpv))
			getitem = tbz2.getfile
		else:
			getitem = self.bintree.remotepkgs[tbz2name].get
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
		mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))

	def cp_list(self, *pargs, **kwargs):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cp_list(self, *pargs, **kwargs)

	def cpv_all(self):
		if not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.cpv_all(self)

class vardbapi(dbapi):
	def __init__(self, root, categories=None, settings=None, vartree=None):
		self.root       = root[:]
		#cache for category directory mtimes
		self.mtdircache = {}
		#cache for dependency checks
		self.matchcache = {}
		#cache for cp_list results
		self.cpcache    = {}
		self.blockers   = None
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings
		if categories is None:
			categories = settings.categories
		self.categories = categories[:]
		if vartree is None:
			vartree = globals()["db"][root]["vartree"]
		self.vartree = vartree
		self._aux_cache_keys = set(["SLOT", "COUNTER", "PROVIDE", "USE",
			"IUSE", "DEPEND", "RDEPEND", "PDEPEND"])
		self._aux_cache = None
		self._aux_cache_version = "1"
		self._aux_cache_filename = os.path.join(self.root,
			CACHE_PATH.lstrip(os.path.sep), "vdb_metadata.pickle")

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.root+VDB_PATH+"/"+mykey)

	def cpv_counter(self,mycpv):
		"This method will grab the COUNTER. Returns a counter value."
		try:
			return long(self.aux_get(mycpv, ["COUNTER"])[0])
		except KeyError, ValueError:
			pass
		cdir=self.root+VDB_PATH+"/"+mycpv
		cpath=self.root+VDB_PATH+"/"+mycpv+"/COUNTER"

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption on XFS (unexpected reboot.)
		corrupted=0
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except ValueError:
				print "portage: COUNTER for",mycpv,"was corrupted; resetting to value of 0"
				counter=long(0)
				corrupted=1
			cfile.close()
		elif os.path.exists(cdir):
			mys = pkgsplit(mycpv)
			myl = self.match(mys[0],use_cache=0)
			print mys,myl
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
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n",
						noiselevel=-1)
					writemsg("!!! unmerge this exact version.\n", noiselevel=-1)
					writemsg("!!! %s\n" % e, noiselevel=-1)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n",
					noiselevel=-1)
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n",
					noiselevel=-1)
				writemsg("!!! remerge the package.\n", noiselevel=-1)
				sys.exit(1)
		else:
			counter=long(0)
		if corrupted:
			# update new global counter file
			write_atomic(cpath, str(counter))
		return counter

	def cpv_inject(self,mycpv):
		"injects a real package into our on-disk database; assumes mycpv is valid and doesn't already exist"
		os.makedirs(self.root+VDB_PATH+"/"+mycpv)
		counter = self.counter_tick(self.root, mycpv=mycpv)
		# write local package counter so that emerge clean does the right thing
		write_atomic(os.path.join(self.root, VDB_PATH, mycpv, "COUNTER"), str(counter))

	def isInjected(self,mycpv):
		if self.cpv_exists(mycpv):
			if os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/INJECTED"):
				return True
			if not os.path.exists(self.root+VDB_PATH+"/"+mycpv+"/CONTENTS"):
				return True
		return False

	def move_ent(self,mylist):
		origcp=mylist[1]
		newcp=mylist[2]

		# sanity check
		for cp in [origcp,newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise portage.exception.InvalidPackageName(cp)
		origmatches=self.match(origcp,use_cache=0)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			mynewcpv=newcp+"-"+mycpsplit[2]
			mynewcat=newcp.split("/")[0]
			if mycpsplit[3]!="r0":
				mynewcpv += "-"+mycpsplit[3]
			mycpsplit_new = catpkgsplit(mynewcpv)
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue
			writemsg_stdout("@")
			if not os.path.exists(self.root+VDB_PATH+"/"+mynewcat):
				#create the directory
				os.makedirs(self.root+VDB_PATH+"/"+mynewcat)
			newpath=self.root+VDB_PATH+"/"+mynewcpv
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

	def update_ents(self, update_iter):
		"""Run fixdbentries on all installed packages (time consuming).  Like
		fixpackages, this should be run from a helper script and display
		a progress indicator."""
		dbdir = os.path.join(self.root, VDB_PATH)
		for catdir in listdir(dbdir):
			catdir = dbdir+"/"+catdir
			if os.path.isdir(catdir):
				for pkgdir in listdir(catdir):
					pkgdir = catdir+"/"+pkgdir
					if os.path.isdir(pkgdir):
						fixdbentries(update_iter, pkgdir)

	def move_slot_ent(self,mylist):
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]

		if not isvalidatom(pkg):
			raise portage.exception.InvalidAtom(pkg)

		origmatches=self.match(pkg,use_cache=0)
		
		if not origmatches:
			return
		for mycpv in origmatches:
			origpath=self.root+VDB_PATH+"/"+mycpv
			if not os.path.exists(origpath):
				continue

			slot=grabfile(origpath+"/SLOT");
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			writemsg_stdout("s")
			write_atomic(os.path.join(origpath, "SLOT"), newslot+"\n")

	def cp_list(self,mycp,use_cache=1):
		mysplit=mycp.split("/")
		if mysplit[0] == '*':
			mysplit[0] = mysplit[0][1:]
		try:
			mystat=os.stat(self.root+VDB_PATH+"/"+mysplit[0])[stat.ST_MTIME]
		except OSError:
			mystat=0
		if use_cache and self.cpcache.has_key(mycp):
			cpc=self.cpcache[mycp]
			if cpc[0]==mystat:
				return cpc[1]
		list=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)

		if (list is None):
			return []
		returnme=[]
		for x in list:
			if x.startswith("."):
				continue
			if x[0] == '-':
				#writemsg(red("INCOMPLETE MERGE:")+str(x[len("-MERGING-"):])+"\n")
				continue
			ps=pkgsplit(x)
			if not ps:
				self.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if len(mysplit) > 1:
				if ps[0]==mysplit[1]:
					returnme.append(mysplit[0]+"/"+x)
		if use_cache:
			self.cpcache[mycp]=[mystat,returnme]
		elif self.cpcache.has_key(mycp):
			del self.cpcache[mycp]
		return returnme

	def cpv_all(self,use_cache=1):
		returnme=[]
		basepath = self.root+VDB_PATH+"/"

		for x in self.categories:
			for y in listdir(basepath+x,EmptyOnError=1):
				if y.startswith("."):
					continue
				subpath = x+"/"+y
				# -MERGING- should never be a cpv, nor should files.
				if os.path.isdir(basepath+subpath) and (pkgsplit(y) is not None):
					returnme += [subpath]
		return returnme

	def cp_all(self,use_cache=1):
		mylist = self.cpv_all(use_cache=use_cache)
		d={}
		for y in mylist:
			if y[0] == '*':
				y = y[1:]
			mysplit=catpkgsplit(y)
			if not mysplit:
				self.invalidentry(self.root+VDB_PATH+"/"+y)
				continue
			d[mysplit[0]+"/"+mysplit[1]] = None
		return d.keys()

	def checkblockers(self,origdep):
		pass

	def match(self,origdep,use_cache=1):
		"caching match function"
		mydep = dep_expand(
			origdep, mydb=self, use_cache=use_cache, settings=self.settings)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		if not use_cache:
			if self.matchcache.has_key(mycat):
				del self.mtdircache[mycat]
				del self.matchcache[mycat]
			mymatch = match_from_list(mydep,
				self.cp_list(mykey, use_cache=use_cache))
			myslot = portage.dep.dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			return mymatch
		try:
			curmtime=os.stat(self.root+VDB_PATH+"/"+mycat)[stat.ST_MTIME]
		except (IOError, OSError):
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat]=curmtime
			self.matchcache[mycat]={}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch=match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
			myslot = portage.dep.dep_getslot(mydep)
			if myslot is not None:
				mymatch = [cpv for cpv in mymatch \
					if self.aux_get(cpv, ["SLOT"])[0] == myslot]
			self.matchcache[mycat][mydep]=mymatch
		return self.matchcache[mycat][mydep][:]

	def findname(self, mycpv):
		return self.root+VDB_PATH+"/"+str(mycpv)+"/"+mycpv.split("/")[1]+".ebuild"

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
				portage.util.apply_secpass_permissions(
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
				self._aux_cache = {"version":self._aux_cache_version}
				self._aux_cache["packages"] = {}
			self._aux_cache["modified"] = False
		mydir = os.path.join(self.root, VDB_PATH, mycpv)
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
			if cache_valid and set(metadata) != self._aux_cache_keys:
				# Allow self._aux_cache_keys to change without a cache version
				# bump.
				cache_valid = False
		if cache_valid:
			mydata.update(metadata)
			pull_me = set(wants).difference(self._aux_cache_keys)
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
		mydir = os.path.join(self.root, VDB_PATH, mycpv)
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
		cat, pkg = cpv.split("/")
		mylink = dblink(cat, pkg, self.root, self.settings,
		treetype="vartree", vartree=self.vartree)
		if not mylink.exists():
			raise KeyError(cpv)
		for k, v in values.iteritems():
			mylink.setfile(k, v)

	def counter_tick(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,incrementing=1,mycpv=mycpv)

	def get_counter_tick_core(self,myroot,mycpv=None):
		return self.counter_tick_core(myroot,incrementing=0,mycpv=mycpv)+1

	def counter_tick_core(self,myroot,incrementing=1,mycpv=None):
		"This method will grab the next COUNTER value and record it back to the global file.  Returns new counter value."
		cpath=myroot+"var/cache/edb/counter"
		changed=0
		min_counter = 0
		if mycpv:
			mysplit = pkgsplit(mycpv)
			for x in self.match(mysplit[0],use_cache=0):
				if x==mycpv:
					continue
				try:
					old_counter = long(self.aux_get(x,["COUNTER"])[0])
					writemsg("COUNTER '%d' '%s'\n" % (old_counter, x),1)
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
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except (ValueError,OverflowError):
				try:
					counter = long(commands.getoutput(find_counter).strip())
					writemsg("!!! COUNTER was corrupted; resetting to value of %d\n" % counter,
						noiselevel=-1)
					changed=1
				except (ValueError,OverflowError):
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
				counter=long(0)
			changed=1

		if counter < min_counter:
			counter = min_counter+1000
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
			self.root       = clone.root[:]
			self.dbapi      = copy.deepcopy(clone.dbapi)
			self.populated  = 1
			self.settings   = config(clone=clone.settings)
		else:
			self.root       = root[:]
			if settings is None:
				settings = globals()["settings"]
			self.settings = settings # for key_expand calls
			if categories is None:
				categories = settings.categories
			self.dbapi = vardbapi(self.root, categories=categories,
				settings=settings, vartree=self)
			self.populated  = 1

	def zap(self,mycpv):
		return

	def inject(self,mycpv):
		return

	def get_provide(self,mycpv):
		myprovides=[]
		mylines = None
		try:
			mylines, myuse = self.dbapi.aux_get(mycpv, ["PROVIDE","USE"])
			if mylines:
				myuse = myuse.split()
				mylines = flatten(portage.dep.use_reduce(portage.dep.paren_reduce(mylines), uselist=myuse))
				for myprovide in mylines:
					mys = catpkgsplit(myprovide)
					if not mys:
						mys = myprovide.split("/")
					myprovides += [mys[0] + "/" + mys[1]]
			return myprovides
		except SystemExit, e:
			raise
		except Exception, e:
			mydir = os.path.join(self.root, VDB_PATH, mycpv)
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
					myprovides[mykey]  = [node]
		return myprovides

	def dep_bestmatch(self,mydep,use_cache=1):
		"compatibility method -- all matches, not just visible ones"
		#mymatch=best(match(dep_expand(mydep,self.dbapi),self.dbapi))
		mymatch = best(self.dbapi.match(
			dep_expand(mydep, mydb=self.dbapi, settings=self.settings),
			use_cache=use_cache))
		if mymatch is None:
			return ""
		else:
			return mymatch

	def dep_match(self,mydep,use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch=match(mydep,self.dbapi)
		mymatch=self.dbapi.match(mydep,use_cache=use_cache)
		if mymatch is None:
			return []
		else:
			return mymatch

	def exists_specific(self,cpv):
		return self.dbapi.cpv_exists(cpv)

	def getallcpv(self):
		"""temporary function, probably to be renamed --- Gets a list of all
		category/package-versions installed on the system."""
		return self.dbapi.cpv_all()

	def getallnodes(self):
		"""new behavior: these are all *unmasked* nodes.  There may or may not be available
		masked package for nodes in this nodes list."""
		return self.dbapi.cp_all()

	def exists_specific_cat(self,cpv,use_cache=1):
		cpv = key_expand(cpv, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		a=catpkgsplit(cpv)
		if not a:
			return 0
		mylist=listdir(self.root+VDB_PATH+"/"+a[0],EmptyOnError=1)
		for x in mylist:
			b=pkgsplit(x)
			if not b:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+a[0]+"/"+x)
				continue
			if a[1]==b[0]:
				return 1
		return 0

	def getebuildpath(self,fullpackage):
		cat,package=fullpackage.split("/")
		return self.root+VDB_PATH+"/"+fullpackage+"/"+package+".ebuild"

	def getnode(self,mykey,use_cache=1):
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		if not mykey:
			return []
		mysplit=mykey.split("/")
		mydirlist=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)
		returnme=[]
		for x in mydirlist:
			mypsplit=pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if mypsplit[0]==mysplit[1]:
				appendme=[mysplit[0]+"/"+x,[mysplit[0],mypsplit[0],mypsplit[1],mypsplit[2]]]
				returnme.append(appendme)
		return returnme


	def getslot(self,mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		try:
			return self.dbapi.aux_get(mycatpkg, ["SLOT"])[0]
		except KeyError:
			return ""

	def hasnode(self,mykey,use_cache):
		"""Does the particular node (cat/pkg key) exist?"""
		mykey = key_expand(mykey, mydb=self.dbapi, use_cache=use_cache,
			settings=self.settings)
		mysplit=mykey.split("/")
		mydirlist=listdir(self.root+VDB_PATH+"/"+mysplit[0],EmptyOnError=1)
		for x in mydirlist:
			mypsplit=pkgsplit(x)
			if not mypsplit:
				self.dbapi.invalidentry(self.root+VDB_PATH+"/"+mysplit[0]+"/"+x)
				continue
			if mypsplit[0]==mysplit[1]:
				return 1
		return 0

	def populate(self):
		self.populated=1

auxdbkeys=[
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE',      'CDEPEND',
	'PDEPEND',   'PROVIDE', 'EAPI',
	'UNUSED_01', 'UNUSED_02', 'UNUSED_03', 'UNUSED_04',
	'UNUSED_05', 'UNUSED_06', 'UNUSED_07',
	]
auxdbkeylen=len(auxdbkeys)

def close_portdbapi_caches():
	for i in portdbapi.portdbapi_instances:
		i.close_caches()


class portdbapi(dbapi):
	"""this tree will scan a portage directory located at root (passed to init)"""
	portdbapi_instances = []

	def __init__(self,porttree_root,mysettings=None):
		portdbapi.portdbapi_instances.append(self)

		if mysettings:
			self.mysettings = mysettings
		else:
			global settings
			self.mysettings = config(clone=settings)

		# This is strictly for use in aux_get() doebuild calls when metadata
		# is generated by the depend phase.  It's safest to use a clone for
		# this purpose because doebuild makes many changes to the config
		# instance that is passed in.
		self.doebuild_settings = config(clone=self.mysettings)

		self.manifestVerifyLevel  = None
		self.manifestVerifier     = None
		self.manifestCache        = {}    # {location: [stat, md5]}
		self.manifestMissingCache = []

		if "gpg" in self.mysettings.features:
			self.manifestVerifyLevel   = portage.gpg.EXISTS
			if "strict" in self.mysettings.features:
				self.manifestVerifyLevel = portage.gpg.MARGINAL
				self.manifestVerifier = portage.gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", minimumTrust=self.manifestVerifyLevel)
			elif "severe" in self.mysettings.features:
				self.manifestVerifyLevel = portage.gpg.TRUSTED
				self.manifestVerifier = portage.gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", requireSignedRing=True, minimumTrust=self.manifestVerifyLevel)
			else:
				self.manifestVerifier = portage.gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", minimumTrust=self.manifestVerifyLevel)

		#self.root=settings["PORTDIR"]
		self.porttree_root = os.path.realpath(porttree_root)

		self.depcachedir = self.mysettings.depcachedir[:]

		self.tmpfs = self.mysettings["PORTAGE_TMPFS"]
		if self.tmpfs and not os.path.exists(self.tmpfs):
			self.tmpfs = None
		if self.tmpfs and not os.access(self.tmpfs, os.W_OK):
			self.tmpfs = None
		if self.tmpfs and not os.access(self.tmpfs, os.R_OK):
			self.tmpfs = None

		self.eclassdb = portage.eclass_cache.cache(self.porttree_root,
			overlays=self.mysettings["PORTDIR_OVERLAY"].split())

		self.metadbmodule = self.mysettings.load_best_module("portdbapi.metadbmodule")

		#if the portdbapi is "frozen", then we assume that we can cache everything (that no updates to it are happening)
		self.xcache={}
		self.frozen=0

		self.porttrees = [self.porttree_root] + \
			[os.path.realpath(t) for t in self.mysettings["PORTDIR_OVERLAY"].split()]
		self.treemap = {}
		for path in self.porttrees:
			repo_name_path = os.path.join( path, REPO_NAME_LOC )
			try:
				repo_name = open( repo_name_path ,'r').readline().strip()
				self.treemap[repo_name] = path
			except (OSError,IOError):
				pass
		
		self.auxdbmodule  = self.mysettings.load_best_module("portdbapi.auxdbmodule")
		self.auxdb        = {}
		self._init_cache_dirs()
		# XXX: REMOVE THIS ONCE UNUSED_0 IS YANKED FROM auxdbkeys
		# ~harring
		filtered_auxdbkeys = filter(lambda x: not x.startswith("UNUSED_0"), auxdbkeys)
		if secpass < 1:
			from portage.cache import metadata_overlay, volatile
			for x in self.porttrees:
				db_ro = self.auxdbmodule(self.depcachedir, x,
					filtered_auxdbkeys, gid=portage_gid, readonly=True)
				self.auxdb[x] = metadata_overlay.database(
					self.depcachedir, x, filtered_auxdbkeys,
					gid=portage_gid, db_rw=volatile.database,
					db_ro=db_ro)
		else:
			for x in self.porttrees:
				# location, label, auxdbkeys
				self.auxdb[x] = self.auxdbmodule(
					self.depcachedir, x, filtered_auxdbkeys, gid=portage_gid)
		# Selectively cache metadata in order to optimize dep matching.
		self._aux_cache_keys = set(["EAPI", "KEYWORDS", "SLOT"])
		self._aux_cache = {}

	def _init_cache_dirs(self):
		"""Create /var/cache/edb/dep and adjust permissions for the portage
		group."""

		dirmode  = 02070
		filemode =   060
		modemask =    02

		try:
			for mydir in (self.depcachedir,):
				if portage.util.ensure_dirs(mydir, gid=portage_gid, mode=dirmode, mask=modemask):
					writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage.exception.OperationNotPermitted(
							"Failed to apply recursive permissions for the portage group.")
		except portage.exception.PortageException, e:
			pass

	def close_caches(self):
		for x in self.auxdb.keys():
			self.auxdb[x].sync()
		self.auxdb.clear()

	def flush_cache(self):
		for x in self.auxdb.values():
			x.sync()

	def finddigest(self,mycpv):
		try:
			mydig   = self.findname2(mycpv)[0]
			if not mydig:
				return ""
			mydigs  = mydig.split("/")[:-1]
			mydig   = "/".join(mydigs)
			mysplit = mycpv.split("/")
		except OSError:
			return ""
		return mydig+"/files/digest-"+mysplit[-1]

	def findname(self,mycpv):
		return self.findname2(mycpv)[0]

	def getRepositoryPath( self, repository_id ):
		"""
		This function is required for GLEP 42 compliance; given a valid repository ID
		it must return a path to the repository
		TreeMap = { id:path }
		"""
		if repository_id in self.treemap:
			return self.treemap[repository_id]
		return None

	def getRepositories( self ):
		"""
		This function is required for GLEP 42 compliance; it will return a list of
		repository ID's
		TreeMap = { id:path }
		"""
		return [k for k in self.treemap.keys() if k]

	def findname2(self, mycpv, mytree=None):
		""" 
		Returns the location of the CPV, and what overlay it was in.
		Searches overlays first, then PORTDIR; this allows us to return the first
		matching file.  As opposed to starting in portdir and then doing overlays
		second, we would have to exhaustively search the overlays until we found
		the file we wanted.
		"""
		if not mycpv:
			return "",0
		mysplit=mycpv.split("/")
		psplit=pkgsplit(mysplit[1])

		if mytree:
			mytrees = [mytree]
		else:
			mytrees = self.porttrees[:]
			mytrees.reverse()
		if psplit:
			for x in mytrees:
				file=x+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"
				if os.access(file, os.R_OK):
					return[file, x]
		return None, 0

	def aux_get(self, mycpv, mylist, mytree=None):
		"stub code for returning auxilliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or raise KeyError if error'
		cache_me = False
		if not mytree and not set(mylist).difference(self._aux_cache_keys):
			aux_cache = self._aux_cache.get(mycpv)
			if aux_cache is not None:
				return [aux_cache[x] for x in mylist]
			cache_me = True
		global auxdbkeys,auxdbkeylen
		cat,pkg = mycpv.split("/", 1)

		myebuild, mylocation = self.findname2(mycpv, mytree)

		if not myebuild:
			writemsg("!!! aux_get(): ebuild path for '%(cpv)s' not specified:\n" % {"cpv":mycpv},
				noiselevel=1)
			writemsg("!!!            %s\n" % myebuild, noiselevel=1)
			raise KeyError(mycpv)

		myManifestPath = "/".join(myebuild.split("/")[:-1])+"/Manifest"
		if "gpg" in self.mysettings.features:
			try:
				mys = portage.gpg.fileStats(myManifestPath)
				if (myManifestPath in self.manifestCache) and \
				   (self.manifestCache[myManifestPath] == mys):
					pass
				elif self.manifestVerifier:
					if not self.manifestVerifier.verify(myManifestPath):
						# Verification failed the desired level.
						raise portage.exception.UntrustedSignature, "Untrusted Manifest: %(manifest)s" % {"manifest":myManifestPath}

				if ("severe" in self.mysettings.features) and \
				   (mys != portage.gpg.fileStats(myManifestPath)):
					raise portage.exception.SecurityViolation, "Manifest changed: %(manifest)s" % {"manifest":myManifestPath}

			except portage.exception.InvalidSignature, e:
				if ("strict" in self.mysettings.features) or \
				   ("severe" in self.mysettings.features):
					raise
				writemsg("!!! INVALID MANIFEST SIGNATURE DETECTED: %(manifest)s\n" % {"manifest":myManifestPath})
			except portage.exception.MissingSignature, e:
				if ("severe" in self.mysettings.features):
					raise
				if ("strict" in self.mysettings.features):
					if myManifestPath not in self.manifestMissingCache:
						writemsg("!!! WARNING: Missing signature in: %(manifest)s\n" % {"manifest":myManifestPath})
						self.manifestMissingCache.insert(0,myManifestPath)
			except (OSError,portage.exception.FileNotFound), e:
				if ("strict" in self.mysettings.features) or \
				   ("severe" in self.mysettings.features):
					raise portage.exception.SecurityViolation, "Error in verification of signatures: %(errormsg)s" % {"errormsg":str(e)}
				writemsg("!!! Manifest is missing or inaccessable: %(manifest)s\n" % {"manifest":myManifestPath},
					noiselevel=-1)


		if os.access(myebuild, os.R_OK):
			emtime=os.stat(myebuild)[stat.ST_MTIME]
		else:
			writemsg("!!! aux_get(): ebuild for '%(cpv)s' does not exist at:\n" % {"cpv":mycpv},
				noiselevel=-1)
			writemsg("!!!            %s\n" % myebuild,
				noiselevel=-1)
			raise KeyError

		try:
			mydata = self.auxdb[mylocation][mycpv]
			if emtime != long(mydata.get("_mtime_", 0)):
				doregen = True
			elif len(mydata.get("_eclasses_", [])) > 0:
				doregen = not self.eclassdb.is_eclass_data_valid(mydata["_eclasses_"])
			else:
				doregen = False
				
		except KeyError:
			doregen = True
		except CacheError:
			doregen = True
			try:				del self.auxdb[mylocation][mycpv]
			except KeyError:	pass

		writemsg("auxdb is valid: "+str(not doregen)+" "+str(pkg)+"\n", 2)

		if doregen:
			writemsg("doregen: %s %s\n" % (doregen,mycpv), 2)
			writemsg("Generating cache entry(0) for: "+str(myebuild)+"\n",1)

			self.doebuild_settings.reset()
			mydata = {}
			myret = doebuild(myebuild, "depend",
				self.doebuild_settings["ROOT"], self.doebuild_settings,
				dbkey=mydata, tree="porttree", mydbapi=self)
			if myret != os.EX_OK:
				raise KeyError(mycpv)

			if "EAPI" not in mydata or not mydata["EAPI"].strip():
				mydata["EAPI"] = "0"

			if not eapi_is_supported(mydata["EAPI"]):
				# if newer version, wipe everything and negate eapi
				eapi = mydata["EAPI"]
				mydata = {}
				map(lambda x:mydata.setdefault(x, ""), auxdbkeys)
				mydata["EAPI"] = "-"+eapi

			if mydata.get("INHERITED", False):
				mydata["_eclasses_"] = self.eclassdb.get_eclass_data(mydata["INHERITED"].split())
			else:
				mydata["_eclasses_"] = {}
			
			del mydata["INHERITED"]

			mydata["_mtime_"] = emtime

			self.auxdb[mylocation][mycpv] = mydata

		if not mydata.setdefault("EAPI", "0"):
			mydata["EAPI"] = "0"

		#finally, we look at our internal cache entry and return the requested data.
		returnme = []
		for x in mylist:
			if x == "INHERITED":
				returnme.append(' '.join(mydata.get("_eclasses_", {}).keys()))
			else:
				returnme.append(mydata.get(x,""))

		if cache_me:
			aux_cache = {}
			for x in self._aux_cache_keys:
				aux_cache[x] = mydata.get(x, "")
			self._aux_cache[mycpv] = aux_cache

		return returnme

	def getfetchlist(self, mypkg, useflags=None, mysettings=None, all=0, mytree=None):
		if mysettings is None:
			mysettings = self.mysettings
		try:
			myuris = self.aux_get(mypkg, ["SRC_URI"], mytree=mytree)[0]
		except KeyError:
			print red("getfetchlist():")+" aux_get() error reading "+mypkg+"; aborting."
			sys.exit(1)

		if useflags is None:
			useflags = mysettings["USE"].split()

		myurilist = portage.dep.paren_reduce(myuris)
		myurilist = portage.dep.use_reduce(myurilist,uselist=useflags,matchall=all)
		newuris = flatten(myurilist)

		myfiles = []
		for x in newuris:
			mya = os.path.basename(x)
			if not mya in myfiles:
				myfiles.append(mya)
		return [newuris, myfiles]

	def getfetchsizes(self,mypkg,useflags=None,debug=0):
		# returns a filename:size dictionnary of remaining downloads
		myebuild = self.findname(mypkg)
		pkgdir = os.path.dirname(myebuild)
		mf = Manifest(pkgdir, self.mysettings["DISTDIR"])
		checksums = mf.getDigests()
		if not checksums:
			if debug: print "[empty/missing/bad digest]: "+mypkg
			return None
		filesdict={}
		if useflags is None:
			myuris, myfiles = self.getfetchlist(mypkg,all=1)
		else:
			myuris, myfiles = self.getfetchlist(mypkg,useflags=useflags)
		#XXX: maybe this should be improved: take partial downloads
		# into account? check checksums?
		for myfile in myfiles:
			if myfile not in checksums:
				if debug:
					writemsg("[bad digest]: missing %s for %s\n" % (myfile, mypkg))
				continue
			file_path = os.path.join(self.mysettings["DISTDIR"], myfile)
			mystat = None
			try:
				mystat = os.stat(file_path)
			except OSError, e:
				pass
			if mystat is None:
				existing_size = 0
			else:
				existing_size = mystat.st_size
			remaining_size = int(checksums[myfile]["size"]) - existing_size
			if remaining_size > 0:
				# Assume the download is resumable.
				filesdict[myfile] = remaining_size
			elif remaining_size < 0:
				# The existing file is too large and therefore corrupt.
				filesdict[myfile] = int(checksums[myfile]["size"])
		return filesdict

	def fetch_check(self, mypkg, useflags=None, mysettings=None, all=False):
		if not useflags:
			if mysettings:
				useflags = mysettings["USE"].split()
		myuri, myfiles = self.getfetchlist(mypkg, useflags=useflags, mysettings=mysettings, all=all)
		myebuild = self.findname(mypkg)
		pkgdir = os.path.dirname(myebuild)
		mf = Manifest(pkgdir, self.mysettings["DISTDIR"])
		mysums = mf.getDigests()

		failures = {}
		for x in myfiles:
			if not mysums or x not in mysums:
				ok     = False
				reason = "digest missing"
			else:
				try:
					ok, reason = portage.checksum.verify_all(
						os.path.join(self.mysettings["DISTDIR"], x), mysums[x])
				except portage.exception.FileNotFound, e:
					ok = False
					reason = "File Not Found: '%s'" % str(e)
			if not ok:
				failures[x] = reason
		if failures:
			return False
		return True

	def getsize(self,mypkg,useflags=None,debug=0):
		# returns the total size of remaining downloads
		#
		# we use getfetchsizes() now, so this function would be obsoleted
		#
		filesdict=self.getfetchsizes(mypkg,useflags=useflags,debug=debug)
		if filesdict is None:
			return "[empty/missing/bad digest]"
		mysize=0
		for myfile in filesdict.keys():
			mysum+=filesdict[myfile]
		return mysum

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		cps2=mykey.split("/")
		cps=catpkgsplit(mykey,silent=0)
		if not cps:
			#invalid cat/pkg-v
			return 0
		if self.findname(cps[0]+"/"+cps2[1]):
			return 1
		else:
			return 0

	def cp_all(self):
		"returns a list of all keys in our tree"
		d={}
		for x in self.mysettings.categories:
			for oroot in self.porttrees:
				for y in listdir(oroot+"/"+x,EmptyOnError=1,ignorecvs=1,dirsonly=1):
					d[x+"/"+y] = None
		l = d.keys()
		l.sort()
		return l

	def p_list(self,mycp):
		d={}
		for oroot in self.porttrees:
			for x in listdir(oroot+"/"+mycp,EmptyOnError=1,ignorecvs=1):
				if x[-7:]==".ebuild":
					d[x[:-7]] = None
		return d.keys()

	def cp_list(self, mycp, use_cache=1, mytree=None):
		mysplit=mycp.split("/")
		d={}
		if mytree:
			mytrees = [mytree]
		else:
			mytrees = self.porttrees
		for oroot in mytrees:
			for x in listdir(oroot+"/"+mycp,EmptyOnError=1,ignorecvs=1):
				if x.endswith(".ebuild"):
					pf = x[:-7]
					ps = pkgsplit(pf)
					if not ps:
						writemsg("\nInvalid ebuild name: %s\n" % \
							os.path.join(oroot, mycp, x), noiselevel=-1)
						continue
					d[mysplit[0]+"/"+pf] = None
		return d.keys()

	def freeze(self):
		for x in ["list-visible","bestmatch-visible","match-visible","match-all"]:
			self.xcache[x]={}
		self.frozen=1

	def melt(self):
		self.xcache={}
		self.frozen=0

	def xmatch(self,level,origdep,mydep=None,mykey=None,mylist=None):
		"caching match function; very trick stuff"
		#if no updates are being made to the tree, we can consult our xcache...
		if self.frozen:
			try:
				return self.xcache[level][origdep][:]
			except KeyError:
				pass

		if not mydep:
			#this stuff only runs on first call of xmatch()
			#create mydep, mykey from origdep
			mydep = dep_expand(origdep, mydb=self, settings=self.mysettings)
			mykey=dep_getkey(mydep)

		if level=="list-visible":
			#a list of all visible packages, not called directly (just by xmatch())
			#myval=self.visible(self.cp_list(mykey))
			myval=self.gvisible(self.visible(self.cp_list(mykey)))
		elif level=="bestmatch-visible":
			#dep match -- best match of all visible packages
			myval=best(self.xmatch("match-visible",None,mydep=mydep,mykey=mykey))
			#get all visible matches (from xmatch()), then choose the best one
		elif level=="bestmatch-list":
			#dep match -- find best match but restrict search to sublist
			myval=best(match_from_list(mydep,mylist))
			#no point is calling xmatch again since we're not caching list deps
		elif level=="match-list":
			#dep match -- find all matches but restrict search to sublist (used in 2nd half of visible())
			myval=match_from_list(mydep,mylist)
		elif level=="match-visible":
			#dep match -- find all visible matches
			myval = match_from_list(mydep,
				self.xmatch("list-visible", mykey, mydep=mykey, mykey=mykey))
			#get all visible packages, then get the matching ones
		elif level=="match-all":
			#match *all* visible *and* masked packages
			myval=match_from_list(mydep,self.cp_list(mykey))
		else:
			print "ERROR: xmatch doesn't handle",level,"query!"
			raise KeyError
		myslot = portage.dep.dep_getslot(mydep)
		if myslot is not None:
			slotmatches = []
			for cpv in myval:
				try:
					if self.aux_get(cpv, ["SLOT"])[0] == myslot:
						slotmatches.append(cpv)
				except KeyError:
					pass # ebuild masked by corruption
			myval = slotmatches
		if self.frozen and (level not in ["match-list","bestmatch-list"]):
			self.xcache[level][mydep]=myval
			if origdep and origdep != mydep:
				self.xcache[level][origdep] = myval
		return myval[:]

	def match(self,mydep,use_cache=1):
		return self.xmatch("match-visible",mydep)

	def visible(self,mylist):
		"""two functions in one.  Accepts a list of cpv values and uses the package.mask *and*
		packages file to remove invisible entries, returning remaining items.  This function assumes
		that all entries in mylist have the same category and package name."""
		if (mylist is None) or (len(mylist)==0):
			return []
		newlist=mylist[:]
		#first, we mask out packages in the package.mask file
		mykey=newlist[0]
		cpv=catpkgsplit(mykey)
		if not cpv:
			#invalid cat/pkg-v
			print "visible(): invalid cat/pkg-v:",mykey
			return []
		mycp=cpv[0]+"/"+cpv[1]
		maskdict=self.mysettings.pmaskdict
		unmaskdict=self.mysettings.punmaskdict
		if maskdict.has_key(mycp):
			for x in maskdict[mycp]:
				mymatches=self.xmatch("match-all",x)
				if mymatches is None:
					#error in package.mask file; print warning and continue:
					print "visible(): package.mask entry \""+x+"\" is invalid, ignoring..."
					continue
				for y in mymatches:
					unmask=0
					if unmaskdict.has_key(mycp):
						for z in unmaskdict[mycp]:
							mymatches_unmask=self.xmatch("match-all",z)
							if y in mymatches_unmask:
								unmask=1
								break
					if unmask==0:
						try:
							newlist.remove(y)
						except ValueError:
							pass

		revmaskdict=self.mysettings.prevmaskdict
		if revmaskdict.has_key(mycp):
			for x in revmaskdict[mycp]:
				#important: only match against the still-unmasked entries...
				#notice how we pass "newlist" to the xmatch() call below....
				#Without this, ~ deps in the packages files are broken.
				mymatches=self.xmatch("match-list",x,mylist=newlist)
				if mymatches is None:
					#error in packages file; print warning and continue:
					print "emerge: visible(): profile packages entry \""+x+"\" is invalid, ignoring..."
					continue
				pos=0
				while pos<len(newlist):
					if newlist[pos] not in mymatches:
						del newlist[pos]
					else:
						pos += 1
		return newlist

	def gvisible(self,mylist):
		"strip out group-masked (not in current group) entries"

		if mylist is None:
			return []
		newlist=[]

		accept_keywords = self.mysettings["ACCEPT_KEYWORDS"].split()
		pkgdict = self.mysettings.pkeywordsdict
		for mycpv in mylist:
			try:
				keys, eapi = self.aux_get(mycpv, ["KEYWORDS", "EAPI"])
			except KeyError:
				continue
			except portage.exception.PortageException, e:
				writemsg("!!! Error: aux_get('%s', ['KEYWORDS', 'EAPI'])\n" % \
					mycpv, noiselevel=-1)
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				del e
				continue
			mygroups=keys.split()
			# Repoman may modify this attribute as necessary.
			pgroups = accept_keywords[:]
			match=0
			cp = dep_getkey(mycpv)
			if pkgdict.has_key(cp):
				matches = match_to_list(mycpv, pkgdict[cp].keys())
				for atom in matches:
					pgroups.extend(pkgdict[cp][atom])
				if matches:
					inc_pgroups = []
					for x in pgroups:
						# The -* special case should be removed once the tree 
						# is clean of KEYWORDS=-* crap
						if x != "-*" and x.startswith("-"):
							try:
								inc_pgroups.remove(x[1:])
							except ValueError:
								pass
						if x not in inc_pgroups:
							inc_pgroups.append(x)
					pgroups = inc_pgroups
					del inc_pgroups
			hasstable = False
			hastesting = False
			for gp in mygroups:
				if gp=="*":
					writemsg("--- WARNING: Package '%s' uses '*' keyword.\n" % mycpv,
						noiselevel=-1)
					match=1
					break
				elif gp in pgroups:
					match=1
					break
				elif gp[0] == "~":
					hastesting = True
				elif gp[0] != "-":
					hasstable = True
			if not match and ((hastesting and "~*" in pgroups) or (hasstable and "*" in pgroups) or "**" in pgroups):
				match=1
			if match and eapi_is_supported(eapi):
				newlist.append(mycpv)
		return newlist

class binarytree(object):
	"this tree scans for a list of all packages available in PKGDIR"
	def __init__(self, root, pkgdir, virtual=None, settings=None, clone=None):
		if clone:
			# XXX This isn't cloning. It's an instance of the same thing.
			self.root=clone.root
			self.pkgdir=clone.pkgdir
			self.dbapi=clone.dbapi
			self.populated=clone.populated
			self.tree=clone.tree
			self.remotepkgs=clone.remotepkgs
			self.invalids=clone.invalids
			self.settings = clone.settings
		else:
			self.root=root
			#self.pkgdir=settings["PKGDIR"]
			self.pkgdir = normalize_path(pkgdir)
			self.dbapi = bindbapi(self, settings=settings)
			self.populated=0
			self.tree={}
			self.remotepkgs={}
			self.invalids=[]
			self.settings = settings
			self._pkg_paths = {}

	def move_ent(self,mylist):
		if not self.populated:
			self.populate()
		origcp=mylist[1]
		newcp=mylist[2]
		# sanity check
		for cp in [origcp,newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise portage.exception.InvalidPackageName(cp)
		origcat = origcp.split("/")[0]
		mynewcat=newcp.split("/")[0]
		origmatches=self.dbapi.cp_list(origcp)
		if not origmatches:
			return
		for mycpv in origmatches:

			mycpsplit=catpkgsplit(mycpv)
			mynewcpv=newcp+"-"+mycpsplit[2]
			if mycpsplit[3]!="r0":
				mynewcpv += "-"+mycpsplit[3]
			myoldpkg=mycpv.split("/")[1]
			mynewpkg=mynewcpv.split("/")[1]

			if (mynewpkg != myoldpkg) and os.path.exists(self.getname(mynewcpv)):
				writemsg("!!! Cannot update binary: Destination exists.\n",
					noiselevel=-1)
				writemsg("!!! "+mycpv+" -> "+mynewcpv+"\n", noiselevel=-1)
				continue

			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n",
					noiselevel=-1)
				continue

			#print ">>> Updating data in:",mycpv
			writemsg_stdout("%")
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
			self.dbapi.cpv_inject(mynewcpv)

		return 1

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

	def move_slot_ent(self, mylist):
		if not self.populated:
			self.populate()
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]
		
		if not isvalidatom(pkg):
			raise portage.exception.InvalidAtom(pkg)
		
		origmatches=self.dbapi.match(pkg)
		if not origmatches:
			return
		for mycpv in origmatches:
			mycpsplit=catpkgsplit(mycpv)
			myoldpkg=mycpv.split("/")[1]
			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n",
					noiselevel=-1)
				continue

			#print ">>> Updating data in:",mycpv
			mytbz2 = portage.xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()

			slot = mydata["SLOT"]
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			writemsg_stdout("S")
			mydata["SLOT"] = newslot+"\n"
			mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))
		return 1

	def update_ents(self, update_iter):
		if len(update_iter) == 0:
			return
		if not self.populated:
			self.populate()

		for mycpv in self.dbapi.cp_all():
			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n",
					noiselevel=-1)
				continue
			#print ">>> Updating binary data:",mycpv
			writemsg_stdout("*")
			mytbz2 = portage.xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			updated_items = update_dbentries(update_iter, mydata)
			if len(updated_items) > 0:
				mydata.update(updated_items)
				mytbz2.recompose_mem(portage.xpak.xpak_mem(mydata))
		return 1

	def prevent_collision(self, cpv):
		"""Make sure that the file location ${PKGDIR}/All/${PF}.tbz2 is safe to
		use for a given cpv.  If a collision will occur with an existing
		package from another category, the existing package will be bumped to
		${PKGDIR}/${CATEGORY}/${PF}.tbz2 so that both can coexist."""
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
				self._move_from_all(other_cat + "/" + mypkg)
		"""The file may or may not exist. Move it if necessary and update
		internal state for future calls to getname()."""
		self._move_to_all(cpv)

	def _move_to_all(self, cpv):
		"""If the file exists, move it.  Whether or not it exists, update state
		for future getname() calls."""
		mycat , mypkg = catsplit(cpv)
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
		mycat , mypkg = catsplit(cpv)
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

	def populate(self, getbinpkgs=0,getbinpkgsonly=0):
		"populates the binarytree"
		if (not os.path.isdir(self.pkgdir) and not getbinpkgs):
			return 0
		if (not os.path.isdir(self.pkgdir+"/All") and not getbinpkgs):
			return 0

		if not getbinpkgsonly:
			pkg_paths = {}
			dirs = listdir(self.pkgdir, dirsonly=True, EmptyOnError=True)
			if "All" in dirs:
				dirs.remove("All")
			dirs.sort()
			dirs.insert(0, "All")
			for mydir in dirs:
				for myfile in listdir(os.path.join(self.pkgdir, mydir)):
					if not myfile.endswith(".tbz2"):
						continue
					mypath = os.path.join(mydir, myfile)
					full_path = os.path.join(self.pkgdir, mypath)
					if os.path.islink(full_path):
						continue
					mytbz2 = portage.xpak.tbz2(full_path)
					# For invalid packages, mycat could be None.
					mycat = mytbz2.getfile("CATEGORY")
					mypf = mytbz2.getfile("PF")
					mypkg = myfile[:-5]
					if not mycat or not mypf:
						#old-style or corrupt package
						writemsg("!!! Invalid binary package: '%s'\n" % full_path,
							noiselevel=-1)
						writemsg("!!! This binary package is not " + \
							"recoverable and should be deleted.\n",
							noiselevel=-1)
						self.invalids.append(mypkg)
						continue
					mycat = mycat.strip()
					if mycat != mydir and mydir != "All":
						continue
					if mypkg != mypf.strip():
						continue
					mycpv = mycat + "/" + mypkg
					if mycpv in pkg_paths:
						# All is first, so it's preferred.
						continue
					pkg_paths[mycpv] = mypath
					self.dbapi.cpv_inject(mycpv)
			self._pkg_paths = pkg_paths

		if getbinpkgs and not self.settings["PORTAGE_BINHOST"]:
			writemsg(red("!!! PORTAGE_BINHOST unset, but use is requested.\n"),
				noiselevel=-1)

		if getbinpkgs and \
			self.settings["PORTAGE_BINHOST"] and not self.remotepkgs:
			try:
				chunk_size = long(self.settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except (ValueError, KeyError):
				chunk_size = 3000

			writemsg(green("Fetching binary packages info...\n"))
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
				mycat=self.remotepkgs[mypkg]["CATEGORY"].strip()
				fullpkg=mycat+"/"+mypkg[:-5]
				mykey=dep_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					#print "cpv_inject("+str(fullpkg)+")"
					self.dbapi.cpv_inject(fullpkg)
					#print "  -- Injected"
				except SystemExit, e:
					raise
				except:
					writemsg("!!! Failed to inject remote binary package:"+str(fullpkg)+"\n",
						noiselevel=-1)
					del self.remotepkgs[mypkg]
					continue
		self.populated=1

	def inject(self,cpv):
		return self.dbapi.cpv_inject(cpv)

	def exists_specific(self,cpv):
		if not self.populated:
			self.populate()
		return self.dbapi.match(
			dep_expand("="+cpv, mydb=self.dbapi, settings=self.settings))

	def dep_bestmatch(self,mydep):
		"compatibility method -- all matches, not just visible ones"
		if not self.populated:
			self.populate()
		writemsg("\n\n", 1)
		writemsg("mydep: %s\n" % mydep, 1)
		mydep = dep_expand(mydep, mydb=self.dbapi, settings=self.settings)
		writemsg("mydep: %s\n" % mydep, 1)
		mykey=dep_getkey(mydep)
		writemsg("mykey: %s\n" % mykey, 1)
		mymatch=best(match_from_list(mydep,self.dbapi.cp_list(mykey)))
		writemsg("mymatch: %s\n" % mymatch, 1)
		if mymatch is None:
			return ""
		return mymatch

	def getname(self,pkgname):
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
		mypath = os.path.join("All", mypkg + ".tbz2")
		if mypath in self._pkg_paths.values():
			mypath = os.path.join(mycat, mypkg + ".tbz2")
		self._pkg_paths[mycpv] = mypath # cache for future lookups
		return os.path.join(self.pkgdir, mypath)

	def isremote(self,pkgname):
		"Returns true if the package is kept remotely."
		mysplit=pkgname.split("/")
		remote = (not os.path.exists(self.getname(pkgname))) and self.remotepkgs.has_key(mysplit[1]+".tbz2")
		return remote

	def get_use(self,pkgname):
		mysplit=pkgname.split("/")
		if self.isremote(pkgname):
			return self.remotepkgs[mysplit[1]+".tbz2"]["USE"][:].split()
		tbz2=portage.xpak.tbz2(self.getname(pkgname))
		return tbz2.getfile("USE").split()

	def gettbz2(self,pkgname):
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
		mydest = self.pkgdir+"/All/"
		try:
			os.makedirs(mydest, 0775)
		except (OSError, IOError):
			pass
		return portage.getbinpkg.file_get(
			self.settings["PORTAGE_BINHOST"] + "/" + tbz2name,
			mydest, fcmd=self.settings["RESUMECOMMAND"])

	def getslot(self,mycatpkg):
		"Get a slot for a catpkg; assume it exists."
		myslot = ""
		try:
			myslot=self.dbapi.aux_get(mycatpkg,["SLOT"])[0]
		except SystemExit, e:
			raise
		except Exception, e:
			pass
		return myslot

class dblink:
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
		
		self.cat     = cat
		self.pkg     = pkg
		self.mycpv   = self.cat+"/"+self.pkg
		self.mysplit = pkgsplit(self.mycpv)
		self.treetype = treetype
		if vartree is None:
			global db
			vartree = db[myroot]["vartree"]
		self.vartree = vartree

		self.dbroot   = normalize_path(os.path.join(myroot, VDB_PATH))
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir    = self.dbpkgdir

		self._lock_vdb = None

		self.settings = mysettings
		if self.settings==1:
			raise ValueError

		self.myroot=myroot
		protect_obj = portage.util.ConfigProtect(myroot,
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
		portage.util.ensure_dirs(self.dbroot)
		self._lock_vdb = portage.locks.lockdir(self.dbroot)

	def unlockdb(self):
		if self._lock_vdb:
			portage.locks.unlockdir(self._lock_vdb)
			self._lock_vdb = None

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir

	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)

	def create(self):
		"create the skeleton db directory structure.  No contents, virtuals, provides or anything.  Also will create /var/db/pkg if necessary."
		"""
		This function should never get called (there is no reason to use it).
		"""
		# XXXXX Delete this eventually
		raise Exception, "This is bad. Don't use it."
		if not os.path.exists(self.dbdir):
			os.makedirs(self.dbdir)

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
		if not os.path.exists(self.dbdir+"/CONTENTS"):
			return None
		if self.contentscache != []:
			return self.contentscache
		pkgfiles={}
		myc=open(self.dbdir+"/CONTENTS","r")
		mylines=myc.readlines()
		myc.close()
		null_byte = "\0"
		contents_file = os.path.join(self.dbdir, "CONTENTS")
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
				if mydat[0]=="obj":
					#format: type, mtime, md5sum
					pkgfiles[" ".join(mydat[1:-2])]=[mydat[0], mydat[-1], mydat[-2]]
				elif mydat[0]=="dir":
					#format: type
					pkgfiles[" ".join(mydat[1:])]=[mydat[0] ]
				elif mydat[0]=="sym":
					#format: type, mtime, dest
					x=len(mydat)-1
					if (x >= 13) and (mydat[-1][-1]==')'): # Old/Broken symlink entry
						mydat = mydat[:-10]+[mydat[-10:][stat.ST_MTIME][:-1]]
						writemsg("FIXED SYMLINK LINE: %s\n" % mydat, 1)
						x=len(mydat)-1
					splitter=-1
					while(x>=0):
						if mydat[x]=="->":
							splitter=x
							break
						x=x-1
					if splitter==-1:
						return None
					pkgfiles[" ".join(mydat[1:splitter])]=[mydat[0], mydat[-1], " ".join(mydat[(splitter+1):-1])]
				elif mydat[0]=="dev":
					#format: type
					pkgfiles[" ".join(mydat[1:])]=[mydat[0] ]
				elif mydat[0]=="fif":
					#format: type
					pkgfiles[" ".join(mydat[1:])]=[mydat[0]]
				else:
					return None
			except (KeyError,IndexError):
				print "portage: CONTENTS line",pos,"corrupt!"
		self.contentscache=pkgfiles
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
			except portage.exception.UnsupportedAPIException, e:
				# Sometimes this happens due to corruption of the EAPI file.
				writemsg("!!! FAILED prerm: %s\n" % \
					os.path.join(self.dbdir, "EAPI"), noiselevel=-1)
				writemsg("%s\n" % str(e), noiselevel=-1)
				return 1
			catdir = os.path.dirname(self.settings["PORTAGE_BUILDDIR"])
			portage.util.ensure_dirs(os.path.dirname(catdir),
				uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		builddir_lock = None
		catdir_lock = None
		try:
			if myebuildpath:
				catdir_lock = portage.locks.lockdir(catdir)
				portage.util.ensure_dirs(catdir,
					uid=portage_uid, gid=portage_gid,
					mode=070, mask=0)
				builddir_lock = portage.locks.lockdir(
					self.settings["PORTAGE_BUILDDIR"])
				try:
					portage.locks.unlockdir(catdir_lock)
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

		finally:
			if builddir_lock:
				portage.locks.unlockdir(builddir_lock)
			try:
				if myebuildpath and not catdir_lock:
					# Lock catdir for removal if empty.
					catdir_lock = portage.locks.lockdir(catdir)
			finally:
				if catdir_lock:
					try:
						os.rmdir(catdir)
					except OSError, e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					portage.locks.unlockdir(catdir_lock)
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
			pkgfiles=self.getcontents()

		if pkgfiles:
			mykeys=pkgfiles.keys()
			mykeys.sort()
			mykeys.reverse()

			#process symlinks second-to-last, directories last.
			mydirs=[]
			modprotect="/lib/modules/"
			for objkey in mykeys:
				obj = normalize_path(objkey)
				if obj[:2]=="//":
					obj=obj[1:]
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
						writemsg_stdout("--- !found "+str(pkgfiles[objkey][0])+ " %s\n" % obj)
						continue
				# next line includes a tweak to protect modules from being unmerged,
				# but we don't protect modules from being overwritten if they are
				# upgraded. We effectively only want one half of the config protection
				# functionality for /lib/modules. For portage-ng both capabilities
				# should be able to be independently specified.
				if obj.startswith(modprotect):
					writemsg_stdout("--- cfgpro %s %s\n" % (pkgfiles[objkey][0], obj))
					continue

				lmtime=str(lstatobj[stat.ST_MTIME])
				if (pkgfiles[objkey][0] not in ("dir","fif","dev")) and (lmtime != pkgfiles[objkey][1]):
					writemsg_stdout("--- !mtime %s %s\n" % (pkgfiles[objkey][0], obj))
					continue

				if pkgfiles[objkey][0]=="dir":
					if statobj is None or not stat.S_ISDIR(statobj.st_mode):
						writemsg_stdout("--- !dir   %s %s\n" % ("dir", obj))
						continue
					mydirs.append(obj)
				elif pkgfiles[objkey][0]=="sym":
					if not islink:
						writemsg_stdout("--- !sym   %s %s\n" % ("sym", obj))
						continue
					try:
						os.unlink(obj)
						writemsg_stdout("<<<        %s %s\n" % ("sym",obj))
					except (OSError,IOError),e:
						writemsg_stdout("!!!        %s %s\n" % ("sym",obj))
				elif pkgfiles[objkey][0]=="obj":
					if statobj is None or not stat.S_ISREG(statobj.st_mode):
						writemsg_stdout("--- !obj   %s %s\n" % ("obj", obj))
						continue
					mymd5 = None
					try:
						mymd5 = portage.checksum.perform_md5(obj, calc_prelink=1)
					except portage.exception.FileNotFound, e:
						# the file has disappeared between now and our stat call
						writemsg_stdout("--- !obj   %s %s\n" % ("obj", obj))
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != pkgfiles[objkey][2].lower():
						writemsg_stdout("--- !md5   %s %s\n" % ("obj", obj))
						continue
					try:
						os.unlink(obj)
					except (OSError,IOError),e:
						pass
					writemsg_stdout("<<<        %s %s\n" % ("obj",obj))
				elif pkgfiles[objkey][0]=="fif":
					if not stat.S_ISFIFO(lstatobj[stat.ST_MODE]):
						writemsg_stdout("--- !fif   %s %s\n" % ("fif", obj))
						continue
					writemsg_stdout("---        %s %s\n" % ("fif",obj))
				elif pkgfiles[objkey][0]=="dev":
					writemsg_stdout("---        %s %s\n" % ("dev",obj))

			mydirs.sort()
			mydirs.reverse()

			for obj in mydirs:
				try:
					os.rmdir(obj)
					writemsg_stdout("<<<        %s %s\n" % ("dir",obj))
				except (OSError, IOError):
					writemsg_stdout("--- !empty dir %s\n" % obj)

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

	def isowner(self,filename,destroot):
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

	def treewalk(self, srcroot, destroot, inforoot, myebuild, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		"""
		
		This function does the following:
		
		Collision Protection.
		calls doebuild(mydo=pkg_preinst)
		Merges the package to the livefs
		unmerges old version (if required)
		calls doebuild(mydo=pkg_postinst)
		calls env_update
		
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

		otherversions=[]
		for v in self.vartree.dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		slot_matches = self.vartree.dbapi.match(
			"%s:%s" % (self.mysplit[0], self.settings["SLOT"]))
		if slot_matches:
			# Used by self.isprotected().
			self._installed_instance = dblink(self.cat,
				catsplit(slot_matches[0])[1], destroot, self.settings,
				vartree=self.vartree)

		# check for package collisions
		if "collision-protect" in self.settings.features:
			collision_ignore = set([normalize_path(myignore) for myignore in \
				self.settings.get("COLLISION_IGNORE", "").split()])
			myfilelist = listdir(srcroot, recursive=1, filesonly=1, followSymlinks=False)

			# the linkcheck only works if we are in srcroot
			mycwd = getcwd()
			os.chdir(srcroot)
			mysymlinks = filter(os.path.islink, listdir(srcroot, recursive=1, filesonly=0, followSymlinks=False))
			myfilelist.extend(mysymlinks)
			mysymlinked_directories = [s + os.path.sep for s in mysymlinks]
			del mysymlinks


			stopmerge=False
			starttime=time.time()
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

			print green("*")+" checking "+str(len(myfilelist))+" files for package collisions"
			for f in myfilelist:
				nocheck = False
				# listdir isn't intelligent enough to exclude symlinked dirs,
				# so we have to do it ourself
				for s in mysymlinked_directories:
					if f.startswith(s):
						nocheck = True
						break
				if nocheck:
					continue
				i=i+1
				if i % 1000 == 0:
					print str(i)+" files checked ..."
				if f[0] != "/":
					f="/"+f
				isowned = False
				for ver in [self]+mypkglist:
					if (ver.isowner(f, destroot) or ver.isprotected(f)):
						isowned = True
						break
				if not isowned:
					collisions.append(f)
					print "existing file "+f+" is not owned by this package"
					stopmerge=True
					if collision_ignore:
						if f in collision_ignore:
							stopmerge = False
						else:
							for myignore in collision_ignore:
								if f.startswith(myignore + os.path.sep):
									stopmerge = False
									break
			#print green("*")+" spent "+str(time.time()-starttime)+" seconds checking for file collisions"
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

		# get current counter value (counter_tick also takes care of incrementing it)
		# XXX Need to make this destroot, but it needs to be initialized first. XXX
		# XXX bis: leads to some invalidentry() call through cp_all().
		counter = self.vartree.dbapi.counter_tick(self.myroot, mycpv=self.mycpv)
		# write local package counter for recording
		lcfile = open(self.dbtmpdir+"/COUNTER","w")
		lcfile.write(str(counter))
		lcfile.close()

		# open CONTENTS file (possibly overwriting old one) for recording
		outfile=open(self.dbtmpdir+"/CONTENTS","w")

		self.updateprotect()

		#if we have a file containing previously-merged config file md5sums, grab it.
		conf_mem_file = os.path.join(destroot, CONFIG_MEMORY_FILE)
		cfgfiledict = grabdict(conf_mem_file)
		if self.settings.has_key("NOCONFMEM"):
			cfgfiledict["IGNORE"]=1
		else:
			cfgfiledict["IGNORE"]=0

		# set umask to 0 for merging; back up umask, save old one in prevmask (since this is a global change)
		mymtime    = long(time.time())
		prevmask   = os.umask(0)
		secondhand = []

		# we do a first merge; this will recurse through all files in our srcroot but also build up a
		# "second hand" of symlinks to merge later
		if self.mergeme(srcroot,destroot,outfile,secondhand,"",cfgfiledict,mymtime):
			return 1

		# now, it's time for dealing our second hand; we'll loop until we can't merge anymore.	The rest are
		# broken symlinks.  We'll merge them too.
		lastlen=0
		while len(secondhand) and len(secondhand)!=lastlen:
			# clear the thirdhand.	Anything from our second hand that
			# couldn't get merged will be added to thirdhand.

			thirdhand=[]
			self.mergeme(srcroot,destroot,outfile,thirdhand,secondhand,cfgfiledict,mymtime)

			#swap hands
			lastlen=len(secondhand)

			# our thirdhand now becomes our secondhand.  It's ok to throw
			# away secondhand since thirdhand contains all the stuff that
			# couldn't be merged.
			secondhand = thirdhand

		if len(secondhand):
			# force merge of remaining symlinks (broken or circular; oh well)
			self.mergeme(srcroot,destroot,outfile,None,secondhand,cfgfiledict,mymtime)

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

	def mergeme(self,srcroot,destroot,outfile,secondhand,stufftomerge,cfgfiledict,thismtime):
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
		if type(stufftomerge)==types.StringType:
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist = listdir(join(srcroot, stufftomerge))
			offset=stufftomerge
		else:
			mergelist=stufftomerge
			offset=""
		for x in mergelist:
			mysrc = join(srcroot, offset, x)
			mydest = join(destroot, offset, x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest = join(sep, offset, x)
			# stat file once, test using S_* macros many times (faster that way)
			try:
				mystat=os.lstat(mysrc)
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


			mymode=mystat[stat.ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydmode = os.lstat(mydest).st_mode
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				#dest file doesn't exist
				mydmode=None

			if stat.S_ISLNK(mymode):
				# we are merging a symbolic link
				myabsto=abssymlink(mysrc)
				if myabsto.startswith(srcroot):
					myabsto=myabsto[len(srcroot):]
				myabsto = myabsto.lstrip(sep)
				myto=os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.startswith(self.settings["D"]):
						myto=myto[len(self.settings["D"]):]
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
								newmd5 = portage.checksum.perform_md5(
									join(srcroot, myabsto))
							except portage.exception.FileNotFound:
								# Maybe the target is merged already.
								try:
									newmd5 = portage.checksum.perform_md5(
										myrealto)
								except portage.exception.FileNotFound:
									newmd5 = None
							mydest = new_protect_filename(mydest,newmd5=newmd5)

				# if secondhand is None it means we're operating in "force" mode and should not create a second hand.
				if (secondhand!=None) and (not os.path.exists(myrealto)):
					# either the target directory doesn't exist yet or the target file doesn't exist -- or
					# the target is a broken symlink.  We will add this file to our "second hand" and merge
					# it later.
					secondhand.append(mysrc[len(srcroot):])
					continue
				# unlinking no longer necessary; "movefile" will overwrite symlinks atomically and correctly
				mymtime=movefile(mysrc,mydest,newmtime=thismtime,sstat=mystat, mysettings=self.settings)
				if mymtime!=None:
					writemsg_stdout(">>> %s -> %s\n" % (mydest, myto))
					outfile.write("sym "+myrealdest+" -> "+myto+" "+str(mymtime)+"\n")
				else:
					print "!!! Failed to move file."
					print "!!!",mydest,"->",myto
					sys.exit(1)
			elif stat.S_ISDIR(mymode):
				# we are merging a directory
				if mydmode!=None:
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
						if movefile(mydest,mydest+".backup", mysettings=self.settings) is None:
							sys.exit(1)
						print "bak",mydest,mydest+".backup"
						#now create our directory
						if self.settings.selinux_enabled():
							sid = selinux.get_sid(mysrc)
							selinux.secure_mkdir(mydest,sid)
						else:
							os.mkdir(mydest)
						if bsd_chflags:
							bsd_chflags.lchflags(mydest, dflags)
						os.chmod(mydest,mystat[0])
						os.chown(mydest,mystat[4],mystat[5])
						writemsg_stdout(">>> %s/\n" % mydest)
				else:
					#destination doesn't exist
					if self.settings.selinux_enabled():
						sid = selinux.get_sid(mysrc)
						selinux.secure_mkdir(mydest,sid)
					else:
						os.mkdir(mydest)
					os.chmod(mydest,mystat[0])
					os.chown(mydest,mystat[4],mystat[5])
					writemsg_stdout(">>> %s/\n" % mydest)
				outfile.write("dir "+myrealdest+"\n")
				# recurse and merge this directory
				if self.mergeme(srcroot, destroot, outfile, secondhand,
					join(offset, x), cfgfiledict, thismtime):
					return 1
			elif stat.S_ISREG(mymode):
				# we are merging a regular file
				mymd5=portage.checksum.perform_md5(mysrc,calc_prelink=1)
				# calculate config file protection stuff
				mydestdir=os.path.dirname(mydest)
				moveme=1
				zing="!!!"
				if mydmode!=None:
					# destination file exists
					if stat.S_ISDIR(mydmode):
						# install of destination is blocked by an existing directory with the same name
						moveme=0
						writemsg_stdout("!!! %s\n" % mydest)
					elif stat.S_ISREG(mydmode) or (stat.S_ISLNK(mydmode) and os.path.exists(mydest) and stat.S_ISREG(os.stat(mydest)[stat.ST_MODE])):
						cfgprot=0
						# install of destination is blocked by an existing regular file,
						# or by a symlink to an existing regular file;
						# now, config file management may come into play.
						# we only need to tweak mydest if cfg file management is in play.
						if self.isprotected(mydest):
							# we have a protection path; enable config file management.
							destmd5=portage.checksum.perform_md5(mydest,calc_prelink=1)
							if mymd5==destmd5:
								#file already in place; simply update mtimes of destination
								os.utime(mydest,(thismtime,thismtime))
								zing="---"
								moveme=0
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
					mymtime=movefile(mysrc,mydest,newmtime=thismtime,sstat=mystat, mysettings=self.settings)
					if mymtime is None:
						sys.exit(1)
					zing=">>>"
				else:
					mymtime=thismtime
					# We need to touch the destination so that on --update the
					# old package won't yank the file with it. (non-cfgprot related)
					os.utime(mydest,(thismtime,thismtime))
					zing="---"
				if self.settings["USERLAND"] == "Darwin" and myrealdest[-2:] == ".a":

					# XXX kludge, can be killed when portage stops relying on
					# md5+mtime, and uses refcounts
					# alright, we've fooled w/ mtime on the file; this pisses off static archives
					# basically internal mtime != file's mtime, so the linker (falsely) thinks
					# the archive is stale, and needs to have it's toc rebuilt.

					myf = open(mydest, "r+")

					# ar mtime field is digits padded with spaces, 12 bytes.
					lms=str(thismtime+5).ljust(12)
					myf.seek(0)
					magic=myf.read(8)
					if magic != "!<arch>\n":
						# not an archive (dolib.a from portage.py makes it here fex)
						myf.close()
					else:
						st = os.stat(mydest)
						while myf.tell() < st.st_size - 12:
							# skip object name
							myf.seek(16,1)

							# update mtime
							myf.write(lms)

							# skip uid/gid/mperm
							myf.seek(20,1)

							# read the archive member's size
							x=long(myf.read(10))

							# skip the trailing newlines, and add the potential
							# extra padding byte if it's not an even size
							myf.seek(x + 2 + (x % 2),1)

						# and now we're at the end. yay.
						myf.close()
						mymd5 = portage.checksum.perform_md5(mydest, calc_prelink=1)
					os.utime(mydest,(thismtime,thismtime))

				if mymtime!=None:
					zing=">>>"
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				writemsg_stdout("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing="!!!"
				if mydmode is None:
					# destination doesn't exist
					if movefile(mysrc,mydest,newmtime=thismtime,sstat=mystat, mysettings=self.settings)!=None:
						zing=">>>"
					else:
						sys.exit(1)
				if stat.S_ISFIFO(mymode):
					outfile.write("fif %s\n" % myrealdest)
				else:
					outfile.write("dev %s\n" % myrealdest)
				writemsg_stdout(zing+" "+mydest+"\n")

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
		myfile=open(self.dbdir+"/"+name,"r")
		mydata=myfile.read().split()
		myfile.close()
		return " ".join(mydata)

	def copyfile(self,fname):
		shutil.copyfile(fname,self.dbdir+"/"+os.path.basename(fname))

	def getfile(self,fname):
		if not os.path.exists(self.dbdir+"/"+fname):
			return ""
		myfile=open(self.dbdir+"/"+fname,"r")
		mydata=myfile.read()
		myfile.close()
		return mydata

	def setfile(self,fname,data):
		write_atomic(os.path.join(self.dbdir, fname), data)

	def getelements(self,ename):
		if not os.path.exists(self.dbdir+"/"+ename):
			return []
		myelement=open(self.dbdir+"/"+ename,"r")
		mylines=myelement.readlines()
		myreturn=[]
		for x in mylines:
			for y in x[:-1].split():
				myreturn.append(y)
		myelement.close()
		return myreturn

	def setelements(self,mylist,ename):
		myelement=open(self.dbdir+"/"+ename,"w")
		for x in mylist:
			myelement.write(x+"\n")
		myelement.close()

	def isregular(self):
		"Is this a regular package (does it have a CATEGORY file?  A dblink can be virtual *and* regular)"
		return os.path.exists(self.dbdir+"/CATEGORY")

class FetchlistDict(UserDict.DictMixin):
	"""This provide a mapping interface to retrieve fetch lists.  It's used
	to allow portage.manifest.Manifest to access fetch lists via a standard
	mapping interface rather than use the dbapi directly."""
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
		return self.portdb.getfetchlist(pkg_key, mysettings=self.settings,
			all=True, mytree=self.mytree)[1]
	def has_key(self, pkg_key):
		"""Returns true if the given package exists within pkgdir."""
		return pkg_key in self.keys()
	def keys(self):
		"""Returns keys for all packages within pkgdir"""
		return self.portdb.cp_list(self.cp, mytree=self.mytree)

def pkgmerge(mytbz2, myroot, mysettings, mydbapi=None, vartree=None, prev_mtimes=None):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""
	global db
	if mydbapi is None:
		mydbapi = db[myroot]["bintree"].dbapi
	if vartree is None:
		vartree = db[myroot]["vartree"]
	if mytbz2[-5:]!=".tbz2":
		print "!!! Not a .tbz2 file"
		return 1

	tbz2_lock = None
	builddir_lock = None
	catdir_lock = None
	try:
		""" Don't lock the tbz2 file because the filesytem could be readonly or
		shared by a cluster."""
		#tbz2_lock = portage.locks.lockfile(mytbz2, wantnewlockfile=1)

		mypkg = os.path.basename(mytbz2)[:-5]
		xptbz2 = portage.xpak.tbz2(mytbz2)
		mycat = xptbz2.getfile("CATEGORY")
		if not mycat:
			writemsg("!!! CATEGORY info missing from info chunk, aborting...\n",
				noiselevel=-1)
			return 1
		mycat = mycat.strip()

		# These are the same directories that would be used at build time.
		builddir = os.path.join(
			mysettings["PORTAGE_TMPDIR"], "portage", mycat, mypkg)
		catdir = os.path.dirname(builddir)
		pkgloc = os.path.join(builddir, "image")
		infloc = os.path.join(builddir, "build-info")
		myebuild = os.path.join(
			infloc, os.path.basename(mytbz2)[:-4] + "ebuild")
		portage.util.ensure_dirs(os.path.dirname(catdir),
			uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		catdir_lock = portage.locks.lockdir(catdir)
		portage.util.ensure_dirs(catdir,
			uid=portage_uid, gid=portage_gid, mode=070, mask=0)
		builddir_lock = portage.locks.lockdir(builddir)
		try:
			portage.locks.unlockdir(catdir_lock)
		finally:
			catdir_lock = None
		try:
			shutil.rmtree(builddir)
		except (IOError, OSError), e:
			if e.errno != errno.ENOENT:
				raise
			del e
		for mydir in (builddir, pkgloc, infloc):
			portage.util.ensure_dirs(mydir, uid=portage_uid,
				gid=portage_gid, mode=0755)
		writemsg_stdout(">>> Extracting info\n")
		xptbz2.unpackinfo(infloc)
		mysettings.load_infodir(infloc)
		# Store the md5sum in the vdb.
		fp = open(os.path.join(infloc, "BINPKGMD5"), "w")
		fp.write(str(portage.checksum.perform_md5(mytbz2))+"\n")
		fp.close()

		debug = mysettings.get("PORTAGE_DEBUG", "") == "1"

		# Eventually we'd like to pass in the saved ebuild env here.
		retval = doebuild(myebuild, "setup", myroot, mysettings, debug=debug,
			tree="bintree", mydbapi=mydbapi, vartree=vartree)
		if retval != os.EX_OK:
			writemsg("!!! Setup failed: %s\n" % retval, noiselevel=-1)
			return retval

		writemsg_stdout(">>> Extracting %s\n" % mypkg)
		retval = portage.process.spawn_bash(
			"bzip2 -dqc -- '%s' | tar -xp -C '%s' -f -" % (mytbz2, pkgloc),
			env=mysettings.environ())
		if retval != os.EX_OK:
			writemsg("!!! Error Extracting '%s'\n" % mytbz2, noiselevel=-1)
			return retval
		#portage.locks.unlockfile(tbz2_lock)
		#tbz2_lock = None

		mylink = dblink(mycat, mypkg, myroot, mysettings, vartree=vartree,
			treetype="bintree")
		retval = mylink.merge(pkgloc, infloc, myroot, myebuild, cleanup=0,
			mydbapi=mydbapi, prev_mtimes=prev_mtimes)
		return retval
	finally:
		if tbz2_lock:
			portage.locks.unlockfile(tbz2_lock)
		if builddir_lock:
			try:
				shutil.rmtree(builddir)
			except (IOError, OSError), e:
				if e.errno != errno.ENOENT:
					raise
				del e
			portage.locks.unlockdir(builddir_lock)
			try:
				if not catdir_lock:
					# Lock catdir for removal if empty.
					catdir_lock = portage.locks.lockdir(catdir)
			finally:
				if catdir_lock:
					try:
						os.rmdir(catdir)
					except OSError, e:
						if e.errno not in (errno.ENOENT,
							errno.ENOTEMPTY, errno.EEXIST):
							raise
						del e
					portage.locks.unlockdir(catdir_lock)

def deprecated_profile_check():
	if not os.access(DEPRECATED_PROFILE_FILE, os.R_OK):
		return False
	deprecatedfile = open(DEPRECATED_PROFILE_FILE, "r")
	dcontent = deprecatedfile.readlines()
	deprecatedfile.close()
	newprofile = dcontent[0]
	writemsg(red("\n!!! Your current profile is deprecated and not supported anymore.\n"),
		noiselevel=-1)
	writemsg(red("!!! Please upgrade to the following profile if possible:\n"),
		noiselevel=-1)
	writemsg(8*" "+green(newprofile)+"\n", noiselevel=-1)
	if len(dcontent) > 1:
		writemsg("To upgrade do the following steps:\n", noiselevel=-1)
		for myline in dcontent[1:]:
			writemsg(myline, noiselevel=-1)
		writemsg("\n\n", noiselevel=-1)
	return True

# gets virtual package settings
def getvirtuals(myroot):
	global settings
	writemsg("--- DEPRECATED call to getvirtual\n")
	return settings.getvirtuals(myroot)

def commit_mtimedb(mydict=None, filename=None):
	if mydict is None:
		global mtimedb
		if "mtimedb" not in globals() or mtimedb is None:
			return
		mtimedb.commit()
		return
	if filename is None:
		global mtimedbfile
		filename = mtimedbfile
	mydict["version"] = VERSION
	d = {} # for full backward compat, pickle it as a plain dict object.
	d.update(mydict)
	try:
		f = atomic_ofstream(filename)
		cPickle.dump(d, f, -1)
		f.close()
		portage.util.apply_secpass_permissions(filename, uid=uid, gid=portage_gid, mode=0664)
	except (IOError, OSError), e:
		pass

def portageexit():
	global uid,portage_gid,portdb,db
	if secpass and not os.environ.has_key("SANDBOX_ACTIVE"):
		close_portdbapi_caches()
		commit_mtimedb()

atexit_register(portageexit)

def global_updates(mysettings, trees, prev_mtimes):
	"""
	Perform new global updates if they exist in $PORTDIR/profiles/updates/.

	@param mysettings: A config instance for ROOT="/".
	@type mysettings: config
	@param trees: A dictionary containing portage trees.
	@type trees: dict
	@param prev_mtimes: A dictionary containing mtimes of files located in
		$PORTDIR/profiles/updates/.
	@type prev_mtimes: dict
	@rtype: None or List
	@return: None if no were no updates, otherwise a list of update commands
		that have been performed.
	"""
	# only do this if we're root and not running repoman/ebuild digest
	global secpass
	if secpass < 2 or "SANDBOX_ACTIVE" in os.environ:
		return
	updpath = os.path.join(mysettings["PORTDIR"], "profiles", "updates")

	try:
		if mysettings["PORTAGE_CALLER"] == "fixpackages":
			update_data = grab_updates(updpath)
		else:
			update_data = grab_updates(updpath, prev_mtimes)
	except portage.exception.DirectoryNotFound:
		writemsg("--- 'profiles/updates' is empty or not available. Empty portage tree?\n")
		return
	myupd = None
	if len(update_data) > 0:
		do_upgrade_packagesmessage = 0
		myupd = []
		timestamps = {}
		for mykey, mystat, mycontent in update_data:
			writemsg_stdout("\n\n")
			writemsg_stdout(green("Performing Global Updates: ")+bold(mykey)+"\n")
			writemsg_stdout("(Could take a couple of minutes if you have a lot of binary packages.)\n")
			writemsg_stdout("  "+bold(".")+"='update pass'  "+bold("*")+"='binary update'  "+bold("@")+"='/var/db move'\n"+"  "+bold("s")+"='/var/db SLOT move' "+bold("S")+"='binary SLOT move' "+bold("p")+"='update /etc/portage/package.*'\n")
			valid_updates, errors = parse_updates(mycontent)
			myupd.extend(valid_updates)
			writemsg_stdout(len(valid_updates) * "." + "\n")
			if len(errors) == 0:
				# Update our internal mtime since we
				# processed all of our directives.
				timestamps[mykey] = long(mystat.st_mtime)
			else:
				for msg in errors:
					writemsg("%s\n" % msg, noiselevel=-1)

		update_config_files("/",
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split(),
			myupd)

		trees["/"]["bintree"] = binarytree("/", mysettings["PKGDIR"],
			settings=mysettings)
		for update_cmd in myupd:
			if update_cmd[0] == "move":
				trees["/"]["vartree"].dbapi.move_ent(update_cmd)
				trees["/"]["bintree"].move_ent(update_cmd)
			elif update_cmd[0] == "slotmove":
				trees["/"]["vartree"].dbapi.move_slot_ent(update_cmd)
				trees["/"]["bintree"].move_slot_ent(update_cmd)

		# The above global updates proceed quickly, so they
		# are considered a single mtimedb transaction.
		if len(timestamps) > 0:
			# We do not update the mtime in the mtimedb
			# until after _all_ of the above updates have
			# been processed because the mtimedb will
			# automatically commit when killed by ctrl C.
			for mykey, mtime in timestamps.iteritems():
				prev_mtimes[mykey] = mtime

		# We gotta do the brute force updates for these now.
		if mysettings["PORTAGE_CALLER"] == "fixpackages" or \
		"fixpackages" in mysettings.features:
			trees["/"]["bintree"].update_ents(myupd)
		else:
			do_upgrade_packagesmessage = 1

		# Update progress above is indicated by characters written to stdout so
		# we print a couple new lines here to separate the progress output from
		# what follows.
		print
		print

		if do_upgrade_packagesmessage and \
			listdir(os.path.join(mysettings["PKGDIR"], "All"), EmptyOnError=1):
			writemsg_stdout(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the")
			writemsg_stdout("\n    tbz2's in the packages directory. "+bold("Note: This can take a very long time."))
			writemsg_stdout("\n")
	if myupd:
		return myupd

#continue setting up other trees

class MtimeDB(dict):
	def __init__(self, filename):
		dict.__init__(self)
		self.filename = filename
		self._load(filename)

	def _load(self, filename):
		try:
			f = open(filename)
			mypickle = cPickle.Unpickler(f)
			mypickle.find_global = None
			d = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, cPickle.UnpicklingError):
			d = {}

		if "old" in d:
			d["updates"] = d["old"]
			del d["old"]
		if "cur" in d:
			del d["cur"]

		d.setdefault("starttime", 0)
		d.setdefault("version", "")
		for k in ("info", "ldpath", "updates"):
			d.setdefault(k, {})

		mtimedbkeys = set(("info", "ldpath", "resume", "resume_backup",
			"starttime", "updates", "version"))

		for k in d.keys():
			if k not in mtimedbkeys:
				writemsg("Deleting invalid mtimedb key: %s\n" % str(k))
				del d[k]
		self.update(d)
		self._clean_data = copy.deepcopy(d)

	def commit(self):
		if not self.filename:
			return
		d = {}
		d.update(self)
		# Only commit if the internal state has changed.
		if d != self._clean_data:
			commit_mtimedb(mydict=d, filename=self.filename)
			self._clean_data = copy.deepcopy(d)

def create_trees(config_root=None, target_root=None, trees=None):
	if trees is None:
		trees = {}
	else:
		# clean up any existing portdbapi instances
		for myroot in trees:
			portdb = trees[myroot]["porttree"].dbapi
			portdb.close_caches()
			portdbapi.portdbapi_instances.remove(portdb)
			del trees[myroot]["porttree"], myroot, portdb

	settings = config(config_root=config_root, target_root=target_root,
		config_incrementals=portage.const.INCREMENTALS)
	settings.lock()
	settings.validate()

	myroots = [(settings["ROOT"], settings)]
	if settings["ROOT"] != "/":
		settings = config(config_root=None, target_root=None,
			config_incrementals=portage.const.INCREMENTALS)
		settings.lock()
		settings.validate()
		myroots.append((settings["ROOT"], settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, None))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals, myroot)
		trees[myroot].addLazySingleton(
			"vartree", vartree, myroot, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, myroot, settings=mysettings)
		trees[myroot].addLazySingleton("bintree",
			binarytree, myroot, mysettings["PKGDIR"], settings=mysettings)
	return trees

# Initialization of legacy globals.  No functions/classes below this point
# please!  When the above functions and classes become independent of the
# below global variables, it will be possible to make the below code
# conditional on a backward compatibility flag (backward compatibility could
# be disabled via an environment variable, for example).  This will enable new
# code that is aware of this flag to import portage without the unnecessary
# overhead (and other issues!) of initializing the legacy globals.

def init_legacy_globals():
	global db, settings, root, portdb, selinux_enabled, mtimedbfile, mtimedb, \
	archlist, features, groups, pkglines, thirdpartymirrors, usedefaults, \
	profiledir, flushmtimedb

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(022)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, "/")

	db = create_trees(**kwargs)

	settings = db["/"]["vartree"].settings
	portdb = db["/"]["porttree"].dbapi

	for myroot in db:
		if myroot != "/":
			settings = db[myroot]["vartree"].settings
			portdb = db[myroot]["porttree"].dbapi
			break

	root = settings["ROOT"]

	mtimedbfile = os.path.join("/", CACHE_PATH.lstrip(os.path.sep), "mtimedb")
	mtimedb = MtimeDB(mtimedbfile)

	# ========================================================================
	# COMPATIBILITY
	# These attributes should not be used
	# within Portage under any circumstances.
	# ========================================================================
	archlist    = settings.archlist()
	features    = settings.features
	groups      = settings["ACCEPT_KEYWORDS"].split()
	pkglines    = settings.packages
	selinux_enabled   = settings.selinux_enabled()
	thirdpartymirrors = settings.thirdpartymirrors()
	usedefaults       = settings.use_defs
	profiledir  = None
	if os.path.isdir(PROFILE_PATH):
		profiledir = PROFILE_PATH
	def flushmtimedb(record):
		writemsg("portage.flushmtimedb() is DEPRECATED\n")
	# ========================================================================
	# COMPATIBILITY
	# These attributes should not be used
	# within Portage under any circumstances.
	# ========================================================================

# WARNING!
# The PORTAGE_LEGACY_GLOBALS environment variable is reserved for internal
# use within Portage.  External use of this variable is unsupported because
# it is experimental and it's behavior is likely to change.
if "PORTAGE_LEGACY_GLOBALS" not in os.environ:
	init_legacy_globals()

# Clear the cache
dircache={}

# ============================================================================
# ============================================================================

