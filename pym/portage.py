# portage.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage.py,v 1.524.2.76 2005/05/29 12:40:08 jstubbs Exp $


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
	import os,string,types,signal,fcntl,errno
	import time,traceback,copy
	import re,pwd,grp,commands
	import shlex,shutil
	try:
		import cPickle
	except ImportError:
		import pickle as cPickle

	import stat
	import commands
	from time import sleep
	from random import shuffle
	from cache.cache_errors import CacheError
except ImportError, e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. There are internal modules for\n")
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
	import cvstree
	import xpak
	import getbinpkg
	import portage_dep

	# XXX: This needs to get cleaned up.
	import output
	from output import blue, bold, brown, darkblue, darkgreen, darkred, darkteal, \
	  darkyellow, fuchsia, fuscia, green, purple, red, teal, turquoise, white, \
	  xtermTitle, xtermTitleReset, yellow

	import portage_const
	from portage_const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
	  USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
	  PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
	  EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
	  MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
	  DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
	  INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
	  INCREMENTALS, STICKIES, EAPI, MISC_SH_BINARY

	from portage_data import ostype, lchown, userland, secpass, uid, wheelgid, \
	                         portage_uid, portage_gid

	import portage_util
	from portage_util import atomic_ofstream, apply_secpass_permissions, \
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


# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================


def exithandler(signum,frame):
	"""Handles ^C interrupts in a sane manner"""
	signal.signal(signal.SIGINT, signal.SIG_IGN)
	signal.signal(signal.SIGTERM, signal.SIG_IGN)

	# 0=send to *everybody* in process group
	sys.exit(1)

signal.signal(signal.SIGCHLD, signal.SIG_DFL)
signal.signal(signal.SIGINT, exithandler)
signal.signal(signal.SIGTERM, exithandler)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

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
			raise portage_exception.PortageException
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
features=[]

def tokenize(mystring):
	"""breaks a string like 'foo? (bar) oni? (blah (blah))'
	into embedded lists; returns None on paren mismatch"""

	# This function is obsoleted.
	# Use dep_parenreduce

	newtokens=[]
	curlist=newtokens
	prevlists=[]
	level=0
	accum=""
	for x in mystring:
		if x=="(":
			if accum:
				curlist.append(accum)
				accum=""
			prevlists.append(curlist)
			curlist=[]
			level=level+1
		elif x==")":
			if accum:
				curlist.append(accum)
				accum=""
			if level==0:
				writemsg("!!! tokenizer: Unmatched left parenthesis in:\n'"+str(mystring)+"'\n")
				return None
			newlist=curlist
			curlist=prevlists.pop()
			curlist.append(newlist)
			level=level-1
		elif x in string.whitespace:
			if accum:
				curlist.append(accum)
				accum=""
		else:
			accum=accum+x
	if accum:
		curlist.append(accum)
	if (level!=0):
		writemsg("!!! tokenizer: Exiting with unterminated parenthesis in:\n'"+str(mystring)+"'\n")
		return None
	return newtokens

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
			if myparent==None:
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

# valid end of version components; integers specify offset from release version
# pre=prerelease, p=patchlevel (should always be followed by an int), rc=release candidate
# all but _p (where it is required) can be followed by an optional trailing integer

endversion={"pre":-2,"p":0,"alpha":-4,"beta":-3,"rc":-1}
# as there's no reliable way to set {}.keys() order
# netversion_keys will be used instead of endversion.keys
# to have fixed search order, so that "pre" is checked
# before "p"
endversion_keys = ["pre", "p", "alpha", "beta", "rc"]

#parse /etc/env.d and generate /etc/profile.env

def env_update(makelinks=1):
	global root
	if not os.path.exists(root+"etc/env.d"):
		prevmask=os.umask(0)
		os.makedirs(root+"etc/env.d",0755)
		os.umask(prevmask)
	fns=listdir(root+"etc/env.d",EmptyOnError=1)
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
		myconfig=getconfig(root+"etc/env.d/"+x)
		if myconfig==None:
			writemsg("!!! Parsing error in "+str(root)+"etc/env.d/"+str(x)+"\n")
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

	if os.path.exists(root+"etc/ld.so.conf"):
		myld=open(root+"etc/ld.so.conf")
		myldlines=myld.readlines()
		myld.close()
		oldld=[]
		for x in myldlines:
			#each line has at least one char (a newline)
			if x[0]=="#":
				continue
			oldld.append(x[:-1])
	#	os.rename(root+"etc/ld.so.conf",root+"etc/ld.so.conf.bak")
	# Where is the new ld.so.conf generated? (achim)
	else:
		oldld=None

	ld_cache_update=False

	newld=specials["LDPATH"]
	if (oldld!=newld):
		#ld.so.conf needs updating and ldconfig needs to be run
		myfd = atomic_ofstream(os.path.join(root, "etc", "ld.so.conf"))
		myfd.write("# ld.so.conf autogenerated by env-update; make all changes to\n")
		myfd.write("# contents of /etc/env.d directory\n")
		for x in specials["LDPATH"]:
			myfd.write(x+"\n")
		myfd.close()
		ld_cache_update=True

	# Update prelink.conf if we are prelink-enabled
	if prelink_capable:
		newprelink = atomic_ofstream(os.path.join(root, "etc", "prelink.conf"))
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

	if not mtimedb.has_key("ldpath"):
		mtimedb["ldpath"]={}

	for x in specials["LDPATH"]+['/usr/lib','/lib']:
		try:
			newldpathtime=os.stat(x)[stat.ST_MTIME]
		except SystemExit, e:
			raise
		except:
			newldpathtime=0
		if mtimedb["ldpath"].has_key(x):
			if mtimedb["ldpath"][x]==newldpathtime:
				pass
			else:
				mtimedb["ldpath"][x]=newldpathtime
				ld_cache_update=True
		else:
			mtimedb["ldpath"][x]=newldpathtime
			ld_cache_update=True

	# Only run ldconfig as needed
	if (ld_cache_update or makelinks):
		# ldconfig has very different behaviour between FreeBSD and Linux
		if ostype=="Linux" or ostype.lower().endswith("gnu"):
			# We can't update links if we haven't cleaned other versions first, as
			# an older package installed ON TOP of a newer version will cause ldconfig
			# to overwrite the symlinks we just made. -X means no links. After 'clean'
			# we can safely create links.
			writemsg(">>> Regenerating "+str(root)+"etc/ld.so.cache...\n")
			if makelinks:
				commands.getstatusoutput("cd / ; /sbin/ldconfig -r "+root)
			else:
				commands.getstatusoutput("cd / ; /sbin/ldconfig -X -r "+root)
		elif ostype in ("FreeBSD","DragonFly"):
			writemsg(">>> Regenerating "+str(root)+"var/run/ld-elf.so.hints...\n")
			commands.getstatusoutput("cd / ; /sbin/ldconfig -elf -i -f "+str(root)+"var/run/ld-elf.so.hints "+str(root)+"etc/ld.so.conf")

	del specials["LDPATH"]

	penvnotice  = "# THIS FILE IS AUTOMATICALLY GENERATED BY env-update.\n"
	penvnotice += "# DO NOT EDIT THIS FILE. CHANGES TO STARTUP PROFILES\n"
	cenvnotice  = penvnotice[:]
	penvnotice += "# GO INTO /etc/profile NOT /etc/profile.env\n\n"
	cenvnotice += "# GO INTO /etc/csh.cshrc NOT /etc/csh.env\n\n"

	#create /etc/profile.env for bash support
	outfile = atomic_ofstream(os.path.join(root, "etc", "profile.env"))
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
	outfile = atomic_ofstream(os.path.join(root, "etc", "csh.env"))
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
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, x))
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
			writemsg("--- Invalid atom in %s: %s\n" % (myfilename, pkgs[x]))
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


autouse_val = None
def autouse(myvartree,use_cache=1):
	"returns set of USE variables auto-enabled due to packages being installed"
	global usedefaults, autouse_val
	if autouse_val is not None:
		return autouse_val
	if profiledir==None:
		autouse_val = ""
		return ""
	myusevars=""
	for myuse in usedefaults:
		dep_met = True
		for mydep in usedefaults[myuse]:
			if not myvartree.dep_match(mydep,use_cache=True):
				dep_met = False
				break
		if dep_met:
			myusevars += " "+myuse
	autouse_val = myusevars
	return myusevars

def check_config_instance(test):
	if not test or (str(test.__class__) != 'portage.config'):
		raise TypeError, "Invalid type for config object: %s" % test.__class__

class config:
	def __init__(self, clone=None, mycpv=None, config_profile_path=None, config_incrementals=None):

		self.already_in_regenerate = 0

		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []

		self.virtuals = {}
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
		else:
			self.depcachedir = DEPCACHE_PATH

			if not config_profile_path:
				global profiledir
				writemsg("config_profile_path not specified to class config\n")
				self.profile_path = profiledir[:]
			else:
				self.profile_path = config_profile_path[:]

			if not config_incrementals:
				writemsg("incrementals not specified to class config\n")
				self.incrementals = copy.deepcopy(portage_const.INCREMENTALS)
			else:
				self.incrementals = copy.deepcopy(config_incrementals)

			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"]    = getconfig(MODULES_FILE_PATH)
			if self.modules["user"] == None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "cache.metadata.database",
				"portdbapi.auxdbmodule":  "cache.flat_hash.database",
			}

			self.usemask=[]
			self.configlist=[]
			self.backupenv={}
			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ globals, defaults, conf, pkg, auto, backupenv (incrementals), origenv ]

			# The symlink might not exist or might not be a symlink.
			try:
				self.profiles=[abssymlink(self.profile_path)]
			except SystemExit, e:
				raise
			except:
				self.profiles=[self.profile_path]

			mypath = self.profiles[0]
			while os.path.exists(mypath+"/parent"):
				mypath = os.path.normpath(mypath+"///"+grabfile(mypath+"/parent")[0])
				if os.path.exists(mypath):
					self.profiles.insert(0,mypath)

			if os.environ.has_key("PORTAGE_CALLER") and os.environ["PORTAGE_CALLER"] == "repoman":
				pass
			else:
				# XXX: This should depend on ROOT?
				if os.path.exists("/"+CUSTOM_PROFILE_PATH):
					self.user_profile_dir = os.path.normpath("/"+"///"+CUSTOM_PROFILE_PATH)
					self.profiles.append(self.user_profile_dir[:])

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
				mygcfg_dlists = [getconfig(os.path.join(x, "make.globals")) for x in self.profiles+["/etc"]]
				self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=portage_const.INCREMENTALS, ignore_none=1)

				if self.mygcfg == None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
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
					if self.mygcfg == None:
						self.mygcfg = {}
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! %s\n" % (e))
					writemsg("!!! 'rm -Rf /usr/portage/profiles; emerge sync' may fix this. If it does\n")
					writemsg("!!! not then please report this to bugs.gentoo.org and, if possible, a dev\n")
					writemsg("!!! on #gentoo (irc.freenode.org)\n")
					sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			try:
				# XXX: Should depend on root?
				self.mygcfg=getconfig("/"+MAKE_CONF_FILE,allow_sourcing=True)
				if self.mygcfg == None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
				sys.exit(1)


			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

			#backup-env (for recording our calculated incremental variables:)
			self.backupenv = os.environ.copy()
			self.configlist.append(self.backupenv) # XXX Why though?
			self.configdict["backupenv"]=self.configlist[-1]

			self.configlist.append(os.environ.copy())
			self.configdict["env"]=self.configlist[-1]


			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			if os.environ.get("PORTAGE_CALLER","") == "repoman":
				# repoman shouldn't use local settings.
				locations = [self["PORTDIR"] + "/profiles"]
				self.pusedict = {}
				self.pkeywordsdict = {}
				self.punmaskdict = {}
			else:
				locations = [self["PORTDIR"] + "/profiles", USER_CONFIG_PATH]
				for ov in self["PORTDIR_OVERLAY"].split():
					ov = os.path.normpath(ov)
					if os.path.isdir(ov+"/profiles"):
						locations.append(ov+"/profiles")

				pusedict=grabdict_package(USER_CONFIG_PATH+"/package.use", recursive=1)
				self.pusedict = {}
				for key in pusedict.keys():
					cp = dep_getkey(key)
					if not self.pusedict.has_key(cp):
						self.pusedict[cp] = {}
					self.pusedict[cp][key] = pusedict[key]

				#package.keywords
				pkgdict=grabdict_package(USER_CONFIG_PATH+"/package.keywords", recursive=1)
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
				pkgunmasklines = grabfile_package(USER_CONFIG_PATH+"/package.unmask",recursive=1)
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

			# get virtuals -- needs categories
			self.loadVirtuals('/')

			#package.mask
			pkgmasklines = [grabfile_package(os.path.join(x, "package.mask")) for x in self.profiles]
			for l in locations:
				pkgmasklines.append(grabfile_package(l+os.path.sep+"package.mask", recursive=1))
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
					writemsg("Invalid package name in package.provided: "+pkgprovidedlines[x]+"\n")
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
			useorder="env:pkg:conf:auto:defaults"
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

		if self.has_key("PORT_LOGDIR") and not self["PORT_LOGDIR"]:
			# port_logdir is defined, but empty.  this causes a traceback in doebuild.
			writemsg(yellow("!!!")+" PORT_LOGDIR was defined, but set to nothing.\n")
			writemsg(yellow("!!!")+" Disabling it.  Please set it to a non null value.\n")
			del self["PORT_LOGDIR"]

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
					writemsg(red("!!! Invalid PORTDIR_OVERLAY (not a dir): "+ov+"\n"))
			self["PORTDIR_OVERLAY"] = string.join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")

		self.regenerate()

		self.features = portage_util.unique_array(self["FEATURES"].split())

		#XXX: Should this be temporary? Is it possible at all to have a default?
		if "gpg" in self.features:
			if not os.path.exists(self["PORTAGE_GPG_DIR"]) or not os.path.isdir(self["PORTAGE_GPG_DIR"]):
				writemsg("PORTAGE_GPG_DIR is invalid. Removing gpg from FEATURES.\n")
				self.features.remove("gpg")

		if not portage_exec.sandbox_capable and ("sandbox" in self.features or "usersandbox" in self.features):
			writemsg(red("!!! Problem with sandbox binary. Disabling...\n\n"))
			if "sandbox" in self.features:
				self.features.remove("sandbox")
			if "usersandbox" in self.features:
				self.features.remove("usersandbox")

		self.features.sort()
		self["FEATURES"] = " ".join(["-*"]+self.features)
		self.backup_changes("FEATURES")

		if not len(self["CBUILD"]) and len(self["CHOST"]):
			self["CBUILD"] = self["CHOST"]
			self.backup_changes("CBUILD")

		if mycpv:
			self.setcpv(mycpv)

	def loadVirtuals(self,root):
		self.virtuals = self.getvirtuals(root)

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
			writemsg("No pkg setup for settings instance?\n")
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
					except SystemExit, e:
						raise
					except:
						writemsg("!!! Unable to read file: %s\n" % infodir+"/"+filename)
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
		self.reset(keeping_pkg=1,use_cache=use_cache)

	def setinst(self,mycpv,mydbapi):
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
		global usesplit,profiledir

		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals=portage_const.INCREMENTALS
		for mykey in myincrementals:
			if mykey=="USE":
				mydbs=self.uvlist
				# XXX Global usage of db... Needs to go away somehow.
				if db.has_key(root) and db[root].has_key("vartree"):
					self.configdict["auto"]["USE"]=autouse(db[root]["vartree"],use_cache=use_cache)
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
						writemsg(red("USE flags should not start with a '+': %s\n" % x))
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

		#cache split-up USE var in a global
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

	def getvirtuals(self, myroot):
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
			temp_vartree = vartree(myroot,self.dirVirtuals,categories=self.categories)
			# Reduce the provides into a list by CP.
			self.treeVirtuals = map_dictlist_vals(getCPFromCPV,temp_vartree.get_all_provides())

		return self.__getvirtuals_compile()

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
			if x == None:
				writemsg("!!! lookuplist is null.\n")
			elif x.has_key(mykey):
				match = x[mykey]
				break

		if mykey == "CONFIG_PROTECT_MASK":
			match += " /etc/env.d"

		return match

	def has_key(self,mykey):
		for x in self.lookuplist:
			if x.has_key(mykey):
				return 1
		return 0

	def __contains__(self, mykey):
		"""Called to implement membership test operators (in and not in)."""
		return bool(self.has_key(mykey))

	def keys(self):
		mykeys=[]
		for x in self.lookuplist:
			for y in x.keys():
				if y not in mykeys:
					mykeys.append(y)
		return mykeys

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

	# XXX: Negative RESTRICT word
	droppriv=(droppriv and ("userpriv" in features) and not \
		(("nouserpriv" in string.split(mysettings["RESTRICT"])) or \
		 ("userpriv" in string.split(mysettings["RESTRICT"]))))

	if droppriv and not uid and portage_gid and portage_uid:
		keywords.update({"uid":portage_uid,"gid":portage_gid,"groups":[portage_gid],"umask":002})

	if not free:
		free=((droppriv and "usersandbox" not in features) or \
			(not droppriv and "sandbox" not in features and "usersandbox" not in features))

	if sesandbox:
		con = selinux.getcontext()
		con = string.replace(con, mysettings["PORTAGE_T"], mysettings["PORTAGE_SANDBOX_T"])
		selinux.setexec(con)

	if not free:
		keywords["opt_name"] += " sandbox"
		return portage_exec.spawn_sandbox(mystring,env=env,**keywords)
	else:
		keywords["opt_name"] += " bash"
		return portage_exec.spawn_bash(mystring,env=env,**keywords)
	
	if sesandbox:
		selinux.setexec(None)

