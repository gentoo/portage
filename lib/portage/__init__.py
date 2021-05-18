# Copyright 1998-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# pylint: disable=ungrouped-imports

VERSION = "HEAD"

# ===========================================================================
# START OF IMPORTS -- START OF IMPORTS -- START OF IMPORTS -- START OF IMPORT
# ===========================================================================

try:
	import asyncio
	import sys
	import errno
	if not hasattr(errno, 'ESTALE'):
		# ESTALE may not be defined on some systems, such as interix.
		errno.ESTALE = -1
	import multiprocessing.util
	import re
	import types
	import platform

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
	sys.stderr.write("    "+str(e)+"\n\n")
	raise

try:

	import portage.proxy.lazyimport
	import portage.proxy as proxy
	proxy.lazyimport.lazyimport(globals(),
		'portage.cache.cache_errors:CacheError',
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
		'portage.dbapi.vartree:dblink,merge,unmerge,vardbapi,vartree',
		'portage.dbapi.virtual:fakedbapi',
		'portage.debug',
		'portage.dep',
		'portage.dep:best_match_to_list,dep_getcpv,dep_getkey,' + \
			'flatten,get_operator,isjustname,isspecific,isvalidatom,' + \
			'match_from_list,match_to_list',
		'portage.dep.dep_check:dep_check,dep_eval,dep_wordreduce,dep_zapdeps',
		'portage.eclass_cache',
		'portage.elog',
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
		'portage.package.ebuild.deprecated_profile_check:' + \
			'deprecated_profile_check',
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
		'portage.util.movefile:movefile',
		'portage.util.mtimedb:MtimeDB',
		'portage.versions',
		'portage.versions:best,catpkgsplit,catsplit,cpv_getkey,' + \
			'cpv_getkey@getCPFromCPV,endversion_keys,' + \
			'suffix_value@endversion,pkgcmp,pkgsplit,vercmp,ververify',
		'portage.xpak',
		'subprocess',
		'time',
	)

	from collections import OrderedDict

	import portage.const
	from portage.const import VDB_PATH, PRIVATE_PATH, CACHE_PATH, DEPCACHE_PATH, \
		USER_CONFIG_PATH, MODULES_FILE_PATH, CUSTOM_PROFILE_PATH, PORTAGE_BASE_PATH, \
		PORTAGE_BIN_PATH, PORTAGE_PYM_PATH, PROFILE_PATH, LOCALE_DATA_PATH, \
		EBUILD_SH_BINARY, SANDBOX_BINARY, BASH_BINARY, \
		MOVE_BINARY, PRELINK_BINARY, WORLD_FILE, MAKE_CONF_FILE, MAKE_DEFAULTS_FILE, \
		DEPRECATED_PROFILE_FILE, USER_VIRTUALS_FILE, EBUILD_SH_ENV_FILE, \
		INVALID_ENV_FILE, CUSTOM_MIRRORS_FILE, CONFIG_MEMORY_FILE,\
		INCREMENTALS, EAPI, MISC_SH_BINARY, REPO_NAME_LOC, REPO_NAME_FILE

