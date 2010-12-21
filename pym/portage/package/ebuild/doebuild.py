# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['doebuild', 'doebuild_environment', 'spawn', 'spawnebuild']

import codecs
import gzip
from itertools import chain
import logging
import os as _os
import re
import shutil
import signal
import stat
import sys
import tempfile
from textwrap import wrap
import time
import warnings
import zlib

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.config:check_config_instance',
	'portage.package.ebuild.digestcheck:digestcheck',
	'portage.package.ebuild.digestgen:digestgen',
	'portage.package.ebuild.fetch:fetch',
	'portage.package.ebuild._spawn_nofetch:spawn_nofetch',
	'portage.util.ExtractKernelVersion:ExtractKernelVersion'
)

from portage import auxdbkeys, bsd_chflags, dep_check, \
	eapi_is_supported, merge, os, selinux, \
	unmerge, _encodings, _parse_eapi_ebuild_head, _os_merge, \
	_shell_quote, _unicode_decode, _unicode_encode
from portage.const import EBUILD_SH_ENV_FILE, EBUILD_SH_ENV_DIR, \
	EBUILD_SH_BINARY, INVALID_ENV_FILE, MISC_SH_BINARY
from portage.data import portage_gid, portage_uid, secpass, \
	uid, userpriv_groups
from portage.dbapi.virtual import fakedbapi
from portage.dep import Atom, paren_enclose, use_reduce
from portage.eapi import eapi_exports_KV, eapi_exports_merge_type, \
	eapi_exports_replace_vars, \
	eapi_has_src_prepare_and_src_configure, eapi_has_pkg_pretend
from portage.elog import elog_process
from portage.elog.messages import eerror, eqawarn
from portage.exception import DigestException, FileNotFound, \
	IncorrectParameter, InvalidDependString, PermissionDenied, \
	UnsupportedAPIException
from portage.localization import _
from portage.manifest import Manifest
from portage.output import style_to_ansi_code
from portage.package.ebuild.prepare_build_dirs import prepare_build_dirs
from portage.util import apply_recursive_permissions, \
	apply_secpass_permissions, noiselimit, normalize_path, \
	writemsg, writemsg_stdout, write_atomic
from portage.util.lafilefixer import rewrite_lafile	
from portage.versions import _pkgsplit
from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildPhase import EbuildPhase
from _emerge.EbuildSpawnProcess import EbuildSpawnProcess
from _emerge.PollScheduler import PollScheduler

_unsandboxed_phases = frozenset([
	"clean", "cleanrm", "config",
	"help", "info", "postinst",
	"preinst", "pretend", "postrm",
	"prerm", "setup"
])

def _doebuild_spawn(phase, settings, actionmap=None, **kwargs):
	"""
	All proper ebuild phases which execute ebuild.sh are spawned
	via this function. No exceptions.
	"""

	if phase in _unsandboxed_phases:
		kwargs['free'] = True

	if phase == 'depend':
		kwargs['droppriv'] = 'userpriv' in settings.features

	if actionmap is not None and phase in actionmap:
		kwargs.update(actionmap[phase]["args"])
		cmd = actionmap[phase]["cmd"] % phase
	else:
		if phase == 'cleanrm':
			ebuild_sh_arg = 'clean'
		else:
			ebuild_sh_arg = phase

		cmd = "%s %s" % (_shell_quote(
			os.path.join(settings["PORTAGE_BIN_PATH"],
			os.path.basename(EBUILD_SH_BINARY))),
			ebuild_sh_arg)

	settings['EBUILD_PHASE'] = phase
	try:
		return spawn(cmd, settings, **kwargs)
	finally:
		settings.pop('EBUILD_PHASE', None)

def _spawn_phase(phase, settings, actionmap=None, **kwargs):
	if kwargs.get('returnpid'):
		return _doebuild_spawn(phase, settings, actionmap=actionmap, **kwargs)

	ebuild_phase = EbuildPhase(actionmap=actionmap, background=False,
		phase=phase, scheduler=PollScheduler().sched_iface,
		settings=settings)
	ebuild_phase.start()
	ebuild_phase.wait()
	return ebuild_phase.returncode