def fetch(myuris, mysettings, listonly=0, fetchonly=0, locks_in_subdir=".locks",use_locks=1, try_mirrors=1):
	"fetch files.  Will use digest file if available."

	# 'nomirror' is bad/negative logic. You Restrict mirroring, not no-mirroring.
	if ("mirror" in mysettings["RESTRICT"].split()) or \
	   ("nomirror" in mysettings["RESTRICT"].split()):
		if ("mirror" in features) and ("lmirror" not in features):
			# lmirror should allow you to bypass mirror restrictions.
			# XXX: This is not a good thing, and is temporary at best.
			print ">>> \"mirror\" mode desired and \"mirror\" restriction found; skipping fetch."
			return 1

	global thirdpartymirrors

	check_config_instance(mysettings)

	custommirrors=grabdict(CUSTOM_MIRRORS_FILE,recursive=1)

	mymirrors=[]

	if listonly or ("distlocks" not in features):
		use_locks = 0

	fetch_to_ro = 0
	if "skiprocheck" in features:
		fetch_to_ro = 1

	if not os.access(mysettings["DISTDIR"],os.W_OK) and fetch_to_ro:
		if use_locks:
			writemsg(red("!!! You are fetching to a read-only filesystem, you should turn locking off"));
			writemsg("!!! This can be done by adding -distlocks to FEATURES in /etc/make.conf");
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

	mydigests = {}
	digestfn  = mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]
	if os.path.exists(digestfn):
		mydigests = digestParseFile(digestfn)

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
		except (OSError,IOError),e:
			# file does not exist
			writemsg(_("!!! %(file)s not found in %(dir)s\n") % {"file":myfile, "dir":mysettings["DISTDIR"]})
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
				writemsg(_("!!! %(file)s not found in %(dir)s\n") % {"file":myfile, "dir":mysettings["DISTDIR"]})
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
						writemsg(red("!!! YOU HAVE A BROKEN PYTHON/GLIBC.\n"))
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
				writemsg("Invalid mirror definition in SRC_URI:\n")
				writemsg("  %s\n" % (myuri))
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
			writemsg("Warning: No mirrors available for file '%s'\n" % (myfile))
			missingSourceHost = True
	if missingSourceHost:
		return 0
	del missingSourceHost

	can_fetch=True
	if not os.access(mysettings["DISTDIR"]+"/",os.W_OK):
		if not fetch_to_ro:
			print "!!! No write access to %s" % mysettings["DISTDIR"]+"/"
			can_fetch=False
	else:
		def distdir_perms(filename):
			all_applied = True
			try:
				all_applied = portage_util.apply_secpass_permissions(filename, gid=portage_gid, mode=0775)
			except portage_exception.OperationNotPermitted:
				all_applied = False
			if not all_applied:
				writemsg(("!!! Unable to apply group permissions to '%s'." \
				+ "  Non-root users may experience issues.\n") % filename)
		distdir_perms(mysettings["DISTDIR"])
		if use_locks and locks_in_subdir:
			distlocks_subdir = os.path.join(mysettings["DISTDIR"], locks_in_subdir)
			try:
				distdir_perms(distlocks_subdir)
			except portage_exception.FileNotFound:
				os.mkdir(distlocks_subdir)
				distdir_perms(distlocks_subdir)
			if not os.access(distlocks_subdir, os.W_OK):
				writemsg("!!! No write access to write to %s.  Aborting.\n" % distlocks_subdir)
				return 0
			del distlocks_subdir
		del distdir_perms

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
									writemsg("!!! Previously fetched file: "+str(myfile)+"\n")
									writemsg("!!! Reason: "+reason[0]+"\n")
									writemsg("!!! Got:      %s\n!!! Expected: %s\n" % (reason[0], reason[1]))
									writemsg("Refetching...\n\n")
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
					writemsg("An exception was caught(1)...\nFailing the download: %s.\n" % (str(e)),1)
					fetched=0

				if not can_fetch:
					if fetched != 2:
						if fetched == 0:
							writemsg("!!! File %s isn't fetched but unable to get it.\n" % myfile)
						else:
							writemsg("!!! File %s isn't fully fetched, but unable to complete it\n" % myfile)
						return 0
					else:
						continue

				# check if we can actually write to the directory/existing file.
				if fetched!=2 and os.path.exists(mysettings["DISTDIR"]+"/"+myfile) != \
					os.access(mysettings["DISTDIR"]+"/"+myfile, os.W_OK) and not fetch_to_ro:
					writemsg(red("***")+" Lack write access to %s, failing fetch\n" % str(mysettings["DISTDIR"]+"/"+myfile))
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
					try:
						if selinux_enabled:
							con = selinux.getcontext()
							con = string.replace(con, mysettings["PORTAGE_T"], mysettings["PORTAGE_FETCH_T"])
							selinux.setexec(con)
							myret = spawn(myfetch, mysettings, free=1, droppriv=("userfetch" in mysettings.features))
							selinux.setexec(None)
						else:
							myret = spawn(myfetch, mysettings, free=1, droppriv=("userfetch" in mysettings.features))
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
									portage_util.writemsg("chown failed on distfile: " + str(myfile))
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
									writemsg("!!! Fetched file: "+str(myfile)+" VERIFY FAILED!\n")
									writemsg("!!! Reason: "+reason[0]+"\n")
									writemsg("!!! Got:      %s\n!!! Expected: %s\n" % (reason[0], reason[1]))
									writemsg("Removing corrupt distfile...\n")
									os.unlink(mysettings["DISTDIR"]+"/"+myfile)
									fetched=0
								else:
									for x_key in mydigests[myfile].keys():
										writemsg(">>> "+str(myfile)+" "+x_key+" ;-)\n")
									fetched=2
									break
						except (OSError,IOError),e:
							writemsg("An exception was caught(2)...\nFailing the download: %s.\n" % (str(e)),1)
							fetched=0
					else:
						if not myret:
							fetched=2
							break
						elif mydigests!=None:
							writemsg("No digest file available and download failed.\n\n")
		finally:
			if use_locks and file_lock:
				portage_locks.unlockfile(file_lock)

		if listonly:
			writemsg("\n")
		if (fetched!=2) and not listonly:
			writemsg("!!! Couldn't download "+str(myfile)+". Aborting.\n")
			return 0
	return 1


def digestCreate(myfiles,basedir,oldDigest={}):
	"""Takes a list of files and the directory they are in and returns the
	dict of dict[filename][CHECKSUM_KEY] = hash
	returns None on error."""
	mydigests={}
	for x in myfiles:
		print "<<<",x
		myfile=os.path.normpath(basedir+"///"+x)
		if os.path.exists(myfile):
			if not os.access(myfile, os.R_OK):
				print "!!! Given file does not appear to be readable. Does it exist?"
				print "!!! File:",myfile
				return None
			mydigests[x] = portage_checksum.perform_multiple_checksums(myfile, hashes=portage_const.MANIFEST1_HASH_FUNCTIONS)
			mysize       = os.stat(myfile)[stat.ST_SIZE]
		else:
			if x in oldDigest:
				# DeepCopy because we might not have a unique reference.
				mydigests[x] = copy.deepcopy(oldDigest[x])
				mysize       = copy.deepcopy(oldDigest[x]["size"])
			else:
				print "!!! We have a source URI, but no file..."
				print "!!! File:",myfile
				return None

		if mydigests[x].has_key("size") and (mydigests[x]["size"] != mysize):
			raise portage_exception.DigestException, "Size mismatch during checksums"
		mydigests[x]["size"] = copy.deepcopy(mysize)
	return mydigests

def digestCreateLines(filelist, mydict):
	mylines = []
	mydigests = copy.deepcopy(mydict)
	for myarchive in filelist:
		mysize = mydigests[myarchive]["size"]
		if len(mydigests[myarchive]) == 0:
			raise portage_exception.DigestException, "No generate digest for '%(file)s'" % {"file":myarchive}
		for sumName in mydigests[myarchive].keys():
			if sumName not in portage_checksum.get_valid_checksum_keys():
				continue
			mysum = mydigests[myarchive][sumName]

			myline  = sumName[:]
			myline += " "+mysum
			myline += " "+myarchive
			myline += " "+str(mysize)
			mylines.append(myline)
	return mylines

