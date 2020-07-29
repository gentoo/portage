# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

__all__ = ['fetch']

import errno
import functools
import glob
import io
import itertools
import json
import logging
import random
import re
import stat
import sys
import tempfile
import time

from collections import OrderedDict
from urllib.parse import urlparse
from urllib.parse import quote as urlquote

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.config:check_config_instance,config',
	'portage.package.ebuild.doebuild:doebuild_environment,' + \
		'_doebuild_spawn',
	'portage.package.ebuild.prepare_build_dirs:prepare_build_dirs',
	'portage.util:atomic_ofstream',
	'portage.util.configparser:SafeConfigParser,read_configs,' +
		'ConfigParserError',
	'portage.util.install_mask:_raise_exc',
	'portage.util._urlopen:urlopen',
)

from portage import os, selinux, shutil, _encodings, \
	_movefile, _shell_quote, _unicode_encode
from portage.checksum import (get_valid_checksum_keys, perform_md5, verify_all,
	_filter_unaccelarated_hashes, _hash_filter, _apply_hash_filter,
	checksum_str)
from portage.const import BASH_BINARY, CUSTOM_MIRRORS_FILE, \
	GLOBAL_CONFIG_PATH
from portage.data import portage_gid, portage_uid, userpriv_groups
from portage.exception import FileNotFound, OperationNotPermitted, \
	PortageException, TryAgain
from portage.localization import _
from portage.locks import lockfile, unlockfile
from portage.output import colorize, EOutput
from portage.util import apply_recursive_permissions, \
	apply_secpass_permissions, ensure_dirs, grabdict, shlex_split, \
	varexpand, writemsg, writemsg_level, writemsg_stdout
from portage.process import spawn

_download_suffix = '.__download__'

_userpriv_spawn_kwargs = (
	("uid",    portage_uid),
	("gid",    portage_gid),
	("groups", userpriv_groups),
	("umask",  0o02),
)

def _hide_url_passwd(url):
	return re.sub(r'//([^:\s]+):[^@\s]+@', r'//\1:*password*@', url)


def _want_userfetch(settings):
	"""
	Check if it's desirable to drop privileges for userfetch.

	@param settings: portage config
	@type settings: portage.package.ebuild.config.config
	@return: True if desirable, False otherwise
	"""
	return ('userfetch' in settings.features and
		portage.data.secpass >= 2 and os.getuid() == 0)


def _drop_privs_userfetch(settings):
	"""
	Drop privileges for userfetch, and update portage.data.secpass
	to correspond to the new privilege level.
	"""
	spawn_kwargs = dict(_userpriv_spawn_kwargs)
	try:
		_ensure_distdir(settings, settings['DISTDIR'])
	except PortageException:
		if not os.path.isdir(settings['DISTDIR']):
			raise
	os.setgid(int(spawn_kwargs['gid']))
	os.setgroups(spawn_kwargs['groups'])
	os.setuid(int(spawn_kwargs['uid']))
	os.umask(spawn_kwargs['umask'])
	portage.data.secpass = 1


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
			0 : portage._get_stdin().fileno(),
			1 : sys.__stdout__.fileno(),
			2 : sys.__stdout__.fileno(),
		}

	logname = None
	if "userfetch" in settings.features and \
		os.getuid() == 0 and portage_gid and portage_uid and \
		hasattr(os, "setgroups"):
		kwargs.update(_userpriv_spawn_kwargs)
		logname = portage.data._portage_username

	spawn_func = spawn

	if settings.selinux_enabled():
		spawn_func = selinux.spawn_wrapper(spawn_func,
			settings["PORTAGE_FETCH_T"])

		# bash is an allowed entrypoint, while most binaries are not
		if args[0] != BASH_BINARY:
			args = [BASH_BINARY, "-c", "exec \"$@\"", args[0]] + args

	# Ensure that EBUILD_PHASE is set to fetch, so that config.environ()
	# does not filter the calling environment (which may contain needed
	# proxy variables, as in bug #315421).
	phase_backup = settings.get('EBUILD_PHASE')
	settings['EBUILD_PHASE'] = 'fetch'
	env = settings.environ()
	if logname is not None:
		env["LOGNAME"] = logname
	try:
		rval = spawn_func(args, env=env, **kwargs)
	finally:
		if phase_backup is None:
			settings.pop('EBUILD_PHASE', None)
		else:
			settings['EBUILD_PHASE'] = phase_backup

	return rval

