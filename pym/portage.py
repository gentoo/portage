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
	import copy, errno, os, re, shutil, string, time, types
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
except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. These are internal modules for\n")
	sys.stderr.write("!!! python and failure here indicates that you have a problem with python\n")
	sys.stderr.write("!!! itself and thus portage is not able to continue processing.\n\n")

	sys.stderr.write("!!! You might consider starting python with verbose flags to see what has\n")
	sys.stderr.write("!!! gone wrong. Here is the information we got for this exception:\n")
	sys.stderr.write("    "+str(e)+"\n\n");
	raise

try:
	# XXX: This should get renamed to bsd_chflags, I think.
	import chflags
	bsd_chflags = chflags
except ImportError:
	bsd_chflags = None

try:
	from cache.cache_errors import CacheError
	import cvstree
	import xpak
	import getbinpkg
	import portage_dep

	# XXX: This needs to get cleaned up.
	import output
	from output import bold, colorize, green, red, yellow

	import portage_const
	from portage_const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
	  USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
	  PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
	  EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
	  MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
	  DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
	  INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
	  INCREMENTALS, EAPI, MISC_SH_BINARY

	from portage_data import ostype, lchown, userland, secpass, uid, wheelgid, \
	                         portage_uid, portage_gid
	from portage_manifest import Manifest

	import portage_util
	from portage_util import atomic_ofstream, apply_secpass_permissions, apply_recursive_permissions, \
		dump_traceback, getconfig, grabdict, grabdict_package, grabfile, grabfile_package, \
		map_dictlist_vals, pickle_read, pickle_write, stack_dictlist, stack_dicts, stack_lists, \
		unique_array, varexpand, writedict, writemsg, writemsg_stdout, write_atomic
	import portage_exception
	import portage_gpg
	import portage_locks
	import portage_exec
	from portage_exec import atexit_register, run_exitfuncs
	from portage_locks import unlockfile,unlockdir,lockfile,lockdir
	import portage_checksum
	from portage_checksum import perform_md5,perform_checksum,prelink_capable
	import eclass_cache
	from portage_localization import _
	from portage_update import fixdbentries, update_dbentries, grab_updates

	# Need these functions directly in portage namespace to not break every external tool in existence
	from portage_versions import ververify,vercmp,catsplit,catpkgsplit,pkgsplit,pkgcmp

	# endversion and endversion_keys are for backward compatibility only.
	from portage_versions import endversion_keys
	from portage_versions import suffix_value as endversion

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
	import portage_selinux as selinux
except OSError, e:
	writemsg("!!! SELinux not loaded: %s\n" % str(e), noiselevel=-1)
	del e
except ImportError:
	pass

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================


def load_mod(name):
	modname = string.join(string.split(name,".")[:-1],".")
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
	except SystemExit, e:
		raise
	except:
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

def suffix_array(array,suffix,doblanks=1):
	"""Appends a given suffix to each element in an Array/List/Tuple.
	Returns a List."""
	if type(array) not in [types.ListType, types.TupleType]:
		raise TypeError, "List or Tuple expected. Got %s" % type(array)
	newarray=[]
	for x in array:
		if x or doblanks:
			newarray.append(x + suffix)
		else:
			newarray.append(x)
	return newarray

def prefix_array(array,prefix,doblanks=1):
	"""Prepends a given prefix to each element in an Array/List/Tuple.
	Returns a List."""
	if type(array) not in [types.ListType, types.TupleType]:
		raise TypeError, "List or Tuple expected. Got %s" % type(array)
	newarray=[]
	for x in array:
		if x or doblanks:
			newarray.append(prefix + x)
		else:
			newarray.append(x)
	return newarray

def normalize_path(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			newpath = newpath[1:]
	return newpath

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
			raise portage_exception.DirectoryNotFound(mypath)
	except (IOError,OSError,portage_exception.PortageException):
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

starttime=long(time.time())

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
		self.dict={}
		#okeys = keys, in order they were added (to optimize firstzero() ordering)
		self.okeys=[]

	def addnode(self,mykey,myparent):
		if not self.dict.has_key(mykey):
			self.okeys.append(mykey)
			if myparent is None:
				self.dict[mykey]=[0,[]]
			else:
				self.dict[mykey]=[0,[myparent]]
				self.dict[myparent][0]=self.dict[myparent][0]+1
			return
		if myparent and (not myparent in self.dict[mykey][1]):
			self.dict[mykey][1].append(myparent)
			self.dict[myparent][0]=self.dict[myparent][0]+1

	def delnode(self,mykey):
		if not self.dict.has_key(mykey):
			return
		for x in self.dict[mykey][1]:
			self.dict[x][0]=self.dict[x][0]-1
		del self.dict[mykey]
		while 1:
			try:
				self.okeys.remove(mykey)
			except ValueError:
				break

	def allnodes(self):
		"returns all nodes in the dictionary"
		return self.dict.keys()

	def firstzero(self):
		"returns first node with zero references, or NULL if no such node exists"
		for x in self.okeys:
			if self.dict[x][0]==0:
				return x
		return None

	def depth(self, mykey):
		depth=0
		while (self.dict[mykey][1]):
			depth=depth+1
			mykey=self.dict[mykey][1][0]
		return depth

	def allzeros(self):
		"returns all nodes with zero references, or NULL if no such node exists"
		zerolist = []
		for x in self.dict.keys():
			mys = string.split(x)
			if mys[0] != "blocks" and self.dict[x][0]==0:
				zerolist.append(x)
		return zerolist

	def hasallzeros(self):
		"returns 0/1, Are all nodes zeros? 1 : 0"
		zerolist = []
		for x in self.dict.keys():
			if self.dict[x][0]!=0:
				return 0
		return 1

	def empty(self):
		if len(self.dict)==0:
			return 1
		return 0

	def hasnode(self,mynode):
		return self.dict.has_key(mynode)

	def copy(self):
		mygraph=digraph()
		for x in self.dict.keys():
			mygraph.dict[x]=self.dict[x][:]
			mygraph.okeys=self.okeys[:]
		return mygraph

def elog_process(cpv, mysettings):
	mylogfiles = listdir(mysettings["T"]+"/logging/")
	# shortcut for packages without any messages
	if len(mylogfiles) == 0:
		return
	# exploit listdir() file order so we process log entries in chronological order
	mylogfiles.reverse()
	mylogentries = {}
	for f in mylogfiles:
		msgfunction, msgtype = f.split(".")
		if not msgtype.upper() in mysettings["PORTAGE_ELOG_CLASSES"].split() \
				and not msgtype.lower() in mysettings["PORTAGE_ELOG_CLASSES"].split():
			continue
		if msgfunction not in portage_const.EBUILD_PHASES:
			print "!!! can't process invalid log file: %s" % f
			continue
		if not msgfunction in mylogentries:
			mylogentries[msgfunction] = []
		msgcontent = open(mysettings["T"]+"/logging/"+f, "r").readlines()
		mylogentries[msgfunction].append((msgtype, msgcontent))

	# in case the filters matched all messages
	if len(mylogentries) == 0:
		return

	# generate a single string with all log messages
	fulllog = ""
	for phase in portage_const.EBUILD_PHASES:
		if not phase in mylogentries:
			continue
		for msgtype,msgcontent in mylogentries[phase]:
			fulllog += "%s: %s\n" % (msgtype, phase)
			for line in msgcontent:
				fulllog += line
			fulllog += "\n"

	# pass the processing to the individual modules
	logsystems = mysettings["PORTAGE_ELOG_SYSTEM"].split()
	for s in logsystems:
		try:
			# FIXME: ugly ad.hoc import code
			# TODO:  implement a common portage module loader
			logmodule = __import__("elog_modules.mod_"+s)
			m = getattr(logmodule, "mod_"+s)
			m.process(mysettings, cpv, mylogentries, fulllog)
		except (ImportError, AttributeError), e:
			print "!!! Error while importing logging modules while loading \"mod_%s\":" % s
			print e
		except portage_exception.PortageException, e:
			print e

	# clean logfiles to avoid repetitions
	for f in mylogfiles:
		try:
			os.unlink(os.path.join(mysettings["T"], "logging", f))
		except OSError:
			pass

#parse /etc/env.d and generate /etc/profile.env

def env_update(makelinks=1, target_root=None, prev_mtimes=None):
	if target_root is None:
		global root
		target_root = root
	if prev_mtimes is None:
		global mtimedb
		prev_mtimes = mtimedb["ldpath"]
	envd_dir = os.path.join(target_root, "etc", "env.d")
	portage_util.ensure_dirs(envd_dir, mode=0755)
	fns = listdir(envd_dir, EmptyOnError=1)
	fns.sort()
	pos=0
	while (pos<len(fns)):
		if len(fns[pos])<=2:
			del fns[pos]
			continue
		if (fns[pos][0] not in string.digits) or (fns[pos][1] not in string.digits):
			del fns[pos]
			continue
		pos=pos+1

	specials={
	  "KDEDIRS":[],"PATH":[],"CLASSPATH":[],"LDPATH":[],"MANPATH":[],
		"INFODIR":[],"INFOPATH":[],"ROOTPATH":[],"CONFIG_PROTECT":[],
		"CONFIG_PROTECT_MASK":[],"PRELINK_PATH":[],"PRELINK_PATH_MASK":[],
		"PYTHONPATH":[], "ADA_INCLUDE_PATH":[], "ADA_OBJECTS_PATH":[]
	}
	colon_separated = [
		"ADA_INCLUDE_PATH",  "ADA_OBJECTS_PATH",
		"LDPATH",            "MANPATH",
		"PATH",              "PRELINK_PATH",
		"PRELINK_PATH_MASK", "PYTHONPATH"
	]

	env={}

	for x in fns:
		# don't process backup files
		if x[-1]=='~' or x[-4:]==".bak":
			continue
		file_path = os.path.join(envd_dir, x)
		myconfig = getconfig(file_path)
		if myconfig is None:
			writemsg("!!! Parsing error in '%s'\n" % file_path, noiselevel=-1)
			#parse error
			continue
		# process PATH, CLASSPATH, LDPATH
		for myspec in specials.keys():
			if myconfig.has_key(myspec):
				if myspec in colon_separated:
					specials[myspec].extend(myconfig[myspec].split(":"))
				else:
					specials[myspec].append(myconfig[myspec])
				del myconfig[myspec]
		# process all other variables
		for myenv in myconfig.keys():
			env[myenv]=myconfig[myenv]

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

	newld=specials["LDPATH"]
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

	for lib_dir in portage_util.unique_array(specials["LDPATH"]+['usr/lib','usr/lib64','usr/lib32','lib','lib64','lib32']):
		x = os.path.join(target_root, lib_dir.lstrip(os.sep))
		try:
			newldpathtime = os.stat(x)[stat.ST_MTIME]
		except OSError, oe:
			if oe.errno == errno.ENOENT:
				try:
					del prev_mtimes[x]
				except KeyError:
					pass
				# ignore this path because it doesn't exist
				continue
			raise
		mtime_changed = False
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

	for path in specials.keys():
		if len(specials[path])==0:
			continue
		outstring="export "+path+"='"
		if path in ["CONFIG_PROTECT","CONFIG_PROTECT_MASK"]:
			for x in specials[path][:-1]:
				outstring += x+" "
		else:
			for x in specials[path][:-1]:
				outstring=outstring+x+":"
		outstring=outstring+specials[path][-1]+"'"
		outfile.write(outstring+"\n")

	#create /etc/profile.env
	for x in env.keys():
		if type(env[x])!=types.StringType:
			continue
		outfile.write("export "+x+"='"+env[x]+"'\n")
	outfile.close()

	#create /etc/csh.env for (t)csh support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "csh.env"))
	outfile.write(cenvnotice)

	for path in specials.keys():
		if len(specials[path])==0:
			continue
		outstring="setenv "+path+" '"
		if path in ["CONFIG_PROTECT","CONFIG_PROTECT_MASK"]:
			for x in specials[path][:-1]:
				outstring += x+" "
		else:
			for x in specials[path][:-1]:
				outstring=outstring+x+":"
		outstring=outstring+specials[path][-1]+"'"
		outfile.write(outstring+"\n")
		#get it out of the way
		del specials[path]

	#create /etc/csh.env
	for x in env.keys():
		if type(env[x])!=types.StringType:
			continue
		outfile.write("setenv "+x+" '"+env[x]+"'\n")
	outfile.close()

def new_protect_filename(mydest, newmd5=None):
	"""Resolves a config-protect filename for merging, optionally
	using the last filename if the md5 matches.
	(dest,md5) ==> 'string'            --- path_to_target_filename
	(dest)     ==> ('next', 'highest') --- next_target and most-recent_target
	"""

	# config protection filename format:
	# ._cfg0000_foo
	# 0123456789012
	prot_num=-1
	last_pfile=""

	if (len(mydest) == 0):
		raise ValueError, "Empty path provided where a filename is required"
	if (mydest[-1]=="/"): # XXX add better directory checking
		raise ValueError, "Directory provided but this function requires a filename"
	if not os.path.exists(mydest):
		return mydest

	real_filename = os.path.basename(mydest)
	real_dirname  = os.path.dirname(mydest)
	for pfile in listdir(real_dirname):
		if pfile[0:5] != "._cfg":
			continue
		if pfile[10:] != real_filename:
			continue
		try:
			new_prot_num = int(pfile[5:9])
			if new_prot_num > prot_num:
				prot_num = new_prot_num
				last_pfile = pfile
		except SystemExit, e:
			raise
		except:
			continue
	prot_num = prot_num + 1

	new_pfile = os.path.normpath(real_dirname+"/._cfg"+string.zfill(prot_num,4)+"_"+real_filename)
	old_pfile = os.path.normpath(real_dirname+"/"+last_pfile)
	if last_pfile and newmd5:
		if portage_checksum.perform_md5(real_dirname+"/"+last_pfile) == newmd5:
			return old_pfile
		else:
			return new_pfile
	elif newmd5:
		return new_pfile
	else:
		return (new_pfile, old_pfile)

#XXX: These two are now implemented in portage_util.py but are needed here
#XXX: until the isvalidatom() dependency is sorted out.

def grabdict_package(myfilename,juststrings=0,recursive=0):
	pkgs=grabdict(myfilename, juststrings=juststrings, empty=1,recursive=recursive)
	for x in pkgs.keys():
		if not isvalidatom(x):
			del(pkgs[x])
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, x),
				noiselevel=-1)
	return pkgs

def grabfile_package(myfilename,compatlevel=0,recursive=0):
	pkgs=grabfile(myfilename,compatlevel,recursive=recursive)
	for x in range(len(pkgs)-1,-1,-1):
		pkg = pkgs[x]
		if pkg[0] == "-":
			pkg = pkg[1:]
		if pkg[0] == "*":
			pkg = pkg[1:]
		if not isvalidatom(pkg):
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, pkgs[x]),
				noiselevel=-1)
			del(pkgs[x])
	return pkgs

# returns a tuple.  (version[string], error[string])
# They are pretty much mutually exclusive.
# Either version is a string and error is none, or
# version is None and error is a string
#
def ExtractKernelVersion(base_dir):
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

	lines = map(string.strip, lines)

	version = ''

	#XXX: The following code relies on the ordering of vars within the Makefile
	for line in lines:
		# split on the '=' then remove annoying whitespace
		items = string.split(line, '=')
		items = map(string.strip, items)
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
		version += string.join(string.split(string.join(grabfile(base_dir+"/"+lv))), "")

	# Check the .config for a CONFIG_LOCALVERSION and append that too, also stripping whitespace
	kernelconfig = getconfig(base_dir+"/.config")
	if kernelconfig and kernelconfig.has_key("CONFIG_LOCALVERSION"):
		version += string.join(string.split(kernelconfig["CONFIG_LOCALVERSION"]), "")

	return (version,None)