except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the ebuild\n")
	sys.stderr.write("!!! repository under '/var/db/repos/gentoo/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise


# We use utf_8 encoding everywhere. Previously, we used
# sys.getfilesystemencoding() for the 'merge' encoding, but that had
# various problems:
#
#   1) If the locale is ever changed then it can cause orphan files due
#      to changed character set translation.
#
#   2) Ebuilds typically install files with utf_8 encoded file names,
#      and then portage would be forced to rename those files to match
#      sys.getfilesystemencoding(), possibly breaking things.
#
#   3) Automatic translation between encodings can lead to nonsensical
#      file names when the source encoding is unknown by portage.
#
#   4) It's inconvenient for ebuilds to convert the encodings of file
#      names to match the current locale, and upstreams typically encode
#      file names with utf_8 encoding.
#
# So, instead of relying on sys.getfilesystemencoding(), we avoid the above
# problems by using a constant utf_8 'merge' encoding for all locales, as
# discussed in bug #382199 and bug #381509.
_encodings = {
	'content'                : 'utf_8',
	'fs'                     : 'utf_8',
	'merge'                  : 'utf_8',
	'repo.content'           : 'utf_8',
	'stdio'                  : 'utf_8',
}


def _decode_argv(argv):
	# With Python 3, the surrogateescape encoding error handler makes it
	# possible to access the original argv bytes, which can be useful
	# if their actual encoding does no match the filesystem encoding.
	fs_encoding = sys.getfilesystemencoding()
	return [_unicode_decode(x.encode(fs_encoding, 'surrogateescape'))
		for x in argv]


def _unicode_encode(s, encoding=_encodings['content'], errors='backslashreplace'):
	if isinstance(s, str):
		s = s.encode(encoding, errors)
	return s


def _unicode_decode(s, encoding=_encodings['content'], errors='replace'):
	if isinstance(s, bytes):
		s = str(s, encoding=encoding, errors=errors)
	return s


_native_string = _unicode_decode


class _unicode_func_wrapper:
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

	def _process_args(self, args, kwargs):

		encoding = self._encoding
		wrapped_args = [_unicode_encode(x, encoding=encoding, errors='strict')
			for x in args]
		if kwargs:
			wrapped_kwargs = dict(
				(k, _unicode_encode(v, encoding=encoding, errors='strict'))
				for k, v in kwargs.items())
		else:
			wrapped_kwargs = {}

		return (wrapped_args, wrapped_kwargs)

	def __call__(self, *args, **kwargs):

		encoding = self._encoding
		wrapped_args, wrapped_kwargs = self._process_args(args, kwargs)

		rval = self._func(*wrapped_args, **wrapped_kwargs)

		# Don't use isinstance() since we don't want to convert subclasses
		# of tuple such as posix.stat_result in Python >=3.2.
		if rval.__class__ in (list, tuple):
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

class _unicode_module_wrapper:
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

class _eintr_func_wrapper:
	"""
	Wraps a function and handles EINTR by calling the function as
	many times as necessary (until it returns without raising EINTR).
	"""

	__slots__ = ('_func',)

	def __init__(self, func):
		self._func = func

	def __call__(self, *args, **kwargs):

		while True:
			try:
				rval = self._func(*args, **kwargs)
				break
			except EnvironmentError as e:
				if e.errno != errno.EINTR:
					raise

		return rval

import os as _os
_os_overrides = {
	id(_os.fdopen)        : _os.fdopen,
	id(_os.popen)         : _os.popen,
	id(_os.read)          : _os.read,
	id(_os.system)        : _os.system,
	id(_os.waitpid)       : _eintr_func_wrapper(_os.waitpid)
}


try:
	_os_overrides[id(_os.mkfifo)] = _os.mkfifo
except AttributeError:
	pass # Jython

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
	__import__('selinux')
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

_python_interpreter = (sys.executable if os.environ.get("VIRTUAL_ENV")
	else os.path.realpath(sys.executable))
_bin_path = PORTAGE_BIN_PATH
_pym_path = PORTAGE_PYM_PATH
_not_installed = os.path.isfile(os.path.join(PORTAGE_BASE_PATH, ".portage_not_installed"))

# Api consumers included in portage should set this to True.
_internal_caller = False

_sync_mode = False

class _ForkWatcher:
	@staticmethod
	def hook(_ForkWatcher):
		_ForkWatcher.current_pid = None
		# Force instantiation of a new event loop policy as a workaround
		# for https://bugs.python.org/issue22087.
		asyncio.set_event_loop_policy(None)

_ForkWatcher.hook(_ForkWatcher)

multiprocessing.util.register_after_fork(_ForkWatcher, _ForkWatcher.hook)

def getpid():
	"""
	Cached version of os.getpid(). ForkProcess updates the cache.
	"""
	if _ForkWatcher.current_pid is None:
		_ForkWatcher.current_pid = _os.getpid()
	return _ForkWatcher.current_pid

def _get_stdin():
	"""
	Buggy code in python's multiprocessing/process.py closes sys.stdin
	and reassigns it to open(os.devnull), but fails to update the
	corresponding __stdin__ reference. So, detect that case and handle
	it appropriately.
	"""
	if not sys.__stdin__.closed:
		return sys.__stdin__
	return sys.stdin

_shell_quote_re = re.compile(r"[\s><=*\\\"'$`;&|(){}\[\]#!~?]")

def _shell_quote(s):
	"""
	Quote a string in double-quotes and use backslashes to
	escape any backslashes, double-quotes, dollar signs, or
	backquotes in the string.
	"""
	if _shell_quote_re.search(s) is None:
		return s
	for letter in "\\\"$`":
		if letter in s:
			s = s.replace(letter, "\\" + letter)
	return "\"%s\"" % s

bsd_chflags = None

if platform.system() in ('FreeBSD',):
	# TODO: remove this class?
	class bsd_chflags:
		chflags = os.chflags
		lchflags = os.lchflags

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

def abssymlink(symlink, target=None):
	"""
	This reads symlinks, resolving the relative symlinks,
	and returning the absolute.
	@param symlink: path of symlink (must be absolute)
	@param target: the target of the symlink (as returned
		by readlink)
	@rtype: str
	@return: the absolute path of the symlink target
	"""
	if target is not None:
		mylink = target
	else:
		mylink = os.readlink(symlink)
	if mylink[0] != '/':
		mydir = os.path.dirname(symlink)
		mylink = mydir + "/" + mylink
	return os.path.normpath(mylink)

_doebuild_manifest_exempt_depend = 0

_testing_eapis = frozenset([
])
_deprecated_eapis = frozenset([
	"3_pre1",
	"3_pre2",
	"4_pre1",
	"4-python",
	"4-slot-abi",
	"5_pre1",
	"5_pre2",
	"5-progress",
	"6_pre1",
	"7_pre1",
])
_supported_eapis = frozenset([str(x) for x in range(portage.const.EAPI + 1)] + list(_testing_eapis) + list(_deprecated_eapis))

def _eapi_is_deprecated(eapi):
	return eapi in _deprecated_eapis

def eapi_is_supported(eapi):
	eapi = str(eapi).strip()

	return eapi in _supported_eapis

# This pattern is specified by PMS section 7.3.1.
_pms_eapi_re = re.compile(r"^[ \t]*EAPI=(['\"]?)([A-Za-z0-9+_.-]*)\1[ \t]*([ \t]#.*)?$")
_comment_or_blank_line = re.compile(r"^\s*(#.*)?$")

def _parse_eapi_ebuild_head(f):
	eapi = None
	eapi_lineno = None
	lineno = 0
	for line in f:
		lineno += 1
		m = _comment_or_blank_line.match(line)
		if m is None:
			eapi_lineno = lineno
			m = _pms_eapi_re.match(line)
			if m is not None:
				eapi = m.group(2)
			break

	return (eapi, eapi_lineno)

def _movefile(src, dest, **kwargs):
	"""Calls movefile and raises a PortageException if an error occurs."""
	if movefile(src, dest, **kwargs) is None:
		raise portage.exception.PortageException(
			"mv '%s' '%s'" % (src, dest))

auxdbkeys = (
  'DEPEND',    'RDEPEND',   'SLOT',      'SRC_URI',
	'RESTRICT',  'HOMEPAGE',  'LICENSE',   'DESCRIPTION',
	'KEYWORDS',  'INHERITED', 'IUSE', 'REQUIRED_USE',
	'PDEPEND',   'BDEPEND', 'EAPI',
	'PROPERTIES', 'DEFINED_PHASES', 'IDEPEND', 'UNUSED_04',
	'UNUSED_03', 'UNUSED_02', 'UNUSED_01',
)
auxdbkeylen = len(auxdbkeys)

def portageexit():
	pass

class _trees_dict(dict):
	__slots__ = ('_running_eroot', '_target_eroot',)
	def __init__(self, *pargs, **kargs):
		dict.__init__(self, *pargs, **kargs)
		self._running_eroot = None
		self._target_eroot = None

def create_trees(config_root=None, target_root=None, trees=None, env=None,
	sysroot=None, eprefix=None):

	if trees is None:
		trees = _trees_dict()
	elif not isinstance(trees, _trees_dict):
		# caller passed a normal dict or something,
		# but we need a _trees_dict instance
		trees = _trees_dict(trees)

	if env is None:
		env = os.environ

	settings = config(config_root=config_root, target_root=target_root,
		env=env, sysroot=sysroot, eprefix=eprefix)
	settings.lock()

	depcachedir = settings.get('PORTAGE_DEPCACHEDIR')
	trees._target_eroot = settings['EROOT']
	myroots = [(settings['EROOT'], settings)]
	if settings["ROOT"] == "/" and settings["EPREFIX"] == const.EPREFIX:
		trees._running_eroot = trees._target_eroot
	else:

		# When ROOT != "/" we only want overrides from the calling
		# environment to apply to the config that's associated
		# with ROOT != "/", so pass a nearly empty dict for the env parameter.
		clean_env = {}
		for k in ('PATH', 'PORTAGE_GRPNAME', 'PORTAGE_REPOSITORIES', 'PORTAGE_USERNAME',
			'PYTHONPATH', 'SSH_AGENT_PID', 'SSH_AUTH_SOCK', 'TERM',
			'ftp_proxy', 'http_proxy', 'https_proxy', 'no_proxy',
			'__PORTAGE_TEST_HARDLINK_LOCKS'):
			v = settings.get(k)
			if v is not None:
				clean_env[k] = v
		if depcachedir is not None:
			clean_env['PORTAGE_DEPCACHEDIR'] = depcachedir
		settings = config(config_root=None, target_root="/",
			env=clean_env, sysroot="/", eprefix=None)
		settings.lock()
		trees._running_eroot = settings['EROOT']
		myroots.append((settings['EROOT'], settings))

	for myroot, mysettings in myroots:
		trees[myroot] = portage.util.LazyItemsDict(trees.get(myroot, {}))
		trees[myroot].addLazySingleton("virtuals", mysettings.getvirtuals)
		trees[myroot].addLazySingleton(
			"vartree", vartree, categories=mysettings.categories,
				settings=mysettings)
		trees[myroot].addLazySingleton("porttree",
			portagetree, settings=mysettings)
		trees[myroot].addLazySingleton("bintree",
			binarytree, pkgdir=mysettings["PKGDIR"], settings=mysettings)
	return trees

if VERSION == 'HEAD':
	class _LazyVersion(proxy.objectproxy.ObjectProxy):
		def _get_target(self):
			global VERSION
			if VERSION is not self:
				return VERSION
			if os.path.isdir(os.path.join(PORTAGE_BASE_PATH, '.git')):
				encoding = _encodings['fs']
				cmd = [BASH_BINARY, "-c", ("cd %s ; git describe --match 'portage-*' || exit $? ; " + \
					"if [ -n \"`git diff-index --name-only --diff-filter=M HEAD`\" ] ; " + \
					"then echo modified ; git rev-list --format=%%ct -n 1 HEAD ; fi ; " + \
					"exit 0") % _shell_quote(PORTAGE_BASE_PATH)]
				cmd = [_unicode_encode(x, encoding=encoding, errors='strict')
					for x in cmd]
				proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT)
				output = _unicode_decode(proc.communicate()[0], encoding=encoding)
				status = proc.wait()
				if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
					output_lines = output.splitlines()
					if output_lines:
						version_split = output_lines[0].split('-')
						if len(version_split) > 1:
							VERSION = version_split[1]
							patchlevel = False
							if len(version_split) > 2:
								patchlevel = True
								VERSION = "%s_p%s" % (VERSION, version_split[2])
							if len(output_lines) > 1 and output_lines[1] == 'modified':
								head_timestamp = None
								if len(output_lines) > 3:
									try:
										head_timestamp = int(output_lines[3])
									except ValueError:
										pass
								timestamp = int(time.time())
								if head_timestamp is not None and timestamp > head_timestamp:
									timestamp = timestamp - head_timestamp
								if not patchlevel:
									VERSION = "%s_p0" % (VERSION,)
								VERSION = "%s_p%d" % (VERSION, timestamp)
							return VERSION
			VERSION = 'HEAD'
			return VERSION
	VERSION = _LazyVersion()

_legacy_global_var_names = ("archlist", "db", "features",
	"groups", "mtimedb", "mtimedbfile", "pkglines",
	"portdb", "profiledir", "root", "selinux_enabled",
	"settings", "thirdpartymirrors")

def _reset_legacy_globals():

	global _legacy_globals_constructed
	_legacy_globals_constructed = set()
	for k in _legacy_global_var_names:
		globals()[k] = _LegacyGlobalProxy(k)

class _LegacyGlobalProxy(proxy.objectproxy.ObjectProxy):

	__slots__ = ('_name',)

	def __init__(self, name):
		proxy.objectproxy.ObjectProxy.__init__(self)
		object.__setattr__(self, '_name', name)

	def _get_target(self):
		name = object.__getattribute__(self, '_name')
		from portage._legacy_globals import _get_legacy_global
		return _get_legacy_global(name)

_reset_legacy_globals()

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
