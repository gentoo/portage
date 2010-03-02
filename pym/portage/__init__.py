# portage.py -- core Portage functionality
# Copyright 1998-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from __future__ import print_function

VERSION="$Rev$"[6:-2] + "-svn"

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

try:
	import sys
	import codecs
	import copy
	import errno
	if not hasattr(errno, 'ESTALE'):
		# ESTALE may not be defined on some systems, such as interix.
		errno.ESTALE = -1
	import logging
	import re
	import time
	import types
	try:
		import cPickle as pickle
	except ImportError:
		import pickle

	import stat
	try:
		from subprocess import getstatusoutput as subprocess_getstatusoutput
	except ImportError:
		from commands import getstatusoutput as subprocess_getstatusoutput

	try:
		from io import StringIO
	except ImportError:
		# Needed for python-2.6 with USE=build since
		# io imports threading which imports thread
		# which is unavailable.
		from StringIO import StringIO

	from time import sleep
	from random import shuffle
	from itertools import chain
	import platform
	import warnings

	# Temporarily delete these imports, to ensure that only the
	# wrapped versions are imported by portage internals.
	import os
	del os
	import shutil
	del shutil

except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete python imports. These are internal modules for\n")
	sys.stderr.write("!!! python and failure here indicates that you have a problem with python\n")
	sys.stderr.write("!!! itself and thus portage is not able to continue processing.\n\n")

	sys.stderr.write("!!! You might consider starting python with verbose flags to see what has\n")
	sys.stderr.write("!!! gone wrong. Here is the information we got for this exception:\n")
	sys.stderr.write("    "+str(e)+"\n\n");
	raise

try:

	try:
		from collections import OrderedDict
	except ImportError:
		from portage.cache.mappings import OrderedDict

	from portage.cache.cache_errors import CacheError
	import portage.proxy.lazyimport
	import portage.proxy as proxy
	proxy.lazyimport.lazyimport(globals(),
		'portage.checksum',
		'portage.checksum:perform_checksum,perform_md5,prelink_capable',
		'portage.cvstree',
		'portage.data',
		'portage.data:lchown,ostype,portage_gid,portage_uid,secpass,' + \
			'uid,userland,userpriv_groups,wheelgid',
		'portage.dbapi',
		'portage.dbapi.bintree:bindbapi,binarytree',
		'portage.dbapi.porttree:close_portdbapi_caches,FetchlistDict,' + \
			'portagetree,portdbapi',
		'portage.dbapi.vartree:vardbapi,vartree,dblink',
		'portage.dbapi.virtual:fakedbapi',
		'portage.dep',
		'portage.dep:best_match_to_list,dep_getcpv,dep_getkey,' + \
			'flatten,get_operator,isjustname,isspecific,isvalidatom,' + \
			'match_from_list,match_to_list',
		'portage.eclass_cache',
		'portage.env.loaders',
		'portage.exception',
		'portage.getbinpkg',
		'portage.locks',
		'portage.locks:lockdir,lockfile,unlockdir,unlockfile',
		'portage.mail',
		'portage.output',
		'portage.output:bold,colorize',
		'portage.package.ebuild.config:autouse,best_from_dict,' + \
			'check_config_instance,config',
		'portage.process',
		'portage.process:atexit_register,run_exitfuncs',
		'portage.update:dep_transform,fixdbentries,grab_updates,' + \
			'parse_updates,update_config_files,update_dbentries,' + \
			'update_dbentry',
		'portage.util',
		'portage.util:atomic_ofstream,apply_secpass_permissions,' + \
			'apply_recursive_permissions,dump_traceback,getconfig,' + \
			'grabdict,grabdict_package,grabfile,grabfile_package,' + \
			'map_dictlist_vals,new_protect_filename,normalize_path,' + \
			'pickle_read,pickle_write,stack_dictlist,stack_dicts,' + \
			'stack_lists,unique_array,varexpand,writedict,writemsg,' + \
			'writemsg_stdout,write_atomic',
		'portage.util.digraph:digraph',
		'portage.versions',
		'portage.versions:best,catpkgsplit,catsplit,cpv_getkey,' + \
			'cpv_getkey@getCPFromCPV,endversion_keys,' + \
			'suffix_value@endversion,pkgcmp,pkgsplit,vercmp,ververify',
		'portage.xpak',
	)

	import portage.const
	from portage.const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
		USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
		PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
		EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
		MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
		DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
		INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
		INCREMENTALS, EAPI, MISC_SH_BINARY, REPO_NAME_LOC, REPO_NAME_FILE

	from portage.localization import _

