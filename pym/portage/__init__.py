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
		'portage.dbapi.cpv_expand:cpv_expand',
		'portage.dbapi.dep_expand:dep_expand',
		'portage.dbapi.porttree:close_portdbapi_caches,FetchlistDict,' + \
			'portagetree,portdbapi',
		'portage.dbapi.vartree:vardbapi,vartree,dblink',
		'portage.dbapi.virtual:fakedbapi',
		'portage.dep',
		'portage.dep:best_match_to_list,dep_getcpv,dep_getkey,' + \
			'flatten,get_operator,isjustname,isspecific,isvalidatom,' + \
			'match_from_list,match_to_list',
		'portage.dep.dep_check:dep_check,dep_eval,dep_wordreduce,dep_zapdeps',
		'portage.eclass_cache',
		'portage.env.loaders',
		'portage.exception',
		'portage.getbinpkg',
		'portage.locks',
		'portage.locks:lockdir,lockfile,unlockdir,unlockfile',
		'portage.mail',
		'portage.manifest:Manifest',
		'portage.output',
		'portage.output:bold,colorize',
		'portage.package.ebuild.doebuild:doebuild,' + \
			'doebuild_environment,spawn,spawnebuild',
		'portage.package.ebuild.config:autouse,best_from_dict,' + \
			'check_config_instance,config',
		'portage.package.ebuild.digestcheck:digestcheck',
		'portage.package.ebuild.digestgen:digestgen',
		'portage.package.ebuild.fetch:fetch',
		'portage.package.ebuild.getmaskingreason:getmaskingreason',
		'portage.package.ebuild.getmaskingstatus:getmaskingstatus',
		'portage.package.ebuild.prepare_build_dirs:prepare_build_dirs',
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
		'portage.util.env_update:env_update',
		'portage.util.ExtractKernelVersion:ExtractKernelVersion',
		'portage.util.listdir:cacheddir,listdir',
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

_doebuild_manifest_exempt_depend = 0

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
			vartree.dbapi.plib_registry.load()
			vartree.dbapi.plib_registry.pruneNonExisting()
			retval = mylink.unmerge(trimworld=mytrimworld, cleanup=1,
				ldpath_mtimes=ldpath_mtimes)
			if retval == os.EX_OK:
				mylink.delete()
			return retval
		return os.EX_OK
	finally:
		vartree.dbapi.linkmap._clear_cache()
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

auxdbkeys = (
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE', 'UNUSED_00',
	'PDEPEND',   'PROVIDE', 'EAPI',
	'PROPERTIES', 'DEFINED_PHASES', 'UNUSED_05', 'UNUSED_04',
	'UNUSED_03', 'UNUSED_02', 'UNUSED_01',
)
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