def digestgen(myarchives,mysettings,overwrite=1,manifestonly=0):
	"""generates digest file if missing.  Assumes all files are available.	If
	overwrite=0, the digest will only be created if it doesn't already exist."""

	# archive files
	basedir=mysettings["DISTDIR"]+"/"
	digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]

	# portage files -- p(ortagefiles)basedir
	pbasedir=mysettings["O"]+"/"
	manifestfn=pbasedir+"Manifest"

	if not manifestonly:
		if not os.path.isdir(mysettings["FILESDIR"]):
			os.makedirs(mysettings["FILESDIR"])
		mycvstree=cvstree.getentries(pbasedir, recursive=1)

		if ("cvs" in features) and os.path.exists(pbasedir+"/CVS"):
			if not cvstree.isadded(mycvstree,"files"):
				if "autoaddcvs" in features:
					print ">>> Auto-adding files/ dir to CVS..."
					spawn("cd "+pbasedir+"; cvs add files",mysettings,free=1)
				else:
					print "--- Warning: files/ is not added to cvs."

		if (not overwrite) and os.path.exists(digestfn):
			return 1

		print green(">>> Generating the digest file...")

		# Track the old digest so we can assume checksums without requiring
		# all files to be downloaded. 'Assuming'
		myolddigest = {}
		if os.path.exists(digestfn):
			myolddigest = digestParseFile(digestfn)

		myarchives.sort()
		try:
			mydigests=digestCreate(myarchives, basedir, oldDigest=myolddigest)
		except portage_exception.DigestException, s:
			print "!!!",s
			return 0
		if mydigests==None: # There was a problem, exit with an errorcode.
			return 0

		try:
			outfile=open(digestfn, "w+")
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! Filesystem error skipping generation. (Read-Only?)"
			print "!!!",e
			return 0
		for x in digestCreateLines(myarchives, mydigests):
			outfile.write(x+"\n")
		outfile.close()
		try:
			os.chown(digestfn,os.getuid(),portage_gid)
			os.chmod(digestfn,0664)
		except SystemExit, e:
			raise
		except Exception,e:
			print e

	print green(">>> Generating the manifest file...")
	mypfiles=listdir(pbasedir,recursive=1,filesonly=1,ignorecvs=1,EmptyOnError=1)
	mypfiles=cvstree.apply_cvsignore_filter(mypfiles)
	mypfiles.sort()
	for x in ["Manifest"]:
		if x in mypfiles:
			mypfiles.remove(x)

	mydigests=digestCreate(mypfiles, pbasedir)
	if mydigests==None: # There was a problem, exit with an errorcode.
		return 0

	try:
		outfile=open(manifestfn, "w+")
	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Filesystem error skipping generation. (Read-Only?)"
		print "!!!",e
		return 0
	for x in digestCreateLines(mypfiles, mydigests):
		outfile.write(x+"\n")
	outfile.close()
	try:
		os.chown(manifestfn,os.getuid(),portage_gid)
		os.chmod(manifestfn,0664)
	except SystemExit, e:
		raise
	except Exception,e:
		print e

	if "cvs" in features and os.path.exists(pbasedir+"/CVS"):
		mycvstree=cvstree.getentries(pbasedir, recursive=1)
		myunaddedfiles=""
		if not manifestonly and not cvstree.isadded(mycvstree,digestfn):
			if digestfn[:len(pbasedir)]==pbasedir:
				myunaddedfiles=digestfn[len(pbasedir):]+" "
			else:
				myunaddedfiles=digestfn+" "
		if not cvstree.isadded(mycvstree,manifestfn[len(pbasedir):]):
			if manifestfn[:len(pbasedir)]==pbasedir:
				myunaddedfiles+=manifestfn[len(pbasedir):]+" "
			else:
				myunaddedfiles+=manifestfn
		if myunaddedfiles:
			if "autoaddcvs" in features:
				print blue(">>> Auto-adding digest file(s) to CVS...")
				spawn("cd "+pbasedir+"; cvs add "+myunaddedfiles,mysettings,free=1)
			else:
				print "--- Warning: digests are not yet added into CVS."
	print darkgreen(">>> Computed message digests.")
	print
	return 1


def digestParseFile(myfilename):
	"""(filename) -- Parses a given file for entries matching:
	<checksumkey> <checksum_hex_string> <filename> <filesize>
	Ignores lines that don't start with a valid checksum identifier
	and returns a dict with the filenames as keys and {checksumkey:checksum}
	as the values."""

	if not os.path.exists(myfilename):
		return None
	mylines = portage_util.grabfile(myfilename, compat_level=1)

	mydigests={}
	for x in mylines:
		myline=string.split(x)
		if len(myline) < 4:
			#invalid line
			continue
		if myline[0] not in portage_checksum.get_valid_checksum_keys():
			continue
		mykey  = myline.pop(0)
		myhash = myline.pop(0)
		mysize = long(myline.pop())
		myfn   = string.join(myline, " ")
		if myfn not in mydigests:
			mydigests[myfn] = {}
		mydigests[myfn][mykey] = myhash
		if "size" in mydigests[myfn]:
			if mydigests[myfn]["size"] != mysize:
				raise portage_exception.DigestException, "Conflicting sizes in digest: %(filename)s" % {"filename":myfilename}
		else:
			mydigests[myfn]["size"] = mysize
	return mydigests

# XXXX strict was added here to fix a missing name error.
# XXXX It's used below, but we're not paying attention to how we get it?
def digestCheckFiles(myfiles, mydigests, basedir, note="", strict=0):
	"""(fileslist, digestdict, basedir) -- Takes a list of files and a dict
	of their digests and checks the digests against the indicated files in
	the basedir given. Returns 1 only if all files exist and match the checksums.
	"""
	for x in myfiles:
		if not mydigests.has_key(x):
			print
			print red("!!! No message digest entry found for file \""+x+".\"")
			print "!!! Most likely a temporary problem. Try 'emerge sync' again later."
			print "!!! If you are certain of the authenticity of the file then you may type"
			print "!!! the following to generate a new digest:"
			print "!!!   ebuild /usr/portage/category/package/package-version.ebuild digest"
			return 0
		myfile=os.path.normpath(basedir+"/"+x)
		if not os.path.exists(myfile):
			if strict:
				print "!!! File does not exist:",myfile
				return 0
			continue

		ok,reason = portage_checksum.verify_all(myfile,mydigests[x])
		if not ok:
			print
			print red("!!! Digest verification Failed:")
			print red("!!!")+"    "+str(os.path.realpath(myfile))
			print red("!!! Reason: ")+reason[0]
			print red("!!! Got:      ")+str(reason[1])
			print red("!!! Expected: ")+str(reason[2])
			print
			return 0
		else:
			writemsg_stdout(">>> checksums "+note+" ;-) %s\n" % x)
	return 1


def digestcheck(myfiles, mysettings, strict=0, justmanifest=0):
	"""Verifies checksums.  Assumes all files have been downloaded."""
	# archive files
	basedir=mysettings["DISTDIR"]+"/"
	digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]

	# portage files -- p(ortagefiles)basedir
	pbasedir=mysettings["O"]+"/"
	manifestfn=pbasedir+"Manifest"

	if not (os.path.exists(digestfn) and os.path.exists(manifestfn)):
		if "digest" in features:
			print ">>> No package digest/Manifest file found."
			print ">>> \"digest\" mode enabled; auto-generating new digest..."
			return digestgen(myfiles,mysettings)
		else:
			if not os.path.exists(manifestfn):
				if strict:
					print red("!!! No package manifest found:"),manifestfn
					return 0
				else:
					print "--- No package manifest found:",manifestfn
			if not os.path.exists(digestfn):
				print "!!! No package digest file found:",digestfn
				print "!!! Type \"ebuild foo.ebuild digest\" to generate it."
				return 0

	mydigests=digestParseFile(digestfn)
	if mydigests==None:
		print "!!! Failed to parse digest file:",digestfn
		return 0
	mymdigests=digestParseFile(manifestfn)
	if "strict" not in features:
		# XXX: Remove this when manifests become mainstream.
		pass
	elif mymdigests==None:
			print "!!! Failed to parse manifest file:",manifestfn
			if strict:
				return 0
	else:
		# Check the portage-related files here.
		mymfiles=listdir(pbasedir,recursive=1,filesonly=1,ignorecvs=1,EmptyOnError=1)
		manifest_files = mymdigests.keys()
		# Files unrelated to the build process are ignored for verification by default
		for x in ["Manifest", "ChangeLog", "metadata.xml"]:
			while x in mymfiles:
				mymfiles.remove(x)
			while x in manifest_files:
				manifest_files.remove(x)
		for x in range(len(mymfiles)-1,-1,-1):
			if mymfiles[x] in manifest_files:
				manifest_files.remove(mymfiles[x])
			elif len(cvstree.apply_cvsignore_filter([mymfiles[x]]))==0:
				# we filter here, rather then above; manifest might have files flagged by the filter.
				# if something is returned, then it's flagged as a bad file
				# manifest doesn't know about it, so we kill it here.
				del mymfiles[x]
			else:
				print red("!!! Security Violation: A file exists that is not in the manifest.")
				print "!!! File:",mymfiles[x]
				if strict:
					return 0
		if manifest_files and strict:
			print red("!!! Files listed in the manifest do not exist!")
			for x in manifest_files:
				print x
			return 0

		if not digestCheckFiles(mymfiles, mymdigests, pbasedir, note="files  ", strict=strict):
			if strict:
				print ">>> Please ensure you have sync'd properly. Please try '"+bold("emerge sync")+"' and"
				print ">>> optionally examine the file(s) for corruption. "+bold("A sync will fix most cases.")
				print
				return 0
			else:
				print "--- Manifest check failed. 'strict' not enabled; ignoring."
				print

	if justmanifest:
		return 1

	# Just return the status, as it's the last check.
	return digestCheckFiles(myfiles, mydigests, basedir, note="src_uri", strict=strict)

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo,actionmap,mysettings,debug,alwaysdep=0,logfile=None):
	if alwaysdep or ("noauto" not in features):
		# process dependency first
		if "dep" in actionmap[mydo].keys():
			retval=spawnebuild(actionmap[mydo]["dep"],actionmap,mysettings,debug,alwaysdep=alwaysdep,logfile=logfile)
			if retval:
				return retval
	kwargs = actionmap[mydo]["args"]
	phase_retval = spawn(actionmap[mydo]["cmd"] % mydo, mysettings, debug=debug, logfile=logfile, **kwargs)
	if phase_retval == os.EX_OK:
		if mydo == "install":
			mycommand = " ".join([MISC_SH_BINARY, "install_qa_check"])
			return spawn(mycommand, mysettings, debug=debug, logfile=logfile, **kwargs)
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

def doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, tree):

	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if mysettings.configdict["pkg"].has_key("CATEGORY"):
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(os.path.normpath(pkg_dir+"/.."))
	mypv = os.path.basename(ebuild_path)[:-7]	
	mycpv = cat+"/"+mypv
	mysplit=pkgsplit(mypv,silent=0)
	if mysplit==None:
		writemsg("!!! Error: PF is null '%s'; exiting.\n" % mypv)
		return 1
	if mydo != "depend":
		# XXX: We're doing a little hack here to curtain the gvisible locking
		# XXX: that creates a deadlock... Really need to isolate that.
		mysettings.reset(use_cache=use_cache)
	mysettings.setcpv(mycpv,use_cache=use_cache)

	if debug: # Otherwise it overrides emerge's settings.
		# We have no other way to set debug... debug can't be passed in
		# due to how it's coded... Don't overwrite this so we can use it.
		mysettings["PORTAGE_DEBUG"]=str(debug)

	mysettings["ROOT"]     = myroot
	mysettings["STARTDIR"] = getcwd()

	mysettings["EBUILD"]   = ebuild_path
	mysettings["O"]        = pkg_dir
	mysettings["CATEGORY"] = cat
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
		try:
			mysettings["INHERITED"], mysettings["RESTRICT"] = db[root][tree].dbapi.aux_get( \
				mycpv,["INHERITED","RESTRICT"])
			mysettings["PORTAGE_RESTRICT"]=string.join(flatten(portage_dep.use_reduce(portage_dep.paren_reduce( \
				mysettings["RESTRICT"]), uselist=mysettings["USE"].split())),' ')
		except SystemExit, e:
			raise
		except:
			pass
		eapi = db[root][tree].dbapi.aux_get(mycpv, ["EAPI"])[0]
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise portage_exception.UnsupportedAPIException(mycpv, eapi)

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	mysettings["SLOT"]=""

	if mysettings.has_key("PATH"):
		mysplit=string.split(mysettings["PATH"],":")
	else:
		mysplit=[]
	if PORTAGE_BIN_PATH not in mysplit:
		mysettings["PATH"]=PORTAGE_BIN_PATH+":"+mysettings["PATH"]


	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["HOME"]         = mysettings["BUILD_PREFIX"]+"/homedir"
	mysettings["PKG_TMPDIR"]   = mysettings["PORTAGE_TMPDIR"]+"/binpkgs"
	
	# Package {pre,post}inst and {pre,post}rm may overlap, so they must have separate
	# locations in order to prevent interference.
	if mydo in ("unmerge", "prerm", "postrm", "cleanrm"):
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(mysettings["PKG_TMPDIR"], mysettings["PF"])
	else:
		mysettings["PORTAGE_BUILDDIR"] = os.path.join(mysettings["BUILD_PREFIX"], mysettings["PF"])

	mysettings["WORKDIR"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "work")
	mysettings["D"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "image") + os.sep
	mysettings["T"] = os.path.join(mysettings["PORTAGE_BUILDDIR"], "temp")

	mysettings["PORTAGE_BASHRC"] = EBUILD_SH_ENV_FILE

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if (mydo!="depend") or not mysettings.has_key("KV"):
		mykv,err1=ExtractKernelVersion(root+"usr/src/linux")
		if mykv:
			# Regular source tree
			mysettings["KV"]=mykv
		else:
			mysettings["KV"]=""

	if (mydo!="depend") or not mysettings.has_key("KVERS"):
		myso=os.uname()[2]
		mysettings["KVERS"]=myso[1]