except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the\n")
	sys.stderr.write("!!! portage tree under '/usr/portage/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise

if sys.hexversion >= 0x3000000:
	basestring = str
	long = int

# Assume utf_8 fs encoding everywhere except in merge code, where the
# user's locale is respected.
_encodings = {
	'content'                : 'utf_8',
	'fs'                     : 'utf_8',
	'merge'                  : sys.getfilesystemencoding(),
	'repo.content'           : 'utf_8',
	'stdio'                  : 'utf_8',
}

# This can happen if python is built with USE=build (stage 1).
if _encodings['merge'] is None:
	_encodings['merge'] = 'ascii'

if sys.hexversion >= 0x3000000:
	def _unicode_encode(s, encoding=_encodings['content'], errors='backslashreplace'):
		if isinstance(s, str):
			s = s.encode(encoding, errors)
		return s

	def _unicode_decode(s, encoding=_encodings['content'], errors='replace'):
		if isinstance(s, bytes):
			s = str(s, encoding=encoding, errors=errors)
		return s
else:
	def _unicode_encode(s, encoding=_encodings['content'], errors='backslashreplace'):
		if isinstance(s, unicode):
			s = s.encode(encoding, errors)
		return s

	def _unicode_decode(s, encoding=_encodings['content'], errors='replace'):
		if isinstance(s, bytes):
			s = unicode(s, encoding=encoding, errors=errors)
		return s

class _unicode_func_wrapper(object):
	"""
	Wraps a function, converts arguments from unicode to bytes,
	and return values to unicode from bytes. Function calls
	will raise UnicodeEncodeError if an argument fails to be
	encoded with the required encoding. Return values that
	are single strings are decoded with errors='replace'. Return 
	values that are lists of strings are decoded with errors='strict'
	and elements that fail to be decoded are omitted from the returned
	list.
	"""
	__slots__ = ('_func', '_encoding')

	def __init__(self, func, encoding=_encodings['fs']):
		self._func = func
		self._encoding = encoding

	def __call__(self, *args, **kwargs):

		encoding = self._encoding
		wrapped_args = [_unicode_encode(x, encoding=encoding, errors='strict')
			for x in args]
		if kwargs:
			wrapped_kwargs = dict(
				(k, _unicode_encode(v, encoding=encoding, errors='strict'))
				for k, v in kwargs.items())
		else:
			wrapped_kwargs = {}

		rval = self._func(*wrapped_args, **wrapped_kwargs)

		if isinstance(rval, (list, tuple)):
			decoded_rval = []
			for x in rval:
				try:
					x = _unicode_decode(x, encoding=encoding, errors='strict')
				except UnicodeDecodeError:
					pass
				else:
					decoded_rval.append(x)

			if isinstance(rval, tuple):
				rval = tuple(decoded_rval)
			else:
				rval = decoded_rval
		else:
			rval = _unicode_decode(rval, encoding=encoding, errors='replace')

		return rval

class _unicode_module_wrapper(object):
	"""
	Wraps a module and wraps all functions with _unicode_func_wrapper.
	"""
	__slots__ = ('_mod', '_encoding', '_overrides', '_cache')

	def __init__(self, mod, encoding=_encodings['fs'], overrides=None, cache=True):
		object.__setattr__(self, '_mod', mod)
		object.__setattr__(self, '_encoding', encoding)
		object.__setattr__(self, '_overrides', overrides)
		if cache:
			cache = {}
		else:
			cache = None
		object.__setattr__(self, '_cache', cache)

	def __getattribute__(self, attr):
		cache = object.__getattribute__(self, '_cache')
		if cache is not None:
			result = cache.get(attr)
			if result is not None:
				return result
		result = getattr(object.__getattribute__(self, '_mod'), attr)
		encoding = object.__getattribute__(self, '_encoding')
		overrides = object.__getattribute__(self, '_overrides')
		override = None
		if overrides is not None:
			override = overrides.get(id(result))
		if override is not None:
			result = override
		elif isinstance(result, type):
			pass
		elif type(result) is types.ModuleType:
			result = _unicode_module_wrapper(result,
				encoding=encoding, overrides=overrides)
		elif hasattr(result, '__call__'):
			result = _unicode_func_wrapper(result, encoding=encoding)
		if cache is not None:
			cache[attr] = result
		return result

import os as _os
_os_overrides = {
	id(_os.fdopen)        : _os.fdopen,
	id(_os.popen)         : _os.popen,
	id(_os.read)          : _os.read,
	id(_os.system)        : _os.system,
}

if hasattr(_os, 'statvfs'):
	_os_overrides[id(_os.statvfs)] = _os.statvfs

os = _unicode_module_wrapper(_os, overrides=_os_overrides,
	encoding=_encodings['fs'])
_os_merge = _unicode_module_wrapper(_os,
	encoding=_encodings['merge'], overrides=_os_overrides)

import shutil as _shutil
shutil = _unicode_module_wrapper(_shutil, encoding=_encodings['fs'])

# Imports below this point rely on the above unicode wrapper definitions.
try:
	import portage._selinux
	selinux = _unicode_module_wrapper(_selinux,
		encoding=_encodings['fs'])
	_selinux_merge = _unicode_module_wrapper(_selinux,
		encoding=_encodings['merge'])
except (ImportError, OSError) as e:
	if isinstance(e, OSError):
		sys.stderr.write("!!! SELinux not loaded: %s\n" % str(e))
	del e
	_selinux = None
	selinux = None
	_selinux_merge = None

from portage.manifest import Manifest

# ===========================================================================
# END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END OF IMPORTS -- END
# ===========================================================================

def _gen_missing_encodings(missing_encodings):

	encodings = {}

	if 'ascii' in missing_encodings:

		class AsciiIncrementalEncoder(codecs.IncrementalEncoder):
			def encode(self, input, final=False):
				return codecs.ascii_encode(input, self.errors)[0]

		class AsciiIncrementalDecoder(codecs.IncrementalDecoder):
			def decode(self, input, final=False):
				return codecs.ascii_decode(input, self.errors)[0]

		class AsciiStreamWriter(codecs.StreamWriter):
			encode = codecs.ascii_encode

		class AsciiStreamReader(codecs.StreamReader):
			decode = codecs.ascii_decode

		codec_info =  codecs.CodecInfo(
			name='ascii',
			encode=codecs.ascii_encode,
			decode=codecs.ascii_decode,
			incrementalencoder=AsciiIncrementalEncoder,
			incrementaldecoder=AsciiIncrementalDecoder,
			streamwriter=AsciiStreamWriter,
			streamreader=AsciiStreamReader,
		)

		for alias in ('ascii', '646', 'ansi_x3.4_1968', 'ansi_x3_4_1968',
			'ansi_x3.4_1986', 'cp367', 'csascii', 'ibm367', 'iso646_us',
			'iso_646.irv_1991', 'iso_ir_6', 'us', 'us_ascii'):
			encodings[alias] = codec_info

	if 'utf_8' in missing_encodings:

		def utf8decode(input, errors='strict'):
			return codecs.utf_8_decode(input, errors, True)

		class Utf8IncrementalEncoder(codecs.IncrementalEncoder):
			def encode(self, input, final=False):
				return codecs.utf_8_encode(input, self.errors)[0]

		class Utf8IncrementalDecoder(codecs.BufferedIncrementalDecoder):
			_buffer_decode = codecs.utf_8_decode

		class Utf8StreamWriter(codecs.StreamWriter):
			encode = codecs.utf_8_encode

		class Utf8StreamReader(codecs.StreamReader):
			decode = codecs.utf_8_decode

		codec_info = codecs.CodecInfo(
			name='utf-8',
			encode=codecs.utf_8_encode,
			decode=utf8decode,
			incrementalencoder=Utf8IncrementalEncoder,
			incrementaldecoder=Utf8IncrementalDecoder,
			streamreader=Utf8StreamReader,
			streamwriter=Utf8StreamWriter,
		)

		for alias in ('utf_8', 'u8', 'utf', 'utf8', 'utf8_ucs2', 'utf8_ucs4'):
			encodings[alias] = codec_info

	return encodings

def _ensure_default_encoding():
	"""
	The python that's inside stage 1 or 2 is built with a minimal
	configuration which does not include the /usr/lib/pythonX.Y/encodings
	directory. This results in error like the following:

	  LookupError: no codec search functions registered: can't find encoding

	In order to solve this problem, detect it early and manually register
	a search function for the ascii and utf_8 codecs. Starting with python-3.0
	this problem is more noticeable because of stricter handling of encoding
	and decoding between strings of characters and bytes.
	"""

	default_fallback = 'utf_8'
	default_encoding = sys.getdefaultencoding().lower().replace('-', '_')
	filesystem_encoding = _encodings['merge'].lower().replace('-', '_')
	required_encodings = set(['ascii', 'utf_8'])
	required_encodings.add(default_encoding)
	required_encodings.add(filesystem_encoding)
	missing_encodings = set()
	for codec_name in required_encodings:
		try:
			codecs.lookup(codec_name)
		except LookupError:
			missing_encodings.add(codec_name)

	if not missing_encodings:
		return

	encodings = _gen_missing_encodings(missing_encodings)

	if default_encoding in missing_encodings and \
		default_encoding not in encodings:
		# Make the fallback codec correspond to whatever name happens
		# to be returned by sys.getfilesystemencoding().

		try:
			encodings[default_encoding] = codecs.lookup(default_fallback)
		except LookupError:
			encodings[default_encoding] = encodings[default_fallback]

	if filesystem_encoding in missing_encodings and \
		filesystem_encoding not in encodings:
		# Make the fallback codec correspond to whatever name happens
		# to be returned by sys.getdefaultencoding().

		try:
			encodings[filesystem_encoding] = codecs.lookup(default_fallback)
		except LookupError:
			encodings[filesystem_encoding] = encodings[default_fallback]

	def search_function(name):
		name = name.lower()
		name = name.replace('-', '_')
		codec_info = encodings.get(name)
		if codec_info is not None:
			return codecs.CodecInfo(
				name=codec_info.name,
				encode=codec_info.encode,
				decode=codec_info.decode,
				incrementalencoder=codec_info.incrementalencoder,
				incrementaldecoder=codec_info.incrementaldecoder,
				streamreader=codec_info.streamreader,
				streamwriter=codec_info.streamwriter,
			)
		return None

	codecs.register(search_function)

	del codec_name, default_encoding, default_fallback, \
		filesystem_encoding, missing_encodings, \
		required_encodings, search_function

# Do this ASAP since writemsg() might not work without it.
_ensure_default_encoding()

def _shell_quote(s):
	"""
	Quote a string in double-quotes and use backslashes to
	escape any backslashes, double-quotes, dollar signs, or
	backquotes in the string.
	"""
	for letter in "\\\"$`":
		if letter in s:
			s = s.replace(letter, "\\" + letter)
	return "\"%s\"" % s

bsd_chflags = None

if platform.system() in ('FreeBSD',):

	class bsd_chflags(object):

		@classmethod
		def chflags(cls, path, flags, opts=""):
			cmd = 'chflags %s %o %s' % (opts, flags, _shell_quote(path))
			status, output = subprocess_getstatusoutput(cmd)
			if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
				return
			# Try to generate an ENOENT error if appropriate.
			if 'h' in opts:
				_os_merge.lstat(path)
			else:
				_os_merge.stat(path)
			# Make sure the binary exists.
			if not portage.process.find_binary('chflags'):
				raise portage.exception.CommandNotFound('chflags')
			# Now we're not sure exactly why it failed or what
			# the real errno was, so just report EPERM.
			e = OSError(errno.EPERM, output)
			e.errno = errno.EPERM
			e.filename = path
			e.message = output
			raise e

		@classmethod
		def lchflags(cls, path, flags):
			return cls.chflags(path, flags, opts='-h')

def load_mod(name):
	modname = ".".join(name.split(".")[:-1])
	mod = __import__(modname)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

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
	if mypath in dircache:
		cacheHit += 1
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cacheMiss += 1
		cached_mtime, list, ftype = -1, [], []
	try:
		pathstat = os.stat(mypath)
		if stat.S_ISDIR(pathstat[stat.ST_MODE]):
			mtime = pathstat.st_mtime
		else:
			raise portage.exception.DirectoryNotFound(mypath)
	except EnvironmentError as e:
		if e.errno == portage.exception.PermissionDenied.errno:
			raise portage.exception.PermissionDenied(mypath)
		del e
		return [], []
	except portage.exception.PortageException:
		return [], []
	# Python retuns mtime in seconds, so if it was changed in the last few seconds, it could be invalid
	if mtime != cached_mtime or time.time() - mtime < 4:
		if mypath in dircache:
			cacheStale += 1
		try:
			list = os.listdir(mypath)
		except EnvironmentError as e:
			if e.errno != errno.EACCES:
				raise
			del e
			raise portage.exception.PermissionDenied(mypath)
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
		if list[x] in ignorelist:
			pass
		elif ignorecvs:
			if list[x][:2] != ".#":
				ret_list.append(list[x])
				ret_ftype.append(ftype[x])
		else:
			ret_list.append(list[x])
			ret_ftype.append(ftype[x])

	writemsg("cacheddirStats: H:%d/M:%d/S:%d\n" % (cacheHit, cacheMiss, cacheStale),10)
	return ret_list, ret_ftype

_ignorecvs_dirs = ('CVS', 'SCCS', '.svn', '.git')

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
	@param ignorecvs: Ignore CVS directories ('CVS','SCCS','.svn','.git')
	@type ignorecvs: Boolean
	@param ignorelist: List of filenames/directories to exclude
	@type ignorelist: List
	@param followSymlinks: Follow Symlink'd files and directories
	@type followSymlinks: Boolean
	@param EmptyOnError: Return [] if an error occurs (deprecated, always True)
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
			if ftype[x] == 1 and not \
				(ignorecvs and os.path.basename(list[x]) in _ignorecvs_dirs):
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

#parse /etc/env.d and generate /etc/profile.env

def env_update(makelinks=1, target_root=None, prev_mtimes=None, contents=None,
	env=None, writemsg_level=None):
	if writemsg_level is None:
		writemsg_level = portage.util.writemsg_level
	if target_root is None:
		global settings
		target_root = settings["ROOT"]
	if prev_mtimes is None:
		global mtimedb
		prev_mtimes = mtimedb["ldpath"]
	if env is None:
		env = os.environ
	envd_dir = os.path.join(target_root, "etc", "env.d")
	portage.util.ensure_dirs(envd_dir, mode=0o755)
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
		except portage.exception.ParseError as e:
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
				for item in myconfig[var].split():
					if item and not item in mylist:
						mylist.append(item)
				del myconfig[var] # prepare for env.update(myconfig)
		if mylist:
			env[var] = " ".join(mylist)
		specials[var] = mylist

	for var in colon_separated:
		mylist = []
		for myconfig in config_list:
			if var in myconfig:
				for item in myconfig[var].split(":"):
					if item and not item in mylist:
						mylist.append(item)
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
		myld = codecs.open(_unicode_encode(ldsoconf_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['content'], errors='replace')
		myldlines=myld.readlines()
		myld.close()
		oldld=[]
		for x in myldlines:
			#each line has at least one char (a newline)
			if x[0]=="#":
				continue
			oldld.append(x[:-1])
	except (IOError, OSError) as e:
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

	# Portage stores mtimes with 1 second granularity but in >=python-2.5 finer
	# granularity is possible.  In order to avoid the potential ambiguity of
	# mtimes that differ by less than 1 second, sleep here if any of the
	# directories have been modified during the current second.
	sleep_for_mtime_granularity = False
	current_time = long(time.time())
	mtime_changed = False
	lib_dirs = set()
	for lib_dir in portage.util.unique_array(specials["LDPATH"]+['usr/lib','usr/lib64','usr/lib32','lib','lib64','lib32']):
		x = os.path.join(target_root, lib_dir.lstrip(os.sep))
		try:
			newldpathtime = os.stat(x)[stat.ST_MTIME]
			lib_dirs.add(normalize_path(x))
		except OSError as oe:
			if oe.errno == errno.ENOENT:
				try:
					del prev_mtimes[x]
				except KeyError:
					pass
				# ignore this path because it doesn't exist
				continue
			raise
		if newldpathtime == current_time:
			sleep_for_mtime_granularity = True
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
		for mypath, mydata in contents.items():
			if mydata[0] not in ("obj","sym"):
				continue
			head, tail = os.path.split(mypath)
			if head in lib_dirs:
				libdir_contents_changed = True
				break
		if not libdir_contents_changed:
			makelinks = False

	ldconfig = "/sbin/ldconfig"
	if "CHOST" in env and "CBUILD" in env and \
		env["CHOST"] != env["CBUILD"]:
		from portage.process import find_binary
		ldconfig = find_binary("%s-ldconfig" % env["CHOST"])

	# Only run ldconfig as needed
	if (ld_cache_update or makelinks) and ldconfig:
		# ldconfig has very different behaviour between FreeBSD and Linux
		if ostype=="Linux" or ostype.lower().endswith("gnu"):
			# We can't update links if we haven't cleaned other versions first, as
			# an older package installed ON TOP of a newer version will cause ldconfig
			# to overwrite the symlinks we just made. -X means no links. After 'clean'
			# we can safely create links.
			writemsg_level(_(">>> Regenerating %setc/ld.so.cache...\n") % \
				(target_root,))
			if makelinks:
				os.system("cd / ; %s -r '%s'" % (ldconfig, target_root))
			else:
				os.system("cd / ; %s -X -r '%s'" % (ldconfig, target_root))
		elif ostype in ("FreeBSD","DragonFly"):
			writemsg_level(_(">>> Regenerating %svar/run/ld-elf.so.hints...\n") % \
				target_root)
			os.system(("cd / ; %s -elf -i " + \
				"-f '%svar/run/ld-elf.so.hints' '%setc/ld.so.conf'") % \
				(ldconfig, target_root, target_root))

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
	for k in env_keys:
		v = env[k]
		if v.startswith('$') and not v.startswith('${'):
			outfile.write("export %s=$'%s'\n" % (k, v[1:]))
		else:
			outfile.write("export %s='%s'\n" % (k, v))
	outfile.close()

	#create /etc/csh.env for (t)csh support
	outfile = atomic_ofstream(os.path.join(target_root, "etc", "csh.env"))
	outfile.write(cenvnotice)
	for x in env_keys:
		outfile.write("setenv %s '%s'\n" % (x, env[x]))
	outfile.close()

	if sleep_for_mtime_granularity:
		while current_time == long(time.time()):
			sleep(1)

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
		f = codecs.open(_unicode_encode(pathname,
			encoding=_encodings['fs'], errors='strict'), mode='r',
			encoding=_encodings['content'], errors='replace')
	except OSError as details:
		return (None, str(details))
	except IOError as details:
		return (None, str(details))

	try:
		for i in range(4):
			lines.append(f.readline())
	except OSError as details:
		return (None, str(details))
	except IOError as details:
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
	if kernelconfig and "CONFIG_LOCALVERSION" in kernelconfig:
		version += "".join(kernelconfig["CONFIG_LOCALVERSION"].split())

	return (version,None)

def _can_test_pty_eof():
	"""
	The _test_pty_eof() function seems to hang on most
	kernels other than Linux.
	This was reported for the following kernels which used to work fine
	without this EOF test: Darwin, AIX, FreeBSD.  They seem to hang on
	the slave_file.close() call.  Note that Python's implementation of
	openpty on Solaris already caused random hangs without this EOF test
	and hence is globally disabled.
	@rtype: bool
	@returns: True if _test_pty_eof() won't hang, False otherwise.
	"""
	return platform.system() in ("Linux",)

def _test_pty_eof():
	"""
	Returns True if this issues is fixed for the currently
	running version of python: http://bugs.python.org/issue5380
	Raises an EnvironmentError from openpty() if it fails.
	"""

	use_fork = False

	import array, fcntl, pty, select, termios
	test_string = 2 * "blah blah blah\n"
	test_string = _unicode_decode(test_string,
		encoding='utf_8', errors='strict')

	# may raise EnvironmentError
	master_fd, slave_fd = pty.openpty()

	# Non-blocking mode is required for Darwin kernel.
	fcntl.fcntl(master_fd, fcntl.F_SETFL,
		fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

	# Disable post-processing of output since otherwise weird
	# things like \n -> \r\n transformations may occur.
	mode = termios.tcgetattr(slave_fd)
	mode[1] &= ~termios.OPOST
	termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

	# Simulate a subprocess writing some data to the
	# slave end of the pipe, and then exiting.
	pid = None
	if use_fork:
		pids = process.spawn_bash(_unicode_encode("echo -n '%s'" % test_string,
			encoding='utf_8', errors='strict'), env=os.environ,
			fd_pipes={0:sys.stdin.fileno(), 1:slave_fd, 2:slave_fd},
			returnpid=True)
		if isinstance(pids, int):
			os.close(master_fd)
			os.close(slave_fd)
			raise EnvironmentError('spawn failed')
		pid = pids[0]
	else:
		os.write(slave_fd, _unicode_encode(test_string,
			encoding='utf_8', errors='strict'))
	os.close(slave_fd)

	# If using a fork, we must wait for the child here,
	# in order to avoid a race condition that would
	# lead to inconsistent results.
	if pid is not None:
		os.waitpid(pid, 0)

	master_file = os.fdopen(master_fd, 'rb')
	eof = False
	data = []
	iwtd = [master_file]
	owtd = []
	ewtd = []

	while not eof:

		events = select.select(iwtd, owtd, ewtd)
		if not events[0]:
			eof = True
			break

		buf = array.array('B')
		try:
			buf.fromfile(master_file, 1024)
		except EOFError:
			eof = True
		except IOError:
			# This is where data loss occurs.
			eof = True

		if not buf:
			eof = True
		else:
			data.append(_unicode_decode(buf.tostring(),
				encoding='utf_8', errors='strict'))

	master_file.close()

	return test_string == ''.join(data)

# If _test_pty_eof() can't be used for runtime detection of
# http://bugs.python.org/issue5380, openpty can't safely be used
# unless we can guarantee that the current version of python has
# been fixed (affects all current versions of python3). When
# this issue is fixed in python3, we can add another sys.hexversion
# conditional to enable openpty support in the fixed versions.
if sys.hexversion >= 0x3000000 and not _can_test_pty_eof():
	_disable_openpty = True
else:
	# Disable the use of openpty on Solaris as it seems Python's openpty
	# implementation doesn't play nice on Solaris with Portage's
	# behaviour causing hangs/deadlocks.
	# Additional note for the future: on Interix, pipes do NOT work, so
	# _disable_openpty on Interix must *never* be True
	_disable_openpty = platform.system() in ("SunOS",)
_tested_pty = False

if not _can_test_pty_eof():
	# Skip _test_pty_eof() on systems where it hangs.
	_tested_pty = True

def _create_pty_or_pipe(copy_term_size=None):
	"""
	Try to create a pty and if then fails then create a normal
	pipe instead.

	@param copy_term_size: If a tty file descriptor is given
		then the term size will be copied to the pty.
	@type copy_term_size: int
	@rtype: tuple
	@returns: A tuple of (is_pty, master_fd, slave_fd) where
		is_pty is True if a pty was successfully allocated, and
		False if a normal pipe was allocated.
	"""

	got_pty = False

	global _disable_openpty, _tested_pty
	if not (_tested_pty or _disable_openpty):
		try:
			if not _test_pty_eof():
				_disable_openpty = True
		except EnvironmentError as e:
			_disable_openpty = True
			writemsg("openpty failed: '%s'\n" % str(e),
				noiselevel=-1)
			del e
		_tested_pty = True

	if _disable_openpty:
		master_fd, slave_fd = os.pipe()
	else:
		from pty import openpty
		try:
			master_fd, slave_fd = openpty()
			got_pty = True
		except EnvironmentError as e:
			_disable_openpty = True
			writemsg("openpty failed: '%s'\n" % str(e),
				noiselevel=-1)
			del e
			master_fd, slave_fd = os.pipe()

	if got_pty:
		# Disable post-processing of output since otherwise weird
		# things like \n -> \r\n transformations may occur.
		import termios
		mode = termios.tcgetattr(slave_fd)
		mode[1] &= ~termios.OPOST
		termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

	if got_pty and \
		copy_term_size is not None and \
		os.isatty(copy_term_size):
		from portage.output import get_term_size, set_term_size
		rows, columns = get_term_size()
		set_term_size(rows, columns, slave_fd)

	return (got_pty, master_fd, slave_fd)

# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring, mysettings, debug=0, free=0, droppriv=0, sesandbox=0, fakeroot=0, **keywords):
	"""
	Spawn a subprocess with extra portage-specific options.
	Optiosn include:

	Sandbox: Sandbox means the spawned process will be limited in its ability t
	read and write files (normally this means it is restricted to ${D}/)
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
	@param fakeroot: Run this command with faked root privileges
	@type fakeroot: Boolean
	@param keywords: Extra options encoded as a dict, to be passed to spawn
	@type keywords: Dictionary
	@rtype: Integer
	@returns:
	1. The return code of the spawned process.
	"""

	if isinstance(mysettings, dict):
		env=mysettings
		keywords["opt_name"]="[ %s ]" % "portage"
	else:
		check_config_instance(mysettings)
		env=mysettings.environ()
		if mysettings.mycpv is not None:
			keywords["opt_name"] = "[%s]" % mysettings.mycpv
		else:
			keywords["opt_name"] = "[%s/%s]" % \
				(mysettings.get("CATEGORY",""), mysettings.get("PF",""))

	fd_pipes = keywords.get("fd_pipes")
	if fd_pipes is None:
		fd_pipes = {
			0:sys.stdin.fileno(),
			1:sys.stdout.fileno(),
			2:sys.stderr.fileno(),
		}
	# In some cases the above print statements don't flush stdout, so
	# it needs to be flushed before allowing a child process to use it
	# so that output always shows in the correct order.
	stdout_filenos = (sys.stdout.fileno(), sys.stderr.fileno())
	for fd in fd_pipes.values():
		if fd in stdout_filenos:
			sys.stdout.flush()
			sys.stderr.flush()
			break

	# The default policy for the sesandbox domain only allows entry (via exec)
	# from shells and from binaries that belong to portage (the number of entry
	# points is minimized).  The "tee" binary is not among the allowed entry
	# points, so it is spawned outside of the sesandbox domain and reads from a
	# pseudo-terminal that connects two domains.
	logfile = keywords.get("logfile")
	mypids = []
	master_fd = None
	slave_fd = None
	fd_pipes_orig = None
	got_pty = False
	if logfile:
		del keywords["logfile"]
		if 1 not in fd_pipes or 2 not in fd_pipes:
			raise ValueError(fd_pipes)

		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=fd_pipes[1])

		if not got_pty and 'sesandbox' in mysettings.features \
			and mysettings.selinux_enabled():
			# With sesandbox, logging works through a pty but not through a
			# normal pipe. So, disable logging if ptys are broken.
			# See Bug #162404.
			logfile = None
			os.close(master_fd)
			master_fd = None
			os.close(slave_fd)
			slave_fd = None

	if logfile:

		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes_orig = fd_pipes.copy()

		# We must set non-blocking mode before we close the slave_fd
		# since otherwise the fcntl call can fail on FreeBSD (the child
		# process might have already exited and closed slave_fd so we
		# have to keep it open in order to avoid FreeBSD potentially
		# generating an EAGAIN exception).
		import fcntl
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes[0] = fd_pipes_orig[0]
		fd_pipes[1] = slave_fd
		fd_pipes[2] = slave_fd
		keywords["fd_pipes"] = fd_pipes

	features = mysettings.features
	# TODO: Enable fakeroot to be used together with droppriv.  The
	# fake ownership/permissions will have to be converted to real
	# permissions in the merge phase.
	fakeroot = fakeroot and uid != 0 and portage.process.fakeroot_capable
	if droppriv and not uid and portage_gid and portage_uid:
		keywords.update({"uid":portage_uid,"gid":portage_gid,
			"groups":userpriv_groups,"umask":0o02})
	if not free:
		free=((droppriv and "usersandbox" not in features) or \
			(not droppriv and "sandbox" not in features and \
			"usersandbox" not in features and not fakeroot))

	if not free and not (fakeroot or process.sandbox_capable):
		free = True

	if free or "SANDBOX_ACTIVE" in os.environ:
		keywords["opt_name"] += " bash"
		spawn_func = portage.process.spawn_bash
	elif fakeroot:
		keywords["opt_name"] += " fakeroot"
		keywords["fakeroot_state"] = os.path.join(mysettings["T"], "fakeroot.state")
		spawn_func = portage.process.spawn_fakeroot
	else:
		keywords["opt_name"] += " sandbox"
		spawn_func = portage.process.spawn_sandbox

	if sesandbox:
		spawn_func = selinux.spawn_wrapper(spawn_func,
			mysettings["PORTAGE_SANDBOX_T"])

	returnpid = keywords.get("returnpid")
	keywords["returnpid"] = True
	try:
		mypids.extend(spawn_func(mystring, env=env, **keywords))
	finally:
		if logfile:
			os.close(slave_fd)

	if returnpid:
		return mypids

	if logfile:
		log_file = open(_unicode_encode(logfile), mode='ab')
		apply_secpass_permissions(logfile,
			uid=portage_uid, gid=portage_gid, mode=0o664)
		stdout_file = os.fdopen(os.dup(fd_pipes_orig[1]), 'wb')
		master_file = os.fdopen(master_fd, 'rb')
		iwtd = [master_file]
		owtd = []
		ewtd = []
		import array, select
		buffsize = 65536
		eof = False
		while not eof:
			events = select.select(iwtd, owtd, ewtd)
			for f in events[0]:
				# Use non-blocking mode to prevent read
				# calls from blocking indefinitely.
				buf = array.array('B')
				try:
					buf.fromfile(f, buffsize)
				except EOFError:
					pass
				if not buf:
					eof = True
					break
				if f is master_file:
					buf.tofile(stdout_file)
					stdout_file.flush()
					buf.tofile(log_file)
					log_file.flush()
		log_file.close()
		stdout_file.close()
		master_file.close()
	pid = mypids[-1]
	retval = os.waitpid(pid, 0)[1]
	portage.process.spawned_pids.remove(pid)
	if retval != os.EX_OK:
		if retval & 0xff:
			return (retval & 0xff) << 8
		return retval >> 8
	return retval

_userpriv_spawn_kwargs = (
	("uid",    portage_uid),
	("gid",    portage_gid),
	("groups", userpriv_groups),
	("umask",  0o02),
)

def _spawn_fetch(settings, args, **kwargs):
	"""
	Spawn a process with appropriate settings for fetching, including
	userfetch and selinux support.
	"""

	global _userpriv_spawn_kwargs

	# Redirect all output to stdout since some fetchers like
	# wget pollute stderr (if portage detects a problem then it
	# can send it's own message to stderr).
	if "fd_pipes" not in kwargs:

		kwargs["fd_pipes"] = {
			0 : sys.stdin.fileno(),
			1 : sys.stdout.fileno(),
			2 : sys.stdout.fileno(),
		}

	if "userfetch" in settings.features and \
		os.getuid() == 0 and portage_gid and portage_uid:
		kwargs.update(_userpriv_spawn_kwargs)

	spawn_func = portage.process.spawn

	if settings.selinux_enabled():
		spawn_func = selinux.spawn_wrapper(spawn_func,
			settings["PORTAGE_FETCH_T"])

		# bash is an allowed entrypoint, while most binaries are not
		if args[0] != BASH_BINARY:
			args = [BASH_BINARY, "-c", "exec \"$@\"", args[0]] + args

	rval = spawn_func(args, env=settings.environ(), **kwargs)

	return rval

_userpriv_test_write_file_cache = {}
_userpriv_test_write_cmd_script = "touch %(file_path)s 2>/dev/null ; rval=$? ; " + \
	"rm -f  %(file_path)s ; exit $rval"

def _userpriv_test_write_file(settings, file_path):
	"""
	Drop privileges and try to open a file for writing. The file may or
	may not exist, and the parent directory is assumed to exist. The file
	is removed before returning.

	@param settings: A config instance which is passed to _spawn_fetch()
	@param file_path: A file path to open and write.
	@return: True if write succeeds, False otherwise.
	"""

	global _userpriv_test_write_file_cache, _userpriv_test_write_cmd_script
	rval = _userpriv_test_write_file_cache.get(file_path)
	if rval is not None:
		return rval

	args = [BASH_BINARY, "-c", _userpriv_test_write_cmd_script % \
		{"file_path" : _shell_quote(file_path)}]

	returncode = _spawn_fetch(settings, args)

	rval = returncode == os.EX_OK
	_userpriv_test_write_file_cache[file_path] = rval
	return rval

def _checksum_failure_temp_file(distdir, basename):
	"""
	First try to find a duplicate temp file with the same checksum and return
	that filename if available. Otherwise, use mkstemp to create a new unique
	filename._checksum_failure_.$RANDOM, rename the given file, and return the
	new filename. In any case, filename will be renamed or removed before this
	function returns a temp filename.
	"""

	filename = os.path.join(distdir, basename)
	size = os.stat(filename).st_size
	checksum = None
	tempfile_re = re.compile(re.escape(basename) + r'\._checksum_failure_\..*')
	for temp_filename in os.listdir(distdir):
		if not tempfile_re.match(temp_filename):
			continue
		temp_filename = os.path.join(distdir, temp_filename)
		try:
			if size != os.stat(temp_filename).st_size:
				continue
		except OSError:
			continue
		try:
			temp_checksum = portage.checksum.perform_md5(temp_filename)
		except portage.exception.FileNotFound:
			# Apparently the temp file disappeared. Let it go.
			continue
		if checksum is None:
			checksum = portage.checksum.perform_md5(filename)
		if checksum == temp_checksum:
			os.unlink(filename)
			return temp_filename

	from tempfile import mkstemp
	fd, temp_filename = mkstemp("", basename + "._checksum_failure_.", distdir)
	os.close(fd)
	os.rename(filename, temp_filename)
	return temp_filename

def _check_digests(filename, digests, show_errors=1):
	"""
	Check digests and display a message if an error occurs.
	@return True if all digests match, False otherwise.
	"""
	verified_ok, reason = portage.checksum.verify_all(filename, digests)
	if not verified_ok:
		if show_errors:
			writemsg(_("!!! Previously fetched"
				" file: '%s'\n") % filename, noiselevel=-1)
			writemsg(_("!!! Reason: %s\n") % reason[0],
				noiselevel=-1)
			writemsg(_("!!! Got:      %s\n"
				"!!! Expected: %s\n") % \
				(reason[1], reason[2]), noiselevel=-1)
		return False
	return True

def _check_distfile(filename, digests, eout, show_errors=1):
	"""
	@return a tuple of (match, stat_obj) where match is True if filename
	matches all given digests (if any) and stat_obj is a stat result, or
	None if the file does not exist.
	"""
	if digests is None:
		digests = {}
	size = digests.get("size")
	if size is not None and len(digests) == 1:
		digests = None

	try:
		st = os.stat(filename)
	except OSError:
		return (False, None)
	if size is not None and size != st.st_size:
		return (False, st)
	if not digests:
		if size is not None:
			eout.ebegin(_("%s size ;-)") % os.path.basename(filename))
			eout.eend(0)
		elif st.st_size == 0:
			# Zero-byte distfiles are always invalid.
			return (False, st)
	else:
		if _check_digests(filename, digests, show_errors=show_errors):
			eout.ebegin("%s %s ;-)" % (os.path.basename(filename),
				" ".join(sorted(digests))))
			eout.eend(0)
		else:
			return (False, st)
	return (True, st)

_fetch_resume_size_re = re.compile('(^[\d]+)([KMGTPEZY]?$)')

_size_suffix_map = {
	''  : 0,
	'K' : 10,
	'M' : 20,
	'G' : 30,
	'T' : 40,
	'P' : 50,
	'E' : 60,
	'Z' : 70,
	'Y' : 80,
}

def fetch(myuris, mysettings, listonly=0, fetchonly=0, locks_in_subdir=".locks",use_locks=1, try_mirrors=1):
	"fetch files.  Will use digest file if available."

	if not myuris:
		return 1

	features = mysettings.features
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()

	from portage.data import secpass
	userfetch = secpass >= 2 and "userfetch" in features
	userpriv = secpass >= 2 and "userpriv" in features

	# 'nomirror' is bad/negative logic. You Restrict mirroring, not no-mirroring.
	if "mirror" in restrict or \
	   "nomirror" in restrict:
		if ("mirror" in features) and ("lmirror" not in features):
			# lmirror should allow you to bypass mirror restrictions.
			# XXX: This is not a good thing, and is temporary at best.
			print(_(">>> \"mirror\" mode desired and \"mirror\" restriction found; skipping fetch."))
			return 1

	# Generally, downloading the same file repeatedly from
	# every single available mirror is a waste of bandwidth
	# and time, so there needs to be a cap.
	checksum_failure_max_tries = 5
	v = checksum_failure_max_tries
	try:
		v = int(mysettings.get("PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS",
			checksum_failure_max_tries))
	except (ValueError, OverflowError):
		writemsg(_("!!! Variable PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS"
			" contains non-integer value: '%s'\n") % \
			mysettings["PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS"], noiselevel=-1)
		writemsg(_("!!! Using PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS "
			"default value: %s\n") % checksum_failure_max_tries,
			noiselevel=-1)
		v = checksum_failure_max_tries
	if v < 1:
		writemsg(_("!!! Variable PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS"
			" contains value less than 1: '%s'\n") % v, noiselevel=-1)
		writemsg(_("!!! Using PORTAGE_FETCH_CHECKSUM_TRY_MIRRORS "
			"default value: %s\n") % checksum_failure_max_tries,
			noiselevel=-1)
		v = checksum_failure_max_tries
	checksum_failure_max_tries = v
	del v

	fetch_resume_size_default = "350K"
	fetch_resume_size = mysettings.get("PORTAGE_FETCH_RESUME_MIN_SIZE")
	if fetch_resume_size is not None:
		fetch_resume_size = "".join(fetch_resume_size.split())
		if not fetch_resume_size:
			# If it's undefined or empty, silently use the default.
			fetch_resume_size = fetch_resume_size_default
		match = _fetch_resume_size_re.match(fetch_resume_size)
		if match is None or \
			(match.group(2).upper() not in _size_suffix_map):
			writemsg(_("!!! Variable PORTAGE_FETCH_RESUME_MIN_SIZE"
				" contains an unrecognized format: '%s'\n") % \
				mysettings["PORTAGE_FETCH_RESUME_MIN_SIZE"], noiselevel=-1)
			writemsg(_("!!! Using PORTAGE_FETCH_RESUME_MIN_SIZE "
				"default value: %s\n") % fetch_resume_size_default,
				noiselevel=-1)
			fetch_resume_size = None
	if fetch_resume_size is None:
		fetch_resume_size = fetch_resume_size_default
		match = _fetch_resume_size_re.match(fetch_resume_size)
	fetch_resume_size = int(match.group(1)) * \
		2 ** _size_suffix_map[match.group(2).upper()]

	# Behave like the package has RESTRICT="primaryuri" after a
	# couple of checksum failures, to increase the probablility
	# of success before checksum_failure_max_tries is reached.
	checksum_failure_primaryuri = 2
	thirdpartymirrors = mysettings.thirdpartymirrors()

	# In the background parallel-fetch process, it's safe to skip checksum
	# verification of pre-existing files in $DISTDIR that have the correct
	# file size. The parent process will verify their checksums prior to
	# the unpack phase.

	parallel_fetchonly = "PORTAGE_PARALLEL_FETCHONLY" in mysettings
	if parallel_fetchonly:
		fetchonly = 1

	check_config_instance(mysettings)

	custommirrors = grabdict(os.path.join(mysettings["PORTAGE_CONFIGROOT"],
		CUSTOM_MIRRORS_FILE), recursive=1)

	mymirrors=[]

	if listonly or ("distlocks" not in features):
		use_locks = 0

	fetch_to_ro = 0
	if "skiprocheck" in features:
		fetch_to_ro = 1

	if not os.access(mysettings["DISTDIR"],os.W_OK) and fetch_to_ro:
		if use_locks:
			writemsg(colorize("BAD",
				_("!!! For fetching to a read-only filesystem, "
				"locking should be turned off.\n")), noiselevel=-1)
			writemsg(_("!!! This can be done by adding -distlocks to "
				"FEATURES in /etc/make.conf\n"), noiselevel=-1)
#			use_locks = 0

	# local mirrors are always added
	if "local" in custommirrors:
		mymirrors += custommirrors["local"]

	if "nomirror" in restrict or \
	   "mirror" in restrict:
		# We don't add any mirrors.
		pass
	else:
		if try_mirrors:
			mymirrors += [x.rstrip("/") for x in mysettings["GENTOO_MIRRORS"].split() if x]

	skip_manifest = mysettings.get("EBUILD_SKIP_MANIFEST") == "1"
	pkgdir = mysettings.get("O")
	if not (pkgdir is None or skip_manifest):
		mydigests = Manifest(
			pkgdir, mysettings["DISTDIR"]).getTypeDigests("DIST")
	else:
		# no digests because fetch was not called for a specific package
		mydigests = {}

	ro_distdirs = [x for x in \
		util.shlex_split(mysettings.get("PORTAGE_RO_DISTDIRS", "")) \
		if os.path.isdir(x)]

	fsmirrors = []
	for x in range(len(mymirrors)-1,-1,-1):
		if mymirrors[x] and mymirrors[x][0]=='/':
			fsmirrors += [mymirrors[x]]
			del mymirrors[x]

	restrict_fetch = "fetch" in restrict
	custom_local_mirrors = custommirrors.get("local", [])
	if restrict_fetch:
		# With fetch restriction, a normal uri may only be fetched from
		# custom local mirrors (if available).  A mirror:// uri may also
		# be fetched from specific mirrors (effectively overriding fetch
		# restriction, but only for specific mirrors).
		locations = custom_local_mirrors
	else:
		locations = mymirrors

	file_uri_tuples = []
	# Check for 'items' attribute since OrderedDict is not a dict.
	if hasattr(myuris, 'items'):
		for myfile, uri_set in myuris.items():
			for myuri in uri_set:
				file_uri_tuples.append((myfile, myuri))
	else:
		for myuri in myuris:
			file_uri_tuples.append((os.path.basename(myuri), myuri))

	filedict = OrderedDict()
	primaryuri_indexes={}
	primaryuri_dict = {}
	thirdpartymirror_uris = {}
	for myfile, myuri in file_uri_tuples:
		if myfile not in filedict:
			filedict[myfile]=[]
			for y in range(0,len(locations)):
				filedict[myfile].append(locations[y]+"/distfiles/"+myfile)
		if myuri[:9]=="mirror://":
			eidx = myuri.find("/", 9)
			if eidx != -1:
				mirrorname = myuri[9:eidx]
				path = myuri[eidx+1:]

				# Try user-defined mirrors first
				if mirrorname in custommirrors:
					for cmirr in custommirrors[mirrorname]:
						filedict[myfile].append(
							cmirr.rstrip("/") + "/" + path)

				# now try the official mirrors
				if mirrorname in thirdpartymirrors:
					shuffle(thirdpartymirrors[mirrorname])

					uris = [locmirr.rstrip("/") + "/" + path \
						for locmirr in thirdpartymirrors[mirrorname]]
					filedict[myfile].extend(uris)
					thirdpartymirror_uris.setdefault(myfile, []).extend(uris)

				if not filedict[myfile]:
					writemsg(_("No known mirror by the name: %s\n") % (mirrorname))
			else:
				writemsg(_("Invalid mirror definition in SRC_URI:\n"), noiselevel=-1)
				writemsg("  %s\n" % (myuri), noiselevel=-1)
		else:
			if restrict_fetch:
				# Only fetch from specific mirrors is allowed.
				continue
			if "primaryuri" in restrict:
				# Use the source site first.
				if myfile in primaryuri_indexes:
					primaryuri_indexes[myfile] += 1
				else:
					primaryuri_indexes[myfile] = 0
				filedict[myfile].insert(primaryuri_indexes[myfile], myuri)
			else:
				filedict[myfile].append(myuri)
			primaryuris = primaryuri_dict.get(myfile)
			if primaryuris is None:
				primaryuris = []
				primaryuri_dict[myfile] = primaryuris
			primaryuris.append(myuri)

	# Prefer thirdpartymirrors over normal mirrors in cases when
	# the file does not yet exist on the normal mirrors.
	for myfile, uris in thirdpartymirror_uris.items():
		primaryuri_dict.setdefault(myfile, []).extend(uris)

	can_fetch=True

	if listonly:
		can_fetch = False

	if can_fetch and not fetch_to_ro:
		global _userpriv_test_write_file_cache
		dirmode  = 0o2070
		filemode =   0o60
		modemask =    0o2
		dir_gid = portage_gid
		if "FAKED_MODE" in mysettings:
			# When inside fakeroot, directories with portage's gid appear
			# to have root's gid. Therefore, use root's gid instead of
			# portage's gid to avoid spurrious permissions adjustments
			# when inside fakeroot.
			dir_gid = 0
		distdir_dirs = [""]
		if "distlocks" in features:
			distdir_dirs.append(".locks")
		try:
			
			for x in distdir_dirs:
				mydir = os.path.join(mysettings["DISTDIR"], x)
				write_test_file = os.path.join(
					mydir, ".__portage_test_write__")

				try:
					st = os.stat(mydir)
				except OSError:
					st = None

				if st is not None and stat.S_ISDIR(st.st_mode):
					if not (userfetch or userpriv):
						continue
					if _userpriv_test_write_file(mysettings, write_test_file):
						continue

				_userpriv_test_write_file_cache.pop(write_test_file, None)
				if portage.util.ensure_dirs(mydir, gid=dir_gid, mode=dirmode, mask=modemask):
					if st is None:
						# The directory has just been created
						# and therefore it must be empty.
						continue
					writemsg(_("Adjusting permissions recursively: '%s'\n") % mydir,
						noiselevel=-1)
					def onerror(e):
						raise # bail out on the first error that occurs during recursion
					if not apply_recursive_permissions(mydir,
						gid=dir_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
						raise portage.exception.OperationNotPermitted(
							_("Failed to apply recursive permissions for the portage group."))
		except portage.exception.PortageException as e:
			if not os.path.isdir(mysettings["DISTDIR"]):
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Directory Not Found: DISTDIR='%s'\n") % mysettings["DISTDIR"], noiselevel=-1)
				writemsg(_("!!! Fetching will fail!\n"), noiselevel=-1)

	if can_fetch and \
		not fetch_to_ro and \
		not os.access(mysettings["DISTDIR"], os.W_OK):
		writemsg(_("!!! No write access to '%s'\n") % mysettings["DISTDIR"],
			noiselevel=-1)
		can_fetch = False

	if can_fetch and use_locks and locks_in_subdir:
			distlocks_subdir = os.path.join(mysettings["DISTDIR"], locks_in_subdir)
			if not os.access(distlocks_subdir, os.W_OK):
				writemsg(_("!!! No write access to write to %s.  Aborting.\n") % distlocks_subdir,
					noiselevel=-1)
				return 0
			del distlocks_subdir

	distdir_writable = can_fetch and not fetch_to_ro
	failed_files = set()
	restrict_fetch_msg = False

	for myfile in filedict:
		"""
		fetched  status
		0        nonexistent
		1        partially downloaded
		2        completely downloaded
		"""
		fetched = 0

		orig_digests = mydigests.get(myfile, {})
		size = orig_digests.get("size")
		if size == 0:
			# Zero-byte distfiles are always invalid, so discard their digests.
			del mydigests[myfile]
			orig_digests.clear()
			size = None
		pruned_digests = orig_digests
		if parallel_fetchonly:
			pruned_digests = {}
			if size is not None:
				pruned_digests["size"] = size

		myfile_path = os.path.join(mysettings["DISTDIR"], myfile)
		has_space = True
		has_space_superuser = True
		file_lock = None
		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		else:
			# check if there is enough space in DISTDIR to completely store myfile
			# overestimate the filesize so we aren't bitten by FS overhead
			if size is not None and hasattr(os, "statvfs"):
				vfs_stat = os.statvfs(mysettings["DISTDIR"])
				try:
					mysize = os.stat(myfile_path).st_size
				except OSError as e:
					if e.errno not in (errno.ENOENT, errno.ESTALE):
						raise
					del e
					mysize = 0
				if (size - mysize + vfs_stat.f_bsize) >= \
					(vfs_stat.f_bsize * vfs_stat.f_bavail):

					if (size - mysize + vfs_stat.f_bsize) >= \
						(vfs_stat.f_bsize * vfs_stat.f_bfree):
						has_space_superuser = False

					if not has_space_superuser:
						has_space = False
					elif secpass < 2:
						has_space = False
					elif userfetch:
						has_space = False

			if not has_space:
				writemsg(_("!!! Insufficient space to store %s in %s\n") % \
					(myfile, mysettings["DISTDIR"]), noiselevel=-1)

				if has_space_superuser:
					writemsg(_("!!! Insufficient privileges to use "
						"remaining space.\n"), noiselevel=-1)
					if userfetch:
						writemsg(_("!!! You may set FEATURES=\"-userfetch\""
							" in /etc/make.conf in order to fetch with\n"
							"!!! superuser privileges.\n"), noiselevel=-1)

			if distdir_writable and use_locks:

				if locks_in_subdir:
					lock_file = os.path.join(mysettings["DISTDIR"],
						locks_in_subdir, myfile)
				else:
					lock_file = myfile_path

				lock_kwargs = {}
				if fetchonly:
					lock_kwargs["flags"] = os.O_NONBLOCK

				try:
					file_lock = portage.locks.lockfile(myfile_path,
						wantnewlockfile=1, **lock_kwargs)
				except portage.exception.TryAgain:
					writemsg(_(">>> File '%s' is already locked by "
						"another fetcher. Continuing...\n") % myfile,
						noiselevel=-1)
					continue
		try:
			if not listonly:

				eout = portage.output.EOutput()
				eout.quiet = mysettings.get("PORTAGE_QUIET") == "1"
				match, mystat = _check_distfile(
					myfile_path, pruned_digests, eout)
				if match:
					if distdir_writable:
						try:
							apply_secpass_permissions(myfile_path,
								gid=portage_gid, mode=0o664, mask=0o2,
								stat_cached=mystat)
						except portage.exception.PortageException as e:
							if not os.access(myfile_path, os.R_OK):
								writemsg(_("!!! Failed to adjust permissions:"
									" %s\n") % str(e), noiselevel=-1)
							del e
					continue

				if distdir_writable and mystat is None:
					# Remove broken symlinks if necessary.
					try:
						os.unlink(myfile_path)
					except OSError:
						pass

				if mystat is not None:
					if stat.S_ISDIR(mystat.st_mode):
						portage.util.writemsg_level(
							_("!!! Unable to fetch file since "
							"a directory is in the way: \n"
							"!!!   %s\n") % myfile_path,
							level=logging.ERROR, noiselevel=-1)
						return 0

					if mystat.st_size == 0:
						if distdir_writable:
							try:
								os.unlink(myfile_path)
							except OSError:
								pass
					elif distdir_writable:
						if mystat.st_size < fetch_resume_size and \
							mystat.st_size < size:
							# If the file already exists and the size does not
							# match the existing digests, it may be that the
							# user is attempting to update the digest. In this
							# case, the digestgen() function will advise the
							# user to use `ebuild --force foo.ebuild manifest`
							# in order to force the old digests to be replaced.
							# Since the user may want to keep this file, rename
							# it instead of deleting it.
							writemsg(_(">>> Renaming distfile with size "
								"%d (smaller than " "PORTAGE_FETCH_RESU"
								"ME_MIN_SIZE)\n") % mystat.st_size)
							temp_filename = \
								_checksum_failure_temp_file(
								mysettings["DISTDIR"], myfile)
							writemsg_stdout(_("Refetching... "
								"File renamed to '%s'\n\n") % \
								temp_filename, noiselevel=-1)
						elif mystat.st_size >= size:
							temp_filename = \
								_checksum_failure_temp_file(
								mysettings["DISTDIR"], myfile)
							writemsg_stdout(_("Refetching... "
								"File renamed to '%s'\n\n") % \
								temp_filename, noiselevel=-1)

				if distdir_writable and ro_distdirs:
					readonly_file = None
					for x in ro_distdirs:
						filename = os.path.join(x, myfile)
						match, mystat = _check_distfile(
							filename, pruned_digests, eout)
						if match:
							readonly_file = filename
							break
					if readonly_file is not None:
						try:
							os.unlink(myfile_path)
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e
						os.symlink(readonly_file, myfile_path)
						continue

				if fsmirrors and not os.path.exists(myfile_path) and has_space:
					for mydir in fsmirrors:
						mirror_file = os.path.join(mydir, myfile)
						try:
							shutil.copyfile(mirror_file, myfile_path)
							writemsg(_("Local mirror has file: %s\n") % myfile)
							break
						except (IOError, OSError) as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e

				try:
					mystat = os.stat(myfile_path)
				except OSError as e:
					if e.errno not in (errno.ENOENT, errno.ESTALE):
						raise
					del e
				else:
					try:
						apply_secpass_permissions(
							myfile_path, gid=portage_gid, mode=0o664, mask=0o2,
							stat_cached=mystat)
					except portage.exception.PortageException as e:
						if not os.access(myfile_path, os.R_OK):
							writemsg(_("!!! Failed to adjust permissions:"
								" %s\n") % str(e), noiselevel=-1)

					# If the file is empty then it's obviously invalid. Remove
					# the empty file and try to download if possible.
					if mystat.st_size == 0:
						if distdir_writable:
							try:
								os.unlink(myfile_path)
							except EnvironmentError:
								pass
					elif myfile not in mydigests:
						# We don't have a digest, but the file exists.  We must
						# assume that it is fully downloaded.
						continue
					else:
						if mystat.st_size < mydigests[myfile]["size"] and \
							not restrict_fetch:
							fetched = 1 # Try to resume this download.
						elif parallel_fetchonly and \
							mystat.st_size == mydigests[myfile]["size"]:
							eout = portage.output.EOutput()
							eout.quiet = \
								mysettings.get("PORTAGE_QUIET") == "1"
							eout.ebegin(
								"%s size ;-)" % (myfile, ))
							eout.eend(0)
							continue
						else:
							verified_ok, reason = portage.checksum.verify_all(
								myfile_path, mydigests[myfile])
							if not verified_ok:
								writemsg(_("!!! Previously fetched"
									" file: '%s'\n") % myfile, noiselevel=-1)
								writemsg(_("!!! Reason: %s\n") % reason[0],
									noiselevel=-1)
								writemsg(_("!!! Got:      %s\n"
									"!!! Expected: %s\n") % \
									(reason[1], reason[2]), noiselevel=-1)
								if reason[0] == _("Insufficient data for checksum verification"):
									return 0
								if distdir_writable:
									temp_filename = \
										_checksum_failure_temp_file(
										mysettings["DISTDIR"], myfile)
									writemsg_stdout(_("Refetching... "
										"File renamed to '%s'\n\n") % \
										temp_filename, noiselevel=-1)
							else:
								eout = portage.output.EOutput()
								eout.quiet = \
									mysettings.get("PORTAGE_QUIET", None) == "1"
								digests = mydigests.get(myfile)
								if digests:
									digests = list(digests)
									digests.sort()
									eout.ebegin(
										"%s %s ;-)" % (myfile, " ".join(digests)))
									eout.eend(0)
								continue # fetch any remaining files

			# Create a reversed list since that is optimal for list.pop().
			uri_list = filedict[myfile][:]
			uri_list.reverse()
			checksum_failure_count = 0
			tried_locations = set()
			while uri_list:
				loc = uri_list.pop()
				# Eliminate duplicates here in case we've switched to
				# "primaryuri" mode on the fly due to a checksum failure.
				if loc in tried_locations:
					continue
				tried_locations.add(loc)
				if listonly:
					writemsg_stdout(loc+" ", noiselevel=-1)
					continue
				# allow different fetchcommands per protocol
				protocol = loc[0:loc.find("://")]

				missing_file_param = False
				fetchcommand_var = "FETCHCOMMAND_" + protocol.upper()
				fetchcommand = mysettings.get(fetchcommand_var)
				if fetchcommand is None:
					fetchcommand_var = "FETCHCOMMAND"
					fetchcommand = mysettings.get(fetchcommand_var)
					if fetchcommand is None:
						portage.util.writemsg_level(
							_("!!! %s is unset. It should "
							"have been defined in\n!!! %s/make.globals.\n") \
							% (fetchcommand_var,
							portage.const.GLOBAL_CONFIG_PATH),
							level=logging.ERROR, noiselevel=-1)
						return 0
				if "${FILE}" not in fetchcommand:
					portage.util.writemsg_level(
						_("!!! %s does not contain the required ${FILE}"
						" parameter.\n") % fetchcommand_var,
						level=logging.ERROR, noiselevel=-1)
					missing_file_param = True

				resumecommand_var = "RESUMECOMMAND_" + protocol.upper()
				resumecommand = mysettings.get(resumecommand_var)
				if resumecommand is None:
					resumecommand_var = "RESUMECOMMAND"
					resumecommand = mysettings.get(resumecommand_var)
					if resumecommand is None:
						portage.util.writemsg_level(
							_("!!! %s is unset. It should "
							"have been defined in\n!!! %s/make.globals.\n") \
							% (resumecommand_var,
							portage.const.GLOBAL_CONFIG_PATH),
							level=logging.ERROR, noiselevel=-1)
						return 0
				if "${FILE}" not in resumecommand:
					portage.util.writemsg_level(
						_("!!! %s does not contain the required ${FILE}"
						" parameter.\n") % resumecommand_var,
						level=logging.ERROR, noiselevel=-1)
					missing_file_param = True

				if missing_file_param:
					portage.util.writemsg_level(
						_("!!! Refer to the make.conf(5) man page for "
						"information about how to\n!!! correctly specify "
						"FETCHCOMMAND and RESUMECOMMAND.\n"),
						level=logging.ERROR, noiselevel=-1)
					if myfile != os.path.basename(loc):
						return 0

				if not can_fetch:
					if fetched != 2:
						try:
							mysize = os.stat(myfile_path).st_size
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e
							mysize = 0

						if mysize == 0:
							writemsg(_("!!! File %s isn't fetched but unable to get it.\n") % myfile,
								noiselevel=-1)
						elif size is None or size > mysize:
							writemsg(_("!!! File %s isn't fully fetched, but unable to complete it\n") % myfile,
								noiselevel=-1)
						else:
							writemsg(_("!!! File %s is incorrect size, "
								"but unable to retry.\n") % myfile, noiselevel=-1)
						return 0
					else:
						continue

				if fetched != 2 and has_space:
					#we either need to resume or start the download
					if fetched == 1:
						try:
							mystat = os.stat(myfile_path)
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e
							fetched = 0
						else:
							if mystat.st_size < fetch_resume_size:
								writemsg(_(">>> Deleting distfile with size "
									"%d (smaller than " "PORTAGE_FETCH_RESU"
									"ME_MIN_SIZE)\n") % mystat.st_size)
								try:
									os.unlink(myfile_path)
								except OSError as e:
									if e.errno not in \
										(errno.ENOENT, errno.ESTALE):
										raise
									del e
								fetched = 0
					if fetched == 1:
						#resume mode:
						writemsg(_(">>> Resuming download...\n"))
						locfetch=resumecommand
						command_var = resumecommand_var
					else:
						#normal mode:
						locfetch=fetchcommand
						command_var = fetchcommand_var
					writemsg_stdout(_(">>> Downloading '%s'\n") % \
						re.sub(r'//(.+):.+@(.+)/',r'//\1:*password*@\2/', loc))
					variables = {
						"DISTDIR": mysettings["DISTDIR"],
						"URI":     loc,
						"FILE":    myfile
					}

					myfetch = util.shlex_split(locfetch)
					myfetch = [varexpand(x, mydict=variables) for x in myfetch]
					myret = -1
					try:

						myret = _spawn_fetch(mysettings, myfetch)

					finally:
						try:
							apply_secpass_permissions(myfile_path,
								gid=portage_gid, mode=0o664, mask=0o2)
						except portage.exception.FileNotFound as e:
							pass
						except portage.exception.PortageException as e:
							if not os.access(myfile_path, os.R_OK):
								writemsg(_("!!! Failed to adjust permissions:"
									" %s\n") % str(e), noiselevel=-1)

					# If the file is empty then it's obviously invalid.  Don't
					# trust the return value from the fetcher.  Remove the
					# empty file and try to download again.
					try:
						if os.stat(myfile_path).st_size == 0:
							os.unlink(myfile_path)
							fetched = 0
							continue
					except EnvironmentError:
						pass

					if mydigests is not None and myfile in mydigests:
						try:
							mystat = os.stat(myfile_path)
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e
							fetched = 0
						else:

							if stat.S_ISDIR(mystat.st_mode):
								# This can happen if FETCHCOMMAND erroneously
								# contains wget's -P option where it should
								# instead have -O.
								portage.util.writemsg_level(
									_("!!! The command specified in the "
									"%s variable appears to have\n!!! "
									"created a directory instead of a "
									"normal file.\n") % command_var,
									level=logging.ERROR, noiselevel=-1)
								portage.util.writemsg_level(
									_("!!! Refer to the make.conf(5) "
									"man page for information about how "
									"to\n!!! correctly specify "
									"FETCHCOMMAND and RESUMECOMMAND.\n"),
									level=logging.ERROR, noiselevel=-1)
								return 0

							# no exception?  file exists. let digestcheck() report
							# an appropriately for size or checksum errors

							# If the fetcher reported success and the file is
							# too small, it's probably because the digest is
							# bad (upstream changed the distfile).  In this
							# case we don't want to attempt to resume. Show a
							# digest verification failure to that the user gets
							# a clue about what just happened.
							if myret != os.EX_OK and \
								mystat.st_size < mydigests[myfile]["size"]:
								# Fetch failed... Try the next one... Kill 404 files though.
								if (mystat[stat.ST_SIZE]<100000) and (len(myfile)>4) and not ((myfile[-5:]==".html") or (myfile[-4:]==".htm")):
									html404=re.compile("<title>.*(not found|404).*</title>",re.I|re.M)
									if html404.search(codecs.open(
										_unicode_encode(myfile_path,
										encoding=_encodings['fs'], errors='strict'),
										mode='r', encoding=_encodings['content'], errors='replace'
										).read()):
										try:
											os.unlink(mysettings["DISTDIR"]+"/"+myfile)
											writemsg(_(">>> Deleting invalid distfile. (Improper 404 redirect from server.)\n"))
											fetched = 0
											continue
										except (IOError, OSError):
											pass
								fetched = 1
								continue
							if True:
								# File is the correct size--check the checksums for the fetched
								# file NOW, for those users who don't have a stable/continuous
								# net connection. This way we have a chance to try to download
								# from another mirror...
								verified_ok,reason = portage.checksum.verify_all(mysettings["DISTDIR"]+"/"+myfile, mydigests[myfile])
								if not verified_ok:
									print(reason)
									writemsg(_("!!! Fetched file: %s VERIFY FAILED!\n") % myfile,
										noiselevel=-1)
									writemsg(_("!!! Reason: %s\n") % reason[0],
										noiselevel=-1)
									writemsg(_("!!! Got:      %s\n!!! Expected: %s\n") % \
										(reason[1], reason[2]), noiselevel=-1)
									if reason[0] == _("Insufficient data for checksum verification"):
										return 0
									temp_filename = \
										_checksum_failure_temp_file(
										mysettings["DISTDIR"], myfile)
									writemsg_stdout(_("Refetching... "
										"File renamed to '%s'\n\n") % \
										temp_filename, noiselevel=-1)
									fetched=0
									checksum_failure_count += 1
									if checksum_failure_count == \
										checksum_failure_primaryuri:
										# Switch to "primaryuri" mode in order
										# to increase the probablility of
										# of success.
										primaryuris = \
											primaryuri_dict.get(myfile)
										if primaryuris:
											uri_list.extend(
												reversed(primaryuris))
									if checksum_failure_count >= \
										checksum_failure_max_tries:
										break
								else:
									eout = portage.output.EOutput()
									eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
									digests = mydigests.get(myfile)
									if digests:
										eout.ebegin("%s %s ;-)" % \
											(myfile, " ".join(sorted(digests))))
										eout.eend(0)
									fetched=2
									break
					else:
						if not myret:
							fetched=2
							break
						elif mydigests!=None:
							writemsg(_("No digest file available and download failed.\n\n"),
								noiselevel=-1)
		finally:
			if use_locks and file_lock:
				portage.locks.unlockfile(file_lock)

		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		if fetched != 2:
			if restrict_fetch and not restrict_fetch_msg:
				restrict_fetch_msg = True
				msg = _("\n!!! %s/%s"
					" has fetch restriction turned on.\n"
					"!!! This probably means that this "
					"ebuild's files must be downloaded\n"
					"!!! manually.  See the comments in"
					" the ebuild for more information.\n\n") % \
					(mysettings["CATEGORY"], mysettings["PF"])
				portage.util.writemsg_level(msg,
					level=logging.ERROR, noiselevel=-1)
				have_builddir = "PORTAGE_BUILDDIR" in mysettings and \
					os.path.isdir(mysettings["PORTAGE_BUILDDIR"])

				global_tmpdir = mysettings["PORTAGE_TMPDIR"]
				private_tmpdir = None
				if not parallel_fetchonly and not have_builddir:
					# When called by digestgen(), it's normal that
					# PORTAGE_BUILDDIR doesn't exist. It's helpful
					# to show the pkg_nofetch output though, so go
					# ahead and create a temporary PORTAGE_BUILDDIR.
					# Use a temporary config instance to avoid altering
					# the state of the one that's been passed in.
					mysettings = config(clone=mysettings)
					from tempfile import mkdtemp
					try:
						private_tmpdir = mkdtemp("", "._portage_fetch_.",
							global_tmpdir)
					except OSError as e:
						if e.errno != portage.exception.PermissionDenied.errno:
							raise
						raise portage.exception.PermissionDenied(global_tmpdir)
					mysettings["PORTAGE_TMPDIR"] = private_tmpdir
					mysettings.backup_changes("PORTAGE_TMPDIR")
					debug = mysettings.get("PORTAGE_DEBUG") == "1"
					portage.doebuild_environment(mysettings["EBUILD"], "fetch",
						mysettings["ROOT"], mysettings, debug, 1, None)
					prepare_build_dirs(mysettings["ROOT"], mysettings, 0)
					have_builddir = True

				if not parallel_fetchonly and have_builddir:
					# To spawn pkg_nofetch requires PORTAGE_BUILDDIR for
					# ensuring sane $PWD (bug #239560) and storing elog
					# messages. Therefore, calling code needs to ensure that
					# PORTAGE_BUILDDIR is already clean and locked here.

					# All the pkg_nofetch goes to stderr since it's considered
					# to be an error message.
					fd_pipes = {
						0 : sys.stdin.fileno(),
						1 : sys.stderr.fileno(),
						2 : sys.stderr.fileno(),
					}

					ebuild_phase = mysettings.get("EBUILD_PHASE")
					try:
						mysettings["EBUILD_PHASE"] = "nofetch"
						spawn(_shell_quote(EBUILD_SH_BINARY) + \
							" nofetch", mysettings, fd_pipes=fd_pipes)
					finally:
						if ebuild_phase is None:
							mysettings.pop("EBUILD_PHASE", None)
						else:
							mysettings["EBUILD_PHASE"] = ebuild_phase
						if private_tmpdir is not None:
							shutil.rmtree(private_tmpdir)

			elif restrict_fetch:
				pass
			elif listonly:
				pass
			elif not filedict[myfile]:
				writemsg(_("Warning: No mirrors available for file"
					" '%s'\n") % (myfile), noiselevel=-1)
			else:
				writemsg(_("!!! Couldn't download '%s'. Aborting.\n") % myfile,
					noiselevel=-1)

			if listonly:
				continue
			elif fetchonly:
				failed_files.add(myfile)
				continue
			return 0
	if failed_files:
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
			except portage.exception.InvalidDependString as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				del e
				return 0
		mytree = os.path.dirname(os.path.dirname(mysettings["O"]))
		manifest1_compat = False
		mf = Manifest(mysettings["O"], mysettings["DISTDIR"],
			fetchlist_dict=fetchlist_dict, manifest1_compat=manifest1_compat)
		# Don't require all hashes since that can trigger excessive
		# fetches when sufficient digests already exist.  To ease transition
		# while Manifest 1 is being removed, only require hashes that will
		# exist before and after the transition.
		required_hash_types = set()
		required_hash_types.add("size")
		required_hash_types.add(portage.const.MANIFEST2_REQUIRED_HASH)
		dist_hashes = mf.fhashdict.get("DIST", {})

		# To avoid accidental regeneration of digests with the incorrect
		# files (such as partially downloaded files), trigger the fetch
		# code if the file exists and it's size doesn't match the current
		# manifest entry. If there really is a legitimate reason for the
		# digest to change, `ebuild --force digest` can be used to avoid
		# triggering this code (or else the old digests can be manually
		# removed from the Manifest).
		missing_files = []
		for myfile in distfiles_map:
			myhashes = dist_hashes.get(myfile)
			if not myhashes:
				try:
					st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
				except OSError:
					st = None
				if st is None or st.st_size == 0:
					missing_files.append(myfile)
				continue
			size = myhashes.get("size")

			try:
				st = os.stat(os.path.join(mysettings["DISTDIR"], myfile))
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				if size == 0:
					missing_files.append(myfile)
					continue
				if required_hash_types.difference(myhashes):
					missing_files.append(myfile)
					continue
			else:
				if st.st_size == 0 or size is not None and size != st.st_size:
					missing_files.append(myfile)
					continue

		if missing_files:
				mytree = os.path.realpath(os.path.dirname(
					os.path.dirname(mysettings["O"])))
				fetch_settings = config(clone=mysettings)
				debug = mysettings.get("PORTAGE_DEBUG") == "1"
				for myfile in missing_files:
					uris = set()
					for cpv in distfiles_map[myfile]:
						myebuild = os.path.join(mysettings["O"],
							catsplit(cpv)[1] + ".ebuild")
						# for RESTRICT=fetch, mirror, etc...
						doebuild_environment(myebuild, "fetch",
							mysettings["ROOT"], fetch_settings,
							debug, 1, myportdb)
						uris.update(myportdb.getFetchMap(
							cpv, mytree=mytree)[myfile])

					fetch_settings["A"] = myfile # for use by pkg_nofetch()

					try:
						st = os.stat(os.path.join(
							mysettings["DISTDIR"],myfile))
					except OSError:
						st = None

					if not fetch({myfile : uris}, fetch_settings):
						writemsg(_("!!! Fetch failed for %s, can't update "
							"Manifest\n") % myfile, noiselevel=-1)
						if myfile in dist_hashes and \
							st is not None and st.st_size > 0:
							# stat result is obtained before calling fetch(),
							# since fetch may rename the existing file if the
							# digest does not match.
							writemsg(_("!!! If you would like to "
								"forcefully replace the existing "
								"Manifest entry\n!!! for %s, use "
								"the following command:\n") % myfile + \
								"!!!    " + colorize("INFORM",
								"ebuild --force %s manifest" % \
								os.path.basename(myebuild)) + "\n",
								noiselevel=-1)
						return 0
		writemsg_stdout(_(">>> Creating Manifest for %s\n") % mysettings["O"])
		try:
			mf.create(requiredDistfiles=myarchives,
				assumeDistHashesSometimes=True,
				assumeDistHashesAlways=(
				"assume-digests" in mysettings.features))
		except portage.exception.FileNotFound as e:
			writemsg(_("!!! File %s doesn't exist, can't update "
				"Manifest\n") % e, noiselevel=-1)
			return 0
		except portage.exception.PortagePackageException as e:
			writemsg(("!!! %s\n") % (e,), noiselevel=-1)
			return 0
		try:
			mf.write(sign=False)
		except portage.exception.PermissionDenied as e:
			writemsg(_("!!! Permission Denied: %s\n") % (e,), noiselevel=-1)
			return 0
		if "assume-digests" not in mysettings.features:
			distlist = list(mf.fhashdict.get("DIST", {}))
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
					fetchlist = myportdb.getFetchMap(pkg_key, mytree=mytree)
					pv = pkg_key.split("/")[1]
					for filename in auto_assumed:
						if filename in fetchlist:
							writemsg_stdout(
								"   %s::%s\n" % (pv, filename))
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

	warnings.warn("portage.digestParseFile() is deprecated",
		DeprecationWarning, stacklevel=2)

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
	if mysettings.get("EBUILD_SKIP_MANIFEST") == "1":
		return 1
	pkgdir = mysettings["O"]
	manifest_path = os.path.join(pkgdir, "Manifest")
	if not os.path.exists(manifest_path):
		writemsg(_("!!! Manifest file not found: '%s'\n") % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
		else:
			return 1
	mf = Manifest(pkgdir, mysettings["DISTDIR"])
	manifest_empty = True
	for d in mf.fhashdict.values():
		if d:
			manifest_empty = False
			break
	if manifest_empty:
		writemsg(_("!!! Manifest is empty: '%s'\n") % manifest_path,
			noiselevel=-1)
		if strict:
			return 0
		else:
			return 1
	eout = portage.output.EOutput()
	eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
	try:
		if strict and "PORTAGE_PARALLEL_FETCHONLY" not in mysettings:
			eout.ebegin(_("checking ebuild checksums ;-)"))
			mf.checkTypeHashes("EBUILD")
			eout.eend(0)
			eout.ebegin(_("checking auxfile checksums ;-)"))
			mf.checkTypeHashes("AUX")
			eout.eend(0)
			eout.ebegin(_("checking miscfile checksums ;-)"))
			mf.checkTypeHashes("MISC", ignoreMissingFiles=True)
			eout.eend(0)
		for f in myfiles:
			eout.ebegin(_("checking %s ;-)") % f)
			ftype = mf.findFile(f)
			if ftype is None:
				raise KeyError(f)
			mf.checkFileHashes(ftype, f)
			eout.eend(0)
	except KeyError as e:
		eout.eend(1)
		writemsg(_("\n!!! Missing digest for %s\n") % str(e), noiselevel=-1)
		return 0
	except portage.exception.FileNotFound as e:
		eout.eend(1)
		writemsg(_("\n!!! A file listed in the Manifest could not be found: %s\n") % str(e),
			noiselevel=-1)
		return 0
	except portage.exception.DigestException as e:
		eout.eend(1)
		writemsg(_("\n!!! Digest verification failed:\n"), noiselevel=-1)
		writemsg("!!! %s\n" % e.value[0], noiselevel=-1)
		writemsg(_("!!! Reason: %s\n") % e.value[1], noiselevel=-1)
		writemsg(_("!!! Got: %s\n") % e.value[2], noiselevel=-1)
		writemsg(_("!!! Expected: %s\n") % e.value[3], noiselevel=-1)
		return 0
	# Make sure that all of the ebuilds are actually listed in the Manifest.
	glep55 = 'parse-eapi-glep-55' in mysettings.features
	for f in os.listdir(pkgdir):
		pf = None
		if glep55:
			pf, eapi = _split_ebuild_name_glep55(f)
		elif f[-7:] == '.ebuild':
			pf = f[:-7]
		if pf is not None and not mf.hasFile("EBUILD", f):
			writemsg(_("!!! A file is not listed in the Manifest: '%s'\n") % \
				os.path.join(pkgdir, f), noiselevel=-1)
			if strict:
				return 0
	""" epatch will just grab all the patches out of a directory, so we have to
	make sure there aren't any foreign files that it might grab."""
	filesdir = os.path.join(pkgdir, "files")

	for parent, dirs, files in os.walk(filesdir):
		try:
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='strict')
		except UnicodeDecodeError:
			parent = _unicode_decode(parent,
				encoding=_encodings['fs'], errors='replace')
			writemsg(_("!!! Path contains invalid "
				"character(s) for encoding '%s': '%s'") \
				% (_encodings['fs'], parent), noiselevel=-1)
			if strict:
				return 0
			continue
		for d in dirs:
			d_bytes = d
			try:
				d = _unicode_decode(d,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				d = _unicode_decode(d,
					encoding=_encodings['fs'], errors='replace')
				writemsg(_("!!! Path contains invalid "
					"character(s) for encoding '%s': '%s'") \
					% (_encodings['fs'], os.path.join(parent, d)),
					noiselevel=-1)
				if strict:
					return 0
				dirs.remove(d_bytes)
				continue
			if d.startswith(".") or d == "CVS":
				dirs.remove(d_bytes)
		for f in files:
			try:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='strict')
			except UnicodeDecodeError:
				f = _unicode_decode(f,
					encoding=_encodings['fs'], errors='replace')
				if f.startswith("."):
					continue
				f = os.path.join(parent, f)[len(filesdir) + 1:]
				writemsg(_("!!! File name contains invalid "
					"character(s) for encoding '%s': '%s'") \
					% (_encodings['fs'], f), noiselevel=-1)
				if strict:
					return 0
				continue
			if f.startswith("."):
				continue
			f = os.path.join(parent, f)[len(filesdir) + 1:]
			file_type = mf.findFile(f)
			if file_type != "AUX" and not f.startswith("digest-"):
				writemsg(_("!!! A file is not listed in the Manifest: '%s'\n") % \
					os.path.join(filesdir, f), noiselevel=-1)
				if strict:
					return 0
	return 1

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo, actionmap, mysettings, debug, alwaysdep=0,
	logfile=None, fd_pipes=None, returnpid=False):
	if not returnpid and \
		(alwaysdep or "noauto" not in mysettings.features):
		# process dependency first
		if "dep" in actionmap[mydo]:
			retval = spawnebuild(actionmap[mydo]["dep"], actionmap,
				mysettings, debug, alwaysdep=alwaysdep, logfile=logfile,
				fd_pipes=fd_pipes, returnpid=returnpid)
			if retval:
				return retval

	eapi = mysettings["EAPI"]

	if mydo == "configure" and eapi in ("0", "1"):
		return os.EX_OK

	if mydo == "prepare" and eapi in ("0", "1"):
		return os.EX_OK

	if mydo == "pretend" and eapi in ("0", "1", "2", "3", "3_pre2"):
		return os.EX_OK

	kwargs = actionmap[mydo]["args"]
	mysettings["EBUILD_PHASE"] = mydo
	_doebuild_exit_status_unlink(
		mysettings.get("EBUILD_EXIT_STATUS_FILE"))

	try:
		phase_retval = spawn(actionmap[mydo]["cmd"] % mydo,
			mysettings, debug=debug, logfile=logfile,
			fd_pipes=fd_pipes, returnpid=returnpid, **kwargs)
	finally:
		mysettings["EBUILD_PHASE"] = ""

	if returnpid:
		return phase_retval

	msg = _doebuild_exit_status_check(mydo, mysettings)
	if msg:
		if phase_retval == os.EX_OK:
			phase_retval = 1
		from textwrap import wrap
		from portage.elog.messages import eerror
		for l in wrap(msg, 72):
			eerror(l, phase=mydo, key=mysettings.mycpv)

	_post_phase_userpriv_perms(mysettings)
	if mydo == "install":
		out = StringIO()
		_check_build_log(mysettings, out=out)
		msg = _unicode_decode(out.getvalue(),
			encoding=_encodings['content'], errors='replace')
		if msg:
			writemsg_stdout(msg, noiselevel=-1)
			if logfile is not None:
				try:
					f = codecs.open(_unicode_encode(logfile,
						encoding=_encodings['fs'], errors='strict'),
						mode='a', encoding=_encodings['content'],
						errors='replace')
				except EnvironmentError:
					pass
				else:
					f.write(msg)
					f.close()
		if phase_retval == os.EX_OK:
			_post_src_install_chost_fix(mysettings)
			phase_retval = _post_src_install_checks(mysettings)

	if mydo == "test" and phase_retval != os.EX_OK and \
		"test-fail-continue" in mysettings.features:
		phase_retval = os.EX_OK

	return phase_retval

_post_phase_cmds = {

	"install" : [
		"install_qa_check",
		"install_symlink_html_docs"],

	"preinst" : [
		"preinst_bsdflags",
		"preinst_sfperms",
		"preinst_selinux_labels",
		"preinst_suid_scan",
		"preinst_mask"],

	"postinst" : [
		"postinst_bsdflags"]
}

def _post_phase_userpriv_perms(mysettings):
	if "userpriv" in mysettings.features and secpass >= 2:
		""" Privileged phases may have left files that need to be made
		writable to a less privileged user."""
		apply_recursive_permissions(mysettings["T"],
			uid=portage_uid, gid=portage_gid, dirmode=0o70, dirmask=0,
			filemode=0o60, filemask=0)

def _post_src_install_checks(mysettings):
	_post_src_install_uid_fix(mysettings)
	global _post_phase_cmds
	retval = _spawn_misc_sh(mysettings, _post_phase_cmds["install"],
		phase='internal_post_src_install')
	if retval != os.EX_OK:
		writemsg(_("!!! install_qa_check failed; exiting.\n"),
			noiselevel=-1)
	return retval

def _check_build_log(mysettings, out=None):
	"""
	Search the content of $PORTAGE_LOG_FILE if it exists
	and generate the following QA Notices when appropriate:

	  * Automake "maintainer mode"
	  * command not found
	  * Unrecognized configure options
	"""
	logfile = mysettings.get("PORTAGE_LOG_FILE")
	if logfile is None:
		return
	try:
		f = codecs.open(_unicode_encode(logfile,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['content'], errors='replace')
	except EnvironmentError:
		return

	am_maintainer_mode = []
	bash_command_not_found = []
	bash_command_not_found_re = re.compile(
		r'(.*): line (\d*): (.*): command not found$')
	command_not_found_exclude_re = re.compile(r'/configure: line ')
	helper_missing_file = []
	helper_missing_file_re = re.compile(
		r'^!!! (do|new).*: .* does not exist$')

	configure_opts_warn = []
	configure_opts_warn_re = re.compile(
		r'^configure: WARNING: [Uu]nrecognized options: ')

	# Exclude output from dev-libs/yaz-3.0.47 which looks like this:
	#
	#Configuration:
	#  Automake:                   ${SHELL} /var/tmp/portage/dev-libs/yaz-3.0.47/work/yaz-3.0.47/config/missing --run automake-1.10
	am_maintainer_mode_re = re.compile(r'/missing --run ')
	am_maintainer_mode_exclude_re = \
		re.compile(r'(/missing --run (autoheader|makeinfo)|^\s*Automake:\s)')

	make_jobserver_re = \
		re.compile(r'g?make\[\d+\]: warning: jobserver unavailable:')
	make_jobserver = []

	try:
		for line in f:
			if am_maintainer_mode_re.search(line) is not None and \
				am_maintainer_mode_exclude_re.search(line) is None:
				am_maintainer_mode.append(line.rstrip("\n"))

			if bash_command_not_found_re.match(line) is not None and \
				command_not_found_exclude_re.search(line) is None:
				bash_command_not_found.append(line.rstrip("\n"))

			if helper_missing_file_re.match(line) is not None:
				helper_missing_file.append(line.rstrip("\n"))

			if configure_opts_warn_re.match(line) is not None:
				configure_opts_warn.append(line.rstrip("\n"))

			if make_jobserver_re.match(line) is not None:
				make_jobserver.append(line.rstrip("\n"))

	finally:
		f.close()

	from portage.elog.messages import eqawarn
	def _eqawarn(lines):
		for line in lines:
			eqawarn(line, phase="install", key=mysettings.mycpv, out=out)
	from textwrap import wrap
	wrap_width = 70

	if am_maintainer_mode:
		msg = [_("QA Notice: Automake \"maintainer mode\" detected:")]
		msg.append("")
		msg.extend("\t" + line for line in am_maintainer_mode)
		msg.append("")
		msg.extend(wrap(_(
			"If you patch Makefile.am, "
			"configure.in,  or configure.ac then you "
			"should use autotools.eclass and "
			"eautomake or eautoreconf. Exceptions "
			"are limited to system packages "
			"for which it is impossible to run "
			"autotools during stage building. "
			"See http://www.gentoo.org/p"
			"roj/en/qa/autofailure.xml for more information."),
			wrap_width))
		_eqawarn(msg)

	if bash_command_not_found:
		msg = [_("QA Notice: command not found:")]
		msg.append("")
		msg.extend("\t" + line for line in bash_command_not_found)
		_eqawarn(msg)

	if helper_missing_file:
		msg = [_("QA Notice: file does not exist:")]
		msg.append("")
		msg.extend("\t" + line[4:] for line in helper_missing_file)
		_eqawarn(msg)

	if configure_opts_warn:
		msg = [_("QA Notice: Unrecognized configure options:")]
		msg.append("")
		msg.extend("\t" + line for line in configure_opts_warn)
		_eqawarn(msg)

	if make_jobserver:
		msg = [_("QA Notice: make jobserver unavailable:")]
		msg.append("")
		msg.extend("\t" + line for line in make_jobserver)
		_eqawarn(msg)

def _post_src_install_chost_fix(settings):
	"""
	It's possible that the ebuild has changed the
	CHOST variable, so revert it to the initial
	setting.
	"""
	if settings.get('CATEGORY') == 'virtual':
		return

	chost = settings.get('CHOST')
	if chost:
		write_atomic(os.path.join(settings['PORTAGE_BUILDDIR'],
			'build-info', 'CHOST'), chost + '\n')

_vdb_use_conditional_keys = ('DEPEND', 'LICENSE', 'PDEPEND',
	'PROPERTIES', 'PROVIDE', 'RDEPEND', 'RESTRICT',)
_vdb_use_conditional_atoms = frozenset(['DEPEND', 'PDEPEND', 'RDEPEND'])

def _post_src_install_uid_fix(mysettings, out=None):
	"""
	Files in $D with user and group bits that match the "portage"
	user or group are automatically mapped to PORTAGE_INST_UID and
	PORTAGE_INST_GID if necessary. The chown system call may clear
	S_ISUID and S_ISGID bits, so those bits are restored if
	necessary.
	"""

	os = _os_merge

	inst_uid = int(mysettings["PORTAGE_INST_UID"])
	inst_gid = int(mysettings["PORTAGE_INST_GID"])

	if bsd_chflags:
		# Temporarily remove all of the flags in order to avoid EPERM errors.
		os.system("mtree -c -p %s -k flags > %s" % \
			(_shell_quote(mysettings["D"]),
			_shell_quote(os.path.join(mysettings["T"], "bsdflags.mtree"))))
		os.system("chflags -R noschg,nouchg,nosappnd,nouappnd %s" % \
			(_shell_quote(mysettings["D"]),))
		os.system("chflags -R nosunlnk,nouunlnk %s 2>/dev/null" % \
			(_shell_quote(mysettings["D"]),))

	destdir = mysettings["D"]
	unicode_errors = []

	while True:

		unicode_error = False
		size = 0
		counted_inodes = set()

		for parent, dirs, files in os.walk(destdir):
			try:
				parent = _unicode_decode(parent,
					encoding=_encodings['merge'], errors='strict')
			except UnicodeDecodeError:
				new_parent = _unicode_decode(parent,
					encoding=_encodings['merge'], errors='replace')
				new_parent = _unicode_encode(new_parent,
					encoding=_encodings['merge'], errors='backslashreplace')
				new_parent = _unicode_decode(new_parent,
					encoding=_encodings['merge'], errors='replace')
				os.rename(parent, new_parent)
				unicode_error = True
				unicode_errors.append(new_parent[len(destdir):])
				break

			for fname in chain(dirs, files):
				try:
					fname = _unicode_decode(fname,
						encoding=_encodings['merge'], errors='strict')
				except UnicodeDecodeError:
					fpath = _os.path.join(
						parent.encode(_encodings['merge']), fname)
					new_fname = _unicode_decode(fname,
						encoding=_encodings['merge'], errors='replace')
					new_fname = _unicode_encode(new_fname,
						encoding=_encodings['merge'], errors='backslashreplace')
					new_fname = _unicode_decode(new_fname,
						encoding=_encodings['merge'], errors='replace')
					new_fpath = os.path.join(parent, new_fname)
					os.rename(fpath, new_fpath)
					unicode_error = True
					unicode_errors.append(new_fpath[len(destdir):])
					fname = new_fname
					fpath = new_fpath
				else:
					fpath = os.path.join(parent, fname)

				mystat = os.lstat(fpath)
				if stat.S_ISREG(mystat.st_mode) and \
					mystat.st_ino not in counted_inodes:
					counted_inodes.add(mystat.st_ino)
					size += mystat.st_size
				if mystat.st_uid != portage_uid and \
					mystat.st_gid != portage_gid:
					continue
				myuid = -1
				mygid = -1
				if mystat.st_uid == portage_uid:
					myuid = inst_uid
				if mystat.st_gid == portage_gid:
					mygid = inst_gid
				apply_secpass_permissions(
					_unicode_encode(fpath, encoding=_encodings['merge']),
					uid=myuid, gid=mygid,
					mode=mystat.st_mode, stat_cached=mystat,
					follow_links=False)

			if unicode_error:
				break

		if not unicode_error:
			break

	if unicode_errors:
		from portage.elog.messages import eerror
		for l in _merge_unicode_error(unicode_errors):
			eerror(l, phase='install', key=mysettings.mycpv, out=out)

	build_info_dir = os.path.join(mysettings['PORTAGE_BUILDDIR'],
		'build-info')

	codecs.open(_unicode_encode(os.path.join(build_info_dir,
		'SIZE'), encoding=_encodings['fs'], errors='strict'),
		'w', encoding=_encodings['repo.content'],
		errors='strict').write(str(size) + '\n')

	codecs.open(_unicode_encode(os.path.join(build_info_dir,
		'BUILD_TIME'), encoding=_encodings['fs'], errors='strict'),
		'w', encoding=_encodings['repo.content'],
		errors='strict').write(str(int(time.time())) + '\n')

	use = frozenset(mysettings['PORTAGE_USE'].split())
	for k in _vdb_use_conditional_keys:
		v = mysettings.configdict['pkg'].get(k)
		if v is None:
			continue
		v = dep.paren_reduce(v)
		v = dep.use_reduce(v, uselist=use)
		v = dep.paren_normalize(v)
		v = dep.paren_enclose(v)
		if not v:
			continue
		if v in _vdb_use_conditional_atoms:
			v_split = []
			for x in v.split():
				try:
					x = dep.Atom(x)
				except exception.InvalidAtom:
					v_split.append(x)
				else:
					v_split.append(str(x.evaluate_conditionals(use)))
			v = ' '.join(v_split)
		codecs.open(_unicode_encode(os.path.join(build_info_dir,
			k), encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='strict').write(v + '\n')

	if bsd_chflags:
		# Restore all of the flags saved above.
		os.system("mtree -e -p %s -U -k flags < %s > /dev/null" % \
			(_shell_quote(mysettings["D"]),
			_shell_quote(os.path.join(mysettings["T"], "bsdflags.mtree"))))

def _merge_unicode_error(errors):
	from textwrap import wrap
	lines = []

	msg = _("This package installs one or more file names containing "
		"characters that do not match your current locale "
		"settings. The current setting for filesystem encoding is '%s'.") \
		% _encodings['merge']
	lines.extend(wrap(msg, 72))

	lines.append("")
	errors.sort()
	lines.extend("\t" + x for x in errors)
	lines.append("")

	if _encodings['merge'].lower().replace('_', '').replace('-', '') != 'utf8':
		msg = _("For best results, UTF-8 encoding is recommended. See "
			"the Gentoo Linux Localization Guide for instructions "
			"about how to configure your locale for UTF-8 encoding:")
		lines.extend(wrap(msg, 72))
		lines.append("")
		lines.append("\t" + \
			"http://www.gentoo.org/doc/en/guide-localization.xml")
		lines.append("")

	return lines

def _post_pkg_preinst_cmd(mysettings):
	"""
	Post phase logic and tasks that have been factored out of
	ebuild.sh. Call preinst_mask last so that INSTALL_MASK can
	can be used to wipe out any gmon.out files created during
	previous functions (in case any tools were built with -pg
	in CFLAGS).
	"""

	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))

	mysettings["EBUILD_PHASE"] = ""
	global _post_phase_cmds
	myargs = [_shell_quote(misc_sh_binary)] + _post_phase_cmds["preinst"]

	return myargs

def _post_pkg_postinst_cmd(mysettings):
	"""
	Post phase logic and tasks that have been factored out of
	build.sh.
	"""

	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))

	mysettings["EBUILD_PHASE"] = ""
	global _post_phase_cmds
	myargs = [_shell_quote(misc_sh_binary)] + _post_phase_cmds["postinst"]

	return myargs