def autouse(myvartree, use_cache=1, mysettings=None):
	"returns set of USE variables auto-enabled due to packages being installed"
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
	def __init__(self, clone=None, mycpv=None, config_profile_path=None,
		config_incrementals=None, config_root="/", target_root="/"):

		self.already_in_regenerate = 0

		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []

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

		if clone:
			self.incrementals = copy.deepcopy(clone.incrementals)
			self.profile_path = copy.deepcopy(clone.profile_path)
			self.user_profile_dir = copy.deepcopy(clone.user_profile_dir)

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

			self.configlist = copy.deepcopy(clone.configlist)
			self.configlist[-1] = os.environ.copy()
			self.configdict = { "globals":   self.configlist[0],
			                    "defaults":  self.configlist[1],
			                    "conf":      self.configlist[2],
			                    "pkg":       self.configlist[3],
			                    "auto":      self.configlist[4],
			                    "backupenv": self.configlist[5],
			                    "env":       self.configlist[6] }
			self.profiles = copy.deepcopy(clone.profiles)
			self.backupenv  = copy.deepcopy(clone.backupenv)
			self.pusedict   = copy.deepcopy(clone.pusedict)
			self.categories = copy.deepcopy(clone.categories)
			self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
			self.pmaskdict = copy.deepcopy(clone.pmaskdict)
			self.punmaskdict = copy.deepcopy(clone.punmaskdict)
			self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
			self.pprovideddict = copy.deepcopy(clone.pprovideddict)
			self.lookuplist = copy.deepcopy(clone.lookuplist)
			self.uvlist     = copy.deepcopy(clone.uvlist)
			self.dirVirtuals = copy.deepcopy(clone.dirVirtuals)
			self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
			config_root = self.backupenv["PORTAGE_CONFIGROOT"]
			target_root = self.backupenv["ROOT"]
		else:

			# backupenv is for calculated incremental variables.
			self.backupenv = os.environ.copy()

			config_root = \
				os.path.normpath(config_root).rstrip(os.path.sep) + os.path.sep
			target_root = \
				os.path.normpath(target_root).rstrip(os.path.sep) + os.path.sep

			for k, v in (("PORTAGE_CONFIGROOT", config_root),
				("ROOT", target_root)):
				if not os.path.isdir(v):
					writemsg("!!! Error: %s='%s' is not a directory. Please correct this.\n" % (k, v),
						noiselevel=-1)
					raise portage_exception.DirectoryNotFound(v)

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
				self.incrementals = copy.deepcopy(portage_const.INCREMENTALS)
			else:
				self.incrementals = copy.deepcopy(config_incrementals)

			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"] = getconfig(
				os.path.join(config_root, MODULES_FILE_PATH.lstrip(os.path.sep)))
			if self.modules["user"] is None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "cache.metadata.database",
				"portdbapi.auxdbmodule":  "cache.flat_hash.database",
			}

			self.usemask=[]
			self.configlist=[]

			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ globals, defaults, conf, pkg, auto, backupenv (incrementals), origenv ]

			# The symlink might not exist or might not be a symlink.
			if self.profile_path is None:
				self.profiles = []
			else:
				self.profiles = [os.path.realpath(self.profile_path)]
				mypath = self.profiles[0]
				while os.path.exists(os.path.join(mypath, "parent")):
					parents_file = os.path.join(mypath, "parent")
					parents = grabfile(parents_file)
					if len(parents) != 1:
						raise portage_exception.ParseError(
							"Expected 1 parent and got %i: '%s'" % \
							(len(parents), parents_file))
					mypath = os.path.normpath(os.path.join(
						mypath, parents[0]))
					if os.path.exists(mypath):
						self.profiles.insert(0, mypath)
					else:
						raise portage_exception.ParseError(
							"Specified parent not found: '%s'" %  parents_file)

			if os.environ.has_key("PORTAGE_CALLER") and os.environ["PORTAGE_CALLER"] == "repoman":
				pass
			else:
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
			usemask_lists = [grabfile(os.path.join(x, "use.mask")) for x in self.profiles]
			self.usemask  = stack_lists(usemask_lists, incremental=True)
			del usemask_lists
			use_defs_lists = [grabdict(os.path.join(x, "use.defaults")) for x in self.profiles]
			self.use_defs  = stack_dictlist(use_defs_lists, incremental=True)
			del use_defs_lists

			try:
				mygcfg_dlists = [getconfig(os.path.join(x, "make.globals")) \
					for x in self.profiles + [os.path.join(config_root, "etc")]]
				self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=portage_const.INCREMENTALS, ignore_none=1)

				if self.mygcfg is None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("!!! %s\n" % (e), noiselevel=-1)
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n", noiselevel=-1)
				writemsg("!!! Errors in this file should be reported on bugs.gentoo.org.\n")
				sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.mygcfg = {}
			if self.profiles:
				try:
					mygcfg_dlists = [getconfig(os.path.join(x, "make.defaults")) for x in self.profiles]
					self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=portage_const.INCREMENTALS, ignore_none=1)
					#self.mygcfg = grab_stacked("make.defaults", self.profiles, getconfig)
					if self.mygcfg is None:
						self.mygcfg = {}
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! %s\n" % (e), noiselevel=-1)
					writemsg("!!! 'rm -Rf /usr/portage/profiles; emerge sync' may fix this. If it does\n",
						noiselevel=-1)
					writemsg("!!! not then please report this to bugs.gentoo.org and, if possible, a dev\n",
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
				writemsg("!!! %s\n" % (e), noiselevel=-1)
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n",
					noiselevel=-1)
				sys.exit(1)


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

			pmask_locations = [os.path.join(self["PORTDIR"], "profiles")]
			pmask_locations.extend(self.profiles)

			if os.environ.get("PORTAGE_CALLER","") == "repoman" and \
				os.environ.get("PORTDIR_OVERLAY","") == "":
				# repoman shouldn't use local settings.
				locations = [self["PORTDIR"] + "/profiles"]
				overlay_profiles = []
			else:
				abs_user_config = os.path.join(config_root,
					USER_CONFIG_PATH.lstrip(os.path.sep))
				locations = [os.path.join(self["PORTDIR"], "profiles"),
					abs_user_config]
				overlay_profiles = []
				for ov in self["PORTDIR_OVERLAY"].split():
					ov = os.path.normpath(ov)
					profiles_dir = os.path.join(ov, "profiles")
					if os.path.isdir(profiles_dir):
						overlay_profiles.append(profiles_dir)
				locations += overlay_profiles
				
				pmask_locations.extend(overlay_profiles)
				if os.environ.get("PORTAGE_CALLER","") != "repoman":
					pmask_locations.append(abs_user_config)

			if os.environ.get("PORTAGE_CALLER","") == "repoman":
				self.pusedict = {}
				self.pkeywordsdict = {}
				self.punmaskdict = {}
			else:
				pusedict = grabdict_package(
					os.path.join(abs_user_config, "package.use"), recursive=1)
				self.pusedict = {}
				for key in pusedict.keys():
					cp = dep_getkey(key)
					if not self.pusedict.has_key(cp):
						self.pusedict[cp] = {}
					self.pusedict[cp][key] = pusedict[key]

				#package.keywords
				pkgdict = grabdict_package(
					os.path.join(abs_user_config, "package.keywords"),
					recursive=1)
				self.pkeywordsdict = {}
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
				self.punmaskdict = {}
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
			for x in range(len(pkgprovidedlines)-1, -1, -1):
				cpvr = catpkgsplit(pkgprovidedlines[x])
				if not cpvr or cpvr[0] == "null":
					writemsg("Invalid package name in package.provided: "+pkgprovidedlines[x]+"\n",
						noiselevel=-1)
					del pkgprovidedlines[x]

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

		self.lookuplist=self.configlist[:]
		self.lookuplist.reverse()

		useorder=self["USE_ORDER"]
		if not useorder:
			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			useorder = "env:pkg:conf:defaults"
			self.backupenv["USE_ORDER"] = useorder
		useordersplit=useorder.split(":")

		self.uvlist=[]
		for x in useordersplit:
			if self.configdict.has_key(x):
				if "PKGUSE" in self.configdict[x].keys():
					del self.configdict[x]["PKGUSE"] # Delete PkgUse, Not legal to set.
				#prepend db to list to get correct order
				self.uvlist[0:0]=[self.configdict[x]]

		self.configdict["env"]["PORTAGE_GID"]=str(portage_gid)
		self.backupenv["PORTAGE_GID"]=str(portage_gid)

		if self["PORTAGE_CACHEDIR"]:
			# XXX: Deprecated -- April 15 -- NJ
			writemsg(yellow(">>> PORTAGE_CACHEDIR has been deprecated!")+"\n")
			writemsg(">>> Please use PORTAGE_DEPCACHEDIR instead.\n")
			self.depcachedir = self["PORTAGE_CACHEDIR"]
			del self["PORTAGE_CACHEDIR"]

		if self["PORTAGE_DEPCACHEDIR"]:
			#the auxcache is the only /var/cache/edb/ entry that stays at / even when "root" changes.
			# XXX: Could move with a CHROOT functionality addition.
			self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			del self["PORTAGE_DEPCACHEDIR"]

		overlays = string.split(self["PORTDIR_OVERLAY"])
		if overlays:
			new_ov=[]
			for ov in overlays:
				ov=os.path.normpath(ov)
				if os.path.isdir(ov):
					new_ov.append(ov)
				else:
					writemsg(red("!!! Invalid PORTDIR_OVERLAY (not a dir): "+ov+"\n"),
						noiselevel=-1)
			self["PORTDIR_OVERLAY"] = string.join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")

		if clone is None:
			self.regenerate()
			self.features = portage_util.unique_array(self["FEATURES"].split())
		else:
			# XXX
			# The below self.regenerate() causes previous changes to FEATURES
			# (and other incrementals) to be reverted.  If this instance is a
			# clone, we need to take the cloned FEATURES from backupenv and
			# save them where the regenerate() call will not destroy them.
			# Later, we use backup_changes() to restore the cloned FEATURES
			# into the backupenv once again.
			self.features = portage_util.unique_array(
				self.backupenv["FEATURES"].split())
			self.regenerate()

		#XXX: Should this be temporary? Is it possible at all to have a default?
		if "gpg" in self.features:
			if not os.path.exists(self["PORTAGE_GPG_DIR"]) or not os.path.isdir(self["PORTAGE_GPG_DIR"]):
				writemsg("PORTAGE_GPG_DIR is invalid. Removing gpg from FEATURES.\n",
					noiselevel=-1)
				self.features.remove("gpg")

		if not portage_exec.sandbox_capable and \
			("sandbox" in self.features or "usersandbox" in self.features):
			if os.environ.get("PORTAGE_CALLER","") == "repoman" and \
				self.profile_path is not None and \
				os.path.realpath(self.profile_path) != \
				os.path.realpath(PROFILE_PATH):
				pass # This profile does not belong to the user running repoman.
			else:
				writemsg(red("!!! Problem with sandbox binary. Disabling...\n\n"),
				noiselevel=-1)
			if "sandbox" in self.features:
				self.features.remove("sandbox")
			if "usersandbox" in self.features:
				self.features.remove("usersandbox")

		self.features.sort()
		self["FEATURES"] = " ".join(self.features)
		self.backup_changes("FEATURES")

		if not len(self["CBUILD"]) and len(self["CHOST"]):
			self["CBUILD"] = self["CHOST"]
			self.backup_changes("CBUILD")

		if mycpv:
			self.setcpv(mycpv)

		self.backupenv["PORTAGE_BIN_PATH"] = PORTAGE_BIN_PATH
		self.backupenv["PORTAGE_PYM_PATH"] = PORTAGE_PYM_PATH

		self["PORTAGE_CONFIGROOT"] = config_root
		self.backup_changes("PORTAGE_CONFIGROOT")
		self["ROOT"] = target_root
		self.backup_changes("ROOT")

		self._init_dirs()

	def _init_dirs(self):
		"""Create tmp, var/tmp and var/lib/portage (relative to $ROOT)."""

		dir_mode_map = {
			"tmp"             :(-1,          01777, 0),
			"var/tmp"         :(-1,          01777, 0),
			"var/lib/portage" :(portage_gid, 02750, 02),
			"var/cache/edb"   :(portage_gid,  0755, 02)
		}

		for mypath, (gid, mode, modemask) in dir_mode_map.iteritems():
			try:
				mydir = os.path.join(self["ROOT"], mypath)
				portage_util.ensure_dirs(mydir, gid=gid, mode=mode, mask=modemask)
			except portage_exception.PortageException, e:
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
		except:
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
		if key and self.configdict["env"].has_key(key):
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError, "No such key defined in environment: %s" % key

	def reset(self,keeping_pkg=0,use_cache=1):
		"reset environment to original settings"
		for x in self.configlist[-1].keys():
			if x not in self.backupenv.keys():
				del self.configlist[-1][x]

		self.configdict["env"].update(self.backupenv)

		self.modifiedkeys = []
		if not keeping_pkg:
			self.puse = ""
			self.configdict["pkg"].clear()
		self.regenerate(use_cache=use_cache)

	def load_infodir(self,infodir):
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
			for filename in listdir(infodir,filesonly=1,EmptyOnError=1):
				if myre.match(filename):
					try:
						mydata = string.strip(open(infodir+"/"+filename).read())
						if len(mydata)<2048:
							if filename == "USE":
								self.configdict["pkg"][filename] = "-* "+mydata
							else:
								self.configdict["pkg"][filename] = mydata
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

	def setcpv(self,mycpv,use_cache=1):
		self.modifying()
		self.mycpv = mycpv
		cp = dep_getkey(mycpv)
		newpuse = ""
		if self.pusedict.has_key(cp):
			self.pusekey = best_match_to_list(self.mycpv, self.pusedict[cp].keys())
			if self.pusekey:
				newpuse = string.join(self.pusedict[cp][self.pusekey])
		if newpuse == self.puse:
			return
		self.puse = newpuse
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE
		# CATEGORY is essential for doebuild calls
		self.configdict["pkg"]["CATEGORY"] = mycpv.split("/")[0]
		self.reset(keeping_pkg=1,use_cache=use_cache)

	def setinst(self,mycpv,mydbapi):
		if len(self.virtuals) == 0:
			self.getvirtuals()
		# Grab the virtuals this package provides and add them into the tree virtuals.
		provides = mydbapi.aux_get(mycpv, ["PROVIDE"])[0]
		if isinstance(mydbapi, portdbapi):
			myuse = self["USE"]
		else:
			myuse = mydbapi.aux_get(mycpv, ["USE"])[0]
		virts = flatten(portage_dep.use_reduce(portage_dep.paren_reduce(provides), uselist=myuse.split()))

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

		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals = self.incrementals

		# If self.features exists, it has already been stacked and may have
		# been mutated, so don't stack it again or else any mutations will be
		# reverted.
		if "FEATURES" in myincrementals and hasattr(self, "features"):
			myincrementals = set(myincrementals)
			myincrementals.remove("FEATURES")

		for mykey in myincrementals:
			if mykey=="USE":
				mydbs=self.uvlist
				if "auto" in self["USE_ORDER"].split(":"):
					self.configdict["auto"]["USE"] = autouse(
						vartree(root=self["ROOT"], categories=self.categories,
							settings=self),
						use_cache=use_cache, mysettings=self)
				else:
					self.configdict["auto"]["USE"]=""
			else:
				mydbs=self.configlist[:-1]

			myflags=[]
			for curdb in mydbs:
				if not curdb.has_key(mykey):
					continue
				#variables are already expanded
				mysplit=curdb[mykey].split()

				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags=[]
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(red("USE flags should not start with a '+': %s\n" % x),
							noiselevel=-1)
						x=x[1:]

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
			self.configlist[-1][mykey]=string.join(myflags," ")
			del myflags

		usesplit=[]

		for x in string.split(self.configlist[-1]["USE"]):
			if x not in self.usemask:
				usesplit.append(x)

		if self.has_key("USE_EXPAND"):
			for var in string.split(self["USE_EXPAND"]):
				if self.has_key(var):
					for x in string.split(self[var]):
						mystr = string.lower(var)+"_"+x
						if mystr not in usesplit and mystr not in self.usemask:
							usesplit.append(mystr)

		# Pre-Pend ARCH variable to USE settings so '-*' in env doesn't kill arch.
		if self.configdict["defaults"].has_key("ARCH"):
			if self.configdict["defaults"]["ARCH"]:
				if self.configdict["defaults"]["ARCH"] not in usesplit:
					usesplit.insert(0,self.configdict["defaults"]["ARCH"])

		self.configlist[-1]["USE"]=string.join(usesplit," ")

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

		myvirts     = {}

		# This breaks catalyst/portage when setting to a fresh/empty root.
		# Virtuals cannot be calculated because there is nothing to work
		# from. So the only ROOT prefixed dir should be local configs.
		#myvirtdirs  = prefix_array(self.profiles,myroot+"/")
		myvirtdirs = copy.deepcopy(self.profiles)
		while self.user_profile_dir in myvirtdirs:
			myvirtdirs.remove(self.user_profile_dir)


		# Rules
		# R1: Collapse profile virtuals
		# R2: Extract user-negatives.
		# R3: Collapse user-virtuals.
		# R4: Apply user negatives to all except user settings.

		# Order of preference:
		# 1. user-declared that are installed
		# 3. installed and in profile
		# 4. installed
		# 2. user-declared set
		# 5. profile

		self.dirVirtuals = [grabdict(os.path.join(x, "virtuals")) for x in myvirtdirs]
		self.dirVirtuals.reverse()

		if self.user_profile_dir and os.path.exists(self.user_profile_dir+"/virtuals"):
			self.userVirtuals = grabdict(self.user_profile_dir+"/virtuals")

		# Store all the negatives for later.
		for x in self.userVirtuals.keys():
			self.negVirtuals[x] = []
			for y in self.userVirtuals[x]:
				if y[0] == '-':
					self.negVirtuals[x].append(y[:])

		# Collapse the user virtuals so that we don't deal with negatives.
		self.userVirtuals = stack_dictlist([self.userVirtuals],incremental=1)

		# Collapse all the profile virtuals including user negations.
		self.dirVirtuals = stack_dictlist([self.negVirtuals]+self.dirVirtuals,incremental=1)

		# Repoman does not use user or tree virtuals.
		if os.environ.get("PORTAGE_CALLER","") != "repoman":
			# XXX: vartree does not use virtuals, does user set matter?
			temp_vartree = vartree(myroot, self.dirVirtuals,
				categories=self.categories, settings=self)
			# Reduce the provides into a list by CP.
			self.treeVirtuals = map_dictlist_vals(getCPFromCPV,temp_vartree.get_all_provides())

		self.virtuals = self.__getvirtuals_compile()
		return self.virtuals

	def __getvirtuals_compile(self):
		"""Actually generate the virtuals we have collected.
		The results are reversed so the list order is left to right.
		Given data is [Best,Better,Good] sets of [Good, Better, Best]"""

		# Virtuals by profile+tree preferences.
		ptVirtuals   = {}
		# Virtuals by user+tree preferences.
		utVirtuals   = {}

		# If a user virtual is already installed, we preference it.
		for x in self.userVirtuals.keys():
			utVirtuals[x] = []
			if self.treeVirtuals.has_key(x):
				for y in self.userVirtuals[x]:
					if y in self.treeVirtuals[x]:
						utVirtuals[x].append(y)
			#print "F:",utVirtuals
			#utVirtuals[x].reverse()
			#print "R:",utVirtuals

		# If a profile virtual is already installed, we preference it.
		for x in self.dirVirtuals.keys():
			ptVirtuals[x] = []
			if self.treeVirtuals.has_key(x):
				for y in self.dirVirtuals[x]:
					if y in self.treeVirtuals[x]:
						ptVirtuals[x].append(y)

		# UserInstalled, ProfileInstalled, Installed, User, Profile
		biglist = [utVirtuals, ptVirtuals, self.treeVirtuals,
		           self.userVirtuals, self.dirVirtuals]

		# We reverse each dictlist so that the order matches everything
		# else in portage. [-*, a, b] [b, c, d] ==> [b, a]
		for dictlist in biglist:
			for key in dictlist:
				dictlist[key].reverse()

		# User settings and profile settings take precedence over tree.
		val = stack_dictlist(biglist,incremental=1)

		return val

	def __delitem__(self,mykey):
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
			mydict[x]=self[x]
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
def spawn(mystring,mysettings,debug=0,free=0,droppriv=0,sesandbox=0,fd_pipes=None,**keywords):
	"""spawn a subprocess with optional sandbox protection,
	depending on whether sandbox is enabled.  The "free" argument,
	when set to 1, will disable sandboxing.  This allows us to
	spawn processes that are supposed to modify files outside of the
	sandbox.  We can't use os.system anymore because it messes up
	signal handling.  Using spawn allows our Portage signal handler
	to work."""

	if type(mysettings) == types.DictType:
		env=mysettings
		keywords["opt_name"]="[ %s ]" % "portage"
	else:
		check_config_instance(mysettings)
		env=mysettings.environ()
		keywords["opt_name"]="[%s]" % mysettings["PF"]

	features = mysettings.features
	# XXX: Negative RESTRICT word
	droppriv=(droppriv and ("userpriv" in features) and not \
		(("nouserpriv" in string.split(mysettings["RESTRICT"])) or \
		 ("userpriv" in string.split(mysettings["RESTRICT"]))))

	if droppriv and not uid and portage_gid and portage_uid:
		keywords.update({"uid":portage_uid,"gid":portage_gid,"groups":[portage_gid],"umask":002})

	if not free:
		free=((droppriv and "usersandbox" not in features) or \
			(not droppriv and "sandbox" not in features and "usersandbox" not in features))

	if free:
		keywords["opt_name"] += " bash"
		spawn_func = portage_exec.spawn_bash
	else:
		keywords["opt_name"] += " sandbox"
		spawn_func = portage_exec.spawn_sandbox

	if sesandbox:
		con = selinux.getcontext()
		con = string.replace(con, mysettings["PORTAGE_T"], mysettings["PORTAGE_SANDBOX_T"])
		selinux.setexec(con)

	retval = spawn_func(mystring, env=env, **keywords)

	if sesandbox:
		selinux.setexec(None)

	return retval

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
			writemsg(red("!!! You are fetching to a read-only filesystem, you should turn locking off"),
				noiselevel=-1)
			writemsg("!!! This can be done by adding -distlocks to FEATURES in /etc/make.conf",
				noiselevel=-1)
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

	for myuri in myuris:
		myfile=os.path.basename(myuri)
		try:
			destdir = mysettings["DISTDIR"]+"/"
			if not os.path.exists(destdir+myfile):
				for mydir in fsmirrors:
					if os.path.exists(mydir+"/"+myfile):
						writemsg(_("Local mirror has file: %(file)s\n" % {"file":myfile}))
						shutil.copyfile(mydir+"/"+myfile,destdir+"/"+myfile)
						break
			try:
				apply_secpass_permissions(os.path.join(mysettings["DISTDIR"], myfile), gid=portage_gid,
					mode=0664, mask=02)
			except portage_exception.FileNotFound:
				pass
			except portage_exception.PortageException, e:
				if not os.access(os.path.join(mysettings["DISTDIR"], myfile), os.R_OK):
					writemsg("!!! Failed to adjust permissions: %s\n" % str(e), noiselevel=-1)
		except (OSError,IOError),e:
			# file does not exist
			writemsg(_("!!! %(file)s not found in %(dir)s\n") % {"file":myfile, "dir":mysettings["DISTDIR"]},
				noiselevel=-1)
			gotit=0

	if "fetch" in mysettings["RESTRICT"].split():
		# fetch is restricted.	Ensure all files have already been downloaded; otherwise,
		# print message and exit.
		gotit=1
		for myuri in myuris:
			myfile=os.path.basename(myuri)
			try:
				mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
			except (OSError,IOError),e:
				# file does not exist
				writemsg(_("!!! %(file)s not found in %(dir)s\n") % {"file":myfile, "dir":mysettings["DISTDIR"]},
					noiselevel=-1)
				gotit=0
		if not gotit:
			print
			print "!!!",mysettings["CATEGORY"]+"/"+mysettings["PF"],"has fetch restriction turned on."
			print "!!! This probably means that this ebuild's files must be downloaded"
			print "!!! manually.  See the comments in the ebuild for more information."
			print
			spawn(EBUILD_SH_BINARY+" nofetch",mysettings)
			return 0
		return 1
	locations=mymirrors[:]
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
					try:
						shuffle(thirdpartymirrors[mirrorname])
					except SystemExit, e:
						raise
					except:
						writemsg(red("!!! YOU HAVE A BROKEN PYTHON/GLIBC.\n"), noiselevel=-1)
						writemsg(    "!!! You are most likely on a pentium4 box and have specified -march=pentium4\n")
						writemsg(    "!!! or -fpmath=sse2. GCC was generating invalid sse2 instructions in versions\n")
						writemsg(    "!!! prior to 3.2.3. Please merge the latest gcc or rebuid python with either\n")
						writemsg(    "!!! -march=pentium3 or set -mno-sse2 in your cflags.\n\n\n")
						time.sleep(10)

					for locmirr in thirdpartymirrors[mirrorname]:
						filedict[myfile].append(locmirr+"/"+myuri[eidx+1:])

				if not filedict[myfile]:
					writemsg("No known mirror by the name: %s\n" % (mirrorname))
			else:
				writemsg("Invalid mirror definition in SRC_URI:\n", noiselevel=-1)
				writemsg("  %s\n" % (myuri), noiselevel=-1)
		else:
			if "primaryuri" in mysettings["RESTRICT"].split():
				# Use the source site first.
				if primaryuri_indexes.has_key(myfile):
					primaryuri_indexes[myfile] += 1
				else:
					primaryuri_indexes[myfile] = 0
				filedict[myfile].insert(primaryuri_indexes[myfile], myuri)
			else:
				filedict[myfile].append(myuri)

	missingSourceHost = False
	for myfile in filedict.keys(): # Gives a list, not just the first one
		if not filedict[myfile]:
			writemsg("Warning: No mirrors available for file '%s'\n" % (myfile),
				noiselevel=-1)
			missingSourceHost = True
	if missingSourceHost:
		return 0
	del missingSourceHost

	can_fetch=True

	if not listonly:
		dirmode  = 02070
		filemode =   060
		modemask =    02
		distdir_dirs = ["", "cvs-src"]
		if "distlocks" in features:
			distdir_dirs.append(".locks")
		try:
			
			for x in distdir_dirs:
				mydir = os.path.join(mysettings["DISTDIR"], x)
				if portage_util.ensure_dirs(mydir, gid=portage_gid, mode=dirmode, mask=modemask):
					writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage_exception.OperationNotPermitted(
							"Failed to apply recursive permissions for the portage group.")
		except portage_exception.PortageException, e:
			if not os.path.isdir(mysettings["DISTDIR"]):
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg("!!! Directory Not Found: DISTDIR='%s'\n" % mysettings["DISTDIR"], noiselevel=-1)
				writemsg("!!! Fetching will fail!\n", noiselevel=-1)

	if not os.access(mysettings["DISTDIR"]+"/",os.W_OK):
		if not fetch_to_ro:
			print "!!! No write access to %s" % mysettings["DISTDIR"]+"/"
			can_fetch=False
	else:
		if use_locks and locks_in_subdir:
			distlocks_subdir = os.path.join(mysettings["DISTDIR"], locks_in_subdir)
			if not os.access(distlocks_subdir, os.W_OK):
				writemsg("!!! No write access to write to %s.  Aborting.\n" % distlocks_subdir,
					noiselevel=-1)
				return 0
			del distlocks_subdir
	for myfile in filedict.keys():
		fetched=0
		file_lock = None
		if listonly:
			writemsg("\n")
		else:
			if use_locks and can_fetch:
				if locks_in_subdir:
					file_lock = portage_locks.lockfile(mysettings["DISTDIR"]+"/"+locks_in_subdir+"/"+myfile,wantnewlockfile=1)
				else:
					file_lock = portage_locks.lockfile(mysettings["DISTDIR"]+"/"+myfile,wantnewlockfile=1)
		try:
			for loc in filedict[myfile]:
				if listonly:
					writemsg(loc+" ")
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

				fetchcommand=string.replace(fetchcommand,"${DISTDIR}",mysettings["DISTDIR"])
				resumecommand=string.replace(resumecommand,"${DISTDIR}",mysettings["DISTDIR"])

				try:
					mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
					if mydigests.has_key(myfile):
						#if we have the digest file, we know the final size and can resume the download.
						if mystat[stat.ST_SIZE]<mydigests[myfile]["size"]:
							fetched=1
						else:
							#we already have it downloaded, skip.
							#if our file is bigger than the recorded size, digestcheck should catch it.
							if not fetchonly:
								fetched=2
							else:
								# Verify checksums at each fetch for fetchonly.
								verified_ok,reason = portage_checksum.verify_all(mysettings["DISTDIR"]+"/"+myfile, mydigests[myfile])
								if not verified_ok:
									print reason
									writemsg("!!! Previously fetched file: "+str(myfile)+"\n", noiselevel=-1)
									writemsg("!!! Reason: "+reason[0]+"\n", noiselevel=-1)
									writemsg("!!! Got:      %s\n!!! Expected: %s\n" % \
										(reason[1], reason[2]), noiselevel=-1)
									writemsg("Refetching...\n\n", noiselevel=-1)
									os.unlink(mysettings["DISTDIR"]+"/"+myfile)
									fetched=0
								else:
									for x_key in mydigests[myfile].keys():
										writemsg(">>> Previously fetched file: "+str(myfile)+" "+x_key+" ;-)\n")
									fetched=2
									break #No need to keep looking for this file, we have it!
					else:
						#we don't have the digest file, but the file exists.  Assume it is fully downloaded.
						fetched=2
				except (OSError,IOError),e:
					# ENOENT is expected from the stat call at the beginning of
					# this try block.
					if e.errno != errno.ENOENT:
						writemsg("An exception was caught(1)...\nFailing the download: %s.\n" % (str(e)),
							noiselevel=-1)
					fetched=0

				if not can_fetch:
					if fetched != 2:
						if fetched == 0:
							writemsg("!!! File %s isn't fetched but unable to get it.\n" % myfile,
								noiselevel=-1)
						else:
							writemsg("!!! File %s isn't fully fetched, but unable to complete it\n" % myfile,
								noiselevel=-1)
						return 0
					else:
						continue

				# check if we can actually write to the directory/existing file.
				if fetched!=2 and os.path.exists(mysettings["DISTDIR"]+"/"+myfile) != \
					os.access(mysettings["DISTDIR"]+"/"+myfile, os.W_OK) and not fetch_to_ro:
					writemsg( red("***") + \
						" Lack write access to %s, failing fetch\n" % \
						os.path.join(mysettings["DISTDIR"], myfile),
						noiselevel=-1)
					fetched=0
					break
				elif fetched!=2:
					#we either need to resume or start the download
					#you can't use "continue" when you're inside a "try" block
					if fetched==1:
						#resume mode:
						writemsg(">>> Resuming download...\n")
						locfetch=resumecommand
					else:
						#normal mode:
						locfetch=fetchcommand
					writemsg(">>> Downloading "+str(loc)+"\n")
					myfetch=string.replace(locfetch,"${URI}",loc)
					myfetch=string.replace(myfetch,"${FILE}",myfile)

					spawn_keywords = {}
					if "userfetch" in mysettings.features and \
						os.getuid() == 0 and portage_gid and portage_uid:
						spawn_keywords.update({
							"uid"    : portage_uid,
							"gid"    : portage_gid,
							"groups" : [portage_gid],
							"umask"  : 002})

					try:

						if mysettings.selinux_enabled():
							con = selinux.getcontext()
							con = string.replace(con, mysettings["PORTAGE_T"], mysettings["PORTAGE_FETCH_T"])
							selinux.setexec(con)

						myret = portage_exec.spawn_bash(myfetch,
							env=mysettings.environ(), **spawn_keywords)

						if mysettings.selinux_enabled():
							selinux.setexec(None)

					finally:
						#if root, -always- set the perms.
						if os.path.exists(mysettings["DISTDIR"]+"/"+myfile) and (fetched != 1 or os.getuid() == 0) \
							and os.access(mysettings["DISTDIR"]+"/",os.W_OK):
							if os.stat(mysettings["DISTDIR"]+"/"+myfile).st_gid != portage_gid:
								try:
									os.chown(mysettings["DISTDIR"]+"/"+myfile,-1,portage_gid)
								except SystemExit, e:
									raise
								except:
									portage_util.writemsg("chown failed on distfile: " + str(myfile),
										noiselevel=-1)
							os.chmod(mysettings["DISTDIR"]+"/"+myfile,0664)

					if mydigests!=None and mydigests.has_key(myfile):
						try:
							mystat=os.stat(mysettings["DISTDIR"]+"/"+myfile)
							# no exception?  file exists. let digestcheck() report
							# an appropriately for size or checksum errors
							if (mystat[stat.ST_SIZE]<mydigests[myfile]["size"]):
								# Fetch failed... Try the next one... Kill 404 files though.
								if (mystat[stat.ST_SIZE]<100000) and (len(myfile)>4) and not ((myfile[-5:]==".html") or (myfile[-4:]==".htm")):
									html404=re.compile("<title>.*(not found|404).*</title>",re.I|re.M)
									try:
										if html404.search(open(mysettings["DISTDIR"]+"/"+myfile).read()):
											try:
												os.unlink(mysettings["DISTDIR"]+"/"+myfile)
												writemsg(">>> Deleting invalid distfile. (Improper 404 redirect from server.)\n")
											except SystemExit, e:
												raise
											except:
												pass
									except SystemExit, e:
										raise
									except:
										pass
								continue
							if not fetchonly:
								fetched=2
								break
							else:
								# File is the correct size--check the checksums for the fetched
								# file NOW, for those users who don't have a stable/continuous
								# net connection. This way we have a chance to try to download
								# from another mirror...
								verified_ok,reason = portage_checksum.verify_all(mysettings["DISTDIR"]+"/"+myfile, mydigests[myfile])
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
									for x_key in mydigests[myfile].keys():
										writemsg(">>> "+str(myfile)+" "+x_key+" ;-)\n")
									fetched=2
									break
						except (OSError,IOError),e:
							# ENOENT is expected from the stat call at the
							# beginning of this try block.
							if e.errno != errno.ENOENT:
								writemsg("An exception was caught(2)...\nFailing the download: %s.\n" % (str(e)),
									noiselevel=-1)
							fetched=0
					else:
						if not myret:
							fetched=2
							break
						elif mydigests!=None:
							writemsg("No digest file available and download failed.\n\n",
								noiselevel=-1)
		finally:
			if use_locks and file_lock:
				portage_locks.unlockfile(file_lock)

		if listonly:
			writemsg("\n")
		if (fetched!=2) and not listonly:
			writemsg("!!! Couldn't download "+str(myfile)+". Aborting.\n",
				noiselevel=-1)
			return 0
	return 1