def prepare_build_dirs(myroot, mysettings, cleanup):

	if not os.path.exists(mysettings["BUILD_PREFIX"]):
		os.makedirs(mysettings["BUILD_PREFIX"])
	apply_secpass_permissions(mysettings["BUILD_PREFIX"],
	uid=portage_uid, gid=portage_gid, mode=00775)

	# We enable cleanup when we want to make sure old cruft (such as the old
	# environment) doesn't interfere with the current phase.
	if cleanup:
		if os.path.exists(mysettings["T"]):
			shutil.rmtree(mysettings["T"])
	if not os.path.exists(mysettings["T"]):
		os.makedirs(mysettings["T"])
	apply_secpass_permissions(mysettings["T"],
	uid=portage_uid, gid=portage_gid, mode=02770)

	logdir = mysettings["T"]+"/logging"
	if not os.path.exists(logdir):
		os.makedirs(logdir)
	apply_secpass_permissions(logdir,
	uid=portage_uid, gid=portage_gid, mode=0770)

	try: # XXX: negative RESTRICT
		if not (("nouserpriv" in string.split(mysettings["PORTAGE_RESTRICT"])) or \
			("userpriv" in string.split(mysettings["PORTAGE_RESTRICT"]))):
			if ("userpriv" in features) and (portage_uid and portage_gid):
				if (secpass==2):
					if os.path.exists(mysettings["HOME"]):
						# XXX: Potentially bad, but held down by HOME replacement above.
						spawn("rm -Rf "+mysettings["HOME"],mysettings, free=1)
					if not os.path.exists(mysettings["HOME"]):
						os.makedirs(mysettings["HOME"])
			elif ("userpriv" in features):
				print "!!! Disabling userpriv from features... Portage UID/GID not valid."
				del features[features.index("userpriv")]
	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Couldn't empty HOME:",mysettings["HOME"]
		print "!!!",e

	try:
		# no reason to check for depend since depend returns above.
		for myvar in ("BUILD_PREFIX", "PORTAGE_BUILDDIR"):
			if not os.path.exists(mysettings[myvar]):
				os.makedirs(mysettings[myvar])
			apply_secpass_permissions(mysettings[myvar],
			uid=portage_uid, gid=portage_gid)
	except OSError, e:
		print "!!! File system problem. (ReadOnly? Out of space?)"
		print "!!! Perhaps: rm -Rf",mysettings["BUILD_PREFIX"]
		print "!!!",str(e)
		return 1

	try:
		if not os.path.exists(mysettings["HOME"]):
			os.makedirs(mysettings["HOME"])
		apply_secpass_permissions(mysettings["HOME"],
		uid=portage_uid, gid=portage_gid, mode=02770)
	except OSError, e:
		print "!!! File system problem. (ReadOnly? Out of space?)"
		print "!!! Failed to create fake home directory in PORTAGE_BUILDDIR"
		print "!!!",str(e)
		return 1

	try:
		if ("ccache" in features):
			if (not mysettings.has_key("CCACHE_DIR")) or (mysettings["CCACHE_DIR"]==""):
				mysettings["CCACHE_DIR"]=mysettings["PORTAGE_TMPDIR"]+"/ccache"
			if not os.path.exists(mysettings["CCACHE_DIR"]):
				os.makedirs(mysettings["CCACHE_DIR"])
			mystat = os.stat(mysettings["CCACHE_DIR"])
			if ("userpriv" in features):
				if mystat[stat.ST_UID] != portage_uid or ((mystat[stat.ST_MODE]&02070)!=02070):
					writemsg("* Adjusting permissions on ccache in %s\n" % mysettings["CCACHE_DIR"])
					spawn("chgrp -R "+str(portage_gid)+" "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("chown "+str(portage_uid)+":"+str(portage_gid)+" "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("chmod -R ug+rw "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("find "+mysettings["CCACHE_DIR"]+" -type d -exec chmod g+xs \{\} \;", mysettings, free=1)
			else:
				if mystat[stat.ST_UID] != 0 or ((mystat[stat.ST_MODE]&02070)!=02070):
					writemsg("* Adjusting permissions on ccache in %s\n" % mysettings["CCACHE_DIR"])
					spawn("chgrp -R "+str(portage_gid)+" "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("chown 0:"+str(portage_gid)+" "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("chmod -R ug+rw "+mysettings["CCACHE_DIR"], mysettings, free=1)
					spawn("find "+mysettings["CCACHE_DIR"]+" -type d -exec chmod g+xs \{\} \;", mysettings, free=1)
	except OSError, e:
		print "!!! File system problem. (ReadOnly? Out of space?)"
		print "!!! Perhaps: rm -Rf",mysettings["BUILD_PREFIX"]
		print "!!!",str(e)
		return 1

	if "confcache" in features:
		confcache_enabled = True
		if "CONFCACHE_DIR" not in mysettings:
			mysettings["CONFCACHE_DIR"] = os.path.join(mysettings["PORTAGE_TMPDIR"], "confcache")
		confcache_dir_mode = 0775

		try:
			os.makedirs(mysettings["CONFCACHE_DIR"], mode=confcache_dir_mode)
		except OSError, oe:
			if oe.errno == errno.EEXIST:
				pass
			elif errno == errno.EPERM:
				writemsg("Operation Not Permitted: makedirs(%s, mode=%s)\n" % (mysettings["CONFCACHE_DIR"], oct(confcache_dir_mode)))
				confcache_enabled = False

		if confcache_enabled:
			try:
				confcache_enabled = apply_secpass_permissions(
					mysettings["CONFCACHE_DIR"],
					gid=portage_gid, mode=confcache_dir_mode)
			except portage_exception.OperationNotPermitted, e:
				writemsg("Operation Not Permitted: %s\n" % str(e))
				confcache_enabled = False

		del confcache_dir_mode

		if confcache_enabled:
			for x in listdir(mysettings["CONFCACHE_DIR"]):
				cache_file = os.path.join(mysettings["CONFCACHE_DIR"], x)
				try:
					confcache_enabled = apply_secpass_permissions(cache_file, gid=portage_gid, mode=0660, mask=07000)
				except portage_exception.OperationNotPermitted, e:
					writemsg("Operation Not Permitted: %s\n" % str(e))
					confcache_enabled = False
				except portage_exception.FileNotFound, e:
					writemsg("File Not Found: %s\n" % str(e))

		if not confcache_enabled:
			writemsg("!!! Failed resetting perms on confcachedir %s\n" % mysettings["CONFCACHE_DIR"])
			features.remove("confcache")
			mysettings["FEATURES"] = " ".join(features)

	if "distcc" in features:
		
		distcc_enabled = True

		if "DISTCC_DIR" not in mysettings or "" == mysettings["DISTCC_DIR"]:
			mysettings["DISTCC_DIR"] = os.path.join(mysettings["BUILD_PREFIX"], ".distcc")
		for x in ("", "lock", "state"):
			mydir = os.path.join(mysettings["DISTCC_DIR"], x)
			try:
				os.makedirs(mydir)
			except OSError, oe:
				if errno.EEXIST == oe.errno:
					pass
				elif errno.EPERM == oe.errno:
					distcc_enabled = False
					break
				else:
					raise
			try:
				distcc_enabled = apply_secpass_permissions(mydir,
				uid=portage_uid, gid=portage_gid, mode=02775)
			except portage_exception.OperationNotPermitted, e:
				writemsg("Operation Not Permitted: %s\n" % str(e))
				distcc_enabled = False
				break

		if not distcc_enabled:
			writemsg("\n!!! File system problem when setting DISTCC_DIR directory permissions.\n")
			writemsg(  "!!! DISTCC_DIR="+str(mysettings["DISTCC_DIR"]+"\n"))
			time.sleep(5)
			features.remove("distcc")
			mysettings["FEATURES"] = " ".join(features)
			mysettings["DISTCC_DIR"]=""

	workdir_mode = 0700
	try:
		workdir_mode = int(eval(mysettings["PORTAGE_WORKDIR_MODE"]))
		if workdir_mode & 07777 != workdir_mode:
			raise ValueError("Invalid file mode: %s" % mysettings["PORTAGE_WORKDIR_MODE"])
	except KeyError, e:
		writemsg("!!! PORTAGE_WORKDIR_MODE is unset, using %s." % oct(workdir_mode))
	except ValueError, e:
		writemsg("%s\n" % e)
		writemsg("!!! Unable to parse PORTAGE_WORKDIR_MODE='%s', using %s.\n" % \
		(mysettings["PORTAGE_WORKDIR_MODE"], oct(workdir_mode)))
	try:
		apply_secpass_permissions(mysettings["WORKDIR"],
		uid=portage_uid, gid=portage_gid, mode=workdir_mode)
	except portage_exception.FileNotFound:
		pass # ebuild.sh will create it

	if "PORT_LOGDIR" in mysettings:
		logging_enabled = True

		try:
			os.makedirs(mysettings["PORT_LOGDIR"])
		except OSError, oe:
			if errno.EEXIST == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("!!! Unable to create PORT_LOGDIR\n")
				writemsg("!!! %s\n" % str(oe))
				logging_enabled = False
			else:
				raise

		if logging_enabled:
			try:
				logging_enabled = \
					apply_secpass_permissions(mysettings["PORT_LOGDIR"],
					uid=portage_uid, gid=portage_gid, mode=02770)
			except portage_exception.OperationNotPermitted, e:
				writemsg("!!! Operation Not Permitted: %s\n" % str(e))
				logging_enabled = False

		if logging_enabled:
			if "LOG_PF" not in mysettings or \
			mysettings["LOG_PF"] != mysettings["PF"]:
				mysettings["LOG_PF"] = mysettings["PF"]
				mysettings["LOG_COUNTER"] = \
					str(db[myroot]["vartree"].dbapi.get_counter_tick_core("/"))

		if not logging_enabled:
			writemsg("!!! Permission issues with PORT_LOGDIR='%s'\n" % mysettings["PORT_LOGDIR"])
			writemsg("!!! Disabling logging.\n")
			mysettings["PORT_LOGDIR"]=""

def doebuild(myebuild,mydo,myroot,mysettings,debug=0,listonly=0,fetchonly=0,cleanup=0,dbkey=None,use_cache=1,fetchall=0,tree=None):
	global db, actionmap_deps

	if not tree:
		dump_traceback("Warning: tree not specified to doebuild")
		tree = "porttree"

	validcommands = ["help","clean","prerm","postrm","cleanrm","preinst","postinst",
	                "config","setup","depend","fetch","digest",
	                "unpack","compile","test","install","rpm","qmerge","merge",
	                "package","unmerge", "manifest"]

	if mydo not in validcommands:
		validcommands.sort()
		writemsg("!!! doebuild: '%s' is not one of the following valid commands:" % mydo)
		for vcount in range(len(validcommands)):
			if vcount%6 == 0:
				writemsg("\n!!! ")
			writemsg(string.ljust(validcommands[vcount], 11))
		writemsg("\n")
		return 1

	if not os.path.exists(myebuild):
		writemsg("!!! doebuild: "+str(myebuild)+" not found for "+str(mydo)+"\n")
		return 1

	mystatus = doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, tree)
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

	logfile=None
	# Build directory creation isn't required for any of these.
	if mydo not in ["fetch","digest","manifest"]:
		mystatus = prepare_build_dirs(myroot, mysettings, cleanup)
		if mystatus:
			return mystatus

		if "PORT_LOGDIR" in mysettings:
			logfile = os.path.join(mysettings["PORT_LOGDIR"], "%s-%s.log" % \
				(mysettings["LOG_COUNTER"], mysettings["LOG_PF"]))

		if mydo=="unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings)

	# if any of these are being called, handle them -- running them out of the sandbox -- and stop now.
	if mydo in ["clean","cleanrm"]:
		if "noclean" in features:
			return 0
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
			spawn(" ".join(myargs), mysettings, debug=debug, free=1, logfile=logfile)
		del mysettings["IMAGE"]
		return phase_retval
	elif mydo in ["prerm","postrm","postinst","config"]:
		mysettings.load_infodir(mysettings["O"])
		return spawn(EBUILD_SH_BINARY+" "+mydo,mysettings,debug=debug,free=1,logfile=logfile)

	mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))
	try:
		mysettings["SLOT"],mysettings["RESTRICT"] = db["/"]["porttree"].dbapi.aux_get(mycpv,["SLOT","RESTRICT"])
	except (IOError,KeyError):
		print red("doebuild():")+" aux_get() error reading "+mycpv+"; aborting."
		sys.exit(1)

	newuris, alist  = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings)
	alluris, aalist = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=mysettings,all=1)
	mysettings["A"]=string.join(alist," ")
	mysettings["AA"]=string.join(aalist," ")
	if ("mirror" in features) or fetchall:
		fetchme=alluris[:]
		checkme=aalist[:]
	elif mydo=="digest":
		fetchme=alluris[:]
		checkme=aalist[:]
		digestfn=mysettings["FILESDIR"]+"/digest-"+mysettings["PF"]
		if os.path.exists(digestfn):
			mydigests=digestParseFile(digestfn)
			if mydigests:
				for x in mydigests:
					while x in checkme:
						i = checkme.index(x)
						del fetchme[i]
						del checkme[i]
	else:
		fetchme=newuris[:]
		checkme=alist[:]

	try:
		if not os.path.exists(mysettings["DISTDIR"]):
			os.makedirs(mysettings["DISTDIR"])
		if not os.path.exists(mysettings["DISTDIR"]+"/cvs-src"):
			os.makedirs(mysettings["DISTDIR"]+"/cvs-src")
	except OSError, e:
		print "!!! File system problem. (Bad Symlink?)"
		print "!!! Fetching may fail:",str(e)

	try:
		mystat=os.stat(mysettings["DISTDIR"]+"/cvs-src")
		if ((mystat[stat.ST_GID]!=portage_gid) or ((mystat[stat.ST_MODE]&02770)!=02770)) and not listonly:
			print "*** Adjusting cvs-src permissions for portage user..."
			apply_secpass_permissions(mysettings["DISTDIR"]+"/cvs-src",
			uid=0, gid=portage_gid, mode=02770, stat_cached=mystat)
			spawn("chgrp -R "+str(portage_gid)+" "+mysettings["DISTDIR"]+"/cvs-src", free=1)
			spawn("chmod -R g+rw "+mysettings["DISTDIR"]+"/cvs-src", free=1)
	except SystemExit, e:
		raise
	except:
		pass

	# Only try and fetch the files if we are going to need them ... otherwise,
	# if user has FEATURES=noauto and they run `ebuild clean unpack compile install`,
	# we will try and fetch 4 times :/
	need_distfiles = (mydo in ("digest", "fetch", "unpack") or
	                  mydo != "manifest" and "noauto" not in features)
	if need_distfiles and not fetch(fetchme, mysettings, listonly=listonly, fetchonly=fetchonly):
		return 1

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

	if mydo=="fetch" and listonly:
		return 0

	if "digest" in features:
		#generate digest if it doesn't exist.
		if mydo=="digest":
			return (not digestgen(aalist,mysettings,overwrite=1))
		else:
			digestgen(aalist,mysettings,overwrite=0)
	elif mydo=="digest":
		#since we are calling "digest" directly, recreate the digest even if it already exists
		return (not digestgen(aalist,mysettings,overwrite=1))
	if mydo=="manifest":
		return (not digestgen(aalist,mysettings,overwrite=1,manifestonly=1))

	# See above comment about fetching only when needed
	if not digestcheck(checkme, mysettings, ("strict" in features), (mydo not in ["digest","fetch","unpack"] and settings["PORTAGE_CALLER"] == "ebuild" and "noauto" in features)):
		return 1

	if mydo=="fetch":
		return 0

	#initial dep checks complete; time to process main commands

	nosandbox=(("userpriv" in features) and ("usersandbox" not in features) and \
		("userpriv" not in mysettings["RESTRICT"]) and ("nouserpriv" not in mysettings["RESTRICT"]))
	if nosandbox and ("userpriv" not in features or "userpriv" in mysettings["RESTRICT"] or \
		"nouserpriv" in mysettings["RESTRICT"]):
		nosandbox = ("sandbox" not in features and "usersandbox" not in features)

	sesandbox = selinux_enabled and "sesandbox" in features
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
		return spawnebuild(mydo,actionmap,mysettings,debug,logfile=logfile)
	elif mydo=="qmerge":
		#check to ensure install was run.  this *only* pops up when users forget it and are using ebuild
		if not os.path.exists(mysettings["PORTAGE_BUILDDIR"]+"/.installed"):
			print "!!! mydo=qmerge, but install phase hasn't been ran"
			sys.exit(1)
		#qmerge is specifically not supposed to do a runtime dep check
		return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["PORTAGE_BUILDDIR"]+"/build-info",myroot,mysettings,myebuild=mysettings["EBUILD"],mytree=tree)
	elif mydo=="merge":
		retval=spawnebuild("install",actionmap,mysettings,debug,alwaysdep=1,logfile=logfile)
		if retval:
			return retval
		return merge(mysettings["CATEGORY"],mysettings["PF"],mysettings["D"],mysettings["PORTAGE_BUILDDIR"]+"/build-info",myroot,mysettings,myebuild=mysettings["EBUILD"],mytree=tree)
	else:
		print "!!! Unknown mydo:",mydo
		sys.exit(1)