def _spawn_misc_sh(mysettings, commands, phase=None, **kwargs):
	"""
	@param mysettings: the ebuild config
	@type mysettings: config
	@param commands: a list of function names to call in misc-functions.sh
	@type commands: list
	@rtype: int
	@returns: the return value from the spawn() call
	"""

	# Note: PORTAGE_BIN_PATH may differ from the global
	# constant when portage is reinstalling itself.
	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))
	mycommand = " ".join([_shell_quote(misc_sh_binary)] + commands)
	_doebuild_exit_status_unlink(
		mysettings.get("EBUILD_EXIT_STATUS_FILE"))
	debug = mysettings.get("PORTAGE_DEBUG") == "1"
	logfile = mysettings.get("PORTAGE_LOG_FILE")
	mysettings.pop("EBUILD_PHASE", None)
	try:
		rval = spawn(mycommand, mysettings, debug=debug,
			logfile=logfile, **kwargs)
	finally:
		pass

	msg = _doebuild_exit_status_check(phase, mysettings)
	if msg:
		if rval == os.EX_OK:
			rval = 1
		from textwrap import wrap
		from portage.elog.messages import eerror
		for l in wrap(msg, 72):
			eerror(l, phase=mydo, key=mysettings.mycpv)

	return rval

_testing_eapis = frozenset()
_deprecated_eapis = frozenset(["3_pre2", "3_pre1", "2_pre3", "2_pre2", "2_pre1"])