def digestgen(myarchives, mysettings, overwrite=1, manifestonly=0, myportdb=None):
	"""Generates a digest file if missing.  Assumes all files are available.
	DEPRECATED: this now only is a compability wrapper for 
	            portage_manifest.Manifest()
	NOTE: manifestonly and overwrite are useless with manifest2 and
	      are therefore ignored."""
	if myportdb is None:
 		writemsg("Warning: myportdb not specified to digestgen\n")
		global portdb
		myportdb = portdb
	mf = Manifest(mysettings["O"], mysettings["DISTDIR"],
		fetchlist_dict=FetchlistDict(mysettings["O"], mysettings, myportdb))
	writemsg_stdout(">>> Creating Manifest for %s\n" % mysettings["O"])
	try:
		mf.create(requiredDistfiles=myarchives, assumeDistHashesSometimes=True,
			assumeDistHashesAlways=("assume-digests" in mysettings.features))
	except portage_exception.FileNotFound, e:
		writemsg("!!! File %s doesn't exist, can't update Manifest\n" % str(e),
			noiselevel=-1)
		return 0
	mf.write(sign=False)
	if "assume-digests" not in mysettings.features:
		distlist = mf.fhashdict.get("DIST", {}).keys()
		distlist.sort()
		auto_assumed = []
		for filename in distlist:
			if not os.path.exists(os.path.join(mysettings["DISTDIR"], filename)):
				auto_assumed.append(filename)
		if auto_assumed:
			mytree = os.path.realpath(
				os.path.dirname(os.path.dirname(mysettings["O"])))
			cp = os.path.sep.join(mysettings["O"].split(os.path.sep)[-2:])
			pkgs = myportdb.cp_list(cp, mytree=mytree)
			pkgs.sort()
			writemsg_stdout("  digest.assumed" + \
				output.colorize("WARN", str(len(auto_assumed)).rjust(18)) + "\n")
			for pkg_key in pkgs:
				fetchlist = myportdb.getfetchlist(pkg_key,
					mysettings=mysettings, all=True, mytree=mytree)[1]
				pv = pkg_key.split("/")[1]
				for filename in auto_assumed:
					if filename in fetchlist:
						writemsg_stdout("   digest-%s::%s\n" % (pv, filename))
	return 1