expandcache={}

def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	global lchown

	try:
		if not sstat:
			sstat=os.lstat(src)
		if bsd_chflags:
			sflags=bsd_chflags.lgetflags(src)
			if sflags < 0:
				# Problem getting flags...
				writemsg("!!! Couldn't get flags for "+dest+"\n")
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
		if(destexists):
			if bsd_chflags.lchflags(dest, 0) < 0:
				writemsg("!!! Couldn't clear flags on file being merged: \n ")
		# We might have an immutable flag on the parent dir; save and clear.
		pflags=bsd_chflags.lgetflags(os.path.dirname(dest))
		bsd_chflags.lchflags(os.path.dirname(dest), 0)

		# Don't bother checking the return value here; if it fails then the next line will catch it.
		bsd_chflags.lchflags(src, 0)

		if bsd_chflags.lhasproblems(src)>0 or (destexists and bsd_chflags.lhasproblems(dest)>0) or bsd_chflags.lhasproblems(os.path.dirname(dest))>0:
			# This is bad: we can't merge the file with these flags set.
			writemsg("!!! Can't merge file "+dest+" because of flags set\n")
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
				if bsd_chflags.lchflags(dest, sflags) < 0 or bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0:
					writemsg("!!! Couldn't restore flags ("+str(flags)+") on " + dest+":\n")
					writemsg("!!! %s\n" % str(e))
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
		if bsd_chflags.lchflags(dest, sflags) < 0 or bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0:
			writemsg("!!! Couldn't restore flags ("+str(sflags)+") on " + dest+":\n")
			return None

	return newmtime

def merge(mycat,mypkg,pkgloc,infloc,myroot,mysettings,myebuild=None,mytree=None):
	mylink=dblink(mycat,mypkg,myroot,mysettings,treetype=mytree)
	return mylink.merge(pkgloc,infloc,myroot,myebuild)

def unmerge(cat,pkg,myroot,mysettings,mytrimworld=1):
	mylink=dblink(cat,pkg,myroot,mysettings,treetype="vartree")
	if mylink.exists():
		mylink.unmerge(trimworld=mytrimworld,cleanup=1)
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
			if mysettings.virtuals.has_key(mykey):
				if len(mysettings.virtuals[mykey])==1:
					a=string.replace(x, mykey, mysettings.virtuals[mykey][0])
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in mysettings.virtuals[mykey]:
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

def dep_zapdeps(unreduced,reduced,myroot,use_binaries=0):
	"""Takes an unreduced and reduced deplist and removes satisfied dependencies.
	Returned deplist contains steps that must be taken to satisfy dependencies."""
	writemsg("ZapDeps -- %s\n" % (use_binaries), 2)
	if not reduced or unreduced == ["||"] or dep_eval(reduced):
		return []

	if unreduced[0] != "||":
		unresolved = []
		for (dep, satisfied) in zip(unreduced, reduced):
			if isinstance(dep, list):
				unresolved += dep_zapdeps(dep, satisfied, myroot, use_binaries=use_binaries)
			elif not satisfied:
				unresolved.append(dep)
		return unresolved

	# We're at a ( || atom ... ) type level
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	target = None
	for (dep, satisfied) in zip(deps, satisfieds):
		if isinstance(dep, list):
			atoms = dep_zapdeps(dep, satisfied, myroot, use_binaries=use_binaries)
		else:
			atoms = [dep]
		missing_atoms = [atom for atom in atoms if not db[myroot]["vartree"].dbapi.match(atom)]

		if not missing_atoms:
			if isinstance(dep, list):
				return atoms  # Sorted out by the recursed dep_zapdeps call
			else:
				target = dep_getkey(dep) # An installed package that's not yet in the graph
				break

		if not target:
			if use_binaries:
				missing_atoms = [atom for atom in atoms if not db[myroot]["bintree"].dbapi.match(atom)]
			else:
				missing_atoms = [atom for atom in atoms if not db[myroot]["porttree"].dbapi.xmatch("match-visible", atom)]
			if not missing_atoms:
				target = (dep, satisfied)

	if not target:
		if isinstance(deps[0], list):
			return dep_zapdeps(deps[0], satisfieds[0], myroot, use_binaries=use_binaries)
		else:
			return [deps[0]]

	if isinstance(target, tuple): # Nothing matching installed
		if isinstance(target[0], list): # ... and the first available was a sublist
			return dep_zapdeps(target[0], target[1], myroot, use_binaries=use_binaries)
		else: # ... and the first available was a single atom
			target = dep_getkey(target[0])

	relevant_atoms = [dep for dep in deps if not isinstance(dep, list) and dep_getkey(dep) == target]

	available_pkgs = {}
	for atom in relevant_atoms:
		if use_binaries:
			pkg_list = db["/"]["bintree"].dbapi.match(atom)
		else:
			pkg_list = db["/"]["porttree"].dbapi.xmatch("match-visible", atom)
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
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	if mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	if isspecific(mydep):
		mysplit=catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0]+"/"+mysplit[1]
	else:
		return mydep

def dep_getcpv(mydep):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	if mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep[0]=="!":
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

def dep_expand(mydep,mydb=None,use_cache=1):
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
	return prefix+cpv_expand(mydep,mydb=mydb,use_cache=use_cache)+postfix

def dep_check(depstring,mydbapi,mysettings,use="yes",mode=None,myuse=None,use_cache=1,use_binaries=0,myroot="/"):
	"""Takes a depend string and parses the condition."""

	#check_config_instance(mysettings)

	if use=="yes":
		if myuse==None:
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
		mymasks=mysettings.usemask+archlist[:]

		while mysettings["ARCH"] in mymasks:
			del mymasks[mymasks.index(mysettings["ARCH"])]
		mysplit = portage_dep.use_reduce(mysplit,uselist=myusesplit,masklist=mymasks,matchall=(use=="all"),excludeall=[mysettings["ARCH"]])
	else:
		mysplit = portage_dep.use_reduce(mysplit,uselist=myusesplit,matchall=(use=="all"))

	# Do the || conversions
	mysplit=portage_dep.dep_opconvert(mysplit)

	#convert virtual dependencies to normal packages.
	mysplit=dep_virtual(mysplit, mysettings)
	#if mysplit==None, then we have a parse error (paren mismatch or misplaced ||)
	#up until here, we haven't needed to look at the database tree

	if mysplit==None:
		return [0,"Parse Error (parentheses mismatch?)"]
	elif mysplit==[]:
		#dependencies were reduced to nothing
		return [1,[]]
	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2==None:
		return [0,"Invalid token"]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)
	myeval=dep_eval(mysplit2)
	writemsg("myeval:   %s\n" % (myeval), 1)

	if myeval:
		return [1,[]]
	else:
		myzaps = dep_zapdeps(mysplit,mysplit2,myroot,use_binaries=use_binaries)
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

def key_expand(mykey,mydb=None,use_cache=1):
	mysplit=mykey.split("/")
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

def cpv_expand(mycpv,mydb=None,use_cache=1):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit=pkgsplit(myslash[-1])
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

def getmaskingreason(mycpv):
	from portage_util import grablines
	global portdb
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError("invalid CPV: %s" % mycpv)
	if not portdb.cpv_exists(mycpv):
		raise KeyError("CPV %s does not exist" % mycpv)
	mycp=mysplit[0]+"/"+mysplit[1]

	pmasklines = grablines(settings["PORTDIR"]+"/profiles/package.mask", recursive=1)
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

def getmaskingstatus(mycpv):
	global portdb
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
	pgroups=groups[:]
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
		return key_expand(mykey,mydb=self.dbapi)

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
	if mymatches==None:
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
			writemsg("!!! Invalid atom: %s\n" % mydep)
			return []
	else:
		operator = None

	mylist = []

	if operator == None:
		for x in candidate_list:
			xs = pkgsplit(x)
			if xs == None:
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
				writemsg("\nInvalid package name: %s\n" % x)
				sys.exit(73)
			if result == None:
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
		if cp_key==None:
			return []
	else:
		cp_key=None
	#Otherwise, this is a special call; we can only select out of the ebuilds specified in the specified mylist
	if (mydep[0]=="="):
		if cp_key==None:
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
				if cp_x==None:
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
		if cp_key==None:
			return []
		if (len(mydep)>1) and (mydep[1]=="="):
			cmpstr=mydep[0:2]
		else:
			cmpstr=mydep[0]
		mynodes=[]
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
				#invalid entry; continue.
				continue
			if cp_key[0]!=cp_x[0]:
				continue
			if eval("pkgcmp(cp_x[1:],cp_key[1:])"+cmpstr+"0"):
				mynodes.append(x)
		return mynodes
	elif mydep[0]=="~":
		if cp_key==None:
			return []
		myrev=-1
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
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
	elif cp_key==None:
		if mydep[0]=="!":
			return []
			#we check ! deps in emerge itself, so always returning [] is correct.
		mynodes=[]
		cp_key=mycpv.split("/")
		for x in mylist:
			cp_x=catpkgsplit(x)
			if cp_x==None:
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
	def __init__(self,root="/",virtual=None,clone=None):
		global portdb
		if clone:
			self.root=clone.root
			self.portroot=clone.portroot
			self.pkglines=clone.pkglines
		else:
			self.root=root
			self.portroot=settings["PORTDIR"]
			self.virtual=virtual
			self.dbapi=portdb

	def dep_bestmatch(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("bestmatch-visible",mydep)
		if mymatch==None:
			return ""
		return mymatch

	def dep_match(self,mydep):
		"compatibility method"
		mymatch=self.dbapi.xmatch("match-visible",mydep)
		if mymatch==None:
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
		mykey=key_expand(cps[0]+"/"+cps[1],mydb=self.dbapi)
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
		mydep=dep_expand(origdep,mydb=self)
		mykey=dep_getkey(mydep)
		mycat=mykey.split("/")[0]
		return match_from_list(mydep,self.cp_list(mykey,use_cache=use_cache))

	def match2(self,mydep,mykey,mylist):
		writemsg("DEPRECATED: dbapi.match2\n")
		match_from_list(mydep,mylist)

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
					writemsg("!!! BAD COUNTER in '%s'\n" % (x))
				if old_counter > min_counter:
					min_counter = old_counter

		# We write our new counter value to a new file that gets moved into
		# place to avoid filesystem corruption.
		if os.path.exists(cpath):
			cfile=open(cpath, "r")
			try:
				counter=long(cfile.readline())
			except (ValueError,OverflowError):
				try:
					counter=long(commands.getoutput("for FILE in $(find /"+VDB_PATH+" -type f -name COUNTER); do echo $(<${FILE}); done | sort -n | tail -n1 | tr -d '\n'"))
					writemsg("!!! COUNTER was corrupted; resetting to value of %d\n" % counter)
					changed=1
				except (ValueError,OverflowError):
					writemsg("!!! COUNTER data is corrupt in pkg db. The values need to be\n")
					writemsg("!!! corrected/normalized so that portage can operate properly.\n")
					writemsg("!!! A simple solution is not yet available so try #gentoo on IRC.\n")
					sys.exit(2)
			cfile.close()
		else:
			try:
				counter=long(commands.getoutput("for FILE in $(find /"+VDB_PATH+" -type f -name COUNTER); do echo $(<${FILE}); done | sort -n | tail -n1 | tr -d '\n'"))
				writemsg("!!! Global counter missing. Regenerated from counter files to: %s\n" % counter)
			except SystemExit, e:
				raise
			except:
				writemsg("!!! Initializing global counter.\n")
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
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n")
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath)



class fakedbapi(dbapi):
	"This is a dbapi to use for the emptytree function.  It's empty, but things can be added to it."
	def __init__(self):
		self.cpvdict={}
		self.cpdict={}

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
	def __init__(self,mybintree=None):
		self.bintree = mybintree
		self.cpvdict={}
		self.cpdict={}

	def aux_get(self,mycpv,wants):
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
				if myval == None:
					myval = ""
				else:
					myval = string.join(myval.split(),' ')
				mylist.append(myval)
		if "EAPI" in wants:
			idx = wants.index("EAPI")
			if not mylist[idx]:
				mylist[idx] = "0"
		return mylist