def _eapi_is_deprecated(eapi):
	return eapi in _deprecated_eapis

def eapi_is_supported(eapi):
	if not isinstance(eapi, basestring):
		# Only call str() when necessary since with python2 it
		# can trigger UnicodeEncodeError if EAPI is corrupt.
		eapi = str(eapi)
	eapi = eapi.strip()

	if _eapi_is_deprecated(eapi):
		return True

	if eapi in _testing_eapis:
		return True

	try:
		eapi = int(eapi)
	except ValueError:
		eapi = -1
	if eapi < 0:
		return False
	return eapi <= portage.const.EAPI

# Generally, it's best not to assume that cache entries for unsupported EAPIs
# can be validated. However, the current package manager specification does not
# guarantee that the EAPI can be parsed without sourcing the ebuild, so
# it's too costly to discard existing cache entries for unsupported EAPIs.
# Therefore, by default, assume that cache entries for unsupported EAPIs can be
# validated. If FEATURES=parse-eapi-* is enabled, this assumption is discarded
# since the EAPI can be determined without the incurring the cost of sourcing
# the ebuild.
_validate_cache_for_unsupported_eapis = True

_parse_eapi_ebuild_head_re = re.compile(r'^EAPI=[\'"]?([^\'"#]*)')
_parse_eapi_ebuild_head_max_lines = 30