_userpriv_test_write_file_cache = {}
_userpriv_test_write_cmd_script = ">> %(file_path)s 2>/dev/null ; rval=$? ; " + \
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


def _ensure_distdir(settings, distdir):
	"""
	Ensure that DISTDIR exists with appropriate permissions.

	@param settings: portage config
	@type settings: portage.package.ebuild.config.config
	@param distdir: DISTDIR path
	@type distdir: str
	@raise PortageException: portage.exception wrapper exception
	"""
	global _userpriv_test_write_file_cache
	dirmode  = 0o070
	filemode =   0o60
	modemask =    0o2
	dir_gid = portage_gid
	if "FAKED_MODE" in settings:
		# When inside fakeroot, directories with portage's gid appear
		# to have root's gid. Therefore, use root's gid instead of
		# portage's gid to avoid spurrious permissions adjustments
		# when inside fakeroot.
		dir_gid = 0

	userfetch = portage.data.secpass >= 2 and "userfetch" in settings.features
	userpriv = portage.data.secpass >= 2 and "userpriv" in settings.features
	write_test_file = os.path.join(distdir, ".__portage_test_write__")

	try:
		st = os.stat(distdir)
	except OSError:
		st = None

	if st is not None and stat.S_ISDIR(st.st_mode):
		if not (userfetch or userpriv):
			return
		if _userpriv_test_write_file(settings, write_test_file):
			return

	_userpriv_test_write_file_cache.pop(write_test_file, None)
	if ensure_dirs(distdir, gid=dir_gid, mode=dirmode, mask=modemask):
		if st is None:
			# The directory has just been created
			# and therefore it must be empty.
			return
		writemsg(_("Adjusting permissions recursively: '%s'\n") % distdir,
			noiselevel=-1)
		if not apply_recursive_permissions(distdir,
			gid=dir_gid, dirmode=dirmode, dirmask=modemask,
			filemode=filemode, filemask=modemask, onerror=_raise_exc):
			raise OperationNotPermitted(
				_("Failed to apply recursive permissions for the portage group."))


def _checksum_failure_temp_file(settings, distdir, basename):
	"""
	First try to find a duplicate temp file with the same checksum and return
	that filename if available. Otherwise, use mkstemp to create a new unique
	filename._checksum_failure_.$RANDOM, rename the given file, and return the
	new filename. In any case, filename will be renamed or removed before this
	function returns a temp filename.
	"""

	filename = os.path.join(distdir, basename)
	if basename.endswith(_download_suffix):
		normal_basename = basename[:-len(_download_suffix)]
	else:
		normal_basename = basename
	size = os.stat(filename).st_size
	checksum = None
	tempfile_re = re.compile(re.escape(normal_basename) + r'\._checksum_failure_\..*')
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
			temp_checksum = perform_md5(temp_filename)
		except FileNotFound:
			# Apparently the temp file disappeared. Let it go.
			continue
		if checksum is None:
			checksum = perform_md5(filename)
		if checksum == temp_checksum:
			os.unlink(filename)
			return temp_filename

	fd, temp_filename = \
		tempfile.mkstemp("", normal_basename + "._checksum_failure_.", distdir)
	os.close(fd)
	_movefile(filename, temp_filename, mysettings=settings)
	return temp_filename

def _check_digests(filename, digests, show_errors=1):
	"""
	Check digests and display a message if an error occurs.
	@return True if all digests match, False otherwise.
	"""
	verified_ok, reason = verify_all(filename, digests)
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

def _check_distfile(filename, digests, eout, show_errors=1, hash_filter=None):
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
		digests = _filter_unaccelarated_hashes(digests)
		if hash_filter is not None:
			digests = _apply_hash_filter(digests, hash_filter)
		if _check_digests(filename, digests, show_errors=show_errors):
			eout.ebegin("%s %s ;-)" % (os.path.basename(filename),
				" ".join(sorted(digests))))
			eout.eend(0)
		else:
			return (False, st)
	return (True, st)

_fetch_resume_size_re = re.compile(r'(^[\d]+)([KMGTPEZY]?$)')

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


class FlatLayout:
	def get_path(self, filename):
		return filename

	def get_filenames(self, distdir):
		for dirpath, dirnames, filenames in os.walk(distdir,
				onerror=_raise_exc):
			for filename in filenames:
				try:
					yield portage._unicode_decode(filename, errors='strict')
				except UnicodeDecodeError:
					# Ignore it. Distfiles names must have valid UTF8 encoding.
					pass
			return

	@staticmethod
	def verify_args(args):
		return len(args) == 1


