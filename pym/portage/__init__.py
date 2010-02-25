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