cptot=0
class vardbapi(dbapi):
	def __init__(self,root,categories=None):
		self.root       = root[:]
		#cache for category directory mtimes
		self.mtdircache = {}
		#cache for dependency checks
		self.matchcache = {}
		#cache for cp_list results
		self.cpcache    = {}
		self.blockers   = None
		self.categories = copy.deepcopy(categories)

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
					writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n")
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.pl or\n")
					writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n")
					writemsg("!!! unmerge this exact version.\n")
					writemsg("!!! %s\n" % e)
					sys.exit(1)
			else:
				writemsg("!!! COUNTER file is missing for "+str(mycpv)+" in /var/db.\n")
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.pl or\n")
				writemsg("!!! Please run /usr/lib/portage/bin/fix-db.py or\n")
				writemsg("!!! remerge the package.\n")
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
		counter=db[self.root]["vartree"].dbapi.counter_tick(self.root,mycpv=mycpv)
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
			spawn(MOVE_BINARY+" "+origpath+" "+newpath,settings, free=1)

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

		if (list==None):
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

		mycats = self.categories
		if mycats == None:
			# XXX: CIRCULAR DEP! This helps backwards compat. --NJ (10 Sept 2004)
			mycats = settings.categories

		for x in mycats:
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
		mydep=dep_expand(origdep,mydb=self,use_cache=use_cache)
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


class vartree(packagetree):
	"this tree will scan a var/db/pkg database located at root (passed to init)"
	def __init__(self,root="/",virtual=None,clone=None,categories=None):
		if clone:
			self.root       = clone.root[:]
			self.dbapi      = copy.deepcopy(clone.dbapi)
			self.populated  = 1
		else:
			self.root       = root[:]
			self.dbapi      = vardbapi(self.root,categories=categories)
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
		mymatch=best(self.dbapi.match(dep_expand(mydep,mydb=self.dbapi),use_cache=use_cache))
		if mymatch==None:
			return ""
		else:
			return mymatch

	def dep_match(self,mydep,use_cache=1):
		"compatibility method -- we want to see all matches, not just visible ones"
		#mymatch=match(mydep,self.dbapi)
		mymatch=self.dbapi.match(mydep,use_cache=use_cache)
		if mymatch==None:
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
		cpv=key_expand(cpv,mydb=self.dbapi,use_cache=use_cache)
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
		mykey=key_expand(mykey,mydb=self.dbapi,use_cache=use_cache)
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
		mykey=key_expand(mykey,mydb=self.dbapi,use_cache=use_cache)
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
			self.mysettings = config(clone=settings)

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
		self.porttree_root = porttree_root

		self.depcachedir = self.mysettings.depcachedir[:]

		self.tmpfs = self.mysettings["PORTAGE_TMPFS"]
		if self.tmpfs and not os.path.exists(self.tmpfs):
			self.tmpfs = None
		if self.tmpfs and not os.access(self.tmpfs, os.W_OK):
			self.tmpfs = None
		if self.tmpfs and not os.access(self.tmpfs, os.R_OK):
			self.tmpfs = None

		self.eclassdb = eclass_cache.cache(self.porttree_root, overlays=settings["PORTDIR_OVERLAY"].split())

		self.metadb       = {}
		self.metadbmodule = self.mysettings.load_best_module("portdbapi.metadbmodule")

		#if the portdbapi is "frozen", then we assume that we can cache everything (that no updates to it are happening)
		self.xcache={}
		self.frozen=0

		self.porttrees=[self.porttree_root]+self.mysettings["PORTDIR_OVERLAY"].split()
		self.auxdbmodule  = self.mysettings.load_best_module("portdbapi.auxdbmodule")
		self.auxdb        = {}

		# XXX: REMOVE THIS ONCE UNUSED_0 IS YANKED FROM auxdbkeys
		# ~harring
		filtered_auxdbkeys = filter(lambda x: not x.startswith("UNUSED_0"), auxdbkeys)
		for x in self.porttrees:
			# location, label, auxdbkeys
			self.auxdb[x] = self.auxdbmodule(portage_const.DEPCACHE_PATH, x, filtered_auxdbkeys, gid=portage_gid)
			
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

	def findname2(self,mycpv):
		"returns file location for this particular package and in_overlay flag"
		if not mycpv:
			return "",0
		mysplit=mycpv.split("/")

		psplit=pkgsplit(mysplit[1])
		ret=None
		if psplit:
			for x in self.porttrees:
				file=x+"/"+mysplit[0]+"/"+psplit[0]+"/"+mysplit[1]+".ebuild"
				if os.access(file, os.R_OK):
					# when found
					ret=[file, x]
		if ret:
			return ret[0], ret[1]

		# when not found
		return None, 0

	def aux_get(self, mycpv, mylist):
		"stub code for returning auxilliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or raise KeyError if error'
		global auxdbkeys,auxdbkeylen

		cat,pkg = string.split(mycpv, "/", 1)

		myebuild, mylocation=self.findname2(mycpv)

		if not myebuild:
			writemsg("!!! aux_get(): ebuild path for '%(cpv)s' not specified:\n" % {"cpv":mycpv})
			writemsg("!!!            %s\n" % myebuild)
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
				writemsg("!!! Manifest is missing or inaccessable: %(manifest)s\n" % {"manifest":myManifestPath})


		if os.access(myebuild, os.R_OK):
			emtime=os.stat(myebuild)[stat.ST_MTIME]
		else:
			writemsg("!!! aux_get(): ebuild for '%(cpv)s' does not exist at:\n" % {"cpv":mycpv})
			writemsg("!!!            %s\n" % myebuild)
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

			# XXX: Part of the gvisible hack/fix to prevent deadlock
			# XXX: through doebuild. Need to isolate this somehow...
			self.mysettings.reset()

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

			myret=doebuild(myebuild,"depend","/",self.mysettings,dbkey=mydbkey,tree="porttree")
			if myret:
				portage_locks.unlockfile(mylock)
				self.lock_held = 0
				#depend returned non-zero exit code...
				writemsg(str(red("\naux_get():")+" (0) Error in "+mycpv+" ebuild. ("+str(myret)+")\n"
				"               Check for syntax error or corruption in the ebuild. (--debug)\n\n"))
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
				  "               Check for syntax error or corruption in the ebuild. (--debug)\n\n"))
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

	def getfetchlist(self,mypkg,useflags=None,mysettings=None,all=0):
		if mysettings == None:
			mysettings = self.mysettings
		try:
			myuris = self.aux_get(mypkg,["SRC_URI"])[0]
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
		mydigest=self.finddigest(mypkg)
		checksums=digestParseFile(mydigest)
		if not checksums:
			if debug: print "[empty/missing/bad digest]: "+mypkg
			return None
		filesdict={}
		if useflags == None:
			myuris, myfiles = self.getfetchlist(mypkg,all=1)
		else:
			myuris, myfiles = self.getfetchlist(mypkg,useflags=useflags)
		#XXX: maybe this should be improved: take partial downloads
		# into account? check checksums?
		for myfile in myfiles:
			if debug and myfile not in checksums.keys():
				print "[bad digest]: missing",myfile,"for",mypkg
			elif myfile in checksums.keys():
				distfile=settings["DISTDIR"]+"/"+myfile
				if not os.access(distfile, os.R_OK):
					filesdict[myfile]=int(checksums[myfile]["size"])
		return filesdict

	def fetch_check(self, mypkg, useflags=None, mysettings=None, all=False):
		if not useflags:
			if mysettings:
				useflags = mysettings["USE"].split()
		myuri, myfiles = self.getfetchlist(mypkg, useflags=useflags, mysettings=mysettings, all=all)
		mydigest       = self.finddigest(mypkg)
		mysums         = digestParseFile(mydigest)

		failures = {}
		for x in myfiles:
			if not mysums or x not in mysums:
				ok     = False
				reason = "digest missing"
			else:
				ok,reason = portage_checksum.verify_all(self.mysettings["DISTDIR"]+"/"+x, mysums[x])
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
		if filesdict==None:
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

	def cp_list(self,mycp,use_cache=1):
		mysplit=mycp.split("/")
		d={}
		for oroot in self.porttrees:
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
			mydep=dep_expand(origdep,mydb=self)
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
		if (mylist==None) or (len(mylist)==0):
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
				if mymatches==None:
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
				if mymatches==None:
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
		global groups
		if mylist==None:
			return []
		newlist=[]

		pkgdict = self.mysettings.pkeywordsdict
		for mycpv in mylist:
			#we need to update this next line when we have fully integrated the new db api
			auxerr=0
			try:
				keys, eapi = db["/"]["porttree"].dbapi.aux_get(mycpv, ["KEYWORDS", "EAPI"])
			except (KeyError,IOError,TypeError):
				continue
			if not keys:
				# KEYWORDS=""
				#print "!!! No KEYWORDS for "+str(mycpv)+" -- Untested Status"
				continue
			mygroups=keys.split()
			pgroups=groups[:]
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
					writemsg("--- WARNING: Package '%s' uses '*' keyword.\n" % mycpv)
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
	def __init__(self,root,pkgdir,virtual=None,clone=None):

		if clone:
			# XXX This isn't cloning. It's an instance of the same thing.
			self.root=clone.root
			self.pkgdir=clone.pkgdir
			self.dbapi=clone.dbapi
			self.populated=clone.populated
			self.tree=clone.tree
			self.remotepkgs=clone.remotepkgs
			self.invalids=clone.invalids
		else:
			self.root=root
			#self.pkgdir=settings["PKGDIR"]
			self.pkgdir=pkgdir
			self.dbapi=bindbapi(self)
			self.populated=0
			self.tree={}
			self.remotepkgs={}
			self.invalids=[]

	def move_ent(self,mylist):
		if not self.populated:
			self.populate()
		origcp=mylist[1]
		newcp=mylist[2]
		# sanity check
		for cp in [origcp,newcp]:
			if not (isvalidatom(cp) and isjustname(cp)):
				raise portage_exception.InvalidPackageName(cp)
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
				writemsg("!!! Cannot update binary: Destination exists.\n")
				writemsg("!!! "+mycpv+" -> "+mynewcpv+"\n")
				continue

			tbz2path=self.getname(mycpv)
			if os.path.exists(tbz2path) and not os.access(tbz2path,os.W_OK):
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
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
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
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
				writemsg("!!! Cannot update readonly binary: "+mycpv+"\n")
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
					writemsg("!!! Invalid binary package: "+mypkg+"\n")
					writemsg("!!! This binary package is not recoverable and should be deleted.\n")
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

		if getbinpkgs and not settings["PORTAGE_BINHOST"]:
			writemsg(red("!!! PORTAGE_BINHOST unset, but use is requested.\n"))

		if getbinpkgs and settings["PORTAGE_BINHOST"] and not self.remotepkgs:
			try:
				chunk_size = long(settings["PORTAGE_BINHOST_CHUNKSIZE"])
				if chunk_size < 8:
					chunk_size = 8
			except SystemExit, e:
				raise
			except:
				chunk_size = 3000

			writemsg(green("Fetching binary packages info...\n"))
			self.remotepkgs = getbinpkg.dir_get_metadata(settings["PORTAGE_BINHOST"], chunk_size=chunk_size)
			writemsg(green("  -- DONE!\n\n"))

			for mypkg in self.remotepkgs.keys():
				if not self.remotepkgs[mypkg].has_key("CATEGORY"):
					#old-style or corrupt package
					writemsg("!!! Invalid remote binary package: "+mypkg+"\n")
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
					writemsg("!!! Failed to inject remote binary package:"+str(fullpkg)+"\n")
					del self.remotepkgs[mypkg]
					continue
		self.populated=1

	def inject(self,cpv):
		return self.dbapi.cpv_inject(cpv)

	def exists_specific(self,cpv):
		if not self.populated:
			self.populate()
		return self.dbapi.match(dep_expand("="+cpv,mydb=self.dbapi))

	def dep_bestmatch(self,mydep):
		"compatibility method -- all matches, not just visible ones"
		if not self.populated:
			self.populate()
		writemsg("\n\n", 1)
		writemsg("mydep: %s\n" % mydep, 1)
		mydep=dep_expand(mydep,mydb=self.dbapi)
		writemsg("mydep: %s\n" % mydep, 1)
		mykey=dep_getkey(mydep)
		writemsg("mykey: %s\n" % mykey, 1)
		mymatch=best(match_from_list(mydep,self.dbapi.cp_list(mykey)))
		writemsg("mymatch: %s\n" % mymatch, 1)
		if mymatch==None:
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
				writemsg("Resuming download of this tbz2, but it is possible that it is corrupt.\n")
		mydest = self.pkgdir+"/All/"
		try:
			os.makedirs(mydest, 0775)
		except SystemExit, e:
			raise
		except:
			pass
		return getbinpkg.file_get(settings["PORTAGE_BINHOST"]+"/"+tbz2name, mydest, fcmd=settings["RESUMECOMMAND"])

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
	"this class provides an interface to the standard text package database"
	def __init__(self,cat,pkg,myroot,mysettings,treetype=None):
		"create a dblink object for cat/pkg.  This dblink entry may or may not exist"
		self.cat     = cat
		self.pkg     = pkg
		self.mycpv   = self.cat+"/"+self.pkg
		self.mysplit = pkgsplit(self.mycpv)
		self.treetype = treetype

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
		self.updateprotect()
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
				mydat[1]=os.path.normpath(root+mydat[1][1:])
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

	def updateprotect(self):
		#do some config file management prep
		self.protect=[]
		for x in string.split(self.settings["CONFIG_PROTECT"]):
			ppath=normalize_path(self.myroot+x)+"/"
			if os.path.isdir(ppath):
				self.protect.append(ppath)

		self.protectmask=[]
		for x in string.split(self.settings["CONFIG_PROTECT_MASK"]):
			ppath=normalize_path(self.myroot+x)+"/"
			if os.path.isdir(ppath):
				self.protectmask.append(ppath)
			#if it doesn't exist, silently skip it

	def isprotected(self,obj):
		"""Checks if obj is in the current protect/mask directories. Returns
		0 on unprotected/masked, and 1 on protected."""
		masked=0
		protected=0
		for ppath in self.protect:
			if (len(ppath) > masked) and (obj[0:len(ppath)]==ppath):
				protected=len(ppath)
				#config file management
				for pmpath in self.protectmask:
					if (len(pmpath) >= protected) and (obj[0:len(pmpath)]==pmpath):
						#skip, it's in the mask
						masked=len(pmpath)
		return (protected > masked)

	def unmerge(self,pkgfiles=None,trimworld=1,cleanup=1):
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
			a=doebuild(myebuildpath,"prerm",self.myroot,self.settings,cleanup=cleanup,use_cache=0,tree=self.treetype)
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED prerm: "+str(a)+"\n")
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
					try:
						os.unlink(obj)
					except (OSError,IOError),e:
						pass
					writemsg_stdout("<<<        %s %s\n" % ("fif",obj))
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
		db[self.myroot]["vartree"].zap(self.mycpv)

		# New code to remove stuff from the world and virtuals files when unmerged.
		if trimworld:
			worldlist = grabfile(os.path.join(self.myroot, WORLD_FILE))
			mykey=cpv_getkey(self.mycpv)
			newworldlist=[]
			for x in worldlist:
				if dep_getkey(x)==mykey:
					matches=db[self.myroot]["vartree"].dbapi.match(x,use_cache=0)
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
			a=doebuild(myebuildpath,"postrm",self.myroot,self.settings,use_cache=0,tree=self.treetype)
			# XXX: Decide how to handle failures here.
			if a != 0:
				writemsg("!!! FAILED postrm: "+str(a)+"\n")
				sys.exit(123)
			doebuild(myebuildpath, "cleanrm", self.myroot, self.settings, tree=self.treetype)
		self.unlockdb()

	def isowner(self,filename,destroot):
		""" check if filename is a new file or belongs to this package
		(for this or a previous version)"""
		destfile = os.path.normpath(destroot+"/"+filename)
		if not os.path.exists(destfile):
			return True
		if self.getcontents() and filename in self.getcontents().keys():
			return True

		return False

	def treewalk(self,srcroot,destroot,inforoot,myebuild,cleanup=0):
		global db
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
		for v in db[self.myroot]["vartree"].dbapi.cp_list(self.mysplit[0]):
			otherversions.append(v.split("/")[1])

		# check for package collisions
		if "collision-protect" in features:
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

			for v in otherversions:
				# should we check for same SLOT here ?
				mypkglist.append(dblink(self.cat,v,destroot,self.settings))

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
					self.unmerge()
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
		a = doebuild(myebuild, "preinst", root, self.settings, cleanup=cleanup, use_cache=0, tree=self.treetype)

		# XXX: Decide how to handle failures here.
		if a != 0:
			writemsg("!!! FAILED preinst: "+str(a)+"\n")
			sys.exit(123)

		# copy "info" files (like SLOT, CFLAGS, etc.) into the database
		for x in listdir(inforoot):
			self.copyfile(inforoot+"/"+x)

		# get current counter value (counter_tick also takes care of incrementing it)
		# XXX Need to make this destroot, but it needs to be initialized first. XXX
		# XXX bis: leads to some invalidentry() call through cp_all().
		counter = db["/"]["vartree"].dbapi.counter_tick(self.myroot,mycpv=self.mycpv)
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

		writemsg_stdout(">>> Safely unmerging already-installed instance...\n")
		self.dbdir = self.dbpkgdir
		self.unmerge(oldcontents,trimworld=0)
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

		mylock = portage_locks.lockfile(os.path.join(destroot, CONFIG_MEMORY_FILE))
		writedict(cfgfiledict, os.path.join(destroot, CONFIG_MEMORY_FILE))
		portage_locks.unlockfile(mylock)

		#do postinst script
		a = doebuild(myebuild, "postinst", root, self.settings, use_cache=0, tree=self.treetype)

		# XXX: Decide how to handle failures here.
		if a != 0:
			writemsg("!!! FAILED postinst: "+str(a)+"\n")
			sys.exit(123)

		downgrade = False
		for v in otherversions:
			if pkgcmp(catpkgsplit(self.pkg)[1:], catpkgsplit(v)[1:]) < 0:
				downgrade = True

		#update environment settings, library paths. DO NOT change symlinks.
		env_update(makelinks=(not downgrade))
		#dircache may break autoclean because it remembers the -MERGING-pkg file
		global dircache
		if dircache.has_key(self.dbcatdir):
			del dircache[self.dbcatdir]
		writemsg_stdout(">>> %s %s\n" % (self.mycpv,"merged."))

		# Process ebuild logfiles
		elog_process(self.mycpv, self.settings)
		doebuild(myebuild, "clean", root, self.settings, tree=self.treetype)
		return 0

	def mergeme(self,srcroot,destroot,outfile,secondhand,stufftomerge,cfgfiledict,thismtime):
		srcroot=os.path.normpath("///"+srcroot)+"/"
		destroot=os.path.normpath("///"+destroot)+"/"
		# this is supposed to merge a list of files.  There will be 2 forms of argument passing.
		if type(stufftomerge)==types.StringType:
			#A directory is specified.  Figure out protection paths, listdir() it and process it.
			mergelist=listdir(srcroot+stufftomerge)
			offset=stufftomerge
			# We need mydest defined up here to calc. protection paths.  This is now done once per
			# directory rather than once per file merge.  This should really help merge performance.
			# Trailing / ensures that protects/masks with trailing /'s match.
			mytruncpath="/"+offset+"/"
			myppath=self.isprotected(mytruncpath)
		else:
			mergelist=stufftomerge
			offset=""
		for x in mergelist:
			mysrc=os.path.normpath("///"+srcroot+offset+x)
			mydest=os.path.normpath("///"+destroot+offset+x)
			# myrealdest is mydest without the $ROOT prefix (makes a difference if ROOT!="/")
			myrealdest="/"+offset+x
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
				writemsg(red("!!!        File:  ")+str(mysrc)+"\n")
				writemsg(red("!!!        Error: ")+str(e)+"\n")
				sys.exit(1)
			except Exception, e:
				writemsg("\n")
				writemsg(red("!!! ERROR: An unknown error has occurred during the merge process.\n"))
				writemsg(red("!!!        A stat call returned the following error for the following file:"))
				writemsg(    "!!!        Please ensure that your filesystem is intact, otherwise report\n")
				writemsg(    "!!!        this as a portage bug at bugs.gentoo.org. Append 'emerge info'.\n")
				writemsg(    "!!!        File:  "+str(mysrc)+"\n")
				writemsg(    "!!!        Error: "+str(e)+"\n")
				sys.exit(1)


			mymode=mystat[stat.ST_MODE]
			# handy variables; mydest is the target object on the live filesystems;
			# mysrc is the source object in the temporary install dir
			try:
				mydmode=os.lstat(mydest)[stat.ST_MODE]
			except SystemExit, e:
				raise
			except:
				#dest file doesn't exist
				mydmode=None

			if stat.S_ISLNK(mymode):
				# we are merging a symbolic link
				myabsto=abssymlink(mysrc)
				if myabsto[0:len(srcroot)]==srcroot:
					myabsto=myabsto[len(srcroot):]
					if myabsto[0]!="/":
						myabsto="/"+myabsto
				myto=os.readlink(mysrc)
				if self.settings and self.settings["D"]:
					if myto.find(self.settings["D"])==0:
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
						srctarget = os.path.normpath(os.path.dirname(mysrc)+"/"+myto)
						if os.path.exists(mysrc) and stat.S_ISDIR(os.stat(mysrc)[stat.ST_MODE]):
							# Kill file blocking installation of symlink to dir #71787
							pass
						elif self.isprotected(mydest):
							# Use md5 of the target in ${D} if it exists...
							if os.path.exists(os.path.normpath(srcroot+myabsto)):
								mydest = new_protect_filename(myrealdest, newmd5=portage_checksum.perform_md5(srcroot+myabsto))
							else:
								mydest = new_protect_filename(myrealdest, newmd5=portage_checksum.perform_md5(myabsto))

				# if secondhand==None it means we're operating in "force" mode and should not create a second hand.
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
						if(bsd_chflags.lchflags(mydest, 0)<0):
							writemsg("!!! Couldn't clear flags on '"+mydest+"'.\n")

					if not os.access(mydest, os.W_OK):
						pkgstuff = pkgsplit(self.pkg)
						writemsg("\n!!! Cannot write to '"+mydest+"'.\n")
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
						if movefile(mydest,mydest+".backup", mysettings=self.settings) == None:
							sys.exit(1)
						print "bak",mydest,mydest+".backup"
						#now create our directory
						if selinux_enabled:
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
					if selinux_enabled:
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
				if self.mergeme(srcroot,destroot,outfile,secondhand,offset+x+"/",cfgfiledict,thismtime):
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
							mydest = new_protect_filename(myrealdest, newmd5=mymd5)

				# whether config protection or not, we merge the new file the
				# same way.  Unless moveme=0 (blocking directory)
				if moveme:
					mymtime=movefile(mysrc,mydest,newmtime=thismtime,sstat=mystat, mysettings=self.settings)
					if mymtime == None:
						sys.exit(1)
					zing=">>>"
				else:
					mymtime=thismtime
					# We need to touch the destination so that on --update the
					# old package won't yank the file with it. (non-cfgprot related)
					os.utime(myrealdest,(thismtime,thismtime))
					zing="---"
				if self.settings["USERLAND"] == "Darwin" and myrealdest[-2:] == ".a":

					# XXX kludge, can be killed when portage stops relying on
					# md5+mtime, and uses refcounts
					# alright, we've fooled w/ mtime on the file; this pisses off static archives
					# basically internal mtime != file's mtime, so the linker (falsely) thinks
					# the archive is stale, and needs to have it's toc rebuilt.

					myf=open(myrealdest,"r+")

					# ar mtime field is digits padded with spaces, 12 bytes.
					lms=str(thismtime+5).ljust(12)
					myf.seek(0)
					magic=myf.read(8)
					if magic != "!<arch>\n":
						# not an archive (dolib.a from portage.py makes it here fex)
						myf.close()
					else:
						st=os.stat(myrealdest)
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
						mymd5=portage_checksum.perform_md5(myrealdest,calc_prelink=1)
					os.utime(myrealdest,(thismtime,thismtime))

				if mymtime!=None:
					zing=">>>"
					outfile.write("obj "+myrealdest+" "+mymd5+" "+str(mymtime)+"\n")
				writemsg_stdout("%s %s\n" % (zing,mydest))
			else:
				# we are merging a fifo or device node
				zing="!!!"
				if mydmode==None:
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

	def merge(self,mergeroot,inforoot,myroot,myebuild=None,cleanup=0):
		return self.treewalk(mergeroot,myroot,inforoot,myebuild,cleanup=cleanup)

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
		myfile=open(self.dbdir+"/"+fname,"w")
		myfile.write(data)
		myfile.close()

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