def _parse_eapi_ebuild_head(f):
	count = 0
	for line in f:
		m = _parse_eapi_ebuild_head_re.match(line)
		if m is not None:
			return m.group(1).strip()
		count += 1
		if count >= _parse_eapi_ebuild_head_max_lines:
			break
	return '0'

# True when FEATURES=parse-eapi-glep-55 is enabled.
_glep_55_enabled = False

_split_ebuild_name_glep55_re = re.compile(r'^(.*)\.ebuild(-([^.]+))?$')

def _split_ebuild_name_glep55(name):
	"""
	@returns: (pkg-ver-rev, eapi)
	"""
	m = _split_ebuild_name_glep55_re.match(name)
	if m is None:
		return (None, None)
	return (m.group(1), m.group(3))

def doebuild_environment(myebuild, mydo, myroot, mysettings, debug, use_cache, mydbapi):

	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if "CATEGORY" in mysettings.configdict["pkg"]:
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(normalize_path(os.path.join(pkg_dir, "..")))

	eapi = None
	if 'parse-eapi-glep-55' in mysettings.features:
		mypv, eapi = portage._split_ebuild_name_glep55(
			os.path.basename(myebuild))
	else:
		mypv = os.path.basename(ebuild_path)[:-7]

	mycpv = cat+"/"+mypv
	mysplit = versions._pkgsplit(mypv)
	if mysplit is None:
		raise portage.exception.IncorrectParameter(
			_("Invalid ebuild path: '%s'") % myebuild)

	# Make a backup of PORTAGE_TMPDIR prior to calling config.reset()
	# so that the caller can override it.
	tmpdir = mysettings["PORTAGE_TMPDIR"]

	if mydo == 'depend':
		if mycpv != mysettings.mycpv:
			# Don't pass in mydbapi here since the resulting aux_get
			# call would lead to infinite 'depend' phase recursion.
			mysettings.setcpv(mycpv)
	else:
		# If IUSE isn't in configdict['pkg'], it means that setcpv()
		# hasn't been called with the mydb argument, so we have to
		# call it here (portage code always calls setcpv properly,
		# but api consumers might not).
		if mycpv != mysettings.mycpv or \
			'IUSE' not in mysettings.configdict['pkg']:
			# Reload env.d variables and reset any previous settings.
			mysettings.reload()
			mysettings.reset()
			mysettings.setcpv(mycpv, mydb=mydbapi)

	# config.reset() might have reverted a change made by the caller,
	# so restore it to it's original value.
	mysettings["PORTAGE_TMPDIR"] = tmpdir

	mysettings.pop("EBUILD_PHASE", None) # remove from backupenv
	mysettings["EBUILD_PHASE"] = mydo

	mysettings["PORTAGE_MASTER_PID"] = str(os.getpid())

	# We are disabling user-specific bashrc files.
	mysettings["BASH_ENV"] = INVALID_ENV_FILE

	if debug: # Otherwise it overrides emerge's settings.
		# We have no other way to set debug... debug can't be passed in
		# due to how it's coded... Don't overwrite this so we can use it.
		mysettings["PORTAGE_DEBUG"] = "1"

	mysettings["EBUILD"]   = ebuild_path
	mysettings["O"]        = pkg_dir
	mysettings.configdict["pkg"]["CATEGORY"] = cat
	mysettings["FILESDIR"] = pkg_dir+"/files"
	mysettings["PF"]       = mypv

	if hasattr(mydbapi, '_repo_info'):
		mytree = os.path.dirname(os.path.dirname(pkg_dir))
		repo_info = mydbapi._repo_info[mytree]
		mysettings['PORTDIR'] = repo_info.portdir
		mysettings['PORTDIR_OVERLAY'] = repo_info.portdir_overlay

	mysettings["PORTDIR"] = os.path.realpath(mysettings["PORTDIR"])
	mysettings["DISTDIR"] = os.path.realpath(mysettings["DISTDIR"])
	mysettings["RPMDIR"]  = os.path.realpath(mysettings["RPMDIR"])

	mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"
	mysettings["SANDBOX_LOG"] = mycpv.replace("/", "_-_")

	mysettings["PROFILE_PATHS"] = "\n".join(mysettings.profiles)
	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if portage.util.noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mydo == 'depend' and \
		'EAPI' not in mysettings.configdict['pkg']:

		if eapi is not None:
			# From parse-eapi-glep-55 above.
			pass
		elif 'parse-eapi-ebuild-head' in mysettings.features:
			eapi = _parse_eapi_ebuild_head(
				codecs.open(_unicode_encode(ebuild_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace'))

		if eapi is not None:
			if not eapi_is_supported(eapi):
				raise portage.exception.UnsupportedAPIException(mycpv, eapi)
			mysettings.configdict['pkg']['EAPI'] = eapi

	if mydo != "depend":
		# Metadata vars such as EAPI and RESTRICT are
		# set by the above config.setcpv() call.
		eapi = mysettings["EAPI"]
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise portage.exception.UnsupportedAPIException(mycpv, eapi)

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	if "PATH" in mysettings:
		mysplit=mysettings["PATH"].split(":")
	else:
		mysplit=[]
	# Note: PORTAGE_BIN_PATH may differ from the global constant
	# when portage is reinstalling itself.
	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	if portage_bin_path not in mysplit:
		mysettings["PATH"] = portage_bin_path + ":" + mysettings["PATH"]

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

	# Prefix forward compatability
	mysettings["ED"] = mysettings["D"]

	mysettings["PORTAGE_BASHRC"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_FILE)
	mysettings["EBUILD_EXIT_STATUS_FILE"] = os.path.join(
		mysettings["PORTAGE_BUILDDIR"], ".exit_status")

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if eapi not in ('0', '1', '2', '3', '3_pre2'):
		# Discard KV for EAPIs that don't support it. Cache KV is restored
		# from the backupenv whenever config.reset() is called.
		mysettings.pop('KV', None)
	elif mydo != 'depend' and 'KV' not in mysettings and \
		mydo in ('compile', 'config', 'configure', 'info',
		'install', 'nofetch', 'postinst', 'postrm', 'preinst',
		'prepare', 'prerm', 'setup', 'test', 'unpack'):
		mykv,err1=ExtractKernelVersion(os.path.join(myroot, "usr/src/linux"))
		if mykv:
			# Regular source tree
			mysettings["KV"]=mykv
		else:
			mysettings["KV"]=""
		mysettings.backup_changes("KV")

	# Allow color.map to control colors associated with einfo, ewarn, etc...
	mycolors = []
	for c in ("GOOD", "WARN", "BAD", "HILITE", "BRACKET"):
		mycolors.append("%s=$'%s'" % \
			(c, portage.output.style_to_ansi_code(c)))
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
		except OSError as oe:
			if errno.ENOENT == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg(_("Operation Not Permitted: rmtree('%s')\n") % \
					clean_dir, noiselevel=-1)
				return 1
			else:
				raise

	def makedirs(dir_path):
		try:
			os.makedirs(dir_path)
		except OSError as oe:
			if errno.EEXIST == oe.errno:
				pass
			elif errno.EPERM == oe.errno:
				writemsg("%s\n" % oe, noiselevel=-1)
				writemsg(_("Operation Not Permitted: makedirs('%s')\n") % \
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
				gid=portage_gid, uid=portage_uid, mode=0o70, mask=0)
		for dir_key in ("PORTAGE_BUILDDIR", "HOME", "PKG_LOGDIR", "T"):
			"""These directories don't necessarily need to be group writable.
			However, the setup phase is commonly run as a privileged user prior
			to the other phases being run by an unprivileged user.  Currently,
			we use the portage group to ensure that the unprivleged user still
			has write access to these directories in any case."""
			portage.util.ensure_dirs(mysettings[dir_key], mode=0o775)
			portage.util.apply_secpass_permissions(mysettings[dir_key],
				uid=portage_uid, gid=portage_gid)
	except portage.exception.PermissionDenied as e:
		writemsg(_("Permission Denied: %s\n") % str(e), noiselevel=-1)
		return 1
	except portage.exception.OperationNotPermitted as e:
		writemsg(_("Operation Not Permitted: %s\n") % str(e), noiselevel=-1)
		return 1
	except portage.exception.FileNotFound as e:
		writemsg(_("File Not Found: '%s'\n") % str(e), noiselevel=-1)
		return 1

	# Reset state for things like noauto and keepwork in FEATURES.
	for x in ('.die_hooks',):
		try:
			os.unlink(os.path.join(mysettings['PORTAGE_BUILDDIR'], x))
		except OSError:
			pass

	_prepare_workdir(mysettings)
	if mysettings.get('EBUILD_PHASE') != 'fetch':
		# Avoid spurious permissions adjustments when fetching with
		# a temporary PORTAGE_TMPDIR setting (for fetchonly).
		_prepare_features_dirs(mysettings)

def _adjust_perms_msg(settings, msg):

	def write(msg):
		writemsg(msg, noiselevel=-1)

	background = settings.get("PORTAGE_BACKGROUND") == "1"
	log_path = settings.get("PORTAGE_LOG_FILE")
	log_file = None

	if background and log_path is not None:
		try:
			log_file = codecs.open(_unicode_encode(log_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='a', encoding=_encodings['content'], errors='replace')
		except IOError:
			def write(msg):
				pass
		else:
			def write(msg):
				log_file.write(_unicode_decode(msg))
				log_file.flush()

	try:
		write(msg)
	finally:
		if log_file is not None:
			log_file.close()

def _prepare_features_dirs(mysettings):

	features_dirs = {
		"ccache":{
			"path_dir": "/usr/lib/ccache/bin",
			"basedir_var":"CCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "ccache"),
			"always_recurse":False},
		"distcc":{
			"path_dir": "/usr/lib/distcc/bin",
			"basedir_var":"DISTCC_DIR",
			"default_dir":os.path.join(mysettings["BUILD_PREFIX"], ".distcc"),
			"subdirs":("lock", "state"),
			"always_recurse":True}
	}
	dirmode  = 0o2070
	filemode =   0o60
	modemask =    0o2
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()
	from portage.data import secpass
	droppriv = secpass >= 2 and \
		"userpriv" in mysettings.features and \
		"userpriv" not in restrict
	for myfeature, kwargs in features_dirs.items():
		if myfeature in mysettings.features:
			failure = False
			basedir = mysettings.get(kwargs["basedir_var"])
			if basedir is None or not basedir.strip():
				basedir = kwargs["default_dir"]
				mysettings[kwargs["basedir_var"]] = basedir
			try:
				path_dir = kwargs["path_dir"]
				if not os.path.isdir(path_dir):
					raise portage.exception.DirectoryNotFound(path_dir)

				mydirs = [mysettings[kwargs["basedir_var"]]]
				if "subdirs" in kwargs:
					for subdir in kwargs["subdirs"]:
						mydirs.append(os.path.join(basedir, subdir))
				for mydir in mydirs:
					modified = portage.util.ensure_dirs(mydir)
					# Generally, we only want to apply permissions for
					# initial creation.  Otherwise, we don't know exactly what
					# permissions the user wants, so should leave them as-is.
					droppriv_fix = False
					if droppriv:
						st = os.stat(mydir)
						if st.st_gid != portage_gid or \
							not dirmode == (stat.S_IMODE(st.st_mode) & dirmode):
							droppriv_fix = True
						if not droppriv_fix:
							# Check permissions of files in the directory.
							for filename in os.listdir(mydir):
								try:
									subdir_st = os.lstat(
										os.path.join(mydir, filename))
								except OSError:
									continue
								if subdir_st.st_gid != portage_gid or \
									((stat.S_ISDIR(subdir_st.st_mode) and \
									not dirmode == (stat.S_IMODE(subdir_st.st_mode) & dirmode))):
									droppriv_fix = True
									break

					if droppriv_fix:
						_adjust_perms_msg(mysettings,
							colorize("WARN", " * ") + \
							_("Adjusting permissions "
							"for FEATURES=userpriv: '%s'\n") % mydir)
					elif modified:
						_adjust_perms_msg(mysettings,
							colorize("WARN", " * ") + \
							_("Adjusting permissions "
							"for FEATURES=%s: '%s'\n") % (myfeature, mydir))

					if modified or kwargs["always_recurse"] or droppriv_fix:
						def onerror(e):
							raise	# The feature is disabled if a single error
									# occurs during permissions adjustment.
						if not apply_recursive_permissions(mydir,
						gid=portage_gid, dirmode=dirmode, dirmask=modemask,
						filemode=filemode, filemask=modemask, onerror=onerror):
							raise portage.exception.OperationNotPermitted(
								_("Failed to apply recursive permissions for the portage group."))

			except portage.exception.DirectoryNotFound as e:
				failure = True
				writemsg(_("\n!!! Directory does not exist: '%s'\n") % \
					(e,), noiselevel=-1)
				writemsg(_("!!! Disabled FEATURES='%s'\n") % myfeature,
					noiselevel=-1)

			except portage.exception.PortageException as e:
				failure = True
				writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Failed resetting perms on %s='%s'\n") % \
					(kwargs["basedir_var"], basedir), noiselevel=-1)
				writemsg(_("!!! Disabled FEATURES='%s'\n") % myfeature,
					noiselevel=-1)

			if failure:
				mysettings.features.remove(myfeature)
				mysettings['FEATURES'] = ' '.join(sorted(mysettings.features))
				time.sleep(5)

def _prepare_workdir(mysettings):
	workdir_mode = 0o700
	try:
		mode = mysettings["PORTAGE_WORKDIR_MODE"]
		if mode.isdigit():
			parsed_mode = int(mode, 8)
		elif mode == "":
			raise KeyError()
		else:
			raise ValueError()
		if parsed_mode & 0o7777 != parsed_mode:
			raise ValueError("Invalid file mode: %s" % mode)
		else:
			workdir_mode = parsed_mode
	except KeyError as e:
		writemsg(_("!!! PORTAGE_WORKDIR_MODE is unset, using %s.\n") % oct(workdir_mode))
	except ValueError as e:
		if len(str(e)) > 0:
			writemsg("%s\n" % e)
		writemsg(_("!!! Unable to parse PORTAGE_WORKDIR_MODE='%s', using %s.\n") % \
		(mysettings["PORTAGE_WORKDIR_MODE"], oct(workdir_mode)))
	mysettings["PORTAGE_WORKDIR_MODE"] = oct(workdir_mode).replace('o', '')
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
			modified = portage.util.ensure_dirs(mysettings["PORT_LOGDIR"])
			if modified:
				apply_secpass_permissions(mysettings["PORT_LOGDIR"],
					uid=portage_uid, gid=portage_gid, mode=0o2770)
		except portage.exception.PortageException as e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg(_("!!! Permission issues with PORT_LOGDIR='%s'\n") % \
				mysettings["PORT_LOGDIR"], noiselevel=-1)
			writemsg(_("!!! Disabling logging.\n"), noiselevel=-1)
			while "PORT_LOGDIR" in mysettings:
				del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings and \
		os.access(mysettings["PORT_LOGDIR"], os.W_OK):
		logid_path = os.path.join(mysettings["PORTAGE_BUILDDIR"], ".logid")
		if not os.path.exists(logid_path):
			open(_unicode_encode(logid_path), 'w')
		logid_time = _unicode_decode(time.strftime("%Y%m%d-%H%M%S",
			time.gmtime(os.stat(logid_path).st_mtime)),
			encoding=_encodings['content'], errors='replace')

		if "split-log" in mysettings.features:
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				mysettings["PORT_LOGDIR"], "build", "%s/%s:%s.log" % \
				(mysettings["CATEGORY"], mysettings["PF"], logid_time))
		else:
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				mysettings["PORT_LOGDIR"], "%s:%s:%s.log" % \
				(mysettings["CATEGORY"], mysettings["PF"], logid_time))

		util.ensure_dirs(os.path.dirname(mysettings["PORTAGE_LOG_FILE"]))

	else:
		# NOTE: When sesandbox is enabled, the local SELinux security policies
		# may not allow output to be piped out of the sesandbox domain. The
		# current policy will allow it to work when a pty is available, but
		# not through a normal pipe. See bug #162404.
		mysettings["PORTAGE_LOG_FILE"] = os.path.join(
			mysettings["T"], "build.log")

def _doebuild_exit_status_check(mydo, settings):
	"""
	Returns an error string if the shell appeared
	to exit unsuccessfully, None otherwise.
	"""
	exit_status_file = settings.get("EBUILD_EXIT_STATUS_FILE")
	if not exit_status_file or \
		os.path.exists(exit_status_file):
		return None
	msg = _("The ebuild phase '%s' has exited "
	"unexpectedly. This type of behavior "
	"is known to be triggered "
	"by things such as failed variable "
	"assignments (bug #190128) or bad substitution "
	"errors (bug #200313). Normally, before exiting, bash should "
	"have displayed an error message above. If bash did not "
	"produce an error message above, it's possible "
	"that the ebuild has called `exit` when it "
	"should have called `die` instead. This behavior may also "
	"be triggered by a corrupt bash binary or a hardware "
	"problem such as memory or cpu malfunction. If the problem is not "
	"reproducible or it appears to occur randomly, then it is likely "
	"to be triggered by a hardware problem. "
	"If you suspect a hardware problem then you should "
	"try some basic hardware diagnostics such as memtest. "
	"Please do not report this as a bug unless it is consistently "
	"reproducible and you are sure that your bash binary and hardware "
	"are functioning properly.") % mydo
	return msg

def _doebuild_exit_status_check_and_log(settings, mydo, retval):
	msg = _doebuild_exit_status_check(mydo, settings)
	if msg:
		if retval == os.EX_OK:
			retval = 1
		from textwrap import wrap
		from portage.elog.messages import eerror
		for l in wrap(msg, 72):
			eerror(l, phase=mydo, key=settings.mycpv)
	return retval

def _doebuild_exit_status_unlink(exit_status_file):
	"""
	Double check to make sure it really doesn't exist
	and raise an OSError if it still does (it shouldn't).
	OSError if necessary.
	"""
	if not exit_status_file:
		return
	try:
		os.unlink(exit_status_file)
	except OSError:
		pass
	if os.path.exists(exit_status_file):
		os.unlink(exit_status_file)

_doebuild_manifest_exempt_depend = 0
_doebuild_manifest_cache = None
_doebuild_broken_ebuilds = set()
_doebuild_broken_manifests = set()

def doebuild(myebuild, mydo, myroot, mysettings, debug=0, listonly=0,
	fetchonly=0, cleanup=0, dbkey=None, use_cache=1, fetchall=0, tree=None,
	mydbapi=None, vartree=None, prev_mtimes=None,
	fd_pipes=None, returnpid=False):

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
	@param fetchall: Used to wrap fetch(), fetches all URIs (even ones invalid due to USE conditionals)
	@type fetchall: Boolean
	@param tree: Which tree to use ('vartree','porttree','bintree', etc..), defaults to 'porttree'
	@type tree: String
	@param mydbapi: a dbapi instance to pass to various functions; this should be a portdbapi instance.
	@type mydbapi: portdbapi instance
	@param vartree: A instance of vartree; used for aux_get calls, defaults to db[myroot]['vartree']
	@type vartree: vartree instance
	@param prev_mtimes: A dict of { filename:mtime } keys used by merge() to do config_protection
	@type prev_mtimes: dictionary
	@param fd_pipes: A dict of mapping for pipes, { '0': stdin, '1': stdout }
		for example.
	@type fd_pipes: Dictionary
	@param returnpid: Return a list of process IDs for a successful spawn, or
		an integer value if spawn is unsuccessful. NOTE: This requires the
		caller clean up all returned PIDs.
	@type returnpid: Boolean
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
	"setup":  [],
	"unpack": ["setup"],
	"prepare": ["unpack"],
	"configure": ["prepare"],
	"compile":["configure"],
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
	noauto = "noauto" in features
	from portage.data import secpass

	clean_phases = ("clean", "cleanrm")
	validcommands = ["help","clean","prerm","postrm","cleanrm","preinst","postinst",
	                "config", "info", "setup", "depend", "pretend",
	                "fetch", "fetchall", "digest",
	                "unpack", "prepare", "configure", "compile", "test",
	                "install", "rpm", "qmerge", "merge",
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

	if mydo == "fetchall":
		fetchall = 1
		mydo = "fetch"

	parallel_fetchonly = mydo in ("fetch", "fetchall") and \
		"PORTAGE_PARALLEL_FETCHONLY" in mysettings

	if mydo not in clean_phases and not os.path.exists(myebuild):
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
		global _doebuild_manifest_cache, _doebuild_broken_ebuilds, \
			_doebuild_broken_ebuilds

		if myebuild in _doebuild_broken_ebuilds:
			return 1

		pkgdir = os.path.dirname(myebuild)
		manifest_path = os.path.join(pkgdir, "Manifest")

		# Avoid checking the same Manifest several times in a row during a
		# regen with an empty cache.
		if _doebuild_manifest_cache is None or \
			_doebuild_manifest_cache.getFullname() != manifest_path:
			_doebuild_manifest_cache = None
			if not os.path.exists(manifest_path):
				out = portage.output.EOutput()
				out.eerror(_("Manifest not found for '%s'") % (myebuild,))
				_doebuild_broken_ebuilds.add(myebuild)
				return 1
			mf = Manifest(pkgdir, mysettings["DISTDIR"])

		else:
			mf = _doebuild_manifest_cache

		try:
			mf.checkFileHashes("EBUILD", os.path.basename(myebuild))
		except KeyError:
			out = portage.output.EOutput()
			out.eerror(_("Missing digest for '%s'") % (myebuild,))
			_doebuild_broken_ebuilds.add(myebuild)
			return 1
		except portage.exception.FileNotFound:
			out = portage.output.EOutput()
			out.eerror(_("A file listed in the Manifest "
				"could not be found: '%s'") % (myebuild,))
			_doebuild_broken_ebuilds.add(myebuild)
			return 1
		except portage.exception.DigestException as e:
			out = portage.output.EOutput()
			out.eerror(_("Digest verification failed:"))
			out.eerror("%s" % e.value[0])
			out.eerror(_("Reason: %s") % e.value[1])
			out.eerror(_("Got: %s") % e.value[2])
			out.eerror(_("Expected: %s") % e.value[3])
			_doebuild_broken_ebuilds.add(myebuild)
			return 1

		if mf.getFullname() in _doebuild_broken_manifests:
			return 1

		if mf is not _doebuild_manifest_cache:

			# Make sure that all of the ebuilds are
			# actually listed in the Manifest.
			glep55 = 'parse-eapi-glep-55' in mysettings.features
			for f in os.listdir(pkgdir):
				pf = None
				if glep55:
					pf, eapi = _split_ebuild_name_glep55(f)
				elif f[-7:] == '.ebuild':
					pf = f[:-7]
				if pf is not None and not mf.hasFile("EBUILD", f):
					f = os.path.join(pkgdir, f)
					if f not in _doebuild_broken_ebuilds:
						out = portage.output.EOutput()
						out.eerror(_("A file is not listed in the "
							"Manifest: '%s'") % (f,))
					_doebuild_broken_manifests.add(manifest_path)
					return 1

			# Only cache it if the above stray files test succeeds.
			_doebuild_manifest_cache = mf

	def exit_status_check(retval):
		msg = _doebuild_exit_status_check(mydo, mysettings)
		if msg:
			if retval == os.EX_OK:
				retval = 1
			from textwrap import wrap
			from portage.elog.messages import eerror
			for l in wrap(msg, 72):
				eerror(l, phase=mydo, key=mysettings.mycpv)
		return retval

	# Note: PORTAGE_BIN_PATH may differ from the global
	# constant when portage is reinstalling itself.
	portage_bin_path = mysettings["PORTAGE_BIN_PATH"]
	ebuild_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(EBUILD_SH_BINARY))
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))

	logfile=None
	builddir_lock = None
	tmpdir = None
	tmpdir_orig = None

	try:
		if mydo in ("digest", "manifest", "help"):
			# Temporarily exempt the depend phase from manifest checks, in case
			# aux_get calls trigger cache generation.
			_doebuild_manifest_exempt_depend += 1

		# If we don't need much space and we don't need a constant location,
		# we can temporarily override PORTAGE_TMPDIR with a random temp dir
		# so that there's no need for locking and it can be used even if the
		# user isn't in the portage group.
		if mydo in ("info",):
			from tempfile import mkdtemp
			tmpdir = mkdtemp()
			tmpdir_orig = mysettings["PORTAGE_TMPDIR"]
			mysettings["PORTAGE_TMPDIR"] = tmpdir

		doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
			use_cache, mydbapi)

		if mydo in clean_phases:
			retval = spawn(_shell_quote(ebuild_sh_binary) + " clean",
				mysettings, debug=debug, fd_pipes=fd_pipes, free=1,
				logfile=None, returnpid=returnpid)
			return retval

		restrict = set(mysettings.get('PORTAGE_RESTRICT', '').split())
		# get possible slot information from the deps file
		if mydo == "depend":
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
			droppriv = "userpriv" in mysettings.features
			if returnpid:
				mypids = spawn(_shell_quote(ebuild_sh_binary) + " depend",
					mysettings, fd_pipes=fd_pipes, returnpid=True,
					droppriv=droppriv)
				return mypids
			elif isinstance(dbkey, dict):
				mysettings["dbkey"] = ""
				pr, pw = os.pipe()
				fd_pipes = {
					0:sys.stdin.fileno(),
					1:sys.stdout.fileno(),
					2:sys.stderr.fileno(),
					9:pw}
				mypids = spawn(_shell_quote(ebuild_sh_binary) + " depend",
					mysettings,
					fd_pipes=fd_pipes, returnpid=True, droppriv=droppriv)
				os.close(pw) # belongs exclusively to the child process now
				f = os.fdopen(pr, 'rb')
				for k, v in zip(auxdbkeys,
					(_unicode_decode(line).rstrip('\n') for line in f)):
					dbkey[k] = v
				f.close()
				retval = os.waitpid(mypids[0], 0)[1]
				portage.process.spawned_pids.remove(mypids[0])
				# If it got a signal, return the signal that was sent, but
				# shift in order to distinguish it from a return value. (just
				# like portage.process.spawn() would do).
				if retval & 0xff:
					retval = (retval & 0xff) << 8
				else:
					# Otherwise, return its exit code.
					retval = retval >> 8
				if retval == os.EX_OK and len(dbkey) != len(auxdbkeys):
					# Don't trust bash's returncode if the
					# number of lines is incorrect.
					retval = 1
				return retval
			elif dbkey:
				mysettings["dbkey"] = dbkey
			else:
				mysettings["dbkey"] = \
					os.path.join(mysettings.depcachedir, "aux_db_key_temp")

			return spawn(_shell_quote(ebuild_sh_binary) + " depend",
				mysettings,
				droppriv=droppriv)

		# Validate dependency metadata here to ensure that ebuilds with invalid
		# data are never installed via the ebuild command. Don't bother when
		# returnpid == True since there's no need to do this every time emerge
		# executes a phase.
		if not returnpid:
			rval = _validate_deps(mysettings, myroot, mydo, mydbapi)
			if rval != os.EX_OK:
				return rval

		if "PORTAGE_TMPDIR" not in mysettings or \
			not os.path.isdir(mysettings["PORTAGE_TMPDIR"]):
			writemsg(_("The directory specified in your "
				"PORTAGE_TMPDIR variable, '%s',\n"
				"does not exist.  Please create this directory or "
				"correct your PORTAGE_TMPDIR setting.\n") % mysettings.get("PORTAGE_TMPDIR", ""), noiselevel=-1)
			return 1
		
		# as some people use a separate PORTAGE_TMPDIR mount
		# we prefer that as the checks below would otherwise be pointless
		# for those people.
		if os.path.exists(os.path.join(mysettings["PORTAGE_TMPDIR"], "portage")):
			checkdir = os.path.join(mysettings["PORTAGE_TMPDIR"], "portage")
		else:
			checkdir = mysettings["PORTAGE_TMPDIR"]

		if not os.access(checkdir, os.W_OK):
			writemsg(_("%s is not writable.\n"
				"Likely cause is that you've mounted it as readonly.\n") % checkdir,
				noiselevel=-1)
			return 1
		else:
			from tempfile import NamedTemporaryFile
			fd = NamedTemporaryFile(prefix="exectest-", dir=checkdir)
			os.chmod(fd.name, 0o755)
			if not os.access(fd.name, os.X_OK):
				writemsg(_("Can not execute files in %s\n"
					"Likely cause is that you've mounted it with one of the\n"
					"following mount options: 'noexec', 'user', 'users'\n\n"
					"Please make sure that portage can execute files in this directory.\n") % checkdir,
					noiselevel=-1)
				fd.close()
				return 1
			fd.close()
		del checkdir

		if mydo == "unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		# Build directory creation isn't required for any of these.
		# In the fetch phase, the directory is needed only for RESTRICT=fetch
		# in order to satisfy the sane $PWD requirement (from bug #239560)
		# when pkg_nofetch is spawned.
		have_build_dirs = False
		if not parallel_fetchonly and \
			mydo not in ('digest', 'help', 'manifest') and \
			not (mydo == 'fetch' and 'fetch' not in restrict):
			mystatus = prepare_build_dirs(myroot, mysettings, cleanup)
			if mystatus:
				return mystatus
			have_build_dirs = True

			# emerge handles logging externally
			if not returnpid:
				# PORTAGE_LOG_FILE is set by the
				# above prepare_build_dirs() call.
				logfile = mysettings.get("PORTAGE_LOG_FILE")

		if have_build_dirs:
			env_file = os.path.join(mysettings["T"], "environment")
			env_stat = None
			saved_env = None
			try:
				env_stat = os.stat(env_file)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
			if not env_stat:
				saved_env = os.path.join(
					os.path.dirname(myebuild), "environment.bz2")
				if not os.path.isfile(saved_env):
					saved_env = None
			if saved_env:
				retval = os.system(
					"bzip2 -dc %s > %s" % \
					(_shell_quote(saved_env),
					_shell_quote(env_file)))
				try:
					env_stat = os.stat(env_file)
				except OSError as e:
					if e.errno != errno.ENOENT:
						raise
					del e
				if os.WIFEXITED(retval) and \
					os.WEXITSTATUS(retval) == os.EX_OK and \
					env_stat and env_stat.st_size > 0:
					# This is a signal to ebuild.sh, so that it knows to filter
					# out things like SANDBOX_{DENY,PREDICT,READ,WRITE} that
					# would be preserved between normal phases.
					open(_unicode_encode(env_file + '.raw'), 'w')
				else:
					writemsg(_("!!! Error extracting saved "
						"environment: '%s'\n") % \
						saved_env, noiselevel=-1)
					try:
						os.unlink(env_file)
					except OSError as e:
						if e.errno != errno.ENOENT:
							raise
						del e
					env_stat = None
			if env_stat:
				pass
			else:
				for var in ("ARCH", ):
					value = mysettings.get(var)
					if value and value.strip():
						continue
					msg = _("%(var)s is not set... "
						"Are you missing the '%(configroot)setc/make.profile' symlink? "
						"Is the symlink correct? "
						"Is your portage tree complete?") % \
						{"var": var, "configroot": mysettings["PORTAGE_CONFIGROOT"]}
					from portage.elog.messages import eerror
					from textwrap import wrap
					for line in wrap(msg, 70):
						eerror(line, phase="setup", key=mysettings.mycpv)
					from portage.elog import elog_process
					elog_process(mysettings.mycpv, mysettings)
					return 1
			del env_file, env_stat, saved_env
			_doebuild_exit_status_unlink(
				mysettings.get("EBUILD_EXIT_STATUS_FILE"))
		else:
			mysettings.pop("EBUILD_EXIT_STATUS_FILE", None)

		# if any of these are being called, handle them -- running them out of
		# the sandbox -- and stop now.
		if mydo == "help":
			return spawn(_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile)
		elif mydo == "setup":
			retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo, mysettings,
				debug=debug, free=1, logfile=logfile, fd_pipes=fd_pipes,
				returnpid=returnpid)
			if returnpid:
				return retval
			retval = exit_status_check(retval)
			if secpass >= 2:
				""" Privileged phases may have left files that need to be made
				writable to a less privileged user."""
				apply_recursive_permissions(mysettings["T"],
					uid=portage_uid, gid=portage_gid, dirmode=0o70, dirmask=0,
					filemode=0o60, filemask=0)
			return retval
		elif mydo == "preinst":
			phase_retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile,
				fd_pipes=fd_pipes, returnpid=returnpid)

			if returnpid:
				return phase_retval

			phase_retval = exit_status_check(phase_retval)
			if phase_retval == os.EX_OK:
				_doebuild_exit_status_unlink(
					mysettings.get("EBUILD_EXIT_STATUS_FILE"))
				mysettings.pop("EBUILD_PHASE", None)
				phase_retval = spawn(
					" ".join(_post_pkg_preinst_cmd(mysettings)),
					mysettings, debug=debug, free=1, logfile=logfile)
				phase_retval = exit_status_check(phase_retval)
				if phase_retval != os.EX_OK:
					writemsg(_("!!! post preinst failed; exiting.\n"),
						noiselevel=-1)
			return phase_retval
		elif mydo == "postinst":
			phase_retval = spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile,
				fd_pipes=fd_pipes, returnpid=returnpid)

			if returnpid:
				return phase_retval

			phase_retval = exit_status_check(phase_retval)
			if phase_retval == os.EX_OK:
				_doebuild_exit_status_unlink(
					mysettings.get("EBUILD_EXIT_STATUS_FILE"))
				mysettings.pop("EBUILD_PHASE", None)
				phase_retval = spawn(" ".join(_post_pkg_postinst_cmd(mysettings)),
					mysettings, debug=debug, free=1, logfile=logfile)
				phase_retval = exit_status_check(phase_retval)
				if phase_retval != os.EX_OK:
					writemsg(_("!!! post postinst failed; exiting.\n"),
						noiselevel=-1)
			return phase_retval
		elif mydo in ("prerm", "postrm", "config", "info"):
			retval =  spawn(
				_shell_quote(ebuild_sh_binary) + " " + mydo,
				mysettings, debug=debug, free=1, logfile=logfile,
				fd_pipes=fd_pipes, returnpid=returnpid)

			if returnpid:
				return retval

			retval = exit_status_check(retval)
			return retval

		mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))

		emerge_skip_distfiles = returnpid
		emerge_skip_digest = returnpid
		# Only try and fetch the files if we are going to need them ...
		# otherwise, if user has FEATURES=noauto and they run `ebuild clean
		# unpack compile install`, we will try and fetch 4 times :/
		need_distfiles = not emerge_skip_distfiles and \
			(mydo in ("fetch", "unpack") or \
			mydo not in ("digest", "manifest") and "noauto" not in features)
		alist = mysettings.configdict["pkg"].get("A")
		aalist = mysettings.configdict["pkg"].get("AA")
		if alist is None or aalist is None:
			# Make sure we get the correct tree in case there are overlays.
			mytree = os.path.realpath(
				os.path.dirname(os.path.dirname(mysettings["O"])))
			useflags = mysettings["PORTAGE_USE"].split()
			try:
				alist = mydbapi.getFetchMap(mycpv, useflags=useflags,
					mytree=mytree)
				aalist = mydbapi.getFetchMap(mycpv, mytree=mytree)
			except portage.exception.InvalidDependString as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Invalid SRC_URI for '%s'.\n") % mycpv,
					noiselevel=-1)
				del e
				return 1
			mysettings.configdict["pkg"]["A"] = " ".join(alist)
			mysettings.configdict["pkg"]["AA"] = " ".join(aalist)
		else:
			alist = set(alist.split())
			aalist = set(aalist.split())
		if ("mirror" in features) or fetchall:
			fetchme = aalist
			checkme = aalist
		else:
			fetchme = alist
			checkme = alist

		if mydo == "fetch":
			# Files are already checked inside fetch(),
			# so do not check them again.
			checkme = []

		if not emerge_skip_distfiles and \
			need_distfiles and not fetch(
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
			elif mydo != 'fetch' and not emerge_skip_digest and \
				"digest" in mysettings.features:
				# Don't do this when called by emerge or when called just
				# for fetch (especially parallel-fetch) since it's not needed
				# and it can interfere with parallel tasks.
				digestgen(aalist, mysettings, overwrite=0, myportdb=mydbapi)
		except portage.exception.PermissionDenied as e:
			writemsg(_("!!! Permission Denied: %s\n") % (e,), noiselevel=-1)
			if mydo in ("digest", "manifest"):
				return 1

		# See above comment about fetching only when needed
		if not emerge_skip_distfiles and \
			not digestcheck(checkme, mysettings, "strict" in features):
			return 1

		if mydo == "fetch":
			return 0

		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		if (mydo != "setup" and "noauto" not in features) or mydo == "unpack":
			orig_distdir = mysettings["DISTDIR"]
			mysettings["PORTAGE_ACTUAL_DISTDIR"] = orig_distdir
			edpath = mysettings["DISTDIR"] = \
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "distdir")
			portage.util.ensure_dirs(edpath, gid=portage_gid, mode=0o755)

			# Remove any unexpected files or directories.
			for x in os.listdir(edpath):
				symlink_path = os.path.join(edpath, x)
				st = os.lstat(symlink_path)
				if x in alist and stat.S_ISLNK(st.st_mode):
					continue
				if stat.S_ISDIR(st.st_mode):
					shutil.rmtree(symlink_path)
				else:
					os.unlink(symlink_path)

			# Check for existing symlinks and recreate if necessary.
			for x in alist:
				symlink_path = os.path.join(edpath, x)
				target = os.path.join(orig_distdir, x)
				try:
					link_target = os.readlink(symlink_path)
				except OSError:
					os.symlink(target, symlink_path)
				else:
					if link_target != target:
						os.unlink(symlink_path)
						os.symlink(target, symlink_path)

		#initial dep checks complete; time to process main commands

		restrict = mysettings["PORTAGE_RESTRICT"].split()
		nosandbox = (("userpriv" in features) and \
			("usersandbox" not in features) and \
			"userpriv" not in restrict and \
			"nouserpriv" not in restrict)
		if nosandbox and ("userpriv" not in features or \
			"userpriv" in restrict or \
			"nouserpriv" in restrict):
			nosandbox = ("sandbox" not in features and \
				"usersandbox" not in features)

		if not process.sandbox_capable:
			nosandbox = True

		sesandbox = mysettings.selinux_enabled() and \
			"sesandbox" in mysettings.features

		droppriv = "userpriv" in mysettings.features and \
			"userpriv" not in restrict and \
			secpass >= 2

		fakeroot = "fakeroot" in mysettings.features

		ebuild_sh = _shell_quote(ebuild_sh_binary) + " %s"
		misc_sh = _shell_quote(misc_sh_binary) + " dyn_%s"

		# args are for the to spawn function
		actionmap = {
"pretend":  {"cmd":ebuild_sh, "args":{"droppriv":0,        "free":1,         "sesandbox":0,         "fakeroot":0}},
"setup":    {"cmd":ebuild_sh, "args":{"droppriv":0,        "free":1,         "sesandbox":0,         "fakeroot":0}},
"unpack":   {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":0,         "sesandbox":sesandbox, "fakeroot":0}},
"prepare":  {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":0,         "sesandbox":sesandbox, "fakeroot":0}},
"configure":{"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":nosandbox, "sesandbox":sesandbox, "fakeroot":0}},
"compile":  {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":nosandbox, "sesandbox":sesandbox, "fakeroot":0}},
"test":     {"cmd":ebuild_sh, "args":{"droppriv":droppriv, "free":nosandbox, "sesandbox":sesandbox, "fakeroot":0}},
"install":  {"cmd":ebuild_sh, "args":{"droppriv":0,        "free":0,         "sesandbox":sesandbox, "fakeroot":fakeroot}},
"rpm":      {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
"package":  {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
		}

		# merge the deps in so we have again a 'full' actionmap
		# be glad when this can die.
		for x in actionmap:
			if len(actionmap_deps.get(x, [])):
				actionmap[x]["dep"] = ' '.join(actionmap_deps[x])

		if mydo in actionmap:
			if mydo == "package":
				# Make sure the package directory exists before executing
				# this phase. This can raise PermissionDenied if
				# the current user doesn't have write access to $PKGDIR.
				parent_dir = os.path.join(mysettings["PKGDIR"],
					mysettings["CATEGORY"])
				portage.util.ensure_dirs(parent_dir)
				if not os.access(parent_dir, os.W_OK):
					raise portage.exception.PermissionDenied(
						"access('%s', os.W_OK)" % parent_dir)
			retval = spawnebuild(mydo,
				actionmap, mysettings, debug, logfile=logfile,
				fd_pipes=fd_pipes, returnpid=returnpid)
		elif mydo=="qmerge":
			# check to ensure install was run.  this *only* pops up when users
			# forget it and are using ebuild
			if not os.path.exists(
				os.path.join(mysettings["PORTAGE_BUILDDIR"], ".installed")):
				writemsg(_("!!! mydo=qmerge, but the install phase has not been run\n"),
					noiselevel=-1)
				return 1
			# qmerge is a special phase that implies noclean.
			if "noclean" not in mysettings.features:
				mysettings.features.add("noclean")
			#qmerge is specifically not supposed to do a runtime dep check
			retval = merge(
				mysettings["CATEGORY"], mysettings["PF"], mysettings["D"],
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "build-info"),
				myroot, mysettings, myebuild=mysettings["EBUILD"], mytree=tree,
				mydbapi=mydbapi, vartree=vartree, prev_mtimes=prev_mtimes)
		elif mydo=="merge":
			retval = spawnebuild("install", actionmap, mysettings, debug,
				alwaysdep=1, logfile=logfile, fd_pipes=fd_pipes,
				returnpid=returnpid)
			retval = exit_status_check(retval)
			if retval != os.EX_OK:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				from portage.elog import elog_process
				elog_process(mysettings.mycpv, mysettings)
			if retval == os.EX_OK:
				retval = merge(mysettings["CATEGORY"], mysettings["PF"],
					mysettings["D"], os.path.join(mysettings["PORTAGE_BUILDDIR"],
					"build-info"), myroot, mysettings,
					myebuild=mysettings["EBUILD"], mytree=tree, mydbapi=mydbapi,
					vartree=vartree, prev_mtimes=prev_mtimes)
		else:
			print(_("!!! Unknown mydo: %s") % mydo)
			return 1

		return retval

	finally:

		if tmpdir:
			mysettings["PORTAGE_TMPDIR"] = tmpdir_orig
			shutil.rmtree(tmpdir)
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

def _validate_deps(mysettings, myroot, mydo, mydbapi):

	invalid_dep_exempt_phases = \
		set(["clean", "cleanrm", "help", "prerm", "postrm"])
	dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	misc_keys = ["LICENSE", "PROPERTIES", "PROVIDE", "RESTRICT", "SRC_URI"]
	other_keys = ["SLOT"]
	all_keys = dep_keys + misc_keys + other_keys
	metadata = dict(zip(all_keys,
		mydbapi.aux_get(mysettings.mycpv, all_keys)))

	class FakeTree(object):
		def __init__(self, mydb):
			self.dbapi = mydb
	dep_check_trees = {myroot:{}}
	dep_check_trees[myroot]["porttree"] = \
		FakeTree(fakedbapi(settings=mysettings))

	msgs = []
	for dep_type in dep_keys:
		mycheck = dep_check(metadata[dep_type], None, mysettings,
			myuse="all", myroot=myroot, trees=dep_check_trees)
		if not mycheck[0]:
			msgs.append("  %s: %s\n    %s\n" % (
				dep_type, metadata[dep_type], mycheck[1]))

	for k in misc_keys:
		try:
			portage.dep.use_reduce(
				portage.dep.paren_reduce(metadata[k]), matchall=True)
		except portage.exception.InvalidDependString as e:
			msgs.append("  %s: %s\n    %s\n" % (
				k, metadata[k], str(e)))

	if not metadata["SLOT"]:
		msgs.append(_("  SLOT is undefined\n"))

	if msgs:
		portage.util.writemsg_level(_("Error(s) in metadata for '%s':\n") % \
			(mysettings.mycpv,), level=logging.ERROR, noiselevel=-1)
		for x in msgs:
			portage.util.writemsg_level(x,
				level=logging.ERROR, noiselevel=-1)
		if mydo not in invalid_dep_exempt_phases:
			return 1

	return os.EX_OK

expandcache={}

def _movefile(src, dest, **kwargs):
	"""Calls movefile and raises a PortageException if an error occurs."""
	if movefile(src, dest, **kwargs) is None:
		raise portage.exception.PortageException(
			"mv '%s' '%s'" % (src, dest))

def movefile(src, dest, newmtime=None, sstat=None, mysettings=None,
		hardlink_candidates=None, encoding=_encodings['fs']):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"

	if mysettings is None:
		global settings
		mysettings = settings

	selinux_enabled = mysettings.selinux_enabled()
	if selinux_enabled:
		selinux = _unicode_module_wrapper(_selinux, encoding=encoding)

	lchown = _unicode_func_wrapper(data.lchown, encoding=encoding)
	os = _unicode_module_wrapper(_os,
		encoding=encoding, overrides=_os_overrides)
	shutil = _unicode_module_wrapper(_shutil, encoding=encoding)

	try:
		if not sstat:
			sstat=os.lstat(src)

	except SystemExit as e:
		raise
	except Exception as e:
		print(_("!!! Stating source file failed... movefile()"))
		print("!!!",e)
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
		# Use normal stat/chflags for the parent since we want to
		# follow any symlinks to the real parent directory.
		pflags = os.stat(os.path.dirname(dest)).st_flags
		if pflags != 0:
			bsd_chflags.chflags(os.path.dirname(dest), 0)

	if destexists:
		if stat.S_ISLNK(dstat[stat.ST_MODE]):
			try:
				os.unlink(dest)
				destexists=0
			except SystemExit as e:
				raise
			except Exception as e:
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
				selinux.symlink(target, dest, src)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			# utime() only works on the target of a symlink, so it's not
			# possible to perserve mtime on symlinks.
			return os.lstat(dest)[stat.ST_MTIME]
		except SystemExit as e:
			raise
		except Exception as e:
			print(_("!!! failed to properly create symlink:"))
			print("!!!",dest,"->",target)
			print("!!!",e)
			return None

	hardlinked = False
	# Since identical files might be merged to multiple filesystems,
	# so os.link() calls might fail for some paths, so try them all.
	# For atomic replacement, first create the link as a temp file
	# and them use os.rename() to replace the destination.
	if hardlink_candidates:
		head, tail = os.path.split(dest)
		hardlink_tmp = os.path.join(head, ".%s._portage_merge_.%s" % \
			(tail, os.getpid()))
		try:
			os.unlink(hardlink_tmp)
		except OSError as e:
			if e.errno != errno.ENOENT:
				writemsg(_("!!! Failed to remove hardlink temp file: %s\n") % \
					(hardlink_tmp,), noiselevel=-1)
				writemsg("!!! %s\n" % (e,), noiselevel=-1)
				return None
			del e
		for hardlink_src in hardlink_candidates:
			try:
				os.link(hardlink_src, hardlink_tmp)
			except OSError:
				continue
			else:
				try:
					os.rename(hardlink_tmp, dest)
				except OSError as e:
					writemsg(_("!!! Failed to rename %s to %s\n") % \
						(hardlink_tmp, dest), noiselevel=-1)
					writemsg("!!! %s\n" % (e,), noiselevel=-1)
					return None
				hardlinked = True
				break

	renamefailed=1
	if hardlinked:
		renamefailed = False
	if not hardlinked and (selinux_enabled or sstat.st_dev == dstat.st_dev):
		try:
			if selinux_enabled:
				ret = selinux.rename(src, dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except OSError as e:
			if e.errno != errno.EXDEV:
				# Some random error.
				print(_("!!! Failed to move %(src)s to %(dest)s") % {"src": src, "dest": dest})
				print("!!!",e)
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		didcopy=0
		if stat.S_ISREG(sstat[stat.ST_MODE]):
			try: # For safety copy then move it over.
				if selinux_enabled:
					selinux.copyfile(src, dest + "#new")
					selinux.rename(dest + "#new", dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except SystemExit as e:
				raise
			except Exception as e:
				print(_('!!! copy %(src)s -> %(dest)s failed.') % {"src": src, "dest": dest})
				print("!!!",e)
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			a = process.spawn([MOVE_BINARY, '-f', src, dest], env=os.environ)
			if a != os.EX_OK:
				writemsg(_("!!! Failed to move special file:\n"), noiselevel=-1)
				writemsg(_("!!! '%(src)s' to '%(dest)s'\n") % \
					{"src": _unicode_decode(src, encoding=encoding),
					"dest": _unicode_decode(dest, encoding=encoding)}, noiselevel=-1)
				writemsg("!!! %s\n" % a, noiselevel=-1)
				return None # failure
		try:
			if didcopy:
				if stat.S_ISLNK(sstat[stat.ST_MODE]):
					lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				else:
					os.chown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
				os.chmod(dest, stat.S_IMODE(sstat[stat.ST_MODE])) # Sticky is reset on chown
				os.unlink(src)
		except SystemExit as e:
			raise
		except Exception as e:
			print(_("!!! Failed to chown/chmod/unlink in movefile()"))
			print("!!!",dest)
			print("!!!",e)
			return None

	# Always use stat_obj[stat.ST_MTIME] for the integral timestamp which
	# is returned, since the stat_obj.st_mtime float attribute rounds *up*
	# if the nanosecond part of the timestamp is 999999881 ns or greater.
	try:
		if hardlinked:
			newmtime = os.stat(dest)[stat.ST_MTIME]
		else:
			# Note: It is not possible to preserve nanosecond precision
			# (supported in POSIX.1-2008 via utimensat) with the IEEE 754
			# double precision float which only has a 53 bit significand.
			if newmtime is not None:
				os.utime(dest, (newmtime, newmtime))
			else:
				newmtime = sstat[stat.ST_MTIME]
				if renamefailed:
					# If rename succeeded then timestamps are automatically
					# preserved with complete precision because the source
					# and destination inode are the same. Otherwise, round
					# down to the nearest whole second since python's float
					# st_mtime cannot be used to preserve the st_mtim.tv_nsec
					# field with complete precision. Note that we have to use
					# stat_obj[stat.ST_MTIME] here because the float
					# stat_obj.st_mtime rounds *up* sometimes.
					os.utime(dest, (newmtime, newmtime))
	except OSError:
		# The utime can fail here with EPERM even though the move succeeded.
		# Instead of failing, use stat to return the mtime if possible.
		try:
			newmtime = os.stat(dest)[stat.ST_MTIME]
		except OSError as e:
			writemsg(_("!!! Failed to stat in movefile()\n"), noiselevel=-1)
			writemsg("!!! %s\n" % dest, noiselevel=-1)
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			return None

	if bsd_chflags:
		# Restore the flags we saved before moving
		if pflags:
			bsd_chflags.chflags(os.path.dirname(dest), pflags)

	return newmtime

def merge(mycat, mypkg, pkgloc, infloc, myroot, mysettings, myebuild=None,
	mytree=None, mydbapi=None, vartree=None, prev_mtimes=None, blockers=None,
	scheduler=None):
	if not os.access(myroot, os.W_OK):
		writemsg(_("Permission denied: access('%s', W_OK)\n") % myroot,
			noiselevel=-1)
		return errno.EACCES
	mylink = dblink(mycat, mypkg, myroot, mysettings, treetype=mytree,
		vartree=vartree, blockers=blockers, scheduler=scheduler)
	return mylink.merge(pkgloc, infloc, myroot, myebuild,
		mydbapi=mydbapi, prev_mtimes=prev_mtimes)

def unmerge(cat, pkg, myroot, mysettings, mytrimworld=1, vartree=None,
	ldpath_mtimes=None, scheduler=None):
	mylink = dblink(cat, pkg, myroot, mysettings, treetype="vartree",
		vartree=vartree, scheduler=scheduler)
	vartree = mylink.vartree
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

def dep_virtual(mysplit, mysettings):
	"Does virtual dependency conversion"
	warnings.warn("portage.dep_virtual() is deprecated",
		DeprecationWarning, stacklevel=2)
	newsplit=[]
	myvirtuals = mysettings.getvirtuals()
	for x in mysplit:
		if isinstance(x, list):
			newsplit.append(dep_virtual(x, mysettings))
		else:
			mykey=dep_getkey(x)
			mychoices = myvirtuals.get(mykey, None)
			if mychoices:
				if len(mychoices) == 1:
					a = x.replace(mykey, dep_getkey(mychoices[0]), 1)
				else:
					if x[0]=="!":
						# blocker needs "and" not "or(||)".
						a=[]
					else:
						a=['||']
					for y in mychoices:
						a.append(x.replace(mykey, dep_getkey(y), 1))
				newsplit.append(a)
			else:
				newsplit.append(x)
	return newsplit

def _expand_new_virtuals(mysplit, edebug, mydbapi, mysettings, myroot="/",
	trees=None, use_mask=None, use_force=None, **kwargs):
	"""
	In order to solve bug #141118, recursively expand new-style virtuals so
	as to collapse one or more levels of indirection, generating an expanded
	search space. In dep_zapdeps, new-style virtuals will be assigned
	zero cost regardless of whether or not they are currently installed. Virtual
	blockers are supported but only when the virtual expands to a single
	atom because it wouldn't necessarily make sense to block all the components
	of a compound virtual.  When more than one new-style virtual is matched,
	the matches are sorted from highest to lowest versions and the atom is
	expanded to || ( highest match ... lowest match )."""
	newsplit = []
	mytrees = trees[myroot]
	portdb = mytrees["porttree"].dbapi
	atom_graph = mytrees.get("atom_graph")
	parent = mytrees.get("parent")
	virt_parent = mytrees.get("virt_parent")
	graph_parent = None
	eapi = None
	if parent is not None:
		if virt_parent is not None:
			graph_parent = virt_parent
			eapi = virt_parent[0].metadata['EAPI']
		else:
			graph_parent = parent
			eapi = parent.metadata["EAPI"]
	repoman = not mysettings.local_config
	if kwargs["use_binaries"]:
		portdb = trees[myroot]["bintree"].dbapi
	myvirtuals = mysettings.getvirtuals()
	pprovideddict = mysettings.pprovideddict
	myuse = kwargs["myuse"]
	for x in mysplit:
		if x == "||":
			newsplit.append(x)
			continue
		elif isinstance(x, list):
			newsplit.append(_expand_new_virtuals(x, edebug, mydbapi,
				mysettings, myroot=myroot, trees=trees, use_mask=use_mask,
				use_force=use_force, **kwargs))
			continue

		if not isinstance(x, portage.dep.Atom):
			try:
				x = portage.dep.Atom(x)
			except portage.exception.InvalidAtom:
				if portage.dep._dep_check_strict:
					raise portage.exception.ParseError(
						_("invalid atom: '%s'") % x)
				else:
					# Only real Atom instances are allowed past this point.
					continue
			else:
				if x.blocker and x.blocker.overlap.forbid and \
					eapi in ("0", "1") and portage.dep._dep_check_strict:
					raise portage.exception.ParseError(
						_("invalid atom: '%s'") % (x,))
				if x.use and eapi in ("0", "1") and \
					portage.dep._dep_check_strict:
					raise portage.exception.ParseError(
						_("invalid atom: '%s'") % (x,))

		if repoman and x.use and x.use.conditional:
			evaluated_atom = portage.dep.remove_slot(x)
			if x.slot:
				evaluated_atom += ":%s" % x.slot
			evaluated_atom += str(x.use._eval_qa_conditionals(
				use_mask, use_force))
			x = portage.dep.Atom(evaluated_atom)

		if not repoman and \
			myuse is not None and isinstance(x, portage.dep.Atom) and x.use:
			if x.use.conditional:
				x = x.evaluate_conditionals(myuse)

		mykey = x.cp
		if not mykey.startswith("virtual/"):
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue
		mychoices = myvirtuals.get(mykey, [])
		if x.blocker:
			# Virtual blockers are no longer expanded here since
			# the un-expanded virtual atom is more useful for
			# maintaining a cache of blocker atoms.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue

		if repoman or not hasattr(portdb, 'match_pkgs'):
			if portdb.cp_list(x.cp):
				newsplit.append(x)
			else:
				# TODO: Add PROVIDE check for repoman.
				a = []
				for y in mychoices:
					a.append(dep.Atom(x.replace(x.cp, y.cp, 1)))
				if not a:
					newsplit.append(x)
				elif len(a) == 1:
					newsplit.append(a[0])
				else:
					newsplit.append(['||'] + a)
			continue

		pkgs = []
		# Ignore USE deps here, since otherwise we might not
		# get any matches. Choices with correct USE settings
		# will be preferred in dep_zapdeps().
		matches = portdb.match_pkgs(x.without_use)
		# Use descending order to prefer higher versions.
		matches.reverse()
		for pkg in matches:
			# only use new-style matches
			if pkg.cp.startswith("virtual/"):
				pkgs.append(pkg)
		if not (pkgs or mychoices):
			# This one couldn't be expanded as a new-style virtual.  Old-style
			# virtuals have already been expanded by dep_virtual, so this one
			# is unavailable and dep_zapdeps will identify it as such.  The
			# atom is not eliminated here since it may still represent a
			# dependency that needs to be satisfied.
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
			continue

		a = []
		for pkg in pkgs:
			virt_atom = '=' + pkg.cpv
			if x.use:
				virt_atom += str(x.use)
			virt_atom = dep.Atom(virt_atom)
			# According to GLEP 37, RDEPEND is the only dependency
			# type that is valid for new-style virtuals. Repoman
			# should enforce this.
			depstring = pkg.metadata['RDEPEND']
			pkg_kwargs = kwargs.copy()
			pkg_kwargs["myuse"] = pkg.use.enabled
			if edebug:
				util.writemsg_level(_("Virtual Parent:      %s\n") \
					% (pkg,), noiselevel=-1, level=logging.DEBUG)
				util.writemsg_level(_("Virtual Depstring:   %s\n") \
					% (depstring,), noiselevel=-1, level=logging.DEBUG)

			# Set EAPI used for validation in dep_check() recursion.
			mytrees["virt_parent"] = (pkg, virt_atom)

			try:
				mycheck = dep_check(depstring, mydbapi, mysettings,
					myroot=myroot, trees=trees, **pkg_kwargs)
			finally:
				# Restore previous EAPI after recursion.
				if virt_parent is not None:
					mytrees["virt_parent"] = virt_parent
				else:
					del mytrees["virt_parent"]

			if not mycheck[0]:
				raise portage.exception.ParseError(
					"%s: %s '%s'" % (y[0], mycheck[1], depstring))

			# pull in the new-style virtual
			mycheck[1].append(virt_atom)
			a.append(mycheck[1])
			if atom_graph is not None:
				atom_graph.add(virt_atom, graph_parent)
		# Plain old-style virtuals.  New-style virtuals are preferred.
		if not pkgs:
				for y in mychoices:
					new_atom = dep.Atom(x.replace(x.cp, y.cp, 1))
					matches = portdb.match(new_atom)
					# portdb is an instance of depgraph._dep_check_composite_db, so
					# USE conditionals are already evaluated.
					if matches and mykey in \
						portdb.aux_get(matches[-1], ['PROVIDE'])[0].split():
						a.append(new_atom)
						if atom_graph is not None:
							atom_graph.add(new_atom, graph_parent)

		if not a and mychoices:
			# Check for a virtual package.provided match.
			for y in mychoices:
				new_atom = dep.Atom(x.replace(x.cp, y.cp, 1))
				if match_from_list(new_atom,
					pprovideddict.get(new_atom.cp, [])):
					a.append(new_atom)
					if atom_graph is not None:
						atom_graph.add(new_atom, graph_parent)

		if not a:
			newsplit.append(x)
			if atom_graph is not None:
				atom_graph.add(x, graph_parent)
		elif len(a) == 1:
			newsplit.append(a[0])
		else:
			newsplit.append(['||'] + a)

	return newsplit

def dep_eval(deplist):
	if not deplist:
		return 1
	if deplist[0]=="||":
		#or list; we just need one "1"
		for x in deplist[1:]:
			if isinstance(x, list):
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
			if isinstance(x, list):
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
		for x, satisfied in zip(unreduced, reduced):
			if isinstance(x, list):
				unresolved += dep_zapdeps(x, satisfied, myroot,
					use_binaries=use_binaries, trees=trees)
			elif not satisfied:
				unresolved.append(x)
		return unresolved

	# We're at a ( || atom ... ) type level and need to make a choice
	deps = unreduced[1:]
	satisfieds = reduced[1:]

	# Our preference order is for an the first item that:
	# a) contains all unmasked packages with the same key as installed packages
	# b) contains all unmasked packages
	# c) contains masked installed packages
	# d) is the first item

	preferred_installed = []
	preferred_in_graph = []
	preferred_any_slot = []
	preferred_non_installed = []
	unsat_use_in_graph = []
	unsat_use_installed = []
	unsat_use_non_installed = []
	other = []

	# unsat_use_* must come after preferred_non_installed
	# for correct ordering in cases like || ( foo[a] foo[b] ).
	choice_bins = (
		preferred_in_graph,
		preferred_installed,
		preferred_any_slot,
		preferred_non_installed,
		unsat_use_in_graph,
		unsat_use_installed,
		unsat_use_non_installed,
		other,
	)

	# Alias the trees we'll be checking availability against
	parent   = trees[myroot].get("parent")
	priority = trees[myroot].get("priority")
	graph_db = trees[myroot].get("graph_db")
	vardb = None
	if "vartree" in trees[myroot]:
		vardb = trees[myroot]["vartree"].dbapi
	if use_binaries:
		mydbapi = trees[myroot]["bintree"].dbapi
	else:
		mydbapi = trees[myroot]["porttree"].dbapi

	# Sort the deps into installed, not installed but already 
	# in the graph and other, not installed and not in the graph
	# and other, with values of [[required_atom], availablility]
	for x, satisfied in zip(deps, satisfieds):
		if isinstance(x, list):
			atoms = dep_zapdeps(x, satisfied, myroot,
				use_binaries=use_binaries, trees=trees)
		else:
			atoms = [x]
		if vardb is None:
			# When called by repoman, we can simply return the first choice
			# because dep_eval() handles preference selection.
			return atoms

		all_available = True
		all_use_satisfied = True
		slot_map = {}
		cp_map = {}
		for atom in atoms:
			if atom.blocker:
				continue
			# Ignore USE dependencies here since we don't want USE
			# settings to adversely affect || preference evaluation.
			avail_pkg = mydbapi.match(atom.without_use)
			if avail_pkg:
				avail_pkg = avail_pkg[-1] # highest (ascending order)
				avail_slot = dep.Atom("%s:%s" % (atom.cp,
					mydbapi.aux_get(avail_pkg, ["SLOT"])[0]))
			if not avail_pkg:
				all_available = False
				all_use_satisfied = False
				break

			if atom.use:
				avail_pkg_use = mydbapi.match(atom)
				if not avail_pkg_use:
					all_use_satisfied = False
				else:
					# highest (ascending order)
					avail_pkg_use = avail_pkg_use[-1]
					if avail_pkg_use != avail_pkg:
						avail_pkg = avail_pkg_use
						avail_slot = dep.Atom("%s:%s" % (atom.cp,
							mydbapi.aux_get(avail_pkg, ["SLOT"])[0]))

			slot_map[avail_slot] = avail_pkg
			pkg_cp = cpv_getkey(avail_pkg)
			highest_cpv = cp_map.get(pkg_cp)
			if highest_cpv is None or \
				pkgcmp(catpkgsplit(avail_pkg)[1:],
				catpkgsplit(highest_cpv)[1:]) > 0:
				cp_map[pkg_cp] = avail_pkg

		this_choice = (atoms, slot_map, cp_map, all_available)
		if all_available:
			# The "all installed" criterion is not version or slot specific.
			# If any version of a package is already in the graph then we
			# assume that it is preferred over other possible packages choices.
			all_installed = True
			for atom in set(dep.Atom(atom.cp) for atom in atoms \
				if not atom.blocker):
				# New-style virtuals have zero cost to install.
				if not vardb.match(atom) and not atom.startswith("virtual/"):
					all_installed = False
					break
			all_installed_slots = False
			if all_installed:
				all_installed_slots = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if not vardb.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_installed_slots = False
						break
			if graph_db is None:
				if all_use_satisfied:
					if all_installed:
						if all_installed_slots:
							preferred_installed.append(this_choice)
						else:
							preferred_any_slot.append(this_choice)
					else:
						preferred_non_installed.append(this_choice)
				else:
					if all_installed_slots:
						unsat_use_installed.append(this_choice)
					else:
						unsat_use_non_installed.append(this_choice)
			else:
				all_in_graph = True
				for slot_atom in slot_map:
					# New-style virtuals have zero cost to install.
					if not graph_db.match(slot_atom) and \
						not slot_atom.startswith("virtual/"):
						all_in_graph = False
						break
				circular_atom = None
				if all_in_graph:
					if parent is None or priority is None:
						pass
					elif priority.buildtime:
						# Check if the atom would result in a direct circular
						# dependency and try to avoid that if it seems likely
						# to be unresolvable. This is only relevant for
						# buildtime deps that aren't already satisfied by an
						# installed package.
						cpv_slot_list = [parent]
						for atom in atoms:
							if atom.blocker:
								continue
							if vardb.match(atom):
								# If the atom is satisfied by an installed
								# version then it's not a circular dep.
								continue
							if atom.cp != parent.cp:
								continue
							if match_from_list(atom, cpv_slot_list):
								circular_atom = atom
								break
				if circular_atom is not None:
					other.append(this_choice)
				else:
					if all_use_satisfied:
						if all_in_graph:
							preferred_in_graph.append(this_choice)
						elif all_installed:
							if all_installed_slots:
								preferred_installed.append(this_choice)
							else:
								preferred_any_slot.append(this_choice)
						else:
							preferred_non_installed.append(this_choice)
					else:
						if all_in_graph:
							unsat_use_in_graph.append(this_choice)
						elif all_installed_slots:
							unsat_use_installed.append(this_choice)
						else:
							unsat_use_non_installed.append(this_choice)
		else:
			other.append(this_choice)

	# Prefer choices which contain upgrades to higher slots. This helps
	# for deps such as || ( foo:1 foo:2 ), where we want to prefer the
	# atom which matches the higher version rather than the atom furthest
	# to the left. Sorting is done separately for each of choice_bins, so
	# as not to interfere with the ordering of the bins. Because of the
	# bin separation, the main function of this code is to allow
	# --depclean to remove old slots (rather than to pull in new slots).
	for choices in choice_bins:
		if len(choices) < 2:
			continue
		for choice_1 in choices[1:]:
			atoms_1, slot_map_1, cp_map_1, all_available_1 = choice_1
			cps = set(cp_map_1)
			for choice_2 in choices:
				if choice_1 is choice_2:
					# choice_1 will not be promoted, so move on
					break
				atoms_2, slot_map_2, cp_map_2, all_available_2 = choice_2
				intersecting_cps = cps.intersection(cp_map_2)
				if not intersecting_cps:
					continue
				has_upgrade = False
				has_downgrade = False
				for cp in intersecting_cps:
					version_1 = cp_map_1[cp]
					version_2 = cp_map_2[cp]
					difference = pkgcmp(catpkgsplit(version_1)[1:],
						catpkgsplit(version_2)[1:])
					if difference != 0:
						if difference > 0:
							has_upgrade = True
						else:
							has_downgrade = True
							break
				if has_upgrade and not has_downgrade:
					# promote choice_1 in front of choice_2
					choices.remove(choice_1)
					index_2 = choices.index(choice_2)
					choices.insert(index_2, choice_1)
					break

	for allow_masked in (False, True):
		for choices in choice_bins:
			for atoms, slot_map, cp_map, all_available in choices:
				if all_available or allow_masked:
					return atoms

	assert(False) # This point should not be reachable

def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	'''
	@rtype: Atom
	'''
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	orig_dep = mydep
	if isinstance(orig_dep, dep.Atom):
		mydep = orig_dep.cp
	else:
		mydep = orig_dep
		has_cat = '/' in orig_dep
		if not has_cat:
			alphanum = re.search(r'\w', orig_dep)
			if alphanum:
				mydep = orig_dep[:alphanum.start()] + "null/" + \
					orig_dep[alphanum.start():]
		try:
			mydep = dep.Atom(mydep)
		except exception.InvalidAtom:
			# Missing '=' prefix is allowed for backward compatibility.
			if not dep.isvalidatom("=" + mydep):
				raise
			mydep = dep.Atom('=' + mydep)
			orig_dep = '=' + orig_dep
		if not has_cat:
			null_cat, pn = catsplit(mydep.cp)
			mydep = pn
		else:
			mydep = mydep.cp
	expanded = cpv_expand(mydep, mydb=mydb,
		use_cache=use_cache, settings=settings)
	return portage.dep.Atom(orig_dep.replace(mydep, expanded, 1))

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
			myusesplit = mysettings["PORTAGE_USE"].split()
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
	try:
		mysplit = portage.dep.paren_reduce(depstring)
	except portage.exception.InvalidDependString as e:
		return [0, str(e)]

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
	except portage.exception.InvalidDependString as e:
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
			use=use, mode=mode, myuse=myuse,
			use_force=useforce, use_mask=mymasks, use_cache=use_cache,
			use_binaries=use_binaries, myroot=myroot, trees=trees)
	except portage.exception.ParseError as e:
		return [0, str(e)]

	mysplit2=mysplit[:]
	mysplit2=dep_wordreduce(mysplit2,mysettings,mydbapi,mode,use_cache=use_cache)
	if mysplit2 is None:
		return [0, _("Invalid token")]

	writemsg("\n\n\n", 1)
	writemsg("mysplit:  %s\n" % (mysplit), 1)
	writemsg("mysplit2: %s\n" % (mysplit2), 1)

	try:
		selected_atoms = dep_zapdeps(mysplit, mysplit2, myroot,
			use_binaries=use_binaries, trees=trees)
	except portage.exception.InvalidAtom as e:
		if portage.dep._dep_check_strict:
			raise # This shouldn't happen.
		# dbapi.match() failed due to an invalid atom in
		# the dependencies of an installed package.
		return [0, _("Invalid atom: '%s'") % (e,)]

	return [1, selected_atoms]

def dep_wordreduce(mydeplist,mysettings,mydbapi,mode,use_cache=1):
	"Reduces the deplist to ones and zeros"
	deplist=mydeplist[:]
	for mypos, token in enumerate(deplist):
		if isinstance(deplist[mypos], list):
			#recurse
			deplist[mypos]=dep_wordreduce(deplist[mypos],mysettings,mydbapi,mode,use_cache=use_cache)
		elif deplist[mypos]=="||":
			pass
		elif token[:1] == "!":
			deplist[mypos] = False
		else:
			mykey = deplist[mypos].cp
			if mysettings and mykey in mysettings.pprovideddict and \
			        match_from_list(deplist[mypos], mysettings.pprovideddict[mykey]):
				deplist[mypos]=True
			elif mydbapi is None:
				# Assume nothing is satisfied.  This forces dep_zapdeps to
				# return all of deps the deps that have been selected
				# (excluding those satisfied by package.provided).
				deplist[mypos] = False
			else:
				if mode:
					x = mydbapi.xmatch(mode, deplist[mypos])
					if mode.startswith("minimum-"):
						mydep = []
						if x:
							mydep.append(x)
					else:
						mydep = x
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

def cpv_expand(mycpv, mydb=None, use_cache=1, settings=None):
	"""Given a string (packagename or virtual) expand it into a valid
	cat/package string. Virtuals use the mydb to determine which provided
	virtual is a valid choice and defaults to the first element when there
	are no installed/available candidates."""
	myslash=mycpv.split("/")
	mysplit = versions._pkgsplit(myslash[-1])
	if settings is None:
		settings = globals()["settings"]
	virts = settings.getvirtuals()
	virts_p = settings.get_virts_p()
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
			if hasattr(mydb, "cp_list"):
				if not mydb.cp_list(mykey, use_cache=use_cache):
					writemsg("virts[%s]: %s\n" % (str(mykey),virts[mykey]), 1)
					mykey_orig = mykey[:]
					for vkey in virts[mykey]:
						# The virtuals file can contain a versioned atom, so
						# it may be necessary to remove the operator and
						# version from the atom before it is passed into
						# dbapi.cp_list().
						if mydb.cp_list(vkey.cp):
							mykey = str(vkey)
							writemsg(_("virts chosen: %s\n") % (mykey), 1)
							break
					if mykey == mykey_orig:
						mykey = str(virts[mykey][0])
						writemsg(_("virts defaulted: %s\n") % (mykey), 1)
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
		if mydb and hasattr(mydb, "categories"):
			for x in mydb.categories:
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
				# AmbiguousPackageName inherits from ValueError,
				# for backward compatibility with calling code
				# that already handles ValueError.
				raise portage.exception.AmbiguousPackageName(matches)
		elif matches:
			mykey=matches[0]

		if not mykey and not isinstance(mydb, list):
			if myp in virts_p:
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

def getmaskingreason(mycpv, metadata=None, settings=None, portdb=None, return_location=False):
	from portage.util import grablines
	if settings is None:
		settings = globals()["settings"]
	if portdb is None:
		portdb = globals()["portdb"]
	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError(_("invalid CPV: %s") % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(zip(db_keys, portdb.aux_get(mycpv, db_keys)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
	if metadata is None:
		# Can't access SLOT due to corruption.
		cpv_slot_list = [mycpv]
	else:
		cpv_slot_list = ["%s:%s" % (mycpv, metadata["SLOT"])]
	mycp=mysplit[0]+"/"+mysplit[1]

	# XXX- This is a temporary duplicate of code from the config constructor.
	locations = [os.path.join(settings["PORTDIR"], "profiles")]
	locations.extend(settings.profiles)
	for ov in settings["PORTDIR_OVERLAY"].split():
		profdir = os.path.join(normalize_path(ov), "profiles")
		if os.path.isdir(profdir):
			locations.append(profdir)
	locations.append(os.path.join(settings["PORTAGE_CONFIGROOT"],
		USER_CONFIG_PATH))
	locations.reverse()
	pmasklists = [(x, grablines(os.path.join(x, "package.mask"), recursive=1)) for x in locations]

	if mycp in settings.pmaskdict:
		for x in settings.pmaskdict[mycp]:
			if match_from_list(x, cpv_slot_list):
				for pmask in pmasklists:
					comment = ""
					comment_valid = -1
					pmask_filename = os.path.join(pmask[0], "package.mask")
					for i in range(len(pmask[1])):
						l = pmask[1][i].strip()
						if l == "":
							comment = ""
							comment_valid = -1
						elif l[0] == "#":
							comment += (l+"\n")
							comment_valid = i + 1
						elif l == x:
							if comment_valid != i:
								comment = ""
							if return_location:
								return (comment, pmask_filename)
							else:
								return comment
						elif comment_valid != -1:
							# Apparently this comment applies to muliple masks, so
							# it remains valid until a blank line is encountered.
							comment_valid += 1
	if return_location:
		return (None, None)
	else:
		return None

def getmaskingstatus(mycpv, settings=None, portdb=None):
	if settings is None:
		settings = config(clone=globals()["settings"])
	if portdb is None:
		portdb = globals()["portdb"]

	metadata = None
	installed = False
	if not isinstance(mycpv, basestring):
		# emerge passed in a Package instance
		pkg = mycpv
		mycpv = pkg.cpv
		metadata = pkg.metadata
		installed = pkg.installed

	mysplit = catpkgsplit(mycpv)
	if not mysplit:
		raise ValueError(_("invalid CPV: %s") % mycpv)
	if metadata is None:
		db_keys = list(portdb._aux_cache_keys)
		try:
			metadata = dict(zip(db_keys, portdb.aux_get(mycpv, db_keys)))
		except KeyError:
			if not portdb.cpv_exists(mycpv):
				raise
			return ["corruption"]
		if "?" in metadata["LICENSE"]:
			settings.setcpv(mycpv, mydb=metadata)
			metadata["USE"] = settings["PORTAGE_USE"]
		else:
			metadata["USE"] = ""
	mycp=mysplit[0]+"/"+mysplit[1]

	rValue = []

	# profile checking
	if settings._getProfileMaskAtom(mycpv, metadata):
		rValue.append("profile")

	# package.mask checking
	if settings._getMaskAtom(mycpv, metadata):
		rValue.append("package.mask")

	# keywords checking
	eapi = metadata["EAPI"]
	mygroups = settings._getKeywords(mycpv, metadata)
	licenses = metadata["LICENSE"]
	properties = metadata["PROPERTIES"]
	slot = metadata["SLOT"]
	if eapi.startswith("-"):
		eapi = eapi[1:]
	if not eapi_is_supported(eapi):
		return ["EAPI %s" % eapi]
	elif _eapi_is_deprecated(eapi) and not installed:
		return ["EAPI %s" % eapi]
	egroups = settings.configdict["backupenv"].get(
		"ACCEPT_KEYWORDS", "").split()
	pgroups = settings["ACCEPT_KEYWORDS"].split()
	myarch = settings["ARCH"]
	if pgroups and myarch not in pgroups:
		"""For operating systems other than Linux, ARCH is not necessarily a
		valid keyword."""
		myarch = pgroups[0].lstrip("~")

	cp = cpv_getkey(mycpv)
	pkgdict = settings.pkeywordsdict.get(cp)
	matches = False
	if pkgdict:
		cpv_slot_list = ["%s:%s" % (mycpv, metadata["SLOT"])]
		for atom, pkgkeywords in pkgdict.items():
			if match_from_list(atom, cpv_slot_list):
				matches = True
				pgroups.extend(pkgkeywords)
	if matches or egroups:
		pgroups.extend(egroups)
		inc_pgroups = set()
		for x in pgroups:
			if x.startswith("-"):
				if x == "-*":
					inc_pgroups.clear()
				else:
					inc_pgroups.discard(x[1:])
			else:
				inc_pgroups.add(x)
		pgroups = inc_pgroups
		del inc_pgroups

	kmask = "missing"

	if '**' in pgroups:
		kmask = None
	else:
		for keyword in pgroups:
			if keyword in mygroups:
				kmask = None
				break

	if kmask:
		fallback = None
		for gp in mygroups:
			if gp=="*":
				kmask=None
				break
			elif gp=="-"+myarch and myarch in pgroups:
				kmask="-"+myarch
				break
			elif gp=="~"+myarch and myarch in pgroups:
				kmask="~"+myarch
				break

	try:
		missing_licenses = settings._getMissingLicenses(mycpv, metadata)
		if missing_licenses:
			allowed_tokens = set(["||", "(", ")"])
			allowed_tokens.update(missing_licenses)
			license_split = licenses.split()
			license_split = [x for x in license_split \
				if x in allowed_tokens]
			msg = license_split[:]
			msg.append("license(s)")
			rValue.append(" ".join(msg))
	except portage.exception.InvalidDependString as e:
		rValue.append("LICENSE: "+str(e))

	try:
		missing_properties = settings._getMissingProperties(mycpv, metadata)
		if missing_properties:
			allowed_tokens = set(["||", "(", ")"])
			allowed_tokens.update(missing_properties)
			properties_split = properties.split()
			properties_split = [x for x in properties_split \
					if x in allowed_tokens]
			msg = properties_split[:]
			msg.append("properties")
			rValue.append(" ".join(msg))
	except portage.exception.InvalidDependString as e:
		rValue.append("PROPERTIES: "+str(e))

	# Only show KEYWORDS masks for installed packages
	# if they're not masked for any other reason.
	if kmask and (not installed or not rValue):
		rValue.append(kmask+" keyword")

	return rValue

auxdbkeys=[
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE', 'UNUSED_00',
	'PDEPEND',   'PROVIDE', 'EAPI',
	'PROPERTIES', 'DEFINED_PHASES', 'UNUSED_05', 'UNUSED_04',
	'UNUSED_03', 'UNUSED_02', 'UNUSED_01',
	]
auxdbkeylen=len(auxdbkeys)

def pkgmerge(mytbz2, myroot, mysettings, mydbapi=None,
	vartree=None, prev_mtimes=None, blockers=None):
	"""will merge a .tbz2 file, returning a list of runtime dependencies
		that must be satisfied, or None if there was a merge error.	This
		code assumes the package exists."""

	warnings.warn("portage.pkgmerge() is deprecated",
		DeprecationWarning, stacklevel=2)

	global db
	if mydbapi is None:
		mydbapi = db[myroot]["bintree"].dbapi
	if vartree is None:
		vartree = db[myroot]["vartree"]
	if mytbz2[-5:]!=".tbz2":
		print(_("!!! Not a .tbz2 file"))
		return 1

	tbz2_lock = None
	mycat = None
	mypkg = None
	did_merge_phase = False
	success = False
	try:
		""" Don't lock the tbz2 file because the filesytem could be readonly or
		shared by a cluster."""
		#tbz2_lock = portage.locks.lockfile(mytbz2, wantnewlockfile=1)

		mypkg = os.path.basename(mytbz2)[:-5]
		xptbz2 = portage.xpak.tbz2(mytbz2)
		mycat = xptbz2.getfile(_unicode_encode("CATEGORY",
			encoding=_encodings['repo.content']))
		if not mycat:
			writemsg(_("!!! CATEGORY info missing from info chunk, aborting...\n"),
				noiselevel=-1)
			return 1
		mycat = _unicode_decode(mycat,
			encoding=_encodings['repo.content'], errors='replace')
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
			uid=portage_uid, gid=portage_gid, mode=0o70, mask=0)
		catdir_lock = portage.locks.lockdir(catdir)
		portage.util.ensure_dirs(catdir,
			uid=portage_uid, gid=portage_gid, mode=0o70, mask=0)
		try:
			shutil.rmtree(builddir)
		except (IOError, OSError) as e:
			if e.errno != errno.ENOENT:
				raise
			del e
		for mydir in (builddir, pkgloc, infloc):
			portage.util.ensure_dirs(mydir, uid=portage_uid,
				gid=portage_gid, mode=0o755)
		writemsg_stdout(_(">>> Extracting info\n"))
		xptbz2.unpackinfo(infloc)
		mysettings.setcpv(mycat + "/" + mypkg, mydb=mydbapi)
		# Store the md5sum in the vdb.
		fp = open(_unicode_encode(os.path.join(infloc, 'BINPKGMD5')), 'w')
		fp.write(str(portage.checksum.perform_md5(mytbz2))+"\n")
		fp.close()

		# This gives bashrc users an opportunity to do various things
		# such as remove binary packages after they're installed.
		mysettings["PORTAGE_BINPKG_FILE"] = mytbz2
		mysettings.backup_changes("PORTAGE_BINPKG_FILE")
		debug = mysettings.get("PORTAGE_DEBUG", "") == "1"

		# Eventually we'd like to pass in the saved ebuild env here.
		retval = doebuild(myebuild, "setup", myroot, mysettings, debug=debug,
			tree="bintree", mydbapi=mydbapi, vartree=vartree)
		if retval != os.EX_OK:
			writemsg(_("!!! Setup failed: %s\n") % retval, noiselevel=-1)
			return retval

		writemsg_stdout(_(">>> Extracting %s\n") % mypkg)
		retval = portage.process.spawn_bash(
			"bzip2 -dqc -- '%s' | tar -xp -C '%s' -f -" % (mytbz2, pkgloc),
			env=mysettings.environ())
		if retval != os.EX_OK:
			writemsg(_("!!! Error Extracting '%s'\n") % mytbz2, noiselevel=-1)
			return retval
		#portage.locks.unlockfile(tbz2_lock)
		#tbz2_lock = None

		mylink = dblink(mycat, mypkg, myroot, mysettings, vartree=vartree,
			treetype="bintree", blockers=blockers)
		retval = mylink.merge(pkgloc, infloc, myroot, myebuild, cleanup=0,
			mydbapi=mydbapi, prev_mtimes=prev_mtimes)
		did_merge_phase = True
		success = retval == os.EX_OK
		return retval
	finally:
		mysettings.pop("PORTAGE_BINPKG_FILE", None)
		if tbz2_lock:
			portage.locks.unlockfile(tbz2_lock)
		if True:
			if not did_merge_phase:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				from portage.elog import elog_process
				elog_process(mycat + "/" + mypkg, mysettings)
			try:
				if success:
					shutil.rmtree(builddir)
			except (IOError, OSError) as e:
				if e.errno != errno.ENOENT:
					raise
				del e

def deprecated_profile_check(settings=None):
	config_root = "/"
	if settings is not None:
		config_root = settings["PORTAGE_CONFIGROOT"]
	deprecated_profile_file = os.path.join(config_root,
		DEPRECATED_PROFILE_FILE)
	if not os.access(deprecated_profile_file, os.R_OK):
		return False
	dcontent = codecs.open(_unicode_encode(deprecated_profile_file,
		encoding=_encodings['fs'], errors='strict'), 
		mode='r', encoding=_encodings['content'], errors='replace').readlines()
	writemsg(colorize("BAD", _("\n!!! Your current profile is "
		"deprecated and not supported anymore.")) + "\n", noiselevel=-1)
	writemsg(colorize("BAD", _("!!! Use eselect profile to update your "
		"profile.")) + "\n", noiselevel=-1)
	if not dcontent:
		writemsg(colorize("BAD", _("!!! Please refer to the "
			"Gentoo Upgrading Guide.")) + "\n", noiselevel=-1)
		return True
	newprofile = dcontent[0]
	writemsg(colorize("BAD", _("!!! Please upgrade to the "
		"following profile if possible:")) + "\n", noiselevel=-1)
	writemsg(8*" " + colorize("GOOD", newprofile) + "\n", noiselevel=-1)
	if len(dcontent) > 1:
		writemsg(_("To upgrade do the following steps:\n"), noiselevel=-1)
		for myline in dcontent[1:]:
			writemsg(myline, noiselevel=-1)
		writemsg("\n\n", noiselevel=-1)
	return True

# gets virtual package settings
def getvirtuals(myroot):
	"""
	Calls portage.settings.getvirtuals().
	@deprecated: Use portage.settings.getvirtuals().
	"""
	global settings
	warnings.warn("portage.getvirtuals() is deprecated",
		DeprecationWarning, stacklevel=2)
	return settings.getvirtuals()

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
		f = atomic_ofstream(filename, mode='wb')
		pickle.dump(d, f, protocol=2)
		f.close()
		portage.util.apply_secpass_permissions(filename,
			uid=uid, gid=portage_gid, mode=0o644)
	except (IOError, OSError) as e:
		pass

def portageexit():
	global uid,portage_gid,portdb,db
	if secpass and os.environ.get("SANDBOX_ON") != "1":
		close_portdbapi_caches()
		commit_mtimedb()

atexit_register(portageexit)

def _global_updates(trees, prev_mtimes):
	"""
	Perform new global updates if they exist in $PORTDIR/profiles/updates/.

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
	root = "/"
	mysettings = trees["/"]["vartree"].settings
	updpath = os.path.join(mysettings["PORTDIR"], "profiles", "updates")

	try:
		if mysettings["PORTAGE_CALLER"] == "fixpackages":
			update_data = grab_updates(updpath)
		else:
			update_data = grab_updates(updpath, prev_mtimes)
	except portage.exception.DirectoryNotFound:
		writemsg(_("--- 'profiles/updates' is empty or "
			"not available. Empty portage tree?\n"), noiselevel=1)
		return
	myupd = None
	if len(update_data) > 0:
		do_upgrade_packagesmessage = 0
		myupd = []
		timestamps = {}
		for mykey, mystat, mycontent in update_data:
			writemsg_stdout("\n\n")
			writemsg_stdout(colorize("GOOD",
				_("Performing Global Updates: "))+bold(mykey)+"\n")
			writemsg_stdout(_("(Could take a couple of minutes if you have a lot of binary packages.)\n"))
			writemsg_stdout(_("  %s='update pass'  %s='binary update'  "
				"%s='/var/db update'  %s='/var/db move'\n"
				"  %s='/var/db SLOT move'  %s='binary move'  "
				"%s='binary SLOT move'\n  %s='update /etc/portage/package.*'\n") % \
				(bold("."), bold("*"), bold("#"), bold("@"), bold("s"), bold("%"), bold("S"), bold("p")))
			valid_updates, errors = parse_updates(mycontent)
			myupd.extend(valid_updates)
			writemsg_stdout(len(valid_updates) * "." + "\n")
			if len(errors) == 0:
				# Update our internal mtime since we
				# processed all of our directives.
				timestamps[mykey] = mystat[stat.ST_MTIME]
			else:
				for msg in errors:
					writemsg("%s\n" % msg, noiselevel=-1)

		world_file = os.path.join(root, WORLD_FILE)
		world_list = grabfile(world_file)
		world_modified = False
		for update_cmd in myupd:
			for pos, atom in enumerate(world_list):
				new_atom = update_dbentry(update_cmd, atom)
				if atom != new_atom:
					world_list[pos] = new_atom
					world_modified = True
		if world_modified:
			world_list.sort()
			write_atomic(world_file,
				"".join("%s\n" % (x,) for x in world_list))

		update_config_files("/",
			mysettings.get("CONFIG_PROTECT","").split(),
			mysettings.get("CONFIG_PROTECT_MASK","").split(),
			myupd)

		trees["/"]["bintree"] = binarytree("/", mysettings["PKGDIR"],
			settings=mysettings)
		vardb = trees["/"]["vartree"].dbapi
		bindb = trees["/"]["bintree"].dbapi
		if not os.access(bindb.bintree.pkgdir, os.W_OK):
			bindb = None
		for update_cmd in myupd:
			if update_cmd[0] == "move":
				moves = vardb.move_ent(update_cmd)
				if moves:
					writemsg_stdout(moves * "@")
				if bindb:
					moves = bindb.move_ent(update_cmd)
					if moves:
						writemsg_stdout(moves * "%")
			elif update_cmd[0] == "slotmove":
				moves = vardb.move_slot_ent(update_cmd)
				if moves:
					writemsg_stdout(moves * "s")
				if bindb:
					moves = bindb.move_slot_ent(update_cmd)
					if moves:
						writemsg_stdout(moves * "S")

		# The above global updates proceed quickly, so they
		# are considered a single mtimedb transaction.
		if len(timestamps) > 0:
			# We do not update the mtime in the mtimedb
			# until after _all_ of the above updates have
			# been processed because the mtimedb will
			# automatically commit when killed by ctrl C.
			for mykey, mtime in timestamps.items():
				prev_mtimes[mykey] = mtime

		# We gotta do the brute force updates for these now.
		if mysettings["PORTAGE_CALLER"] == "fixpackages" or \
		"fixpackages" in mysettings.features:
			def onUpdate(maxval, curval):
				if curval > 0:
					writemsg_stdout("#")
			vardb.update_ents(myupd, onUpdate=onUpdate)
			if bindb:
				def onUpdate(maxval, curval):
					if curval > 0:
						writemsg_stdout("*")
				bindb.update_ents(myupd, onUpdate=onUpdate)
		else:
			do_upgrade_packagesmessage = 1

		# Update progress above is indicated by characters written to stdout so
		# we print a couple new lines here to separate the progress output from
		# what follows.
		print()
		print()

		if do_upgrade_packagesmessage and bindb and \
			bindb.cpv_all():
			writemsg_stdout(_(" ** Skipping packages. Run 'fixpackages' or set it in FEATURES to fix the tbz2's in the packages directory.\n"))
			writemsg_stdout(bold(_("Note: This can take a very long time.")))
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
			f = open(_unicode_encode(filename), 'rb')
			mypickle = pickle.Unpickler(f)
			try:
				mypickle.find_global = None
			except AttributeError:
				# TODO: If py3k, override Unpickler.find_class().
				pass
			d = mypickle.load()
			f.close()
			del f
		except (IOError, OSError, EOFError, ValueError, pickle.UnpicklingError) as e:
			if isinstance(e, pickle.UnpicklingError):
				writemsg(_("!!! Error loading '%s': %s\n") % \
					(filename, str(e)), noiselevel=-1)
			del e
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

		for k in list(d):
			if k not in mtimedbkeys:
				writemsg(_("Deleting invalid mtimedb key: %s\n") % str(k))
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

	myroots = [(settings["ROOT"], settings)]
	if settings["ROOT"] != "/":

		# When ROOT != "/" we only want overrides from the calling
		# environment to apply to the config that's associated
		# with ROOT != "/", so pass a nearly empty dict for the env parameter.
		clean_env = {}
		for k in ('PATH', 'TERM'):
			v = settings.get(k)
			if v is not None:
				clean_env[k] = v
		settings = config(config_root=None, target_root="/", env=clean_env)
		settings.lock()
		myroots.append((settings["ROOT"], settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, {}))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals, myroot)
		trees[myroot].addLazySingleton(
			"vartree", vartree, myroot, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, myroot, settings=mysettings)
		trees[myroot].addLazySingleton("bintree",
			binarytree, myroot, mysettings["PKGDIR"], settings=mysettings)
	return trees

class _LegacyGlobalProxy(proxy.objectproxy.ObjectProxy):
	"""
	Instances of these serve as proxies to global variables
	that are initialized on demand.
	"""

	__slots__ = ('_name',)

	def __init__(self, name):
		proxy.objectproxy.ObjectProxy.__init__(self)
		object.__setattr__(self, '_name', name)

	def _get_target(self):
		init_legacy_globals()
		name = object.__getattribute__(self, '_name')
		return globals()[name]

class _PortdbProxy(proxy.objectproxy.ObjectProxy):
	"""
	The portdb is initialized separately from the rest
	of the variables, since sometimes the other variables
	are needed while the portdb is not.
	"""

	__slots__ = ()

	def _get_target(self):
		init_legacy_globals()
		global db, portdb, root, _portdb_initialized
		if not _portdb_initialized:
			portdb = db[root]["porttree"].dbapi
			_portdb_initialized = True
		return portdb

class _MtimedbProxy(proxy.objectproxy.ObjectProxy):
	"""
	The mtimedb is independent from the portdb and other globals.
	"""

	__slots__ = ('_name',)

	def __init__(self, name):
		proxy.objectproxy.ObjectProxy.__init__(self)
		object.__setattr__(self, '_name', name)

	def _get_target(self):
		global mtimedb, mtimedbfile, _mtimedb_initialized
		if not _mtimedb_initialized:
			mtimedbfile = os.path.join(os.path.sep,
				CACHE_PATH, "mtimedb")
			mtimedb = MtimeDB(mtimedbfile)
			_mtimedb_initialized = True
		name = object.__getattribute__(self, '_name')
		return globals()[name]

_legacy_global_var_names = ("archlist", "db", "features",
	"groups", "mtimedb", "mtimedbfile", "pkglines",
	"portdb", "profiledir", "root", "selinux_enabled",
	"settings", "thirdpartymirrors", "usedefaults")

def _disable_legacy_globals():
	"""
	This deletes the ObjectProxy instances that are used
	for lazy initialization of legacy global variables.
	The purpose of deleting them is to prevent new code
	from referencing these deprecated variables.
	"""
	global _legacy_global_var_names
	for k in _legacy_global_var_names:
		globals().pop(k, None)

# Initialization of legacy globals.  No functions/classes below this point
# please!  When the above functions and classes become independent of the
# below global variables, it will be possible to make the below code
# conditional on a backward compatibility flag (backward compatibility could
# be disabled via an environment variable, for example).  This will enable new
# code that is aware of this flag to import portage without the unnecessary
# overhead (and other issues!) of initializing the legacy globals.

def init_legacy_globals():
	global _globals_initialized
	if _globals_initialized:
		return
	_globals_initialized = True

	global db, settings, root, portdb, selinux_enabled, mtimedbfile, mtimedb, \
	archlist, features, groups, pkglines, thirdpartymirrors, usedefaults, \
	profiledir, flushmtimedb

	# Portage needs to ensure a sane umask for the files it creates.
	os.umask(0o22)

	kwargs = {}
	for k, envvar in (("config_root", "PORTAGE_CONFIGROOT"), ("target_root", "ROOT")):
		kwargs[k] = os.environ.get(envvar, "/")

	global _initializing_globals
	_initializing_globals = True
	db = create_trees(**kwargs)
	del _initializing_globals

	settings = db["/"]["vartree"].settings

	for myroot in db:
		if myroot != "/":
			settings = db[myroot]["vartree"].settings
			break

	root = settings["ROOT"]
	output._init(config_root=settings['PORTAGE_CONFIGROOT'])

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
	profiledir  = os.path.join(settings["PORTAGE_CONFIGROOT"], PROFILE_PATH)
	if not os.path.isdir(profiledir):
		profiledir = None
	def flushmtimedb(record):
		writemsg("portage.flushmtimedb() is DEPRECATED\n")
	# ========================================================================
	# COMPATIBILITY
	# These attributes should not be used
	# within Portage under any circumstances.
	# ========================================================================

if True:

	_mtimedb_initialized = False
	mtimedb     = _MtimedbProxy("mtimedb")
	mtimedbfile = _MtimedbProxy("mtimedbfile")

	_portdb_initialized  = False
	portdb = _PortdbProxy()

	_globals_initialized = False

	for k in ("db", "settings", "root", "selinux_enabled",
		"archlist", "features", "groups",
		"pkglines", "thirdpartymirrors", "usedefaults", "profiledir",
		"flushmtimedb"):
		globals()[k] = _LegacyGlobalProxy(k)

# Clear the cache
dircache={}

# ============================================================================
# ============================================================================