def doebuild_environment(myebuild, mydo, myroot=None, settings=None,
	debug=False, use_cache=None, db=None):
	"""
	The myroot and use_cache parameters are unused.
	"""
	myroot = None
	use_cache = None

	if settings is None:
		raise TypeError("settings argument is required")

	if db is None:
		raise TypeError("db argument is required")

	mysettings = settings
	mydbapi = db
	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)

	if "CATEGORY" in mysettings.configdict["pkg"]:
		cat = mysettings.configdict["pkg"]["CATEGORY"]
	else:
		cat = os.path.basename(normalize_path(os.path.join(pkg_dir, "..")))

	eapi = None
	mypv = os.path.basename(ebuild_path)[:-7]

	mycpv = cat+"/"+mypv
	mysplit = _pkgsplit(mypv)
	if mysplit is None:
		raise IncorrectParameter(
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
	# so restore it to its original value. Sandbox needs canonical
	# paths, so realpath it.
	mysettings["PORTAGE_TMPDIR"] = os.path.realpath(tmpdir)

	mysettings.pop("EBUILD_PHASE", None) # remove from backupenv
	mysettings["EBUILD_PHASE"] = mydo

	# Set requested Python interpreter for Portage helpers.
	mysettings['PORTAGE_PYTHON'] = portage._python_interpreter

	# This is used by assert_sigpipe_ok() that's used by the ebuild
	# unpack() helper. SIGPIPE is typically 13, but its better not
	# to assume that.
	mysettings['PORTAGE_SIGPIPE_STATUS'] = str(128 + signal.SIGPIPE)

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

	if noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mydo == 'depend' and 'EAPI' not in mysettings.configdict['pkg']:
		if eapi is None and 'parse-eapi-ebuild-head' in mysettings.features:
			eapi = _parse_eapi_ebuild_head(
				codecs.open(_unicode_encode(ebuild_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace'))

		if eapi is not None:
			if not eapi_is_supported(eapi):
				raise UnsupportedAPIException(mycpv, eapi)
			mysettings.configdict['pkg']['EAPI'] = eapi

	if mydo != "depend":
		# Metadata vars such as EAPI and RESTRICT are
		# set by the above config.setcpv() call.
		eapi = mysettings["EAPI"]
		if not eapi_is_supported(eapi):
			# can't do anything with this.
			raise UnsupportedAPIException(mycpv, eapi)

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
	mysettings["PM_EBUILD_HOOK_DIR"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_DIR)

	#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.
	if not eapi_exports_KV(eapi):
		# Discard KV for EAPIs that don't support it. Cache KV is restored
		# from the backupenv whenever config.reset() is called.
		mysettings.pop('KV', None)
	elif mydo != 'depend' and 'KV' not in mysettings and \
		mydo in ('compile', 'config', 'configure', 'info',
		'install', 'nofetch', 'postinst', 'postrm', 'preinst',
		'prepare', 'prerm', 'setup', 'test', 'unpack'):
		mykv, err1 = ExtractKernelVersion(
			os.path.join(mysettings['EROOT'], "usr/src/linux"))
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
			(c, style_to_ansi_code(c)))
	mysettings["PORTAGE_COLORMAP"] = "\n".join(mycolors)

_doebuild_manifest_cache = None
_doebuild_broken_ebuilds = set()
_doebuild_broken_manifests = set()
_doebuild_commands_without_builddir = (
	'clean', 'cleanrm', 'depend', 'digest',
	'fetch', 'fetchall', 'help', 'manifest'
)

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
	@param dbkey: A file path where metadata generated by the 'depend' phase
		will be written.
	@type dbkey: String
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
	
	# chunked out deps for each phase, so that ebuild binary can use it 
	# to collapse targets down.
	actionmap_deps={
	"pretend"  : [],
	"setup":  ["pretend"],
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
		mydbapi = portage.db[myroot][tree].dbapi

	if vartree is None and mydo in ("merge", "qmerge", "unmerge"):
		vartree = portage.db[myroot]["vartree"]

	features = mysettings.features

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

	if returnpid and mydo != 'depend':
		warnings.warn("portage.doebuild() called " + \
			"with returnpid parameter enabled. This usage will " + \
			"not be supported in the future.",
			DeprecationWarning, stacklevel=2)

	if mydo == "fetchall":
		fetchall = 1
		mydo = "fetch"

	parallel_fetchonly = mydo in ("fetch", "fetchall") and \
		"PORTAGE_PARALLEL_FETCHONLY" in mysettings

	if mydo not in clean_phases and not os.path.exists(myebuild):
		writemsg("!!! doebuild: %s not found for %s\n" % (myebuild, mydo),
			noiselevel=-1)
		return 1

	if "strict" in features and \
		"digest" not in features and \
		tree == "porttree" and \
		mydo not in ("digest", "manifest", "help") and \
		not portage._doebuild_manifest_exempt_depend:
		# Always verify the ebuild checksums before executing it.
		global _doebuild_manifest_cache, _doebuild_broken_ebuilds

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
		except FileNotFound:
			out = portage.output.EOutput()
			out.eerror(_("A file listed in the Manifest "
				"could not be found: '%s'") % (myebuild,))
			_doebuild_broken_ebuilds.add(myebuild)
			return 1
		except DigestException as e:
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
			for f in os.listdir(pkgdir):
				pf = None
				if f[-7:] == '.ebuild':
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

	logfile=None
	builddir_lock = None
	tmpdir = None
	tmpdir_orig = None

	try:
		if mydo in ("digest", "manifest", "help"):
			# Temporarily exempt the depend phase from manifest checks, in case
			# aux_get calls trigger cache generation.
			portage._doebuild_manifest_exempt_depend += 1

		# If we don't need much space and we don't need a constant location,
		# we can temporarily override PORTAGE_TMPDIR with a random temp dir
		# so that there's no need for locking and it can be used even if the
		# user isn't in the portage group.
		if mydo in ("info",):
			tmpdir = tempfile.mkdtemp()
			tmpdir_orig = mysettings["PORTAGE_TMPDIR"]
			mysettings["PORTAGE_TMPDIR"] = tmpdir

		doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
			use_cache, mydbapi)

		if mydo in clean_phases:
			return _spawn_phase(mydo, mysettings,
				fd_pipes=fd_pipes, returnpid=returnpid)

		restrict = set(mysettings.get('PORTAGE_RESTRICT', '').split())
		# get possible slot information from the deps file
		if mydo == "depend":
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
			if returnpid:
				return _spawn_phase(mydo, mysettings,
					fd_pipes=fd_pipes, returnpid=returnpid)
			elif isinstance(dbkey, dict):
				warnings.warn("portage.doebuild() called " + \
					"with dict dbkey argument. This usage will " + \
					"not be supported in the future.",
					DeprecationWarning, stacklevel=2)
				mysettings["dbkey"] = ""
				pr, pw = os.pipe()
				fd_pipes = {
					0:sys.stdin.fileno(),
					1:sys.stdout.fileno(),
					2:sys.stderr.fileno(),
					9:pw}
				mypids = _spawn_phase(mydo, mysettings, returnpid=True,
					fd_pipes=fd_pipes)
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

			return _spawn_phase(mydo, mysettings,
				fd_pipes=fd_pipes, returnpid=returnpid)

		# Validate dependency metadata here to ensure that ebuilds with invalid
		# data are never installed via the ebuild command. Don't bother when
		# returnpid == True since there's no need to do this every time emerge
		# executes a phase.
		if not returnpid:
			rval = _validate_deps(mysettings, myroot, mydo, mydbapi)
			if rval != os.EX_OK:
				return rval

		# The info phase is special because it uses mkdtemp so and
		# user (not necessarily in the portage group) can run it.
		if mydo not in ('info',) and \
			mydo not in _doebuild_commands_without_builddir:
			rval = _check_temp_dir(mysettings)
			if rval != os.EX_OK:
				return rval

		if mydo == "unmerge":
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		# Build directory creation isn't required for any of these.
		# In the fetch phase, the directory is needed only for RESTRICT=fetch
		# in order to satisfy the sane $PWD requirement (from bug #239560)
		# when pkg_nofetch is spawned.
		have_build_dirs = False
		if not parallel_fetchonly and \
			mydo not in ('digest', 'fetch', 'help', 'manifest'):
			if not returnpid and \
				'PORTAGE_BUILDIR_LOCKED' not in mysettings:
				builddir_lock = EbuildBuildDir(
					scheduler=PollScheduler().sched_iface,
					settings=mysettings)
				builddir_lock.lock()
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
			rval = _prepare_env_file(mysettings)
			if rval != os.EX_OK:
				return rval

		if eapi_exports_merge_type(mysettings["EAPI"]) and \
			"MERGE_TYPE" not in mysettings.configdict["pkg"]:
			if tree == "porttree":
				mysettings.configdict["pkg"]["EMERGE_FROM"] = "ebuild"
				mysettings.configdict["pkg"]["MERGE_TYPE"] = "source"
			elif tree == "bintree":
				mysettings.configdict["pkg"]["EMERGE_FROM"] = "binary"
				mysettings.configdict["pkg"]["MERGE_TYPE"] = "binary"

		if eapi_exports_replace_vars(mysettings["EAPI"]) and \
			(mydo in ("pretend", "setup") or \
			("noauto" not in features and not returnpid and \
			(mydo in actionmap_deps or mydo in ("merge", "package", "qmerge")))):
			if not vartree:
				writemsg("Warning: vartree not given to doebuild. " + \
					"Cannot set REPLACING_VERSIONS in pkg_{pretend,setup}\n")
			else:
				vardb = vartree.dbapi
				cpv = mysettings.mycpv
				cp = portage.versions.cpv_getkey(cpv)
				slot = mysettings["SLOT"]
				cpv_slot = cp + ":" + slot
				mysettings["REPLACING_VERSIONS"] = " ".join(
					set(portage.versions.cpv_getversion(match) \
						for match in vardb.match(cpv_slot) + \
						vardb.match('='+cpv)))
				mysettings.backup_changes("REPLACING_VERSIONS")

		# if any of these are being called, handle them -- running them out of
		# the sandbox -- and stop now.
		if mydo in ("config", "help", "info", "postinst",
			"preinst", "pretend", "postrm", "prerm"):
			return _spawn_phase(mydo, mysettings,
				fd_pipes=fd_pipes, logfile=logfile, returnpid=returnpid)

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
		if not hasattr(mydbapi, 'getFetchMap'):
			if alist is None:
				alist = ""
			if aalist is None:
				aalist = ""
			alist = set(alist.split())
			aalist = set(aalist.split())
		elif alist is None or aalist is None or \
			(not emerge_skip_distfiles and need_distfiles):
			# Make sure we get the correct tree in case there are overlays.
			mytree = os.path.realpath(
				os.path.dirname(os.path.dirname(mysettings["O"])))
			useflags = mysettings["PORTAGE_USE"].split()
			try:
				alist = mydbapi.getFetchMap(mycpv, useflags=useflags,
					mytree=mytree)
				aalist = mydbapi.getFetchMap(mycpv, mytree=mytree)
			except InvalidDependString as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Invalid SRC_URI for '%s'.\n") % mycpv,
					noiselevel=-1)
				del e
				return 1
			mysettings.configdict["pkg"]["A"] = " ".join(alist)
			mysettings.configdict["pkg"]["AA"] = " ".join(aalist)

			if not emerge_skip_distfiles and need_distfiles:
				if "mirror" in features or fetchall:
					fetchme = aalist
				else:
					fetchme = alist
				if not fetch(fetchme, mysettings, listonly=listonly,
					fetchonly=fetchonly):
					spawn_nofetch(mydbapi, myebuild, settings=mysettings)
					return 1

		else:
			alist = set(alist.split())
			aalist = set(aalist.split())

		if mydo == "fetch":
			# Files are already checked inside fetch(),
			# so do not check them again.
			checkme = []
		else:
			checkme = alist

		if mydo == "fetch" and listonly:
			return 0

		try:
			if mydo == "manifest":
				return not digestgen(mysettings=mysettings, myportdb=mydbapi)
			elif mydo == "digest":
				return not digestgen(mysettings=mysettings, myportdb=mydbapi)
			elif mydo != 'fetch' and not emerge_skip_digest and \
				"digest" in mysettings.features:
				# Don't do this when called by emerge or when called just
				# for fetch (especially parallel-fetch) since it's not needed
				# and it can interfere with parallel tasks.
				digestgen(mysettings=mysettings, myportdb=mydbapi)
		except PermissionDenied as e:
			writemsg(_("!!! Permission Denied: %s\n") % (e,), noiselevel=-1)
			if mydo in ("digest", "manifest"):
				return 1

		# See above comment about fetching only when needed
		if tree == 'porttree' and \
			not digestcheck(checkme, mysettings, "strict" in features):
			return 1

		if mydo == "fetch":
			return 0

		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		if tree == 'porttree' and \
			((mydo != "setup" and "noauto" not in features) \
			or mydo == "unpack"):
			_prepare_fake_distdir(mysettings, alist)

		#initial dep checks complete; time to process main commands
		actionmap = _spawn_actionmap(mysettings)

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
				if hasattr(portage, 'db'):
					bintree = portage.db[mysettings["ROOT"]]["bintree"]
					bintree._ensure_dir(os.path.join(
						bintree.pkgdir, mysettings["CATEGORY"]))
				else:
					parent_dir = os.path.join(mysettings["PKGDIR"],
						mysettings["CATEGORY"])
					portage.util.ensure_dirs(parent_dir)
					if not os.access(parent_dir, os.W_OK):
						raise PermissionDenied(
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
			if retval != os.EX_OK:
				# The merge phase handles this already.  Callers don't know how
				# far this function got, so we have to call elog_process() here
				# so that it's only called once.
				elog_process(mysettings.mycpv, mysettings)
			if retval == os.EX_OK:
				retval = merge(mysettings["CATEGORY"], mysettings["PF"],
					mysettings["D"], os.path.join(mysettings["PORTAGE_BUILDDIR"],
					"build-info"), myroot, mysettings,
					myebuild=mysettings["EBUILD"], mytree=tree, mydbapi=mydbapi,
					vartree=vartree, prev_mtimes=prev_mtimes)
		else:
			writemsg_stdout(_("!!! Unknown mydo: %s\n") % mydo, noiselevel=-1)
			return 1

		return retval

	finally:

		if builddir_lock is not None:
			builddir_lock.unlock()
		if tmpdir:
			mysettings["PORTAGE_TMPDIR"] = tmpdir_orig
			shutil.rmtree(tmpdir)

		mysettings.pop("REPLACING_VERSIONS", None)

		# Make sure that DISTDIR is restored to it's normal value before we return!
		if "PORTAGE_ACTUAL_DISTDIR" in mysettings:
			mysettings["DISTDIR"] = mysettings["PORTAGE_ACTUAL_DISTDIR"]
			del mysettings["PORTAGE_ACTUAL_DISTDIR"]

		if logfile and not returnpid:
			try:
				if os.stat(logfile).st_size == 0:
					os.unlink(logfile)
			except OSError:
				pass

		if mydo in ("digest", "manifest", "help"):
			# If necessary, depend phase has been triggered by aux_get calls
			# and the exemption is no longer needed.
			portage._doebuild_manifest_exempt_depend -= 1

def _check_temp_dir(settings):
	if "PORTAGE_TMPDIR" not in settings or \
		not os.path.isdir(settings["PORTAGE_TMPDIR"]):
		writemsg(_("The directory specified in your "
			"PORTAGE_TMPDIR variable, '%s',\n"
			"does not exist.  Please create this directory or "
			"correct your PORTAGE_TMPDIR setting.\n") % \
			settings.get("PORTAGE_TMPDIR", ""), noiselevel=-1)
		return 1

	# as some people use a separate PORTAGE_TMPDIR mount
	# we prefer that as the checks below would otherwise be pointless
	# for those people.
	if os.path.exists(os.path.join(settings["PORTAGE_TMPDIR"], "portage")):
		checkdir = os.path.join(settings["PORTAGE_TMPDIR"], "portage")
	else:
		checkdir = settings["PORTAGE_TMPDIR"]

	if not os.access(checkdir, os.W_OK):
		writemsg(_("%s is not writable.\n"
			"Likely cause is that you've mounted it as readonly.\n") % checkdir,
			noiselevel=-1)
		return 1

	else:
		fd = tempfile.NamedTemporaryFile(prefix="exectest-", dir=checkdir)
		os.chmod(fd.name, 0o755)
		if not os.access(fd.name, os.X_OK):
			writemsg(_("Can not execute files in %s\n"
				"Likely cause is that you've mounted it with one of the\n"
				"following mount options: 'noexec', 'user', 'users'\n\n"
				"Please make sure that portage can execute files in this directory.\n") % checkdir,
				noiselevel=-1)
			return 1

	return os.EX_OK

def _prepare_env_file(settings):
	"""
	Extract environment.bz2 if it exists, but only if the destination
	environment file doesn't already exist. There are lots of possible
	states when doebuild() calls this function, and we want to avoid
	clobbering an existing environment file.
	"""

	env_extractor = BinpkgEnvExtractor(background=False,
		scheduler=PollScheduler().sched_iface, settings=settings)

	if env_extractor.dest_env_exists():
		# There are lots of possible states when doebuild()
		# calls this function, and we want to avoid
		# clobbering an existing environment file.
		return os.EX_OK

	if not env_extractor.saved_env_exists():
		# If the environment.bz2 doesn't exist, then ebuild.sh will
		# source the ebuild as a fallback.
		return os.EX_OK

	env_extractor.start()
	env_extractor.wait()
	return env_extractor.returncode

def _prepare_fake_distdir(settings, alist):
	orig_distdir = settings["DISTDIR"]
	settings["PORTAGE_ACTUAL_DISTDIR"] = orig_distdir
	edpath = settings["DISTDIR"] = \
		os.path.join(settings["PORTAGE_BUILDDIR"], "distdir")
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

def _spawn_actionmap(settings):
	features = settings.features
	restrict = settings["PORTAGE_RESTRICT"].split()
	nosandbox = (("userpriv" in features) and \
		("usersandbox" not in features) and \
		"userpriv" not in restrict and \
		"nouserpriv" not in restrict)
	if nosandbox and ("userpriv" not in features or \
		"userpriv" in restrict or \
		"nouserpriv" in restrict):
		nosandbox = ("sandbox" not in features and \
			"usersandbox" not in features)

	if not portage.process.sandbox_capable:
		nosandbox = True

	sesandbox = settings.selinux_enabled() and \
		"sesandbox" in features

	droppriv = "userpriv" in features and \
		"userpriv" not in restrict and \
		secpass >= 2

	fakeroot = "fakeroot" in features

	portage_bin_path = settings["PORTAGE_BIN_PATH"]
	ebuild_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(EBUILD_SH_BINARY))
	misc_sh_binary = os.path.join(portage_bin_path,
		os.path.basename(MISC_SH_BINARY))
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

	return actionmap

def _validate_deps(mysettings, myroot, mydo, mydbapi):

	invalid_dep_exempt_phases = \
		set(["clean", "cleanrm", "help", "prerm", "postrm"])
	dep_keys = ["DEPEND", "RDEPEND", "PDEPEND"]
	misc_keys = ["LICENSE", "PROPERTIES", "PROVIDE", "RESTRICT", "SRC_URI"]
	other_keys = ["SLOT", "EAPI"]
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

	eapi = metadata["EAPI"]
	for k in misc_keys:
		try:
			use_reduce(metadata[k], is_src_uri=(k=="SRC_URI"), eapi=eapi)
		except InvalidDependString as e:
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

	check_config_instance(mysettings)

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

	if not free and not (fakeroot or portage.process.sandbox_capable):
		free = True

	if mysettings.mycpv is not None:
		keywords["opt_name"] = "[%s]" % mysettings.mycpv
	else:
		keywords["opt_name"] = "[%s/%s]" % \
			(mysettings.get("CATEGORY",""), mysettings.get("PF",""))

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

	if keywords.get("returnpid"):
		return spawn_func(mystring, env=mysettings.environ(), **keywords)

	proc = EbuildSpawnProcess(
		background=False, args=mystring,
		scheduler=PollScheduler().sched_iface, spawn_func=spawn_func,
		settings=mysettings, **keywords)

	proc.start()
	proc.wait()

	return proc.returncode

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo, actionmap, mysettings, debug, alwaysdep=0,
	logfile=None, fd_pipes=None, returnpid=False):

	if returnpid:
		warnings.warn("portage.spawnebuild() called " + \
			"with returnpid parameter enabled. This usage will " + \
			"not be supported in the future.",
			DeprecationWarning, stacklevel=2)

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

	if mydo in ("configure", "prepare") and not eapi_has_src_prepare_and_src_configure(eapi):
		return os.EX_OK

	if mydo == "pretend" and not eapi_has_pkg_pretend(eapi):
		return os.EX_OK

	return _spawn_phase(mydo, mysettings,
		actionmap=actionmap, logfile=logfile,
		fd_pipes=fd_pipes, returnpid=returnpid)

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
		f = open(_unicode_encode(logfile, encoding=_encodings['fs'],
			errors='strict'), mode='rb')
	except EnvironmentError:
		return

	if logfile.endswith('.gz'):
		f =  gzip.GzipFile(filename='', mode='rb', fileobj=f)

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
		re.compile(r'(/missing --run (autoheader|autotest|help2man|makeinfo)|^\s*Automake:\s)')

	make_jobserver_re = \
		re.compile(r'g?make\[\d+\]: warning: jobserver unavailable:')
	make_jobserver = []

	def _eerror(lines):
		for line in lines:
			eerror(line, phase="install", key=mysettings.mycpv, out=out)

	try:
		for line in f:
			line = _unicode_decode(line)
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

	except zlib.error as e:
		_eerror(["portage encountered a zlib error: '%s'" % (e,),
			"while reading the log file: '%s'" % logfile])
	finally:
		f.close()

	def _eqawarn(lines):
		for line in lines:
			eqawarn(line, phase="install", key=mysettings.mycpv, out=out)
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

def _post_src_install_uid_fix(mysettings, out):
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
		fixlafiles_announced = False
		fixlafiles = "fixlafiles" in mysettings.features

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

				if fixlafiles and \
					fname.endswith(".la") and os.path.isfile(fpath):
					f = open(_unicode_encode(fpath,
						encoding=_encodings['merge'], errors='strict'),
						mode='rb')
					has_lafile_header = b'.la - a libtool library file' \
						in f.readline()
					f.seek(0)
					contents = f.read()
					f.close()
					try:
						needs_update, new_contents = rewrite_lafile(contents)
					except portage.exception.InvalidData as e:
						needs_update = False
						if not fixlafiles_announced:
							fixlafiles_announced = True
							writemsg("Fixing .la files\n", fd=out)

						# Suppress warnings if the file does not have the
						# expected header (bug #340725). Even if the header is
						# missing, we still call rewrite_lafile() since some
						# valid libtool archives may not have the header.
						msg = "   %s is not a valid libtool archive, skipping\n" % fpath[len(destdir):]
						qa_msg = "QA Notice: invalid .la file found: %s, %s" % (fpath[len(destdir):], e)
						if has_lafile_header:
							writemsg(msg, fd=out)
							eqawarn(qa_msg, key=mysettings.mycpv, out=out)

					if needs_update:
						if not fixlafiles_announced:
							fixlafiles_announced = True
							writemsg("Fixing .la files\n", fd=out)
						writemsg("   %s\n" % fpath[len(destdir):], fd=out)
						# write_atomic succeeds even in some cases in which
						# a normal write might fail due to file permission
						# settings on some operating systems such as HP-UX
						write_atomic(_unicode_encode(fpath,
							encoding=_encodings['merge'], errors='strict'),
							new_contents, mode='wb')

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
		filename = os.path.join(build_info_dir, k)
		if v is None:
			try:
				os.unlink(filename)
			except OSError:
				pass
			continue

		if k.endswith('DEPEND'):
			token_class = Atom
		else:
			token_class = None

		v = use_reduce(v, uselist=use, token_class=token_class)
		v = paren_enclose(v)
		if not v:
			try:
				os.unlink(filename)
			except OSError:
				pass
			continue
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