def cleanup_pkgmerge(mypkg,origdir):
	shutil.rmtree(settings["PORTAGE_TMPDIR"]+"/binpkgs/"+mypkg)
	if os.path.exists(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment"):
		os.unlink(settings["PORTAGE_TMPDIR"]+"/portage/"+mypkg+"/temp/environment")
	os.chdir(origdir)

def pkgmerge(mytbz2,myroot,mysettings):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""
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
	a = doebuild(myebuild, "setup", myroot, mysettings, tree="bintree", cleanup=1)
	writemsg_stdout(">>> Extracting %s\n" % mypkg)
	notok=spawn("bzip2 -dqc -- '"+mytbz2+"' | tar xpf -",mysettings,free=1)
	if notok:
		print "!!! Error Extracting",mytbz2
		cleanup_pkgmerge(mypkg,origdir)
		return None

	# the merge takes care of pre/postinst and old instance
	# auto-unmerge, virtual/provides updates, etc.
	mysettings.load_infodir(infloc)
	mylink=dblink(mycat,mypkg,myroot,mysettings,treetype="bintree")
	mylink.merge(pkgloc,infloc,myroot,myebuild,cleanup=1)

	if not os.path.exists(infloc+"/RDEPEND"):
		returnme=""
	else:
		#get runtime dependencies
		a=open(infloc+"/RDEPEND","r")
		returnme=string.join(string.split(a.read())," ")
		a.close()
	cleanup_pkgmerge(mypkg,origdir)
	return returnme


if os.environ.has_key("ROOT"):
	root=os.environ["ROOT"]
	if not len(root):
		root="/"
	elif root[-1]!="/":
		root=root+"/"
else:
	root="/"
if root != "/":
	if not os.path.exists(root[:-1]):
		writemsg("!!! Error: ROOT "+root+" does not exist.  Please correct this.\n")
		writemsg("!!! Exiting.\n\n")
		sys.exit(1)
	elif not os.path.isdir(root[:-1]):
		writemsg("!!! Error: ROOT "+root[:-1]+" is not a directory. Please correct this.\n")
		writemsg("!!! Exiting.\n\n")
		sys.exit(1)

#create tmp and var/tmp if they don't exist; read config
os.umask(0)
if not os.path.exists(root+"tmp"):
	writemsg(">>> "+root+"tmp doesn't exist, creating it...\n")
	os.mkdir(root+"tmp",01777)
if not os.path.exists(root+"var/tmp"):
	writemsg(">>> "+root+"var/tmp doesn't exist, creating it...\n")
	try:
		os.mkdir(root+"var",0755)
	except (OSError,IOError):
		pass
	try:
		os.mkdir(root+"var/tmp",01777)
	except SystemExit, e:
		raise
	except:
		writemsg("portage: couldn't create /var/tmp; exiting.\n")
		sys.exit(1)
if not os.path.exists(root+"var/lib/portage"):
	writemsg(">>> "+root+"var/lib/portage doesn't exist, creating it...\n")
	try:
		os.mkdir(root+"var",0755)
	except (OSError,IOError):
		pass
	try:
		os.mkdir(root+"var/lib",0755)
	except (OSError,IOError):
		pass
	try:
		os.mkdir(root+"var/lib/portage",02750)
	except SystemExit, e:
		raise
	except:
		writemsg("portage: couldn't create /var/lib/portage; exiting.\n")
		sys.exit(1)


#####################################
# Deprecation Checks

os.umask(022)
profiledir=None
if os.path.isdir(PROFILE_PATH):
	profiledir = PROFILE_PATH
	if "PORTAGE_CALLER" in os.environ and os.environ["PORTAGE_CALLER"] == "emerge" and os.access(DEPRECATED_PROFILE_FILE, os.R_OK):
		deprecatedfile = open(DEPRECATED_PROFILE_FILE, "r")
		dcontent = deprecatedfile.readlines()
		deprecatedfile.close()
		newprofile = dcontent[0]
		writemsg(red("\n!!! Your current profile is deprecated and not supported anymore.\n"))
		writemsg(red("!!! Please upgrade to the following profile if possible:\n"))
		writemsg(8*" "+green(newprofile)+"\n")
		if len(dcontent) > 1:
			writemsg("To upgrade do the following steps:\n")
			for myline in dcontent[1:]:
				writemsg(myline)
			writemsg("\n\n")

if os.path.exists(USER_VIRTUALS_FILE):
	writemsg(red("\n!!! /etc/portage/virtuals is deprecated in favor of\n"))
	writemsg(red("!!! /etc/portage/profile/virtuals. Please move it to\n"))
	writemsg(red("!!! this new location.\n\n"))

#
#####################################

db={}

# =============================================================================
# =============================================================================
# -----------------------------------------------------------------------------
# We're going to lock the global config to prevent changes, but we need
# to ensure the global settings are right.
settings=config(config_profile_path=PROFILE_PATH,config_incrementals=portage_const.INCREMENTALS)

# useful info
settings["PORTAGE_MASTER_PID"]=str(os.getpid())
settings.backup_changes("PORTAGE_MASTER_PID")
# We are disabling user-specific bashrc files.
settings["BASH_ENV"] = INVALID_ENV_FILE
settings.backup_changes("BASH_ENV")

# gets virtual package settings
def getvirtuals(myroot):
	global settings
	writemsg("--- DEPRECATED call to getvirtual\n")
	return settings.getvirtuals(myroot)

def do_vartree(mysettings):
	global virts,virts_p
	virts=mysettings.getvirtuals("/")
	virts_p={}

	if virts:
		myvkeys=virts.keys()
		for x in myvkeys:
			vkeysplit=x.split("/")
			if not virts_p.has_key(vkeysplit[1]):
				virts_p[vkeysplit[1]]=virts[x]
	db["/"]={"virtuals":virts,"vartree":vartree("/",virts)}
	if root!="/":
		virts=mysettings.getvirtuals(root)
		db[root]={"virtuals":virts,"vartree":vartree(root,virts)}
	#We need to create the vartree first, then load our settings, and then set up our other trees

usedefaults=settings.use_defs

# XXX: This is a circular fix.
#do_vartree(settings)
#settings.loadVirtuals('/')
do_vartree(settings)
#settings.loadVirtuals('/')

settings.reset() # XXX: Regenerate use after we get a vartree -- GLOBAL


# XXX: Might cause problems with root="/" assumptions
portdb=portdbapi(settings["PORTDIR"])

settings.lock()
# -----------------------------------------------------------------------------
# =============================================================================
# =============================================================================


if 'selinux' in settings["USE"].split(" "):
	try:
		import selinux
		if hasattr(selinux, "enabled"):
			selinux_enabled = selinux.enabled
		else:
			selinux_enabled = 1
	except OSError, e:
		writemsg(red("!!! SELinux not loaded: ")+str(e)+"\n")
		selinux_enabled=0
	except ImportError:
		writemsg(red("!!! SELinux module not found.")+" Please verify that it was installed.\n")
		selinux_enabled=0
	if selinux_enabled == 0:
		try:	
			del sys.modules["selinux"]
		except KeyError:
			pass
else:
	selinux_enabled=0

cachedirs=[CACHE_PATH]
if root!="/":
	cachedirs.append(root+CACHE_PATH)
if not os.environ.has_key("SANDBOX_ACTIVE"):
	for cachedir in cachedirs:
		if not os.path.exists(cachedir):
			os.makedirs(cachedir,0755)
			writemsg(">>> "+cachedir+" doesn't exist, creating it...\n")
		if not os.path.exists(cachedir+"/dep"):
			os.makedirs(cachedir+"/dep",2755)
			writemsg(">>> "+cachedir+"/dep doesn't exist, creating it...\n")
		try:
			os.chown(cachedir,uid,portage_gid)
			os.chmod(cachedir,0775)
		except OSError:
			pass
		try:
			mystat=os.lstat(cachedir+"/dep")
			os.chown(cachedir+"/dep",uid,portage_gid)
			os.chmod(cachedir+"/dep",02775)
			if mystat[stat.ST_GID]!=portage_gid:
				spawn("chown -R "+str(uid)+":"+str(portage_gid)+" "+cachedir+"/dep",settings,free=1)
				spawn("chmod -R u+rw,g+rw "+cachedir+"/dep",settings,free=1)
		except OSError:
			pass

def flushmtimedb(record):
	if mtimedb:
		if record in mtimedb.keys():
			del mtimedb[record]
			#print "mtimedb["+record+"] is cleared."
		else:
			writemsg("Invalid or unset record '"+record+"' in mtimedb.\n")

#grab mtimes for eclasses and upgrades
mtimedb={}
mtimedbkeys=[
"updates", "info",
"version", "starttime",
"resume", "resume_backup",
"ldpath"
]
mtimedbfile=root+"var/cache/edb/mtimedb"
try:
	mypickle=cPickle.Unpickler(open(mtimedbfile))
	mypickle.find_global=None
	mtimedb=mypickle.load()
	if mtimedb.has_key("old"):
		mtimedb["updates"]=mtimedb["old"]
		del mtimedb["old"]
	if mtimedb.has_key("cur"):
		del mtimedb["cur"]
except SystemExit, e:
	raise
except:
	#print "!!!",e
	mtimedb={"updates":{},"version":"","starttime":0}

for x in mtimedb.keys():
	if x not in mtimedbkeys:
		writemsg("Deleting invalid mtimedb key: "+str(x)+"\n")
		del mtimedb[x]

#,"porttree":portagetree(root,virts),"bintree":binarytree(root,virts)}
features=settings["FEATURES"].split()

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

def commit_mtimedb():
	if mtimedb:
	# Store mtimedb
		mymfn=mtimedbfile
		f = None
		try:
			mtimedb["version"]=VERSION
			f = atomic_ofstream(mymfn)
			cPickle.dump(mtimedb, f, -1)
			f.close()
		except SystemExit, e:
			raise
		except Exception, e:
			if f is not None:
				f.abort()

		try:
			os.chown(mymfn,uid,portage_gid)
			os.chmod(mymfn,0664)
		except SystemExit, e:
			raise
		except Exception, e:
			pass

def portageexit():
	global uid,portage_gid,portdb,db
	if secpass and not os.environ.has_key("SANDBOX_ACTIVE"):
		close_portdbapi_caches()
		commit_mtimedb()

atexit_register(portageexit)

def update_config_files(update_iter):
	"""Perform global updates on /etc/portage/package.* and the world file."""
	update_files={}
	file_contents={}
	myxfiles = ["package.mask","package.unmask","package.keywords","package.use"]
	myxfiles.extend(prefix_array(myxfiles, "profile/"))
	recursivefiles = []
	for x in myxfiles:
		if os.path.isdir(USER_CONFIG_PATH+os.path.sep+x):
			recursivefiles.extend([x+os.path.sep+y for y in listdir(USER_CONFIG_PATH+os.path.sep+x, filesonly=1, recursive=1)])
		else:
			recursivefiles.append(x)
	myxfiles = recursivefiles
	for x in myxfiles:
		try:
			myfile = open(USER_CONFIG_PATH+os.path.sep+x,"r")
			file_contents[x] = myfile.readlines()
			myfile.close()
		except IOError:
			if file_contents.has_key(x):
				del file_contents[x]
			continue
	worldlist = grabfile(os.path.join("/", WORLD_FILE))

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

	write_atomic(os.path.join("/", WORLD_FILE), "\n".join(worldlist))

	for x in update_files:
		mydblink = dblink('','','/',settings)
		updating_file = os.path.join(USER_CONFIG_PATH, x)
		if mydblink.isprotected(updating_file):
			updating_file = new_protect_filename(updating_file)[0]
		try:
			write_atomic(updating_file, "".join(file_contents[x]))
		except IOError:
			continue

def global_updates():
	updpath = os.path.join(settings["PORTDIR"], "profiles", "updates")
	if not mtimedb.has_key("updates"):
		mtimedb["updates"] = {}
	try:
		if settings["PORTAGE_CALLER"] == "fixpackages":
			update_data = grab_updates(updpath)
		else:
			update_data = grab_updates(updpath, mtimedb["updates"])
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
					writemsg("%s\n" % msg)
		update_config_files(myupd)

		db["/"]["bintree"] = binarytree("/", settings["PKGDIR"], virts)
		for update_cmd in myupd:
			if update_cmd[0] == "move":
				db["/"]["vartree"].dbapi.move_ent(update_cmd)
				db["/"]["bintree"].move_ent(update_cmd)
			elif update_cmd[0] == "slotmove":
				db["/"]["vartree"].dbapi.move_slot_ent(update_cmd)
				db["/"]["bintree"].move_slot_ent(update_cmd)

		# The above global updates proceed quickly, so they
		# are considered a single mtimedb transaction.
		if len(timestamps) > 0:
			# We do not update the mtime in the mtimedb
			# until after _all_ of the above updates have
			# been processed because the mtimedb will
			# automatically commit when killed by ctrl C.
			for mykey, mtime in timestamps.iteritems():
				mtimedb["updates"][mykey] = mtime
			commit_mtimedb()

		# We gotta do the brute force updates for these now.
		if settings["PORTAGE_CALLER"] == "fixpackages" or \
		"fixpackages" in features:
			db["/"]["bintree"].update_ents(myupd)
		else:
			do_upgrade_packagesmessage = 1

		# Update progress above is indicated by characters written to stdout so
		# we print a couple new lines here to separate the progress output from
		# what follows.
		print
		print

		#make sure our internal databases are consistent; recreate our virts and vartree
		do_vartree(settings)
		if do_upgrade_packagesmessage and \
			listdir(os.path.join(settings["PKGDIR"], "All"), EmptyOnError=1):
			writemsg_stdout(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the")
			writemsg_stdout("\n    tbz2's in the packages directory. "+bold("Note: This can take a very long time."))
			writemsg_stdout("\n")

if (secpass==2) and (not os.environ.has_key("SANDBOX_ACTIVE")):
	if settings["PORTAGE_CALLER"] in ["emerge","fixpackages"]:
		#only do this if we're root and not running repoman/ebuild digest
		global_updates()

#continue setting up other trees
db["/"]["porttree"]=portagetree("/",virts)
db["/"]["bintree"]=binarytree("/",settings["PKGDIR"],virts)
if root!="/":
	db[root]["porttree"]=portagetree(root,virts)
	db[root]["bintree"]=binarytree(root,settings["PKGDIR"],virts)

profileroots = [settings["PORTDIR"]+"/profiles/"]
for x in settings["PORTDIR_OVERLAY"].split():
	profileroots.insert(0, x+"/profiles/")
thirdparty_lists = [grabdict(os.path.join(x, "thirdpartymirrors")) for x in profileroots]
thirdpartymirrors = stack_dictlist(thirdparty_lists, incremental=True)

if not os.path.exists(settings["PORTAGE_TMPDIR"]):
	writemsg("portage: the directory specified in your PORTAGE_TMPDIR variable, \""+settings["PORTAGE_TMPDIR"]+",\"\n")
	writemsg("does not exist.  Please create this directory or correct your PORTAGE_TMPDIR setting.\n")
	sys.exit(1)
if not os.path.isdir(settings["PORTAGE_TMPDIR"]):
	writemsg("portage: the directory specified in your PORTAGE_TMPDIR variable, \""+settings["PORTAGE_TMPDIR"]+",\"\n")
	writemsg("is not a directory.  Please correct your PORTAGE_TMPDIR setting.\n")
	sys.exit(1)

# COMPATABILITY -- This shouldn't be used.
pkglines = settings.packages

groups = settings["ACCEPT_KEYWORDS"].split()
archlist = flatten([[myarch, "~"+myarch] for myarch in settings["PORTAGE_ARCHLIST"].split()])

for group in groups:
	if not archlist:
		writemsg("--- 'profiles/arch.list' is empty or not available. Empty portage tree?\n")
		break
	elif (group not in archlist) and group[0]!='-':
		writemsg("\n"+red("!!! INVALID ACCEPT_KEYWORDS: ")+str(group)+"\n")

# Clear the cache
dircache={}

if not os.path.islink(PROFILE_PATH) and os.path.exists(settings["PORTDIR"]+"/profiles"):
	writemsg(red("\a\n\n!!! "+PROFILE_PATH+" is not a symlink and will probably prevent most merges.\n"))
	writemsg(red("!!! It should point into a profile within %s/profiles/\n" % settings["PORTDIR"]))
	writemsg(red("!!! (You can safely ignore this message when syncing. It's harmless.)\n\n\n"))
	time.sleep(3)

# ============================================================================
# ============================================================================