class FilenameHashLayout:
	def __init__(self, algo, cutoffs):
		self.algo = algo
		self.cutoffs = [int(x) for x in cutoffs.split(':')]

	def get_path(self, filename):
		fnhash = checksum_str(filename.encode('utf8'), self.algo)
		ret = ''
		for c in self.cutoffs:
			assert c % 4 == 0
			c = c // 4
			ret += fnhash[:c] + '/'
			fnhash = fnhash[c:]
		return ret + filename

	def get_filenames(self, distdir):
		pattern = ''
		for c in self.cutoffs:
			assert c % 4 == 0
			c = c // 4
			pattern += c * '[0-9a-f]' + '/'
		pattern += '*'
		for x in glob.iglob(portage._unicode_encode(os.path.join(distdir, pattern), errors='strict')):
			try:
				yield portage._unicode_decode(x, errors='strict').rsplit('/', 1)[1]
			except UnicodeDecodeError:
				# Ignore it. Distfiles names must have valid UTF8 encoding.
				pass

	@staticmethod
	def verify_args(args):
		if len(args) != 3:
			return False
		if args[1] not in get_valid_checksum_keys():
			return False
		# argsidate cutoffs
		for c in args[2].split(':'):
			try:
				c = int(c)
			except ValueError:
				break
			else:
				if c % 4 != 0:
					break
		else:
			return True
		return False


class MirrorLayoutConfig:
	"""
	Class to read layout.conf from a mirror.
	"""

	def __init__(self):
		self.structure = ()

	def read_from_file(self, f):
		cp = SafeConfigParser()
		read_configs(cp, [f])
		vals = []
		for i in itertools.count():
			try:
				vals.append(tuple(cp.get('structure', '%d' % i).split()))
			except ConfigParserError:
				break
		self.structure = tuple(vals)

	def serialize(self):
		return self.structure

	def deserialize(self, data):
		self.structure = data

	@staticmethod
	def validate_structure(val):
		if val[0] == 'flat':
			return FlatLayout.verify_args(val)
		if val[0] == 'filename-hash':
			return FilenameHashLayout.verify_args(val)
		return False

	def get_best_supported_layout(self):
		for val in self.structure:
			if self.validate_structure(val):
				if val[0] == 'flat':
					return FlatLayout(*val[1:])
				if val[0] == 'filename-hash':
					return FilenameHashLayout(*val[1:])
		# fallback
		return FlatLayout()

	def get_all_layouts(self):
		ret = []
		for val in self.structure:
			if not self.validate_structure(val):
				raise ValueError("Unsupported structure: {}".format(val))
			if val[0] == 'flat':
				ret.append(FlatLayout(*val[1:]))
			elif val[0] == 'filename-hash':
				ret.append(FilenameHashLayout(*val[1:]))
		if not ret:
			ret.append(FlatLayout())
		return ret


def get_mirror_url(mirror_url, filename, mysettings, cache_path=None):
	"""
	Get correct fetch URL for a given file, accounting for mirror
	layout configuration.

	@param mirror_url: Base URL to the mirror (without '/distfiles')
	@param filename: Filename to fetch
	@param cache_path: Path for mirror metadata cache
	@return: Full URL to fetch
	"""

	mirror_conf = MirrorLayoutConfig()

	cache = {}
	if cache_path is not None:
		try:
			with open(cache_path, 'r') as f:
				cache = json.load(f)
		except (IOError, ValueError):
			pass

	ts, data = cache.get(mirror_url, (0, None))
	# refresh at least daily
	if ts >= time.time() - 86400:
		mirror_conf.deserialize(data)
	else:
		tmpfile = '.layout.conf.%s' % urlparse(mirror_url).hostname
		try:
			if fetch({tmpfile: (mirror_url + '/distfiles/layout.conf',)},
					mysettings, force=1, try_mirrors=0):
				tmpfile = os.path.join(mysettings['DISTDIR'], tmpfile)
				mirror_conf.read_from_file(tmpfile)
			else:
				raise IOError()
		except (ConfigParserError, IOError, UnicodeDecodeError):
			pass
		else:
			cache[mirror_url] = (time.time(), mirror_conf.serialize())
			if cache_path is not None:
				f = atomic_ofstream(cache_path, 'w')
				json.dump(cache, f)
				f.close()

	return (mirror_url + "/distfiles/" +
			urlquote(mirror_conf.get_best_supported_layout().get_path(filename)))