def digestParseFile(myfilename, mysettings=None):
	"""(filename) -- Parses a given file for entries matching:
	<checksumkey> <checksum_hex_string> <filename> <filesize>
	Ignores lines that don't start with a valid checksum identifier
	and returns a dict with the filenames as keys and {checksumkey:checksum}
	as the values.
	DEPRECATED: this function is now only a compability wrapper for
	            portage_manifest.Manifest()."""

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
	            portage_manifest.Manifest()."""
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
	okaymsg = " ;-)\n"
	try:
		writemsg_stdout(">>> checking ebuild checksums")
		mf.checkTypeHashes("EBUILD")
		writemsg_stdout(okaymsg)
		writemsg_stdout(">>> checking auxfile checksums")
		mf.checkTypeHashes("AUX")
		writemsg_stdout(okaymsg)
		writemsg_stdout(">>> checking miscfile checksums")
		mf.checkTypeHashes("MISC", ignoreMissingFiles=True)
		writemsg_stdout(okaymsg)
		for f in myfiles:
			writemsg_stdout(">>> checking %s" % f)
			mf.checkFileHashes(mf.findFile(f), f)
			writemsg_stdout(okaymsg)
	except KeyError, e:
		writemsg("\n!!! Missing digest for %s\n" % str(e), noiselevel=-1)
		return 0
	except portage_exception.FileNotFound, e:
		writemsg("\n!!! A file listed in the Manifest could not be found: %s\n" % str(e),
			noiselevel=-1)
		return 0
	except portage_exception.DigestException, e:
		writemsg("\n!!! Digest verification failed:\n", noiselevel=-1)
		writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
		writemsg("!!! Reason: %s\n" % e.value[1], noiselevel=-1)
		writemsg("!!! Got: %s\n" % e.value[2], noiselevel=-1)
		writemsg("!!! Expected: %s\n" % e.value[3], noiselevel=-1)
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
	del mysettings["EBUILD_PHASE"]
	if phase_retval == os.EX_OK:
		if mydo == "install":
			mycommand = " ".join([MISC_SH_BINARY, "install_qa_check"])
			qa_retval = spawn(mycommand, mysettings, debug=debug, logfile=logfile, **kwargs)
			if qa_retval:
				writemsg("!!! install_qa_check failed; exiting.\n",
					noiselevel=-1)
			return qa_retval
	return phase_retval

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


def eapi_is_supported(eapi):
	return str(eapi).strip() == str(portage_const.EAPI).strip()

def doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, mydbapi):

	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if mysettings.configdict["pkg"].has_key("CATEGORY"):
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(os.path.normpath(pkg_dir+"/.."))
	mypv = os.path.basename(ebuild_path)[:-7]	
	mycpv = cat+"/"+mypv
	mysplit=pkgsplit(mypv,silent=0)
	if mysplit is None:
		writemsg("!!! Error: PF is null '%s'; exiting.\n" % mypv,
			noiselevel=-1)
		return 1

	if mydo != "depend":
		# XXX: We're doing a little hack here to curtain the gvisible locking
		# XXX: that creates a deadlock... Really need to isolate that.
		mysettings.reset(use_cache=use_cache)
	mysettings.setcpv(mycpv,use_cache=use_cache)

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

	mysettings["PROFILE_PATHS"] = string.join(mysettings.profiles,"\n")+"\n"+CUSTOM_PROFILE_PATH
	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if portage_util.noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mydo != "depend":
		eapi, mysettings["INHERITED"], mysettings["SLOT"], mysettings["RESTRICT"]  = \
			mydbapi.aux_get(mycpv, ["EAPI", "INHERITED", "SLOT", "RESTRICT"])
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise portage_exception.UnsupportedAPIException(mycpv, eapi)
		mysettings["PORTAGE_RESTRICT"] = " ".join(flatten(
			portage_dep.use_reduce(portage_dep.paren_reduce(
			mysettings["RESTRICT"]), uselist=mysettings["USE"].split())))

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	if mysettings.has_key("PATH"):
		mysplit=string.split(mysettings["PATH"],":")
	else:
		mysplit=[]
	if PORTAGE_BIN_PATH not in mysplit:
		mysettings["PATH"]=PORTAGE_BIN_PATH+":"+mysettings["PATH"]


	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/binpkgs"
	
	# Package {pre,post}inst and {pre,post}rm may overlap, so they must have separate
	# locations in order to prevent interference.
	if mydo in ("unmerge", "prerm", "postrm", "cleanrm"):
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(mysettings["PKG_TMPDIR"], mysettings["PF"])
	else:
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(mysettings["BUILD_PREFIX"], mysettings["PF"])

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
	for c in ("GOOD", "WARN", "BAD", "HILITE", "BRACKET"):
		mysettings[c] = output.codes[c]

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

	dir_mode_map = {
		"BUILD_PREFIX"     :00070,
		"HOME"             :02070,
		"PORTAGE_BUILDDIR" :00070,
		"PKG_LOGDIR"       :00070,
		"T"                :02070
	}

	mysettings["PKG_LOGDIR"] = os.path.join(mysettings["T"], "logging")

	for dir_key, mode in dir_mode_map.iteritems():
		if not makedirs(mysettings[dir_key]):
			return 1
		try:
			apply_secpass_permissions(mysettings[dir_key],
			gid=portage_gid, mode=mode, mask=02)
		except portage_exception.OperationNotPermitted, e:
			writemsg("Operation Not Permitted: %s\n" % str(e), noiselevel=-1)
			return 1
		except portage_exception.FileNotFound, e:
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
					modified = portage_util.ensure_dirs(mydir,
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
							raise portage_exception.OperationNotPermitted(
								"Failed to apply recursive permissions for the portage group.")
			except portage_exception.PortageException, e:
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
	except portage_exception.FileNotFound:
		pass # ebuild.sh will create it

	if mysettings.get("PORT_LOGDIR", "") == "":
		while "PORT_LOGDIR" in mysettings:
			del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		try:
			portage_util.ensure_dirs(mysettings["PORT_LOGDIR"],
				uid=portage_uid, gid=portage_gid, mode=02770)
		except portage_exception.PortageException, e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! Permission issues with PORT_LOGDIR='%s'\n" % \
				mysettings["PORT_LOGDIR"], noiselevel=-1)
			writemsg("!!! Disabling logging.\n", noiselevel=-1)
			while "PORT_LOGDIR" in mysettings:
				del mysettings["PORT_LOGDIR"]

def doebuild(myebuild, mydo, myroot, mysettings, debug=0, listonly=0,
	fetchonly=0, cleanup=0, dbkey=None, use_cache=1, fetchall=0, tree=None,
	mydbapi=None, vartree=None, prev_mtimes=None):
	if not tree:
		writemsg("Warning: tree not specified to doebuild\n")
		tree = "porttree"
	global db, actionmap_deps
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
			writemsg(string.ljust(validcommands[vcount], 11), noiselevel=-1)
		writemsg("\n", noiselevel=-1)
		return 1

	if not os.path.exists(myebuild):
		writemsg("!!! doebuild: %s not found for %s\n" % (myebuild, mydo),
			noiselevel=-1)
		return 1

	mystatus = doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
		use_cache, mydbapi)
	if mystatus:
		return mystatus

	# get possible slot information from the deps file
	if mydo=="depend":
		if mysettings.has_key("PORTAGE_DEBUG") and mysettings["PORTAGE_DEBUG"]=="1":
			# XXX: This needs to use a FD for saving the output into a file.
			# XXX: Set this up through spawn
			pass
		writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
		if dbkey:
			mysettings["dbkey"] = dbkey
		else:
			mysettings["dbkey"] = mysettings.depcachedir+"/aux_db_key_temp"

		retval = spawn(EBUILD_SH_BINARY+" depend",mysettings)
		return retval

	if not os.path.isdir(mysettings["PORTAGE_TMPDIR"]):
		writemsg("The directory specified in your PORTAGE_TMPDIR variable, '%s',\n" % \
			mysettings["PORTAGE_TMPDIR"], noiselevel=-1)
		writemsg("does not exist.  Please create this directory or correct your PORTAGE_TMPDIR setting.\n",
			noiselevel=-1)
		return 1

	logfile=None
	# Build directory creation isn't required for any of these.
	if mydo not in ["fetch","digest","manifest"]:
		mystatus = prepare_build_dirs(myroot, mysettings, cleanup)
		if mystatus:
			return mystatus

		if mydo == "unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		if "PORT_LOGDIR" in mysettings:
			logid_path = os.path.join(mysettings["PORTAGE_BUILDDIR"], ".logid")
			if not os.path.exists(logid_path):
				f = open(logid_path, "w")
				f.close()
				del f
			logid_time = time.strftime("%Y%m%d-%H%M%S",
				time.gmtime(os.stat(logid_path).st_mtime))
			logfile = os.path.join(mysettings["PORT_LOGDIR"], "%s:%s:%s.log" %\
				(mysettings["CATEGORY"], mysettings["PF"], logid_time))
			mysettings["PORTAGE_LOG_FILE"] = logfile
			del logid_path, logid_time

	# if any of these are being called, handle them -- running them out of the sandbox -- and stop now.
	if mydo in ["clean","cleanrm"]:
		return spawn(EBUILD_SH_BINARY+" clean",mysettings,debug=debug,free=1,logfile=None)
	elif mydo in ["help","setup"]:
		return spawn(EBUILD_SH_BINARY+" "+mydo,mysettings,debug=debug,free=1,logfile=logfile)
	elif mydo == "preinst":
		mysettings.load_infodir(mysettings["O"])
		if mysettings.has_key("EMERGE_FROM") and "binary" == mysettings["EMERGE_FROM"]:
			mysettings["IMAGE"] = os.path.join(mysettings["PKG_TMPDIR"], mysettings["PF"], "bin")
		else:
			mysettings["IMAGE"] = mysettings["D"]
		phase_retval = spawn(" ".join((EBUILD_SH_BINARY, mydo)), mysettings, debug=debug, free=1, logfile=logfile)
		if phase_retval == os.EX_OK:
			# Post phase logic and tasks that have been factored out of ebuild.sh.
			myargs = [MISC_SH_BINARY, "preinst_mask", "preinst_sfperms",
				"preinst_selinux_labels", "preinst_suid_scan"]
			phase_retval = spawn(" ".join(myargs), mysettings, debug=debug, free=1, logfile=logfile)
			if phase_retval != os.EX_OK:
				writemsg("!!! post preinst failed; exiting.\n", noiselevel=-1)
		del mysettings["IMAGE"]
		return phase_retval
	elif mydo in ["prerm","postrm","postinst","config"]:
		mysettings.load_infodir(mysettings["O"])
		return spawn(EBUILD_SH_BINARY+" "+mydo,mysettings,debug=debug,free=1,logfile=logfile)

	mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))

	newuris, alist = mydbapi.getfetchlist(mycpv, mysettings=mysettings)
	alluris, aalist = mydbapi.getfetchlist(
		mycpv, mysettings=mysettings, all=True)
	mysettings["A"]=string.join(alist," ")
	mysettings["AA"]=string.join(aalist," ")
	if ("mirror" in features) or fetchall:
		fetchme=alluris[:]
		checkme=aalist[:]
	elif mydo == "digest":
		fetchme = alluris[:]
		checkme = aalist[:]
		# Skip files that we already have digests for.
		mf = Manifest(mysettings["O"], mysettings["DISTDIR"])
		mydigests = mf.getTypeDigests("DIST")
		for filename, hashes in mydigests.iteritems():
			if len(hashes) == len(mf.hashes):
				while filename in checkme:
					i = checkme.index(filename)
					del fetchme[i]
					del checkme[i]
			del filename, hashes
	else:
		fetchme=newuris[:]
		checkme=alist[:]

	# Only try and fetch the files if we are going to need them ... otherwise,
	# if user has FEATURES=noauto and they run `ebuild clean unpack compile install`,
	# we will try and fetch 4 times :/
	need_distfiles = (mydo in ("digest", "fetch", "unpack") or
	                  mydo != "manifest" and "noauto" not in features)
	if need_distfiles and not fetch(fetchme, mysettings, listonly=listonly, fetchonly=fetchonly):
		return 1

	if mydo=="fetch" and listonly:
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
	except portage_exception.PermissionDenied, e:
		writemsg("!!! %s\n" % str(e), noiselevel=-1)
		if mydo in ("digest", "manifest"):
			return 1

	# See above comment about fetching only when needed
	if not digestcheck(checkme, mysettings, ("strict" in features),
		(mydo not in ["digest","fetch","unpack"] and
		mysettings["PORTAGE_CALLER"] == "ebuild" and "noauto" in features)):
		return 1

	if mydo=="fetch":
		return 0

	# inefficient.  improve this logic via making actionmap easily searchable to see if we're in the chain of what
	# will be executed, either that or forced N doebuild calls instead of a single set of phase calls.
	if (mydo not in ("setup", "clean", "postinst", "preinst", "prerm", "fetch", "digest", "manifest") and 
		"noauto" not in features) or mydo == "unpack":
		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		mysettings["PORTAGE_ACTUAL_DISTDIR"] = orig_distdir = mysettings["DISTDIR"]
		edpath = mysettings["DISTDIR"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "distdir")
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
		apply_secpass_permissions(edpath, gid=portage_gid, mode=0775)
		try:
			for file in aalist:
				os.symlink(os.path.join(orig_distdir, file), os.path.join(edpath, file))
		except OSError:
			print "!!! Failed symlinking in '%s' to ebuild distdir" % file
			raise

	#initial dep checks complete; time to process main commands

	nosandbox=(("userpriv" in features) and ("usersandbox" not in features) and \
		("userpriv" not in mysettings["RESTRICT"]) and ("nouserpriv" not in mysettings["RESTRICT"]))
	if nosandbox and ("userpriv" not in features or "userpriv" in mysettings["RESTRICT"] or \
		"nouserpriv" in mysettings["RESTRICT"]):
		nosandbox = ("sandbox" not in features and "usersandbox" not in features)

	sesandbox = mysettings.selinux_enabled() and "sesandbox" in mysettings.features
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
			for x in ["","/"+mysettings["CATEGORY"],"/All"]:
				if not os.path.exists(mysettings["PKGDIR"]+x):
					os.makedirs(mysettings["PKGDIR"]+x)
		# REBUILD CODE FOR TBZ2 --- XXXX
		retval = spawnebuild(mydo, actionmap, mysettings, debug, logfile=logfile)
	elif mydo=="qmerge":
		#check to ensure install was run.  this *only* pops up when users forget it and are using ebuild
		if not os.path.exists(mysettings["PORTAGE_BUILDDIR"]+"/.installed"):
			print "!!! mydo=qmerge, but install phase hasn't been ran"
			sys.exit(1)
		# qmerge is a special phase that implies noclean.
		if "noclean" not in mysettings.features:
			mysettings.features.append("noclean")
		#qmerge is specifically not supposed to do a runtime dep check
		retval = merge(mysettings["CATEGORY"], mysettings["PF"], mysettings["D"],
			os.path.join(mysettings["PORTAGE_BUILDDIR"], "build-info"), myroot,
			mysettings, myebuild=mysettings["EBUILD"], mytree=tree,
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
		sys.exit(1)

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
		if bsd_chflags:
			sflags=bsd_chflags.lgetflags(src)
			if sflags < 0:
				# Problem getting flags...
				writemsg("!!! Couldn't get flags for "+dest+"\n",
					noiselevel=-1)
				return None

	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except SystemExit, e:
		raise
	except:
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if bsd_chflags:
		# Check that we can actually unset schg etc flags...
		# Clear the flags on source and destination; we'll reinstate them after merging
		if destexists and sflags != 0:
			if bsd_chflags.lchflags(dest, 0) < 0:
				writemsg("!!! Couldn't clear flags on file being merged: \n ",
					noiselevel=-1)
		# We might have an immutable flag on the parent dir; save and clear.
		pflags=bsd_chflags.lgetflags(os.path.dirname(dest))
		if pflags != 0:
			bsd_chflags.lchflags(os.path.dirname(dest), 0)

		# Don't bother checking the return value here; if it fails then the next line will catch it.
		bsd_chflags.lchflags(src, 0)

		if bsd_chflags.lhasproblems(src)>0 or (destexists and bsd_chflags.lhasproblems(dest)>0) or bsd_chflags.lhasproblems(os.path.dirname(dest))>0:
			# This is bad: we can't merge the file with these flags set.
			writemsg("!!! Can't merge file "+dest+" because of flags set\n",
				noiselevel=-1)
			return None

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
			if bsd_chflags:
				# Restore the flags we saved before moving
				if (sflags != 0 and bsd_chflags.lchflags(dest, sflags) < 0) or \
					(pflags and bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0):
					writemsg("!!! Couldn't restore flags ("+str(flags)+") on " + dest+":\n",
						noiselevel=-1)
					writemsg("!!! %s\n" % str(e), noiselevel=-1)
					return None
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
		if (sflags != 0 and bsd_chflags.lchflags(dest, sflags) < 0) or \
			(pflags and bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0):
			writemsg("!!! Couldn't restore flags ("+str(sflags)+") on " + dest+":\n",
				noiselevel=-1)
			return None

	return newmtime

def merge(mycat, mypkg, pkgloc, infloc, myroot, mysettings, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None):
	mylink = dblink(mycat, mypkg, myroot, mysettings, treetype=mytree,
		vartree=vartree)
	return mylink.merge(pkgloc, infloc, myroot, myebuild,
		mydbapi=mydbapi, prev_mtimes=prev_mtimes)

def unmerge(cat, pkg, myroot, mysettings, mytrimworld=1, vartree=None, ldpath_mtimes=None):
	mylink = dblink(
		cat, pkg, myroot, mysettings, treetype="vartree", vartree=vartree)
	if mylink.exists():
		mylink.unmerge(trimworld=mytrimworld, cleanup=1,
			ldpath_mtimes=ldpath_mtimes)
		mylink.delete()
		return 0
	return 1

def isvalidatom(atom):
	mycpv_cps = catpkgsplit(dep_getcpv(atom))
	operator = get_operator(atom)
	if operator:
		if operator[0] in "<>" and atom[-1] == "*":
			return 0
		if mycpv_cps and mycpv_cps[0] != "null":
			# >=cat/pkg-1.0
			return 1
		else:
			# >=cat/pkg or >=pkg-1.0 (no category)
			return 0
	if mycpv_cps:
		# cat/pkg-1.0
		return 0

	if (len(string.split(atom, '/'))==2):
		# cat/pkg
		return 1
	else:
		return 0

def isjustname(mypkg):
	myparts=string.split(mypkg,'-')
	for x in myparts:
		if ververify(x):
			return 0
	return 1

iscache={}
def isspecific(mypkg):
	"now supports packages with no category"
	try:
		return iscache[mypkg]
	except SystemExit, e:
		raise
	except:
		pass
	mysplit=string.split(mypkg,"/")
	if not isjustname(mysplit[-1]):
			iscache[mypkg]=1
			return 1
	iscache[mypkg]=0
	return 0

def getCPFromCPV(mycpv):
	"""Calls pkgsplit on a cpv and returns only the cp."""
	return pkgsplit(mycpv)[0]


def dep_virtual(mysplit, mysettings):
	"Does virtual dependency conversion"
	newsplit=[]
	for x in mysplit:
		if type(x)==types.ListType:
			newsplit.append(dep_virtual(x, mysettings))
		else:
			mykey=dep_getkey(x)
			myvirtuals = mysettings.getvirtuals()
			if myvirtuals.has_key(mykey):
				if len(myvirtuals[mykey]) == 1:
					a = string.replace(x, mykey, myvirtuals[mykey][0])
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in myvirtuals[mykey]:
						a.append(string.replace(x, mykey, y))
				newsplit.append(a)
			else:
				newsplit.append(x)
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
		for (dep, satisfied) in zip(unreduced, reduced):
			if isinstance(dep, list):
				unresolved += dep_zapdeps(dep, satisfied, myroot,
					use_binaries=use_binaries, trees=trees)
			elif not satisfied:
				unresolved.append(dep)
		return unresolved

	# We're at a ( || atom ... ) type level
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	target = None
	for (dep, satisfied) in zip(deps, satisfieds):
		if isinstance(dep, list):
			atoms = dep_zapdeps(dep, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [dep]
		missing_atoms = [atom for atom in atoms if not trees[myroot]["vartree"].dbapi.match(atom)]

		if not missing_atoms:
			if isinstance(dep, list):
				return atoms  # Sorted out by the recursed dep_zapdeps call
			else:
				target = dep_getkey(dep) # An installed package that's not yet in the graph
				break

		if not target:
			if use_binaries:
				missing_atoms = [atom for atom in atoms if not trees[myroot]["bintree"].dbapi.match(atom)]
			else:
				missing_atoms = [atom for atom in atoms if not trees[myroot]["porttree"].dbapi.xmatch("match-visible", atom)]
			if not missing_atoms:
				target = (dep, satisfied)

	if not target:
		if isinstance(deps[0], list):
			return dep_zapdeps(deps[0], satisfieds[0], myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			return [deps[0]]

	if isinstance(target, tuple): # Nothing matching installed
		if isinstance(target[0], list): # ... and the first available was a sublist
			return dep_zapdeps(target[0], target[1], myroot,
				use_binaries=use_binaries, trees=trees)
		else: # ... and the first available was a single atom
			target = dep_getkey(target[0])

	relevant_atoms = [dep for dep in deps if not isinstance(dep, list) and dep_getkey(dep) == target]

	available_pkgs = {}
	for atom in relevant_atoms:
		if use_binaries:
			pkg_list = trees[myroot]["bintree"].dbapi.match(atom)
		else:
			pkg_list = trees[myroot]["porttree"].dbapi.xmatch("match-visible", atom)
		if not pkg_list:
			continue
		pkg = best(pkg_list)
		available_pkgs[pkg] = atom

	if not available_pkgs:
		return [relevant_atoms[0]] # All masked

	target_pkg = best(available_pkgs.keys())
	suitable_atom = available_pkgs[target_pkg]
	return [suitable_atom]



def dep_getkey(mydep):
	if mydep and mydep[0]=="*":
		mydep=mydep[1:]
	if mydep and mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep and mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	if mydep and isspecific(mydep):
		mysplit=catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0]+"/"+mysplit[1]
	else:
		return mydep

def dep_getcpv(mydep):
	if mydep and mydep[0]=="*":
		mydep=mydep[1:]
	if mydep and mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep and mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	return mydep

def dep_transform(mydep,oldkey,newkey):
	origdep=mydep
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	prefix=""
	postfix=""
	if mydep[-1]=="*":
		mydep=mydep[:-1]
		postfix="*"
	if mydep[:2] in [ ">=", "<=" ]:
		prefix=mydep[:2]
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~!":
		prefix=mydep[:1]
		mydep=mydep[1:]
	if mydep==oldkey:
		return prefix+newkey+postfix
	else:
		return origdep

def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	prefix=""
	postfix=""
	if mydep[-1]=="*":
		mydep=mydep[:-1]
		postfix="*"
	if mydep[:2] in [ ">=", "<=" ]:
		prefix=mydep[:2]
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~!":
		prefix=mydep[:1]
		mydep=mydep[1:]
	return prefix + cpv_expand(
		mydep, mydb=mydb, use_cache=use_cache, settings=settings) + postfix

def dep_check(depstring, mydbapi, mysettings, use="yes", mode=None, myuse=None,
	use_cache=1, use_binaries=0, myroot="/", trees=None):
	"""Takes a depend string and parses the condition."""

	#check_config_instance(mysettings)

	if use=="yes":
		if myuse is None:
			#default behavior
			myusesplit = string.split(mysettings["USE"])
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
	mysplit = portage_dep.paren_reduce(depstring)

	if mysettings:
		# XXX: use="all" is only used by repoman. Why would repoman checks want
		# profile-masked USE flags to be enabled?
		#if use=="all":
		#	mymasks=archlist[:]
		#else:
		mymasks = mysettings.usemask + mysettings.archlist()

		while mysettings["ARCH"] in mymasks:
			del mymasks[mymasks.index(mysettings["ARCH"])]
		mysplit = portage_dep.use_reduce(mysplit,uselist=myusesplit,masklist=mymasks,matchall=(use=="all"),excludeall=[mysettings["ARCH"]])
	else:
		mysplit = portage_dep.use_reduce(mysplit,uselist=myusesplit,matchall=(use=="all"))

	# Do the || conversions
	mysplit=portage_dep.dep_opconvert(mysplit)

	#convert virtual dependencies to normal packages.
	mysplit=dep_virtual(mysplit, mysettings)
	#if mysplit is None, then we have a parse error (paren mismatch or misplaced ||)
	#up until here, we haven't needed to look at the database tree

	if mysplit is None:
		return [0,"Parse Error (parentheses mismatch?)"]
	elif mysplit==[]:
		#dependencies were reduced to nothing
		return [1,[]]
	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0,"Invalid token"]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)
	myeval=dep_eval(mysplit2)
	writemsg("myeval:   %s\n" % (myeval), 1)

	if myeval:
		return [1,[]]
	else:
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
	mypos=0
	deplist=mydeplist[:]
	while mypos<len(deplist):
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
		mypos=mypos+1
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
		if mydb:
			writemsg("mydb.__class__: %s\n" % (mydb.__class__), 1)
			if type(mydb)==types.InstanceType:
				if (not mydb.cp_list(mykey,use_cache=use_cache)) and virts and virts.has_key(mykey):
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
		if (len(matches)>1):
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
	from portage_util import grablines
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
	locations = settings.profiles[:]
	locations.append(os.path.join(settings["PORTDIR"], "profiles"))
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH.lstrip(os.path.sep)))
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(os.path.normpath(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
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
				i = 0
				while i < len(pmasklines):
					l = pmasklines[i].strip()
					if l == "":
						comment = ""
					elif l[0] == "#":
						comment += (l+"\n")
					elif l == x:
						return comment
					i = i + 1
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
	mygroups, eapi = portdb.aux_get(mycpv, ["KEYWORDS", "EAPI"])
	if not eapi_is_supported(eapi):
		return ["required EAPI %s, supported EAPI %s" % (eapi, portage_const.EAPI)]
	mygroups = mygroups.split()
	pgroups = settings["ACCEPT_KEYWORDS"].split()
	myarch = settings["ARCH"]
	pkgdict = settings.pkeywordsdict

	cp = dep_getkey(mycpv)
	if pkgdict.has_key(cp):
		matches = match_to_list(mycpv, pkgdict[cp].keys())
		for match in matches:
			pgroups.extend(pkgdict[cp][match])

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

class packagetree:
	def __init__(self,virtual,clone=None):
		if clone:
			self.tree=clone.tree.copy()
			self.populated=clone.populated
			self.virtual=clone.virtual
			self.dbapi=None
		else:
			self.tree={}
			self.populated=0
			self.virtual=virtual
			self.dbapi=None

	def resolve_key(self,mykey):
		return key_expand(mykey, mydb=self.dbapi, settings=self.settings)

	def dep_nomatch(self,mypkgdep):
		mykey=dep_getkey(mypkgdep)
		nolist=self.dbapi.cp_list(mykey)
		mymatch=self.dbapi.match(mypkgdep)
		if not mymatch:
			return nolist
		for x in mymatch:
			if x in nolist:
				nolist.remove(x)
		return nolist

	def depcheck(self,mycheck,use="yes",myusesplit=None):
		return dep_check(mycheck,self.dbapi,use=use,myuse=myusesplit)

	def populate(self):
		"populates the tree with values"
		populated=1
		pass

def best(mymatches):
	"accepts None arguments; assumes matches are valid."
	global bestcount
	if mymatches is None:
		return ""
	if not len(mymatches):
		return ""
	bestmatch=mymatches[0]
	p2=catpkgsplit(bestmatch)[1:]
	for x in mymatches[1:]:
		p1=catpkgsplit(x)[1:]
		if pkgcmp(p1,p2)>0:
			bestmatch=x
			p2=catpkgsplit(bestmatch)[1:]
	return bestmatch

def match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Searches list for entries that matches the package.
	"""
	matches=[]
	for x in mylist:
		if match_from_list(x,[mypkg]):
			if x not in matches:
				matches.append(x)
	return matches