def fetch(myuris, mysettings, listonly=0, fetchonly=0,
	locks_in_subdir=".locks", use_locks=1, try_mirrors=1, digests=None,
	allow_missing_digests=True, force=False):
	"""
	Fetch files to DISTDIR and also verify digests if they are available.

	@param myuris: Maps each file name to a tuple of available fetch URIs.
	@type myuris: dict
	@param mysettings: Portage config instance.
	@type mysettings: portage.config
	@param listonly: Only print URIs and do not actually fetch them.
	@type listonly: bool
	@param fetchonly: Do not block for files that are locked by a
		concurrent fetcher process. This means that the function can
		return successfully *before* all files have been successfully
		fetched!
	@type fetchonly: bool
	@param use_locks: Enable locks. This parameter is ineffective if
		FEATURES=distlocks is disabled in the portage config!
	@type use_locks: bool
	@param digests: Maps each file name to a dict of digest types and values.
	@type digests: dict
	@param allow_missing_digests: Enable fetch even if there are no digests
		available for verification.
	@type allow_missing_digests: bool
	@param force: Force download, even when a file already exists in
		DISTDIR. This is most useful when there are no digests available,
		since otherwise download will be automatically forced if the
		existing file does not match the available digests. Also, this
		avoids the need to remove the existing file in advance, which
		makes it possible to atomically replace the file and avoid
		interference with concurrent processes.
	@type force: bool
	@rtype: int
	@return: 1 if successful, 0 otherwise.
	"""

	if force and digests:
		# Since the force parameter can trigger unnecessary fetch when the
		# digests match, do not allow force=True when digests are provided.
		raise PortageException(_('fetch: force=True is not allowed when digests are provided'))

	if not myuris:
		return 1

	features = mysettings.features
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()
	userfetch = portage.data.secpass >= 2 and "userfetch" in features

	# 'nomirror' is bad/negative logic. You Restrict mirroring, not no-mirroring.
	restrict_mirror = "mirror" in restrict or "nomirror" in restrict
	if restrict_mirror:
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

	distdir_writable = os.access(mysettings["DISTDIR"], os.W_OK)
	fetch_to_ro = 0
	if "skiprocheck" in features:
		fetch_to_ro = 1

	if not distdir_writable and fetch_to_ro:
		if use_locks:
			writemsg(colorize("BAD",
				_("!!! For fetching to a read-only filesystem, "
				"locking should be turned off.\n")), noiselevel=-1)
			writemsg(_("!!! This can be done by adding -distlocks to "
				"FEATURES in /etc/portage/make.conf\n"), noiselevel=-1)
#			use_locks = 0

	# local mirrors are always added
	if try_mirrors and "local" in custommirrors:
		mymirrors += custommirrors["local"]

	if restrict_mirror:
		# We don't add any mirrors.
		pass
	else:
		if try_mirrors:
			mymirrors += [x.rstrip("/") for x in mysettings["GENTOO_MIRRORS"].split() if x]

	hash_filter = _hash_filter(mysettings.get("PORTAGE_CHECKSUM_FILTER", ""))
	if hash_filter.transparent:
		hash_filter = None
	skip_manifest = mysettings.get("EBUILD_SKIP_MANIFEST") == "1"
	if skip_manifest:
		allow_missing_digests = True
	pkgdir = mysettings.get("O")
	if digests is None and not (pkgdir is None or skip_manifest):
		mydigests = mysettings.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(pkgdir))).load_manifest(
			pkgdir, mysettings["DISTDIR"]).getTypeDigests("DIST")
	elif digests is None or skip_manifest:
		# no digests because fetch was not called for a specific package
		mydigests = {}
	else:
		mydigests = digests

	ro_distdirs = [x for x in \
		shlex_split(mysettings.get("PORTAGE_RO_DISTDIRS", "")) \
		if os.path.isdir(x)]

	fsmirrors = []
	for x in range(len(mymirrors)-1,-1,-1):
		if mymirrors[x] and mymirrors[x][0]=='/':
			fsmirrors += [mymirrors[x]]
			del mymirrors[x]

	restrict_fetch = "fetch" in restrict
	force_mirror = "force-mirror" in features and not restrict_mirror
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
			if not uri_set:
				file_uri_tuples.append((myfile, None))
	else:
		for myuri in myuris:
			if urlparse(myuri).scheme:
				file_uri_tuples.append((os.path.basename(myuri), myuri))
			else:
				file_uri_tuples.append((os.path.basename(myuri), None))

	filedict = OrderedDict()
	primaryuri_dict = {}
	thirdpartymirror_uris = {}
	for myfile, myuri in file_uri_tuples:
		if myfile not in filedict:
			filedict[myfile]=[]
			if distdir_writable:
				mirror_cache = os.path.join(mysettings["DISTDIR"],
						".mirror-cache.json")
			else:
				mirror_cache = None
			for l in locations:
				filedict[myfile].append(functools.partial(
					get_mirror_url, l, myfile, mysettings, mirror_cache))
		if myuri is None:
			continue
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
					uris = [locmirr.rstrip("/") + "/" + path \
						for locmirr in thirdpartymirrors[mirrorname]]
					random.shuffle(uris)
					filedict[myfile].extend(uris)
					thirdpartymirror_uris.setdefault(myfile, []).extend(uris)

				if mirrorname not in custommirrors and \
					mirrorname not in thirdpartymirrors:
					writemsg(_("!!! No known mirror by the name: %s\n") % (mirrorname))
			else:
				writemsg(_("Invalid mirror definition in SRC_URI:\n"), noiselevel=-1)
				writemsg("  %s\n" % (myuri), noiselevel=-1)
		else:
			if restrict_fetch or force_mirror:
				# Only fetch from specific mirrors is allowed.
				continue
			primaryuris = primaryuri_dict.get(myfile)
			if primaryuris is None:
				primaryuris = []
				primaryuri_dict[myfile] = primaryuris
			primaryuris.append(myuri)

	# Order primaryuri_dict values to match that in SRC_URI.
	for uris in primaryuri_dict.values():
		uris.reverse()

	# Prefer thirdpartymirrors over normal mirrors in cases when
	# the file does not yet exist on the normal mirrors.
	for myfile, uris in thirdpartymirror_uris.items():
		primaryuri_dict.setdefault(myfile, []).extend(uris)

	# Now merge primaryuri values into filedict (includes mirrors
	# explicitly referenced in SRC_URI).
	if "primaryuri" in restrict:
		for myfile, uris in filedict.items():
			filedict[myfile] = primaryuri_dict.get(myfile, []) + uris
	else:
		for myfile in filedict:
			filedict[myfile] += primaryuri_dict.get(myfile, [])

	can_fetch=True

	if listonly:
		can_fetch = False

	if can_fetch and not fetch_to_ro:
		try:
			_ensure_distdir(mysettings, mysettings["DISTDIR"])
		except PortageException as e:
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

	distdir_writable = can_fetch and not fetch_to_ro
	failed_files = set()
	restrict_fetch_msg = False
	valid_hashes = set(get_valid_checksum_keys())
	valid_hashes.discard("size")

	for myfile in filedict:
		"""
		fetched  status
		0        nonexistent
		1        partially downloaded
		2        completely downloaded
		"""
		fetched = 0

		orig_digests = mydigests.get(myfile, {})

		if not (allow_missing_digests or listonly):
			verifiable_hash_types = set(orig_digests).intersection(valid_hashes)
			if not verifiable_hash_types:
				expected = " ".join(sorted(valid_hashes))
				got = set(orig_digests)
				got.discard("size")
				got = " ".join(sorted(got))
				reason = (_("Insufficient data for checksum verification"),
					got, expected)
				writemsg(_("!!! Fetched file: %s VERIFY FAILED!\n") % myfile,
					noiselevel=-1)
				writemsg(_("!!! Reason: %s\n") % reason[0],
					noiselevel=-1)
				writemsg(_("!!! Got:      %s\n!!! Expected: %s\n") % \
					(reason[1], reason[2]), noiselevel=-1)

				if fetchonly:
					failed_files.add(myfile)
					continue
				else:
					return 0

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
		download_path = myfile_path if fetch_to_ro else myfile_path + _download_suffix
		has_space = True
		has_space_superuser = True
		file_lock = None
		if listonly:
			writemsg_stdout("\n", noiselevel=-1)
		else:
			# check if there is enough space in DISTDIR to completely store myfile
			# overestimate the filesize so we aren't bitten by FS overhead
			vfs_stat = None
			if size is not None and hasattr(os, "statvfs"):
				try:
					vfs_stat = os.statvfs(mysettings["DISTDIR"])
				except OSError as e:
					writemsg_level("!!! statvfs('%s'): %s\n" %
						(mysettings["DISTDIR"], e),
						noiselevel=-1, level=logging.ERROR)
					del e

			if vfs_stat is not None:
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
					elif portage.data.secpass < 2:
						has_space = False
					elif userfetch:
						has_space = False

			if distdir_writable and use_locks:

				lock_kwargs = {}
				if fetchonly:
					lock_kwargs["flags"] = os.O_NONBLOCK

				try:
					file_lock = lockfile(myfile_path,
						wantnewlockfile=1, **lock_kwargs)
				except TryAgain:
					writemsg(_(">>> File '%s' is already locked by "
						"another fetcher. Continuing...\n") % myfile,
						noiselevel=-1)
					continue
		try:
			if not listonly:

				eout = EOutput()
				eout.quiet = mysettings.get("PORTAGE_QUIET") == "1"
				match, mystat = _check_distfile(
					myfile_path, pruned_digests, eout, hash_filter=hash_filter)
				if match and not force:
					# Skip permission adjustment for symlinks, since we don't
					# want to modify anything outside of the primary DISTDIR,
					# and symlinks typically point to PORTAGE_RO_DISTDIRS.
					if distdir_writable and not os.path.islink(myfile_path):
						try:
							apply_secpass_permissions(myfile_path,
								gid=portage_gid, mode=0o664, mask=0o2,
								stat_cached=mystat)
						except PortageException as e:
							if not os.access(myfile_path, os.R_OK):
								writemsg(_("!!! Failed to adjust permissions:"
									" %s\n") % str(e), noiselevel=-1)
							del e
					continue

				# Remove broken symlinks or symlinks to files which
				# _check_distfile did not match above.
				if distdir_writable and mystat is None or os.path.islink(myfile_path):
					try:
						os.unlink(myfile_path)
					except OSError as e:
						if e.errno not in (errno.ENOENT, errno.ESTALE):
							raise
					mystat = None

				if mystat is not None:
					if stat.S_ISDIR(mystat.st_mode):
						writemsg_level(
							_("!!! Unable to fetch file since "
							"a directory is in the way: \n"
							"!!!   %s\n") % myfile_path,
							level=logging.ERROR, noiselevel=-1)
						return 0

					if distdir_writable and not force:
						# Since _check_distfile did not match above, the file
						# is either corrupt or its identity has changed since
						# the last time it was fetched, so rename it.
						temp_filename = _checksum_failure_temp_file(
							mysettings, mysettings["DISTDIR"], myfile)
						writemsg_stdout(_("Refetching... "
							"File renamed to '%s'\n\n") % \
							temp_filename, noiselevel=-1)

				# Stat the temporary download file for comparison with
				# fetch_resume_size.
				try:
					mystat = os.stat(download_path)
				except OSError as e:
					if e.errno not in (errno.ENOENT, errno.ESTALE):
						raise
					mystat = None

				if mystat is not None:
					if mystat.st_size == 0:
						if distdir_writable:
							try:
								os.unlink(download_path)
							except OSError:
								pass
					elif distdir_writable and size is not None:
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
									mysettings, mysettings["DISTDIR"],
									os.path.basename(download_path))
							writemsg_stdout(_("Refetching... "
								"File renamed to '%s'\n\n") % \
								temp_filename, noiselevel=-1)
						elif mystat.st_size >= size:
							temp_filename = \
								_checksum_failure_temp_file(
									mysettings, mysettings["DISTDIR"],
									os.path.basename(download_path))
							writemsg_stdout(_("Refetching... "
								"File renamed to '%s'\n\n") % \
								temp_filename, noiselevel=-1)

				if distdir_writable and ro_distdirs:
					readonly_file = None
					for x in ro_distdirs:
						filename = os.path.join(x, myfile)
						match, mystat = _check_distfile(
							filename, pruned_digests, eout, hash_filter=hash_filter)
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

				# this message is shown only after we know that
				# the file is not already fetched
				if not has_space:
					writemsg(_("!!! Insufficient space to store %s in %s\n") % \
						(myfile, mysettings["DISTDIR"]), noiselevel=-1)

					if has_space_superuser:
						writemsg(_("!!! Insufficient privileges to use "
							"remaining space.\n"), noiselevel=-1)
						if userfetch:
							writemsg(_("!!! You may set FEATURES=\"-userfetch\""
								" in /etc/portage/make.conf in order to fetch with\n"
								"!!! superuser privileges.\n"), noiselevel=-1)

				if fsmirrors and not os.path.exists(myfile_path) and has_space:
					for mydir in fsmirrors:
						mirror_file = os.path.join(mydir, myfile)
						try:
							shutil.copyfile(mirror_file, download_path)
							writemsg(_("Local mirror has file: %s\n") % myfile)
							break
						except (IOError, OSError) as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e

				try:
					mystat = os.stat(download_path)
				except OSError as e:
					if e.errno not in (errno.ENOENT, errno.ESTALE):
						raise
					del e
				else:
					# Skip permission adjustment for symlinks, since we don't
					# want to modify anything outside of the primary DISTDIR,
					# and symlinks typically point to PORTAGE_RO_DISTDIRS.
					if not os.path.islink(download_path):
						try:
							apply_secpass_permissions(download_path,
								gid=portage_gid, mode=0o664, mask=0o2,
								stat_cached=mystat)
						except PortageException as e:
							if not os.access(download_path, os.R_OK):
								writemsg(_("!!! Failed to adjust permissions:"
									" %s\n") % (e,), noiselevel=-1)

					# If the file is empty then it's obviously invalid. Remove
					# the empty file and try to download if possible.
					if mystat.st_size == 0:
						if distdir_writable:
							try:
								os.unlink(download_path)
							except EnvironmentError:
								pass
					elif not orig_digests:
						# We don't have a digest, but the file exists.  We must
						# assume that it is fully downloaded.
						if not force:
							continue
					else:
						if (mydigests[myfile].get("size") is not None
								and mystat.st_size < mydigests[myfile]["size"]
								and not restrict_fetch):
							fetched = 1 # Try to resume this download.
						elif parallel_fetchonly and \
							mystat.st_size == mydigests[myfile]["size"]:
							eout = EOutput()
							eout.quiet = \
								mysettings.get("PORTAGE_QUIET") == "1"
							eout.ebegin(
								"%s size ;-)" % (myfile, ))
							eout.eend(0)
							continue
						else:
							digests = _filter_unaccelarated_hashes(mydigests[myfile])
							if hash_filter is not None:
								digests = _apply_hash_filter(digests, hash_filter)
							verified_ok, reason = verify_all(download_path, digests)
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
											mysettings, mysettings["DISTDIR"],
											os.path.basename(download_path))
									writemsg_stdout(_("Refetching... "
										"File renamed to '%s'\n\n") % \
										temp_filename, noiselevel=-1)
							else:
								if not fetch_to_ro:
									_movefile(download_path, myfile_path, mysettings=mysettings)
								eout = EOutput()
								eout.quiet = \
									mysettings.get("PORTAGE_QUIET", None) == "1"
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
				if isinstance(loc, functools.partial):
					loc = loc()
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

				global_config_path = GLOBAL_CONFIG_PATH
				if portage.const.EPREFIX:
					global_config_path = os.path.join(portage.const.EPREFIX,
							GLOBAL_CONFIG_PATH.lstrip(os.sep))

				missing_file_param = False
				fetchcommand_var = "FETCHCOMMAND_" + protocol.upper()
				fetchcommand = mysettings.get(fetchcommand_var)
				if fetchcommand is None:
					fetchcommand_var = "FETCHCOMMAND"
					fetchcommand = mysettings.get(fetchcommand_var)
					if fetchcommand is None:
						writemsg_level(
							_("!!! %s is unset. It should "
							"have been defined in\n!!! %s/make.globals.\n") \
							% (fetchcommand_var, global_config_path),
							level=logging.ERROR, noiselevel=-1)
						return 0
				if "${FILE}" not in fetchcommand:
					writemsg_level(
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
						writemsg_level(
							_("!!! %s is unset. It should "
							"have been defined in\n!!! %s/make.globals.\n") \
							% (resumecommand_var, global_config_path),
							level=logging.ERROR, noiselevel=-1)
						return 0
				if "${FILE}" not in resumecommand:
					writemsg_level(
						_("!!! %s does not contain the required ${FILE}"
						" parameter.\n") % resumecommand_var,
						level=logging.ERROR, noiselevel=-1)
					missing_file_param = True

				if missing_file_param:
					writemsg_level(
						_("!!! Refer to the make.conf(5) man page for "
						"information about how to\n!!! correctly specify "
						"FETCHCOMMAND and RESUMECOMMAND.\n"),
						level=logging.ERROR, noiselevel=-1)
					if myfile != os.path.basename(loc):
						return 0

				if not can_fetch:
					if fetched != 2:
						try:
							mysize = os.stat(download_path).st_size
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
					continue

				if fetched != 2 and has_space:
					#we either need to resume or start the download
					if fetched == 1:
						try:
							mystat = os.stat(download_path)
						except OSError as e:
							if e.errno not in (errno.ENOENT, errno.ESTALE):
								raise
							del e
							fetched = 0
						else:
							if distdir_writable and mystat.st_size < fetch_resume_size:
								writemsg(_(">>> Deleting distfile with size "
									"%d (smaller than " "PORTAGE_FETCH_RESU"
									"ME_MIN_SIZE)\n") % mystat.st_size)
								try:
									os.unlink(download_path)
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
						_hide_url_passwd(loc))
					variables = {
						"URI":     loc,
						"FILE":    os.path.basename(download_path)
					}

					for k in ("DISTDIR", "PORTAGE_SSH_OPTS"):
						v = mysettings.get(k)
						if v is not None:
							variables[k] = v

					myfetch = shlex_split(locfetch)
					myfetch = [varexpand(x, mydict=variables) for x in myfetch]
					myret = -1
					try:

						myret = _spawn_fetch(mysettings, myfetch)

					finally:
						try:
							apply_secpass_permissions(download_path,
								gid=portage_gid, mode=0o664, mask=0o2)
						except FileNotFound:
							pass
						except PortageException as e:
							if not os.access(download_path, os.R_OK):
								writemsg(_("!!! Failed to adjust permissions:"
									" %s\n") % str(e), noiselevel=-1)
							del e

					# If the file is empty then it's obviously invalid.  Don't
					# trust the return value from the fetcher.  Remove the
					# empty file and try to download again.
					try:
						mystat = os.lstat(download_path)
						if mystat.st_size == 0 or (stat.S_ISLNK(mystat.st_mode) and not os.path.exists(download_path)):
							os.unlink(download_path)
							fetched = 0
							continue
					except EnvironmentError:
						pass

					if mydigests is not None and myfile in mydigests:
						try:
							mystat = os.stat(download_path)
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
								writemsg_level(
									_("!!! The command specified in the "
									"%s variable appears to have\n!!! "
									"created a directory instead of a "
									"normal file.\n") % command_var,
									level=logging.ERROR, noiselevel=-1)
								writemsg_level(
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
									with io.open(
										_unicode_encode(download_path,
										encoding=_encodings['fs'], errors='strict'),
										mode='r', encoding=_encodings['content'], errors='replace'
										) as f:
										if html404.search(f.read()):
											try:
												os.unlink(download_path)
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
								digests = _filter_unaccelarated_hashes(mydigests[myfile])
								if hash_filter is not None:
									digests = _apply_hash_filter(digests, hash_filter)
								verified_ok, reason = verify_all(download_path, digests)
								if not verified_ok:
									writemsg(_("!!! Fetched file: %s VERIFY FAILED!\n") % myfile,
										noiselevel=-1)
									writemsg(_("!!! Reason: %s\n") % reason[0],
										noiselevel=-1)
									writemsg(_("!!! Got:      %s\n!!! Expected: %s\n") % \
										(reason[1], reason[2]), noiselevel=-1)
									if reason[0] == _("Insufficient data for checksum verification"):
										return 0
									if distdir_writable:
										temp_filename = \
											_checksum_failure_temp_file(
												mysettings, mysettings["DISTDIR"],
												os.path.basename(download_path))
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
									if not fetch_to_ro:
										_movefile(download_path, myfile_path, mysettings=mysettings)
									eout = EOutput()
									eout.quiet = mysettings.get("PORTAGE_QUIET", None) == "1"
									if digests:
										eout.ebegin("%s %s ;-)" % \
											(myfile, " ".join(sorted(digests))))
										eout.eend(0)
									fetched=2
									break
					else: # no digests available
						if not myret:
							if not fetch_to_ro:
								_movefile(download_path, myfile_path, mysettings=mysettings)
							fetched=2
							break
						elif mydigests!=None:
							writemsg(_("No digest file available and download failed.\n\n"),
								noiselevel=-1)
		finally:
			if use_locks and file_lock:
				unlockfile(file_lock)
				file_lock = None

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
				writemsg_level(msg,
					level=logging.ERROR, noiselevel=-1)
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
				failed_files.add(myfile)
				continue
			elif fetchonly:
				failed_files.add(myfile)
				continue
			return 0
	if failed_files:
		return 0
	return 1