def best_match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Returns the most specific entry (assumed to be the longest one)
	that matches the package given.
	"""
	# XXX Assumption is wrong sometimes.
	maxlen = 0
	bestm  = None
	for x in match_to_list(mypkg,mylist):
		if len(x) > maxlen:
			maxlen = len(x)
			bestm  = x
	return bestm

def catsplit(mydep):
	return mydep.split("/", 1)

def get_operator(mydep):
	"""
	returns '~', '=', '>', '<', '=*', '>=', or '<='
	"""
	if mydep[0] == "~":
		operator = "~"
	elif mydep[0] == "=":
		if mydep[-1] == "*":
			operator = "=*"
		else:
			operator = "="
	elif mydep[0] in "><":
		if len(mydep) > 1 and mydep[1] == "=":
			operator = mydep[0:2]
		else:
			operator = mydep[0]
	else:
		operator = None

	return operator


def match_from_list(mydep,candidate_list):
	if mydep[0] == "!":
		mydep = mydep[1:]

	mycpv     = dep_getcpv(mydep)
	mycpv_cps = catpkgsplit(mycpv) # Can be None if not specific

	if not mycpv_cps:
		cat,pkg = catsplit(mycpv)
		ver     = None
		rev     = None
	else:
		cat,pkg,ver,rev = mycpv_cps
		if mydep == mycpv:
			raise KeyError, "Specific key requires an operator (%s) (try adding an '=')" % (mydep)

	if ver and rev:
		operator = get_operator(mydep)
		if not operator:
			writemsg("!!! Invalid atom: %s\n" % mydep, noiselevel=-1)
			return []
	else:
		operator = None

	mylist = []

	if operator is None:
		for x in candidate_list:
			xs = pkgsplit(x)
			if xs is None:
				if x != mycpv:
					continue
			elif xs[0] != mycpv:
				continue
			mylist.append(x)

	elif operator == "=": # Exact match
		if mycpv in candidate_list:
			mylist = [mycpv]

	elif operator == "=*": # glob match
		# The old verion ignored _tag suffixes... This one doesn't.
		for x in candidate_list:
			if x[0:len(mycpv)] == mycpv:
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = catpkgsplit(x)
			if xs[0:2] != mycpv_cps[0:2]:
				continue
			if xs[2] != ver:
				continue
			mylist.append(x)

	elif operator in [">", ">=", "<", "<="]:
		for x in candidate_list:
			try:
				result = pkgcmp(pkgsplit(x), [cat+"/"+pkg,ver,rev])
			except SystemExit, e:
				raise
			except:
				writemsg("\nInvalid package name: %s\n" % x, noiselevel=-1)
				sys.exit(73)
			if result is None:
				continue
			elif operator == ">":
				if result > 0:
					mylist.append(x)
			elif operator == ">=":
				if result >= 0:
					mylist.append(x)
			elif operator == "<":
				if result < 0:
					mylist.append(x)
			elif operator == "<=":
				if result <= 0:
					mylist.append(x)
			else:
				raise KeyError, "Unknown operator: %s" % mydep
	else:
		raise KeyError, "Unknown operator: %s" % mydep


	return mylist


def match_from_list_original(mydep,mylist):
	"""(dep,list)
	Reduces the list down to those that fit the dep
	"""
	mycpv=dep_getcpv(mydep)
	if isspecific(mycpv):
		cp_key=catpkgsplit(mycpv)
		if cp_key is None:
			return []
	else:
		cp_key=None
	#Otherwise, this is a special call; we can only select out of the ebuilds specified in the specified mylist
	if (mydep[0]=="="):
		if cp_key is None:
			return []
		if mydep[-1]=="*":
			#example: "=sys-apps/foo-1.0*"
			try:
				#now, we grab the version of our dependency...
				mynewsplit=string.split(cp_key[2],'.')
				#split it...
				mynewsplit[-1]=`int(mynewsplit[-1])+1`
				#and increment the last digit of the version by one.
				#We don't need to worry about _pre and friends because they're not supported with '*' deps.
				new_v=string.join(mynewsplit,".")+"_alpha0"
				#new_v will be used later in the code when we do our comparisons using pkgcmp()
			except SystemExit, e:
				raise
			except:
				#erp, error.
				return []
			mynodes=[]
			cmp1=cp_key[1:]
			cmp1[1]=cmp1[1]+"_alpha0"
			cmp2=[cp_key[1],new_v,"r0"]
			for x in mylist:
				cp_x=catpkgsplit(x)
				if cp_x is None:
					#hrm, invalid entry.  Continue.
					continue
				#skip entries in our list that do not have matching categories
				if cp_key[0]!=cp_x[0]:
					continue
				# ok, categories match. Continue to next step.
				if ((pkgcmp(cp_x[1:],cmp1)>=0) and (pkgcmp(cp_x[1:],cmp2)<0)):
					# entry is >= the version in specified in our dependency, and <= the version in our dep + 1; add it:
					mynodes.append(x)
			return mynodes
		else:
			# Does our stripped key appear literally in our list?  If so, we have a match; if not, we don't.
			if mycpv in mylist:
				return [mycpv]
			else:
				return []
	elif (mydep[0]==">") or (mydep[0]=="<"):
		if cp_key is None:
			return []
		if (len(mydep)>1) and (mydep[1]=="="):
			cmpstr=mydep[0:2]
		else:
			cmpstr=mydep[0]
		mynodes=[]
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x is None:
				#invalid entry; continue.
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if eval("pkgcmp(cp_x[1:],cp_key[1:])"+cmpstr+"0"):
				mynodes.append(x)
		return mynodes
	elif mydep[0]=="~":
		if cp_key is None:
			return []
		myrev=-1
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x is None:
				#invalid entry; continue
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if cp_key[2]!=cp_x[2]:
				#if version doesn't match, skip it
				continue
			myint = int(cp_x[3][1:])
			if myint > myrev:
				myrev   = myint
				mymatch = x
		if myrev == -1:
			return []
		else:
			return [mymatch]
	elif cp_key is None:
		if mydep[0]=="!":
			return []
			#we check ! deps in emerge itself, so always returning [] is correct.
		mynodes=[]
		cp_key=mycpv.split("/")
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x is None:
				#invalid entry; continue
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if cp_key[1]!=cp_x[1]:
				continue
			mynodes.append(x)
		return mynodes
	else:
		return []


class portagetree:
	def __init__(self, root="/", virtual=None, clone=None, settings=None):

		if clone:
			self.root=clone.root
			self.portroot=clone.portroot
			self.pkglines=clone.pkglines
		else:
			self.root=root
			if settings is None:
				settings = globals()["settings"]
			self.settings = settings
			self.portroot=settings["PORTDIR"]
			self.virtual=virtual
			self.dbapi = portdbapi(
				settings["PORTDIR"], mysettings=config(clone=settings))

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
		mysplit=string.split(pkgname,"/")
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

	def aux_get(self,mycpv,mylist):
		"stub code for returning auxiliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		raise NotImplementedError

	def match(self,origdep,use_cache=1):
		mydep = dep_expand(origdep, mydb=self, settings=self.settings)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		return match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))

	def match2(self,mydep,mykey,mylist):
		writemsg("DEPRECATED: dbapi.match2\n")
		match_from_list(mydep,mylist)

	def invalidentry(self, mypath):
		if re.search("portage_lockfile$",mypath):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				portage_locks.unlockfile((mypath,None,None))
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

	def cpv_inject(self,mycpv):
		"""Adds a cpv from the list of available packages."""
		mycp=cpv_getkey(mycpv)
		self.cpvdict[mycpv]=1
		if not self.cpdict.has_key(mycp):
			self.cpdict[mycp]=[]
		if not mycpv in self.cpdict[mycp]:
			self.cpdict[mycp].append(mycpv)

	#def cpv_virtual(self,oldcpv,newcpv):
	#	"""Maps a cpv to the list of available packages."""
	#	mycp=cpv_getkey(newcpv)
	#	self.cpvdict[newcpv]=1
	#	if not self.virtdict.has_key(mycp):
	#		self.virtdict[mycp]=[]
	#	if not mycpv in self.virtdict[mycp]:
	#		self.virtdict[mycp].append(oldcpv)
	#	cpv_remove(oldcpv)

	def cpv_remove(self,mycpv):
		"""Removes a cpv from the list of available packages."""
		mycp=cpv_getkey(mycpv)
		if self.cpvdict.has_key(mycpv):
			del	self.cpvdict[mycpv]
		if not self.cpdict.has_key(mycp):
			return
		while mycpv in self.cpdict[mycp]:
			del self.cpdict[mycp][self.cpdict[mycp].index(mycpv)]
		if not len(self.cpdict[mycp]):
			del self.cpdict[mycp]

class bindbapi(fakedbapi):
	def __init__(self, mybintree=None, settings=None):
		self.bintree = mybintree
		self.cpvdict={}
		self.cpdict={}
		if settings is None:
			settings = globals()["settings"]
		self.settings = settings

	def match(self, *pargs, **kwargs):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		return fakedbapi.match(self, *pargs, **kwargs)

	def aux_get(self,mycpv,wants):
		if self.bintree and not self.bintree.populated:
			self.bintree.populate()
		mysplit = string.split(mycpv,"/")
		mylist  = []
		tbz2name = mysplit[1]+".tbz2"
		if self.bintree and not self.bintree.isremote(mycpv):
			tbz2 = xpak.tbz2(self.bintree.getname(mycpv))
		for x in wants:
			if self.bintree and self.bintree.isremote(mycpv):
				# We use the cache for remote packages
				if self.bintree.remotepkgs[tbz2name].has_key(x):
					mylist.append(self.bintree.remotepkgs[tbz2name][x][:]) # [:] Copy String
				else:
					mylist.append("")
			else:
				myval = tbz2.getfile(x)
				if myval is None:
					myval = ""
				else:
					myval = string.join(myval.split(),' ')
				mylist.append(myval)
		if "EAPI" in wants:
			idx = wants.index("EAPI")
			if not mylist[idx]:
				mylist[idx] = "0"
		return mylist

	def aux_update(self, cpv, values):
		tbz2path = self.bintree.getname(cpv)
		mylock = portage_locks.lockfile(tbz2path, wantnewlockfile=1)
		try:
			if not os.path.exists(tbz2path):
				raise KeyError(cpv)
			mytbz2 = xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			mydata.update(values)
			mytbz2.recompose_mem(xpak.xpak_mem(mydata))
		finally:
			portage_locks.unlockfile(mylock)

cptot=0
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

	def cpv_exists(self,mykey):
		"Tells us whether an actual ebuild exists on disk (no masking)"
		return os.path.exists(self.root+VDB_PATH+"/"+mykey)

	def cpv_counter(self,mycpv):
		"This method will grab the COUNTER. Returns a counter value."
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
				raise portage_exception.InvalidPackageName(cp)
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
			old_eb_path = newpath+"/"+mycpsplit[1]    +"-"+mycpsplit[2]
			new_eb_path = newpath+"/"+mycpsplit_new[1]+"-"+mycpsplit[2]
			if mycpsplit[3] != "r0":
				old_eb_path += "-"+mycpsplit[3]
				new_eb_path += "-"+mycpsplit[3]
			if os.path.exists(old_eb_path+".ebuild"):
				os.rename(old_eb_path+".ebuild", new_eb_path+".ebuild")

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
			raise portage_exception.InvalidAtom(pkg)

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
			return match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
		try:
			curmtime=os.stat(self.root+VDB_PATH+"/"+mycat)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except:
			curmtime=0

		if not self.matchcache.has_key(mycat) or not self.mtdircache[mycat]==curmtime:
			# clear cache entry
			self.mtdircache[mycat]=curmtime
			self.matchcache[mycat]={}
		if not self.matchcache[mycat].has_key(mydep):
			mymatch=match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))
			self.matchcache[mycat][mydep]=mymatch
		return self.matchcache[mycat][mydep][:]

	def findname(self, mycpv):
		return self.root+VDB_PATH+"/"+str(mycpv)+"/"+mycpv.split("/")[1]+".ebuild"

	def aux_get(self, mycpv, wants):
		global auxdbkeys
		results = []
		for x in wants:
			myfn = self.root+VDB_PATH+"/"+str(mycpv)+"/"+str(x)
			if os.access(myfn,os.R_OK):
				myf = open(myfn, "r")
				myd = myf.read()
				myf.close()
				myd = re.sub("[\n\r\t]+"," ",myd)
				myd = re.sub(" +"," ",myd)
				myd = string.strip(myd)
			else:
				myd = ""
			results.append(myd)
		if "EAPI" in wants:
			idx = wants.index("EAPI")
			if not results[idx]:
				results[idx] = "0"
		return results

	def aux_update(self, cpv, values):
		cat, pkg = cpv.split("/")
		mylink = dblink(cat, pkg, self.root, self.settings,
			treetype="vartree", vartree=self.vartree)
		try:
			mylink.lockdb()
		except portage_exception.DirectoryNotFound:
			raise KeyError(cpv)
		try:
			if not mylink.exists():
				raise KeyError(cpv)
			for k, v in values.iteritems():
				mylink.setfile(k, v)
		finally:
			mylink.unlockdb()

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
				except SystemExit, e:
					raise
				except:
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
			except SystemExit, e:
				raise
			except:
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

class vartree(packagetree):
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
		try:
			mylines = grabfile(self.root+VDB_PATH+"/"+mycpv+"/PROVIDE")
			if mylines:
				myuse = grabfile(self.root+VDB_PATH+"/"+mycpv+"/USE")
				myuse = string.split(string.join(myuse))
				mylines = string.join(mylines)
				mylines = flatten(portage_dep.use_reduce(portage_dep.paren_reduce(mylines), uselist=myuse))
				for myprovide in mylines:
					mys = catpkgsplit(myprovide)
					if not mys:
						mys = string.split(myprovide, "/")
					myprovides += [mys[0] + "/" + mys[1]]
			return myprovides
		except SystemExit, e:
			raise
		except Exception, e:
			print
			print "Check " + self.root+VDB_PATH+"/"+mycpv+"/PROVIDE and USE."
			print "Possibly Invalid: " + str(mylines)
			print "Exception: "+str(e)
			print
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
		myslot = ""
		try:
			myslot=string.join(grabfile(self.root+VDB_PATH+"/"+mycatpkg+"/SLOT"))
		except SystemExit, e:
			raise
		except Exception, e:
			pass
		return myslot

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
		self.lock_held = 0;

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
			self.manifestVerifyLevel   = portage_gpg.EXISTS
			if "strict" in self.mysettings.features:
				self.manifestVerifyLevel = portage_gpg.MARGINAL
				self.manifestVerifier = portage_gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", minimumTrust=self.manifestVerifyLevel)
			elif "severe" in self.mysettings.features:
				self.manifestVerifyLevel = portage_gpg.TRUSTED
				self.manifestVerifier = portage_gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", requireSignedRing=True, minimumTrust=self.manifestVerifyLevel)
			else:
				self.manifestVerifier = portage_gpg.FileChecker(self.mysettings["PORTAGE_GPG_DIR"], "gentoo.gpg", minimumTrust=self.manifestVerifyLevel)

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

		self.eclassdb = eclass_cache.cache(self.porttree_root,
			overlays=self.mysettings["PORTDIR_OVERLAY"].split())

		self.metadb       = {}
		self.metadbmodule = self.mysettings.load_best_module("portdbapi.metadbmodule")

		#if the portdbapi is "frozen", then we assume that we can cache everything (that no updates to it are happening)
		self.xcache={}
		self.frozen=0

		self.porttrees = [self.porttree_root] + \
			[os.path.realpath(t) for t in self.mysettings["PORTDIR_OVERLAY"].split()]
		self.auxdbmodule  = self.mysettings.load_best_module("portdbapi.auxdbmodule")
		self.auxdb        = {}
		self._init_cache_dirs()
		# XXX: REMOVE THIS ONCE UNUSED_0 IS YANKED FROM auxdbkeys
		# ~harring
		filtered_auxdbkeys = filter(lambda x: not x.startswith("UNUSED_0"), auxdbkeys)
		for x in self.porttrees:
			# location, label, auxdbkeys
			self.auxdb[x] = self.auxdbmodule(self.depcachedir, x, filtered_auxdbkeys, gid=portage_gid)

	def _init_cache_dirs(self):
		"""Create /var/cache/edb/dep and adjust permissions for the portage
		group."""

		dirmode  = 02070
		filemode =   060
		modemask =    02

		try:
			for mydir in (self.depcachedir,):
				if portage_util.ensure_dirs(mydir, gid=portage_gid, mode=dirmode, mask=modemask):
					writemsg("Adjusting permissions recursively: '%s'\n" % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage_exception.OperationNotPermitted(
							"Failed to apply recursive permissions for the portage group.")
		except portage_exception.PortageException, e:
			pass

	def close_caches(self):
		for x in self.auxdb.keys():
			self.auxdb[x].sync()
		self.auxdb.clear()

	def flush_cache(self):
		self.metadb = {}
		self.auxdb  = {}

	def finddigest(self,mycpv):
		try:
			mydig   = self.findname2(mycpv)[0]
			mydigs  = string.split(mydig, "/")[:-1]
			mydig   = string.join(mydigs, "/")

			mysplit = mycpv.split("/")
		except SystemExit, e:
			raise
		except:
			return ""
		return mydig+"/files/digest-"+mysplit[-1]

	def findname(self,mycpv):
		return self.findname2(mycpv)[0]

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
		global auxdbkeys,auxdbkeylen

		cat,pkg = string.split(mycpv, "/", 1)

		myebuild, mylocation = self.findname2(mycpv, mytree)

		if not myebuild:
			writemsg("!!! aux_get(): ebuild path for '%(cpv)s' not specified:\n" % {"cpv":mycpv},
				noiselevel=-1)
			writemsg("!!!            %s\n" % myebuild, noiselevel=-1)
			raise KeyError, "'%(cpv)s' at %(path)s" % {"cpv":mycpv,"path":myebuild}

		myManifestPath = string.join(myebuild.split("/")[:-1],"/")+"/Manifest"
		if "gpg" in self.mysettings.features:
			try:
				mys = portage_gpg.fileStats(myManifestPath)
				if (myManifestPath in self.manifestCache) and \
				   (self.manifestCache[myManifestPath] == mys):
					pass
				elif self.manifestVerifier:
					if not self.manifestVerifier.verify(myManifestPath):
						# Verification failed the desired level.
						raise portage_exception.UntrustedSignature, "Untrusted Manifest: %(manifest)s" % {"manifest":myManifestPath}

				if ("severe" in self.mysettings.features) and \
				   (mys != portage_gpg.fileStats(myManifestPath)):
					raise portage_exception.SecurityViolation, "Manifest changed: %(manifest)s" % {"manifest":myManifestPath}

			except portage_exception.InvalidSignature, e:
				if ("strict" in self.mysettings.features) or \
				   ("severe" in self.mysettings.features):
					raise
				writemsg("!!! INVALID MANIFEST SIGNATURE DETECTED: %(manifest)s\n" % {"manifest":myManifestPath})
			except portage_exception.MissingSignature, e:
				if ("severe" in self.mysettings.features):
					raise
				if ("strict" in self.mysettings.features):
					if myManifestPath not in self.manifestMissingCache:
						writemsg("!!! WARNING: Missing signature in: %(manifest)s\n" % {"manifest":myManifestPath})
						self.manifestMissingCache.insert(0,myManifestPath)
			except (OSError,portage_exception.FileNotFound), e:
				if ("strict" in self.mysettings.features) or \
				   ("severe" in self.mysettings.features):
					raise portage_exception.SecurityViolation, "Error in verification of signatures: %(errormsg)s" % {"errormsg":str(e)}
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

			if self.tmpfs:
				mydbkey = self.tmpfs+"/aux_db_key_temp"
			else:
				mydbkey = self.depcachedir+"/aux_db_key_temp"

			if self.lock_held:
				raise "Lock is already held by me?"
			self.lock_held = 1
			mylock = portage_locks.lockfile(mydbkey, wantnewlockfile=1)

			if os.path.exists(mydbkey):
				try:
					os.unlink(mydbkey)
				except (IOError, OSError), e:
					portage_locks.unlockfile(mylock)
					self.lock_held = 0
					writemsg("Uncaught handled exception: %(exception)s\n" % {"exception":str(e)})
					raise

			self.doebuild_settings.reset()
			myret = doebuild(myebuild, "depend", "/", self.doebuild_settings,
				dbkey=mydbkey, tree="porttree", mydbapi=self)
			if myret:
				portage_locks.unlockfile(mylock)
				self.lock_held = 0
				#depend returned non-zero exit code...
				writemsg(str(red("\naux_get():")+" (0) Error in "+mycpv+" ebuild. ("+str(myret)+")\n"
				"               Check for syntax error or corruption in the ebuild. (--debug)\n\n"),
					noiselevel=-1)
				raise KeyError

			try:
				mycent=open(mydbkey,"r")
				os.unlink(mydbkey)
				mylines=mycent.readlines()
				mycent.close()

			except (IOError, OSError):
				portage_locks.unlockfile(mylock)
				self.lock_held = 0
				writemsg(str(red("\naux_get():")+" (1) Error in "+mycpv+" ebuild.\n"
				  "               Check for syntax error or corruption in the ebuild. (--debug)\n\n"),
				  noiselevel=-1)
				raise KeyError

			portage_locks.unlockfile(mylock)
			self.lock_held = 0

			mydata = {}
			for x in range(0,len(mylines)):
				if mylines[x][-1] == '\n':
					mylines[x] = mylines[x][:-1]
				mydata[auxdbkeys[x]] = mylines[x]

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

		#finally, we look at our internal cache entry and return the requested data.
		returnme = []
		for x in mylist:
			if x == "INHERITED":
				returnme.append(' '.join(mydata.get("_eclasses_", {}).keys()))
			else:
				returnme.append(mydata.get(x,""))

		if "EAPI" in mylist:
			idx = mylist.index("EAPI")
			if not returnme[idx]:
				returnme[idx] = "0"

		return returnme

	def getfetchlist(self, mypkg, useflags=None, mysettings=None, all=0, mytree=None):
		if mysettings is None:
			mysettings = self.mysettings
		try:
			myuris = self.aux_get(mypkg, ["SRC_URI"], mytree=mytree)[0]
		except (IOError,KeyError):
			print red("getfetchlist():")+" aux_get() error reading "+mypkg+"; aborting."
			sys.exit(1)

		if useflags is None:
			useflags = string.split(mysettings["USE"])

		myurilist = portage_dep.paren_reduce(myuris)
		myurilist = portage_dep.use_reduce(myurilist,uselist=useflags,matchall=all)
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
					ok, reason = portage_checksum.verify_all(
						os.path.join(self.mysettings["DISTDIR"], x), mysums[x])
				except portage_exception.FileNotFound, e:
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
				if x[-7:]==".ebuild":
					d[mysplit[0]+"/"+x[:-7]] = None
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
				return self.xcache[level][origdep]
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
			myval=match_from_list(mydep,self.xmatch("list-visible",None,mydep=mydep,mykey=mykey))
			#get all visible packages, then get the matching ones
		elif level=="match-all":
			#match *all* visible *and* masked packages
			myval=match_from_list(mydep,self.cp_list(mykey))
		else:
			print "ERROR: xmatch doesn't handle",level,"query!"
			raise KeyError
		if self.frozen and (level not in ["match-list","bestmatch-list"]):
			self.xcache[level][mydep]=myval
		return myval

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

		pkgdict = self.mysettings.pkeywordsdict
		for mycpv in mylist:
			#we need to update this next line when we have fully integrated the new db api
			auxerr=0
			keys = None
			try:
				keys, eapi = self.aux_get(mycpv, ["KEYWORDS", "EAPI"])
			except KeyError:
				pass
			except portage_exception.PortageException, e:
				writemsg("!!! Error: aux_get('%s', ['KEYWORDS', 'EAPI'])\n" % mycpv,
					noiselevel=-1)
				writemsg("!!! %s\n" % str(e),
					noiselevel=-1)
			if not keys:
				# KEYWORDS=""
				#print "!!! No KEYWORDS for "+str(mycpv)+" -- Untested Status"
				continue
			mygroups=keys.split()
			# Repoman may modify this attribute as necessary.
			pgroups = self.mysettings["ACCEPT_KEYWORDS"].split()
			match=0
			cp = dep_getkey(mycpv)
			if pkgdict.has_key(cp):
				matches = match_to_list(mycpv, pkgdict[cp].keys())
				for atom in matches:
					pgroups.extend(pkgdict[cp][atom])
			hasstable = False
			hastesting = False
			for gp in mygroups:
				if gp=="*":
					writemsg("--- WARNING: Package '%s' uses '*' keyword.\n" % mycpv,
						noiselevel=-1)
					match=1
					break
				elif "-"+gp in pgroups:
					match=0
					break
				elif gp in pgroups:
					match=1
					break
				elif gp[0] == "~":
					hastesting = True
				elif gp[0] != "-":
					hasstable = True
			if not match and ((hastesting and "~*" in pgroups) or (hasstable and "*" in pgroups)):
				match=1
			if match and eapi_is_supported(eapi):
				newlist.append(mycpv)
		return newlist

class binarytree(packagetree):
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
			self.pkgdir=pkgdir
			self.dbapi = bindbapi(self, settings=settings)
			self.populated=0
			self.tree={}
			self.remotepkgs={}
			self.invalids=[]
			self.settings = settings

	def move_ent(self,mylist):
		if not self.populated:
			self.populate()
		origcp=mylist[1]
		newcp=mylist[2]
		# sanity check
		for cp in [origcp,newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise portage_exception.InvalidPackageName(cp)
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

			mytbz2 = xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			updated_items = update_dbentries([mylist], mydata)
			mydata.update(updated_items)
			mydata["CATEGORY"] = mynewcat+"\n"
			if mynewpkg != myoldpkg:
				mydata[mynewpkg+".ebuild"] = mydata[myoldpkg+".ebuild"]
				del mydata[myoldpkg+".ebuild"]
			mytbz2.recompose_mem(xpak.xpak_mem(mydata))

			self.dbapi.cpv_remove(mycpv)
			if (mynewpkg != myoldpkg):
				os.rename(tbz2path,self.getname(mynewcpv))
			self.dbapi.cpv_inject(mynewcpv)

			# remove the old symlink and category directory, then create
			# the new ones.
			try:
				os.unlink(os.path.join(self.pkgdir, origcat, myoldpkg) + ".tbz2")
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
			try:
				os.rmdir(os.path.join(self.pkgdir, origcat))
			except OSError, e:
				if e.errno not in (errno.ENOENT, errno.ENOTEMPTY):
					raise
			try:
				os.makedirs(os.path.join(self.pkgdir, mynewcat))
			except OSError, e:
				if e.errno != errno.EEXIST:
					raise
			try:
				os.unlink(os.path.join(self.pkgdir, mynewcat, mynewpkg) + ".tbz2")
			except OSError, e:
				if e.errno != errno.ENOENT:
					raise
			os.symlink(os.path.join("..", "All", mynewpkg) + ".tbz2",
				os.path.join(self.pkgdir, mynewcat, mynewpkg) + ".tbz2")
		return 1

	def move_slot_ent(self, mylist):
		if not self.populated:
			self.populate()
		pkg=mylist[1]
		origslot=mylist[2]
		newslot=mylist[3]
		
		if not isvalidatom(pkg):
			raise portage_exception.InvalidAtom(pkg)
		
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
			mytbz2 = xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()

			slot = mydata["SLOT"]
			if (not slot):
				continue

			if (slot[0]!=origslot):
				continue

			writemsg_stdout("S")
			mydata["SLOT"] = newslot+"\n"
			mytbz2.recompose_mem(xpak.xpak_mem(mydata))
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
			mytbz2 = xpak.tbz2(tbz2path)
			mydata = mytbz2.get_data()
			updated_items = update_dbentries(update_iter, mydata)
			if len(updated_items) > 0:
				mydata.update(updated_items)
				mytbz2.recompose_mem(xpak.xpak_mem(mydata))
		return 1

	def populate(self, getbinpkgs=0,getbinpkgsonly=0):
		"populates the binarytree"
		if (not os.path.isdir(self.pkgdir) and not getbinpkgs):
			return 0
		if (not os.path.isdir(self.pkgdir+"/All") and not getbinpkgs):
			return 0

		if (not getbinpkgsonly) and os.path.exists(self.pkgdir+"/All"):
			for mypkg in listdir(self.pkgdir+"/All"):
				if mypkg[-5:]!=".tbz2":
					continue
				mytbz2=xpak.tbz2(self.pkgdir+"/All/"+mypkg)
				mycat=mytbz2.getfile("CATEGORY")
				if not mycat:
					#old-style or corrupt package
					writemsg("!!! Invalid binary package: "+mypkg+"\n",
						noiselevel=-1)
					writemsg("!!! This binary package is not recoverable and should be deleted.\n",
						noiselevel=-1)
					self.invalids.append(mypkg)
					continue
				mycat=string.strip(mycat)
				fullpkg=mycat+"/"+mypkg[:-5]
				mykey=dep_getkey(fullpkg)
				try:
					# invalid tbz2's can hurt things.
					self.dbapi.cpv_inject(fullpkg)
				except SystemExit, e:
					raise
				except:
					continue

		if getbinpkgs and not self.settings["PORTAGE_BINHOST"]:
			writemsg(red("!!! PORTAGE_BINHOST unset, but use is requested.\n"),
				noiselevel=-1)

		if getbinpkgs and \
			self.settings["PORTAGE_BINHOST"] and not self.remotepkgs:
			try:
				chunk_size = long(self.settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except SystemExit, e:
				raise
			except:
				chunk_size = 3000

			writemsg(green("Fetching binary packages info...\n"))
			self.remotepkgs = getbinpkg.dir_get_metadata(
				self.settings["PORTAGE_BINHOST"], chunk_size=chunk_size)
			writemsg(green("  -- DONE!\n\n"))

			for mypkg in self.remotepkgs.keys():
				if not self.remotepkgs[mypkg].has_key("CATEGORY"):
					#old-style or corrupt package
					writemsg("!!! Invalid remote binary package: "+mypkg+"\n",
						noiselevel=-1)
					del self.remotepkgs[mypkg]
					continue
				mycat=string.strip(self.remotepkgs[mypkg]["CATEGORY"])
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
		"returns file location for this particular package"
		mysplit=string.split(pkgname,"/")
		if len(mysplit)==1:
			return self.pkgdir+"/All/"+self.resolve_specific(pkgname)+".tbz2"
		else:
			return self.pkgdir+"/All/"+mysplit[1]+".tbz2"

	def isremote(self,pkgname):
		"Returns true if the package is kept remotely."
		mysplit=string.split(pkgname,"/")
		remote = (not os.path.exists(self.getname(pkgname))) and self.remotepkgs.has_key(mysplit[1]+".tbz2")
		return remote

	def get_use(self,pkgname):
		mysplit=string.split(pkgname,"/")
		if self.isremote(pkgname):
			return string.split(self.remotepkgs[mysplit[1]+".tbz2"]["USE"][:])
		tbz2=xpak.tbz2(self.getname(pkgname))
		return string.split(tbz2.getfile("USE"))

	def gettbz2(self,pkgname):
		"fetches the package from a remote site, if necessary."
		print "Fetching '"+str(pkgname)+"'"
		mysplit  = string.split(pkgname,"/")
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
		except SystemExit, e:
			raise
		except:
			pass
		return getbinpkg.file_get(
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

class config_protect(object):
	def __init__(self, myroot, protect_list, mask_list):
		self.myroot = myroot
		self.protect_list = protect_list
		self.mask_list = mask_list
		self.updateprotect()

	def updateprotect(self):
		#do some config file management prep
		self.protect = []
		for x in self.protect_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep))) + os.path.sep
			if os.path.isdir(ppath):
				self.protect.append(ppath)

		self.protectmask = []
		for x in self.mask_list:
			ppath = normalize_path(
				os.path.join(self.myroot, x.lstrip(os.path.sep))) + os.path.sep
			if os.path.isdir(ppath):
				self.protectmask.append(ppath)
			#if it doesn't exist, silently skip it

	def isprotected(self,obj):
		"""Checks if obj is in the current protect/mask directories. Returns
		0 on unprotected/masked, and 1 on protected."""
		masked=0
		protected=0
		for ppath in self.protect:
			if len(ppath) > masked and obj.startswith(ppath):
				protected=len(ppath)
				#config file management
				for pmpath in self.protectmask:
					if len(pmpath) >= protected and obj.startswith(pmpath):
						#skip, it's in the mask
						masked=len(pmpath)
		return (protected > masked)

class dblink:
	"this class provides an interface to the standard text package database"
	def __init__(self, cat, pkg, myroot, mysettings, treetype=None,
		vartree=None):
		"create a dblink object for cat/pkg.  This dblink entry may or may not exist"
		self.cat     = cat
		self.pkg     = pkg
		self.mycpv   = self.cat+"/"+self.pkg
		self.mysplit = pkgsplit(self.mycpv)
		self.treetype = treetype
		if vartree is None:
			global db
			vartree = db[myroot]["vartree"]
		self.vartree = vartree

		self.dbroot   = os.path.normpath(myroot+VDB_PATH)
		self.dbcatdir = self.dbroot+"/"+cat
		self.dbpkgdir = self.dbcatdir+"/"+pkg
		self.dbtmpdir = self.dbcatdir+"/-MERGING-"+pkg
		self.dbdir    = self.dbpkgdir

		self.lock_pkg = None
		self.lock_tmp = None
		self.lock_num = 0    # Count of the held locks on the db.

		self.settings = mysettings
		if self.settings==1:
			raise ValueError

		self.myroot=myroot
		protect_obj = config_protect(myroot,
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split())
		self.updateprotect = protect_obj.updateprotect
		self.isprotected = protect_obj.isprotected
		self.contentscache=[]

	def lockdb(self):
		if self.lock_num == 0:
			self.lock_pkg = portage_locks.lockdir(self.dbpkgdir)
			self.lock_tmp = portage_locks.lockdir(self.dbtmpdir)
		self.lock_num += 1

	def unlockdb(self):
		self.lock_num -= 1
		if self.lock_num == 0:
			portage_locks.unlockdir(self.lock_tmp)
			portage_locks.unlockdir(self.lock_pkg)

	def getpath(self):
		"return path to location of db information (for >>> informational display)"
		return self.dbdir

	def exists(self):
		"does the db entry exist?  boolean."
		return os.path.exists(self.dbdir)

	def create(self):
		"create the skeleton db directory structure.  No contents, virtuals, provides or anything.  Also will create /var/db/pkg if necessary."
		# XXXXX Delete this eventually
		raise Exception, "This is bad. Don't use it."
		if not os.path.exists(self.dbdir):
			os.makedirs(self.dbdir)

	def delete(self):
		"erase this db entry completely"
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
		if os.path.exists(self.dbdir+"/CONTENTS"):
			os.unlink(self.dbdir+"/CONTENTS")

	def getcontents(self):
		if not os.path.exists(self.dbdir+"/CONTENTS"):
			return None
		if self.contentscache != []:
			return self.contentscache
		pkgfiles={}
		myc=open(self.dbdir+"/CONTENTS","r")
		mylines=myc.readlines()
		myc.close()
		pos=1
		for line in mylines:
			mydat = string.split(line)
			# we do this so we can remove from non-root filesystems
			# (use the ROOT var to allow maintenance on other partitions)
			try:
				mydat[1] = os.path.normpath(os.path.join(
					self.myroot, mydat[1].lstrip(os.path.sep)))
				if mydat[0]=="obj":
					#format: type, mtime, md5sum
					pkgfiles[string.join(mydat[1:-2]," ")]=[mydat[0], mydat[-1], mydat[-2]]
				elif mydat[0]=="dir":
					#format: type
					pkgfiles[string.join(mydat[1:])]=[mydat[0] ]
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
					pkgfiles[string.join(mydat[1:splitter]," ")]=[mydat[0], mydat[-1], string.join(mydat[(splitter+1):-1]," ")]
				elif mydat[0]=="dev":
					#format: type
					pkgfiles[string.join(mydat[1:]," ")]=[mydat[0] ]
				elif mydat[0]=="fif":
					#format: type
					pkgfiles[string.join(mydat[1:]," ")]=[mydat[0]]
				else:
					return None
			except (KeyError,IndexError):
				print "portage: CONTENTS line",pos,"corrupt!"
			pos += 1
		self.contentscache=pkgfiles
		return pkgfiles

	def unmerge(self, pkgfiles=None, trimworld=1, cleanup=1,
		ldpath_mtimes=None):
		global dircache
		dircache={}

		self.lockdb()

		self.settings.load_infodir(self.dbdir)

		if not pkgfiles:
			print "No package files given... Grabbing a set."
			pkgfiles=self.getcontents()

		# Now, don't assume that the name of the ebuild is the same as the
		# name of the dir; the package may have been moved.
		myebuildpath=None

		# We should use the environement file if possible,
		# as it has all sourced files already included.
		# XXX: Need to ensure it doesn't overwrite any important vars though.
		if os.access(self.dbdir+"/environment.bz2", os.R_OK):
			spawn("bzip2 -d "+self.dbdir+"/environment.bz2",self.settings,free=1)

		if not myebuildpath:
			mystuff=listdir(self.dbdir,EmptyOnError=1)
			for x in mystuff:
				if x[-7:]==".ebuild":
					myebuildpath=self.dbdir+"/"+x
					break

		#do prerm script
		if myebuildpath and os.path.exists(myebuildpath):
			# Eventually, we'd like to pass in the saved ebuild env here...
			a = doebuild(myebuildpath, "prerm", self.myroot, self.settings,
				cleanup=cleanup, use_cache=0, tree="vartree",
				mydbapi=self.vartree.dbapi, vartree=self.vartree)
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED prerm: "+str(a)+"\n", noiselevel=-1)
				sys.exit(123)

		if pkgfiles:
			mykeys=pkgfiles.keys()
			mykeys.sort()
			mykeys.reverse()

			self.updateprotect()

			#process symlinks second-to-last, directories last.
			mydirs=[]
			modprotect="/lib/modules/"
			for objkey in mykeys:
				obj=os.path.normpath(objkey)
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
				if self.isprotected(obj) or ((len(obj) > len(modprotect)) and (obj[0:len(modprotect)]==modprotect)):
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
						mymd5 = portage_checksum.perform_md5(obj, calc_prelink=1)
					except portage_exception.FileNotFound, e:
						# the file has disappeared between now and our stat call
						writemsg_stdout("--- !obj   %s %s\n" % ("obj", obj))
						continue

					# string.lower is needed because db entries used to be in upper-case.  The
					# string.lower allows for backwards compatibility.
					if mymd5 != string.lower(pkgfiles[objkey][2]):
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
			last_non_empty = ""

			for obj in mydirs:
				if not last_non_empty.startswith(obj) and not listdir(obj):
					try:
						os.rmdir(obj)
						writemsg_stdout("<<<        %s %s\n" % ("dir",obj))
						last_non_empty = ""
						continue
					except (OSError,IOError),e:
						#immutable?
						pass

				writemsg_stdout("--- !empty dir %s\n" % obj)
				last_non_empty = obj
				continue

		#remove self from vartree database so that our own virtual gets zapped if we're the last node
		self.vartree.zap(self.mycpv)

		# New code to remove stuff from the world and virtuals files when unmerged.
		if trimworld:
			worldlist = grabfile(os.path.join(self.myroot, WORLD_FILE))
			mykey=cpv_getkey(self.mycpv)
			newworldlist=[]
			for x in worldlist:
				if dep_getkey(x)==mykey:
					matches = self.vartree.dbapi.match(x,use_cache=0)
					if not matches:
						#zap our world entry
						pass
					elif (len(matches)==1) and (matches[0]==self.mycpv):
						#zap our world entry
						pass
					else:
						#others are around; keep it.
						newworldlist.append(x)
				else:
					#this doesn't match the package we're unmerging; keep it.
					newworldlist.append(x)

			# if the base dir doesn't exist, create it.
			# (spanky noticed bug)
			# XXX: dumb question, but abstracting the root uid might be wise/useful for
			# 2nd pkg manager installation setups.
			my_private_path = os.path.join(self.myroot, PRIVATE_PATH)
			if not os.path.exists(my_private_path):
				os.makedirs(my_private_path, mode=0755)
				os.chown(my_private_path, 0, portage_gid)
				os.chmod(my_private_path, 02770)

			write_atomic(os.path.join(self.myroot, WORLD_FILE),
			"\n".join(newworldlist))

		#do original postrm
		if myebuildpath and os.path.exists(myebuildpath):
			# XXX: This should be the old config, not the current one.
			# XXX: Use vardbapi to load up env vars.
			a = doebuild(myebuildpath, "postrm", self.myroot, self.settings,
			 use_cache=0, tree="vartree", mydbapi=self.vartree.dbapi,
			 vartree=self.vartree)
			
			# process logs created during pre/postrm
			elog_process(self.mycpv, self.settings)
			
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED postrm: "+str(a)+"\n", noiselevel=-1)
				sys.exit(123)
			doebuild(myebuildpath, "cleanrm", self.myroot, self.settings,
				tree="vartree", mydbapi=self.vartree.dbapi,
				vartree=self.vartree)
		self.unlockdb()
		env_update(target_root=self.myroot, prev_mtimes=ldpath_mtimes)

	def isowner(self,filename,destroot):
		""" check if filename is a new file or belongs to this package
		(for this or a previous version)"""
		destfile = os.path.normpath(destroot+"/"+filename)
		if not os.path.exists(destfile):
			return True
		if self.getcontents() and filename in self.getcontents().keys():
			return True

		return False

	def treewalk(self, srcroot, destroot, inforoot, myebuild, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		# srcroot  = ${D};
		# destroot = where to merge, ie. ${ROOT},
		# inforoot = root of db entry,
		# secondhand = list of symlinks that have been skipped due to
		#              their target not existing (will merge later),

		if not os.path.exists(self.dbcatdir):
			os.makedirs(self.dbcatdir)

		# This blocks until we can get the dirs to ourselves.
		self.lockdb()

		otherversions=[]
		for v in self.vartree.dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		# check for package collisions
		if "collision-protect" in self.settings.features:
			myfilelist = listdir(srcroot, recursive=1, filesonly=1, followSymlinks=False)

			# the linkcheck only works if we are in srcroot
			mycwd = os.getcwd()
			os.chdir(srcroot)
			mysymlinks = filter(os.path.islink, listdir(srcroot, recursive=1, filesonly=0, followSymlinks=False))
			myfilelist.extend(mysymlinks)

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

			print green("*")+" checking "+str(len(myfilelist))+" files for package collisions"
			for f in myfilelist:
				nocheck = False
				# listdir isn't intelligent enough to exclude symlinked dirs,
				# so we have to do it ourself
				for s in mysymlinks:
					# the length comparison makes sure that the symlink itself is checked
					if f[:len(s)] == s and len(f) > len(s):
						nocheck = True
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
					print "existing file "+f+" is not owned by this package"
					stopmerge=True
			print green("*")+" spent "+str(time.time()-starttime)+" seconds checking for file collisions"
			if stopmerge:
				print red("*")+" This package is blocked because it wants to overwrite"
				print red("*")+" files belonging to other packages (see messages above)."
				print red("*")+" If you have no clue what this is all about report it "
				print red("*")+" as a bug for this package on http://bugs.gentoo.org"
				print
				print red("package "+self.cat+"/"+self.pkg+" NOT merged")
				print
				# Why is the package already merged here db-wise? Shouldn't be the case
				# only unmerge if it ia new package and has no contents
				if not self.getcontents():
					self.unmerge(ldpath_mtimes=prev_mtimes)
					self.delete()
				self.unlockdb()
				sys.exit(1)
			try:
				os.chdir(mycwd)
			except SystemExit, e:
				raise
			except:
				pass


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
		if a != 0:
			writemsg("!!! FAILED preinst: "+str(a)+"\n", noiselevel=-1)
			sys.exit(123)

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
		cfgfiledict = grabdict(os.path.join(destroot, CONFIG_MEMORY_FILE))
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

		self.unlockdb()

		#write out our collection of md5sums
		if cfgfiledict.has_key("IGNORE"):
			del cfgfiledict["IGNORE"]

		my_private_path = os.path.join(destroot, PRIVATE_PATH)
		if not os.path.exists(my_private_path):
			os.makedirs(my_private_path)
			os.chown(my_private_path, os.getuid(), portage_gid)
			os.chmod(my_private_path, 02770)

		mylock = portage_locks.lockfile(
			os.path.join(destroot, CONFIG_MEMORY_FILE), wantnewlockfile=1)
		writedict(cfgfiledict, os.path.join(destroot, CONFIG_MEMORY_FILE))
		portage_locks.unlockfile(mylock)

		#do postinst script
		a = doebuild(myebuild, "postinst", destroot, self.settings, use_cache=0,
			tree=self.treetype, mydbapi=mydbapi, vartree=self.vartree)

		# XXX: Decide how to handle failures here.
		if a != 0:
			writemsg("!!! FAILED postinst: "+str(a)+"\n", noiselevel=-1)
			sys.exit(123)

		downgrade = False
		for v in otherversions:
			if pkgcmp(catpkgsplit(self.pkg)[1:], catpkgsplit(v)[1:]) < 0:
				downgrade = True

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=(not downgrade),
			target_root=self.settings["ROOT"], prev_mtimes=prev_mtimes)
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
		return 0

	def mergeme(self,srcroot,destroot,outfile,secondhand,stufftomerge,cfgfiledict,thismtime):
		from os.path import sep, normpath, join
		srcroot = normpath(3*sep + srcroot).rstrip(sep) + sep
		destroot = normpath(3*sep + destroot).rstrip(sep) + sep
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if type(stufftomerge)==types.StringType:
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist = listdir(join(srcroot, stufftomerge))
			offset=stufftomerge
			# We need mydest defined up here to calc. protection paths.  This is now done once per
			# directory rather than once per file merge.  This should really help merge performance.
			# Trailing / ensures that protects/masks with trailing /'s match.
			mytruncpath = join(destroot, offset).rstrip(sep) + sep
			myppath=self.isprotected(mytruncpath)
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
			except SystemExit, e:
				raise
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
					if myabsto[0]!="/":
						myabsto="/"+myabsto
				myto=os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.startswith(self.settings["D"]):
						myto=myto[len(self.settings["D"]):]
				# myrealto contains the path of the real file to which this symlink points.
				# we can simply test for existence of this file to see if the target has been merged yet
				myrealto=os.path.normpath(os.path.join(destroot,myabsto))
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
							if os.path.exists(os.path.normpath(srcroot+myabsto)):
								mydest = new_protect_filename(mydest,
									newmd5=portage_checksum.perform_md5(srcroot+myabsto))
							else:
								mydest = new_protect_filename(mydest,
									newmd5=portage_checksum.perform_md5(myabsto))

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
					print ">>>",mydest,"->",myto
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
						dflags=bsd_chflags.lgetflags(mydest)
						if dflags != 0 and bsd_chflags.lchflags(mydest, 0) < 0:
							writemsg("!!! Couldn't clear flags on '"+mydest+"'.\n",
								noiselevel=-1)

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
					if bsd_chflags:
						bsd_chflags.lchflags(mydest, bsd_chflags.lgetflags(mysrc))
					os.chown(mydest,mystat[4],mystat[5])
					writemsg_stdout(">>> %s/\n" % mydest)
				outfile.write("dir "+myrealdest+"\n")
				# recurse and merge this directory
				if self.mergeme(srcroot, destroot, outfile, secondhand,
					join(offset, x), cfgfiledict, thismtime):
					return 1
			elif stat.S_ISREG(mymode):
				# we are merging a regular file
				mymd5=portage_checksum.perform_md5(mysrc,calc_prelink=1)
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
						if myppath:
							# we have a protection path; enable config file management.
							destmd5=portage_checksum.perform_md5(mydest,calc_prelink=1)
							cycled=0
							if cfgfiledict.has_key(myrealdest):
								if destmd5 in cfgfiledict[myrealdest]:
									#cycle
									print "cycle"
									del cfgfiledict[myrealdest]
									cycled=1
							if mymd5==destmd5:
								#file already in place; simply update mtimes of destination
								os.utime(mydest,(thismtime,thismtime))
								zing="---"
								moveme=0
							elif cycled:
								#mymd5!=destmd5 and we've cycled; move mysrc into place as a ._cfg file
								moveme=1
								cfgfiledict[myrealdest]=[mymd5]
								cfgprot=1
							elif cfgfiledict.has_key(myrealdest) and (mymd5 in cfgfiledict[myrealdest]):
								#myd5!=destmd5, we haven't cycled, and the file we're merging has been already merged previously
								zing="-o-"
								moveme=cfgfiledict["IGNORE"]
								cfgprot=cfgfiledict["IGNORE"]
							else:
								#mymd5!=destmd5, we haven't cycled, and the file we're merging hasn't been merged before
								moveme=1
								cfgprot=1
								if not cfgfiledict.has_key(myrealdest):
									cfgfiledict[myrealdest]=[]
								if mymd5 not in cfgfiledict[myrealdest]:
									cfgfiledict[myrealdest].append(mymd5)
								# only record the last md5
								if len(cfgfiledict[myrealdest])>1:
									del cfgfiledict[myrealdest][0]
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
						mymd5 = portage_checksum.perform_md5(mydest, calc_prelink=1)
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
						if stat.S_ISFIFO(mymode):
							# we don't record device nodes in CONTENTS,
							# although we do merge them.
							outfile.write("fif "+myrealdest+"\n")
					else:
						sys.exit(1)
				writemsg_stdout(zing+" "+mydest+"\n")

	def merge(self, mergeroot, inforoot, myroot, myebuild=None, cleanup=0,
		mydbapi=None, prev_mtimes=None):
		return self.treewalk(mergeroot, myroot, inforoot, myebuild,
			cleanup=cleanup, mydbapi=mydbapi, prev_mtimes=prev_mtimes)

	def getstring(self,name):
		"returns contents of a file with whitespace converted to spaces"
		if not os.path.exists(self.dbdir+"/"+name):
			return ""
		myfile=open(self.dbdir+"/"+name,"r")
		mydata=string.split(myfile.read())
		myfile.close()
		return string.join(mydata," ")

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
			for y in string.split(x[:-1]):
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
	to allow portage_manifest.Manifest to access fetch lists via a standard
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

def cleanup_pkgmerge(mypkg, origdir, settings=None):
	if settings is None:
		settings = globals()["settings"]
	shutil.rmtree(settings["PORTAGE_TMPDIR"]+"/binpkgs/"+mypkg)
	if os.path.exists(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment"):
		os.unlink(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment")
	os.chdir(origdir)

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
		return None
	mypkg=os.path.basename(mytbz2)[:-5]
	xptbz2=xpak.tbz2(mytbz2)
	pkginfo={}
	mycat=xptbz2.getfile("CATEGORY")
	if not mycat:
		print "!!! CATEGORY info missing from info chunk, aborting..."
		return None
	mycat=mycat.strip()
	mycatpkg=mycat+"/"+mypkg
	tmploc=mysettings["PORTAGE_TMPDIR"]+"/binpkgs/"
	pkgloc=tmploc+"/"+mypkg+"/bin/"
	infloc=tmploc+"/"+mypkg+"/inf/"
	myebuild=tmploc+"/"+mypkg+"/inf/"+os.path.basename(mytbz2)[:-4]+"ebuild"
	if os.path.exists(tmploc+"/"+mypkg):
		shutil.rmtree(tmploc+"/"+mypkg,1)
	os.makedirs(pkgloc)
	os.makedirs(infloc)
	writemsg_stdout(">>> Extracting info\n")
	xptbz2.unpackinfo(infloc)
	# run pkg_setup early, so we can bail out early
	# (before extracting binaries) if there's a problem
	origdir=getcwd()
	os.chdir(pkgloc)

	mysettings.configdict["pkg"]["CATEGORY"] = mycat;
	# Eventually we'd like to pass in the saved ebuild env here.
	# Do cleanup=1 to ensure that there is no cruft prior to the setup phase.
	a = doebuild(myebuild, "setup", myroot, mysettings, tree="bintree",
		cleanup=1, mydbapi=mydbapi, vartree=vartree)
	writemsg_stdout(">>> Extracting %s\n" % mypkg)
	notok=spawn("bzip2 -dqc -- '"+mytbz2+"' | tar xpf -",mysettings,free=1)
	if notok:
		print "!!! Error Extracting",mytbz2
		cleanup_pkgmerge(mypkg, origdir, settings=mysettings)
		return None

	# the merge takes care of pre/postinst and old instance
	# auto-unmerge, virtual/provides updates, etc.
	mysettings.load_infodir(infloc)
	mylink = dblink(mycat, mypkg, myroot, mysettings, vartree=vartree,
		treetype="bintree")
	mylink.merge(pkgloc, infloc, myroot, myebuild, cleanup=1, mydbapi=mydbapi,
		prev_mtimes=prev_mtimes)

	if not os.path.exists(infloc+"/RDEPEND"):
		returnme=""
	else:
		#get runtime dependencies
		a=open(infloc+"/RDEPEND","r")
		returnme=string.join(string.split(a.read())," ")
		a.close()
	cleanup_pkgmerge(mypkg, origdir, settings=mysettings)
	return returnme

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

def parse_updates(mycontent):
	"""Valid updates are returned as a list of split update commands."""
	myupd = []
	errors = []
	mylines = mycontent.splitlines()
	for myline in mylines:
		mysplit = myline.split()
		if len(mysplit) == 0:
			continue
		if mysplit[0] not in ("move", "slotmove"):
			errors.append("ERROR: Update type not recognized '%s'" % myline)
			continue
		if mysplit[0]=="move":
			if len(mysplit)!=3:
				errors.append("ERROR: Update command invalid '%s'" % myline)
				continue
			orig_value, new_value = mysplit[1], mysplit[2]
			for cp in (orig_value, new_value):
				if not (isvalidatom(cp) and isjustname(cp)):
					errors.append("ERROR: Malformed update entry '%s'" % myline)
					continue
		if mysplit[0]=="slotmove":
			if len(mysplit)!=4:
				errors.append("ERROR: Update command invalid '%s'" % myline)
				continue
			pkg, origslot, newslot = mysplit[1], mysplit[2], mysplit[3]
			if not isvalidatom(pkg):
				errors.append("ERROR: Malformed update entry '%s'" % myline)
				continue
		
		# The list of valid updates is filtered by continue statements above.
		myupd.append(mysplit)
	return myupd, errors

def commit_mtimedb(mydict=None, filename=None):
	if mydict is None:
		global mtimedb
		if "mtimedb" not in globals() or mtimedb is None:
			return
		mydict = mtimedb
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
		portage_util.apply_secpass_permissions(filename, uid=uid, gid=portage_gid, mode=0664)
	except (IOError, OSError), e:
		pass

def portageexit():
	global uid,portage_gid,portdb,db
	if secpass and not os.environ.has_key("SANDBOX_ACTIVE"):
		close_portdbapi_caches()
		commit_mtimedb()

atexit_register(portageexit)

def update_config_files(config_root, protect, protect_mask, update_iter):
	"""Perform global updates on /etc/portage/package.* and the world file.
	config_root - location of files to update
	protect - list of paths from CONFIG_PROTECT
	protect_mask - list of paths from CONFIG_PROTECT_MASK
	update_iter - list of update commands as returned from parse_updates()"""
	update_files={}
	file_contents={}
	myxfiles = ["package.mask","package.unmask","package.keywords","package.use"]
	myxfiles.extend(prefix_array(myxfiles, "profile/"))
	abs_user_config = os.path.join(config_root,
		USER_CONFIG_PATH.lstrip(os.path.sep))
	recursivefiles = []
	for x in myxfiles:
		config_file = os.path.join(abs_user_config, x)
		if os.path.isdir(config_file):
			recursivefiles.extend([os.path.join(x, y) \
				for y in listdir(config_file, filesonly=1, recursive=1)])
		else:
			recursivefiles.append(x)
	myxfiles = recursivefiles
	for x in myxfiles:
		try:
			myfile = open(os.path.join(abs_user_config, x),"r")
			file_contents[x] = myfile.readlines()
			myfile.close()
		except IOError:
			if file_contents.has_key(x):
				del file_contents[x]
			continue
	worldlist = grabfile(os.path.join(config_root, WORLD_FILE))

	for update_cmd in update_iter:
		if update_cmd[0] == "move":
			old_value, new_value = update_cmd[1], update_cmd[2]
			#update world entries:
			for x in range(0,len(worldlist)):
				#update world entries, if any.
				worldlist[x] = dep_transform(worldlist[x], old_value, new_value)

			#update /etc/portage/packages.*
			for x in file_contents:
				for mypos in range(0,len(file_contents[x])):
					line = file_contents[x][mypos]
					if line[0] == "#" or string.strip(line) == "":
						continue
					key = dep_getkey(line.split()[0])
					if key == old_value:
						file_contents[x][mypos] = string.replace(line, old_value, new_value)
						update_files[x] = 1
						sys.stdout.write("p")
						sys.stdout.flush()

	write_atomic(os.path.join(config_root, WORLD_FILE), "\n".join(worldlist))

	protect_obj = config_protect(config_root, protect, protect_mask)
	for x in update_files:
		updating_file = os.path.join(abs_user_config, x)
		if protect_obj.isprotected(updating_file):
			updating_file = new_protect_filename(updating_file)[0]
		try:
			write_atomic(updating_file, "".join(file_contents[x]))
		except portage_exception.PortageException, e:
			writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
			writemsg("!!! An error occured while updating a config file:" + \
				" '%s'\n" % updating_file, noiselevel=-1)
			continue

def global_updates(mysettings, trees, prev_mtimes):
	"""Perform new global updates if they exist in $PORTDIR/profiles/updates/."""
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
	except portage_exception.DirectoryNotFound:
		writemsg("--- 'profiles/updates' is empty or not available. Empty portage tree?\n")
		return
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
				timestamps[mykey] = mystat.st_mtime
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

#continue setting up other trees
class LazyBintreeItem(object):
	"""This class implements lazy construction of db[root]["bintree"]."""
	def __init__(self, myroot, settings):
		self._myroot = myroot
		self._bintree = None
		self._settings = settings
	def __call__(self):
		if self._bintree is None:
			self._bintree = binarytree(self._myroot, self._settings["PKGDIR"],
				settings=self._settings)
			# The binarytree likely needs to be populated now, so we
			# do it now to make sure that all method calls are safe.
			self._bintree.populate()
		return self._bintree

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
		except (IOError, OSError, EOFError):
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
		d = {}
		d.update(self)
		# Only commit if the internal state has changed.
		if d != self._clean_data:
			commit_mtimedb(mydict=d, filename=self.filename)
			self._clean_data = copy.deepcopy(d)

def create_trees(config_root="/", target_root="/", trees=None):
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
		config_incrementals=portage_const.INCREMENTALS)

	settings.reset()
	settings.lock()
	settings.validate()

	myroots = [(settings["ROOT"], settings)]
	if settings["ROOT"] != "/":
		settings = config(config_root="/", target_root="/",
			config_incrementals=portage_const.INCREMENTALS)
		settings.reset()
		settings.lock()
		settings.validate()
		myroots.append(("/", settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage_util.LazyItemsDict(trees.get(myroot, None))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals, myroot)
		trees[myroot].addLazySingleton(
			"vartree", vartree, myroot, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, myroot, settings=mysettings)
		trees[myroot].addLazyItem("bintree",
			LazyBintreeItem(myroot, mysettings))
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

