# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['doebuild', 'doebuild_environment', 'spawn', 'spawnebuild']

import grp
import gzip
import errno
import fnmatch
import io
from itertools import chain
import logging
import os as _os
import platform
import pwd
import re
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
	'portage.package.ebuild.fetch:_drop_privs_userfetch,_want_userfetch,fetch',
	'portage.package.ebuild.prepare_build_dirs:_prepare_fake_distdir',
	'portage.package.ebuild._ipc.QueryCommand:QueryCommand',
	'portage.dep._slot_operator:evaluate_slot_operator_equal_deps',
	'portage.package.ebuild._spawn_nofetch:spawn_nofetch',
	'portage.util.elf.header:ELFHeader',
	'portage.dep.soname.multilib_category:compute_multilib_category',
	'portage.util._desktop_entry:validate_desktop_entry',
	'portage.util._dyn_libs.NeededEntry:NeededEntry',
	'portage.util._dyn_libs.soname_deps:SonameDepsProcessor',
	'portage.util._async.SchedulerInterface:SchedulerInterface',
	'portage.util._eventloop.global_event_loop:global_event_loop',
	'portage.util.ExtractKernelVersion:ExtractKernelVersion'
)

from portage import bsd_chflags, \
	eapi_is_supported, merge, os, selinux, shutil, \
	unmerge, _encodings, _os_merge, \
	_shell_quote, _unicode_decode, _unicode_encode
from portage.const import EBUILD_SH_ENV_FILE, EBUILD_SH_ENV_DIR, \
	EBUILD_SH_BINARY, INVALID_ENV_FILE, MISC_SH_BINARY, PORTAGE_PYM_PACKAGES
from portage.data import portage_gid, portage_uid, secpass, \
	uid, userpriv_groups
from portage.dbapi.porttree import _parse_uri_map
from portage.dep import Atom, check_required_use, \
	human_readable_required_use, paren_enclose, use_reduce
from portage.eapi import (eapi_exports_KV, eapi_exports_merge_type,
	eapi_exports_replace_vars, eapi_exports_REPOSITORY,
	eapi_has_required_use, eapi_has_src_prepare_and_src_configure,
	eapi_has_pkg_pretend, _get_eapi_attrs)
from portage.elog import elog_process, _preload_elog_modules
from portage.elog.messages import eerror, eqawarn
from portage.exception import (DigestException, FileNotFound,
	IncorrectParameter, InvalidData, InvalidDependString,
	PermissionDenied, UnsupportedAPIException)
from portage.localization import _
from portage.output import colormap
from portage.package.ebuild.prepare_build_dirs import prepare_build_dirs
from portage.process import find_binary
from portage.util import ( apply_recursive_permissions,
	apply_secpass_permissions,
	noiselimit,
	shlex_split,
	varexpand,
	writemsg,
	writemsg_stdout,
	write_atomic
	)
from portage.util.cpuinfo import get_cpu_count
from portage.util.lafilefixer import rewrite_lafile
from portage.util.compression_probe import _compressors
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util.path import first_existing
from portage.util.socks5 import get_socks5_proxy
from portage.versions import _pkgsplit
from _emerge.BinpkgEnvExtractor import BinpkgEnvExtractor
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildPhase import EbuildPhase
from _emerge.EbuildSpawnProcess import EbuildSpawnProcess
from _emerge.Package import Package
from _emerge.RootConfig import RootConfig


_unsandboxed_phases = frozenset([
	"clean", "cleanrm", "config",
	"help", "info", "postinst",
	"preinst", "pretend", "postrm",
	"prerm", "setup"
])

# phases in which IPC with host is allowed
_ipc_phases = frozenset([
	"setup", "pretend", "config", "info",
	"preinst", "postinst", "prerm", "postrm",
])

# phases which execute in the global PID namespace
_global_pid_phases = frozenset([
	'config', 'depend', 'preinst', 'prerm', 'postinst', 'postrm'])

_phase_func_map = {
	"config": "pkg_config",
	"setup": "pkg_setup",
	"nofetch": "pkg_nofetch",
	"unpack": "src_unpack",
	"prepare": "src_prepare",
	"configure": "src_configure",
	"compile": "src_compile",
	"test": "src_test",
	"install": "src_install",
	"preinst": "pkg_preinst",
	"postinst": "pkg_postinst",
	"prerm": "pkg_prerm",
	"postrm": "pkg_postrm",
	"info": "pkg_info",
	"pretend": "pkg_pretend",
}

_vdb_use_conditional_keys = Package._dep_keys + \
	('LICENSE', 'PROPERTIES', 'RESTRICT',)

def _doebuild_spawn(phase, settings, actionmap=None, **kwargs):
	"""
	All proper ebuild phases which execute ebuild.sh are spawned
	via this function. No exceptions.
	"""

	if phase in _unsandboxed_phases:
		kwargs['free'] = True

	kwargs['ipc'] = 'ipc-sandbox' not in settings.features or \
		phase in _ipc_phases
	kwargs['mountns'] = 'mount-sandbox' in settings.features
	kwargs['networked'] = (
		'network-sandbox' not in settings.features or
		(phase == 'unpack' and
			'live' in settings['PORTAGE_PROPERTIES'].split()) or
		(phase == 'test' and
			'test_network' in settings['PORTAGE_PROPERTIES'].split()) or
		phase in _ipc_phases or
		'network-sandbox' in settings['PORTAGE_RESTRICT'].split())
	kwargs['pidns'] = ('pid-sandbox' in settings.features and
		phase not in _global_pid_phases)

	if phase == 'depend':
		kwargs['droppriv'] = 'userpriv' in settings.features
		# It's not necessary to close_fds for this phase, since
		# it should not spawn any daemons, and close_fds is
		# best avoided since it can interact badly with some
		# garbage collectors (see _setup_pipes docstring).
		kwargs['close_fds'] = False

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

def _spawn_phase(phase, settings, actionmap=None, returnpid=False,
		logfile=None, **kwargs):

	if returnpid:
		return _doebuild_spawn(phase, settings, actionmap=actionmap,
			returnpid=returnpid, logfile=logfile, **kwargs)

	# The logfile argument is unused here, since EbuildPhase uses
	# the PORTAGE_LOG_FILE variable if set.
	ebuild_phase = EbuildPhase(actionmap=actionmap, background=False,
		phase=phase, scheduler=SchedulerInterface(asyncio._safe_loop()),
		settings=settings, **kwargs)

	ebuild_phase.start()
	ebuild_phase.wait()
	return ebuild_phase.returncode

def _doebuild_path(settings, eapi=None):
	"""
	Generate the PATH variable.
	"""

	# Note: PORTAGE_BIN_PATH may differ from the global constant
	# when portage is reinstalling itself.
	portage_bin_path = [settings["PORTAGE_BIN_PATH"]]
	if portage_bin_path[0] != portage.const.PORTAGE_BIN_PATH:
		# Add a fallback path for restarting failed builds (bug 547086)
		portage_bin_path.append(portage.const.PORTAGE_BIN_PATH)
	prerootpath = [x for x in settings.get("PREROOTPATH", "").split(":") if x]
	rootpath = [x for x in settings.get("ROOTPATH", "").split(":") if x]
	rootpath_set = frozenset(rootpath)
	overrides = [x for x in settings.get(
		"__PORTAGE_TEST_PATH_OVERRIDE", "").split(":") if x]

	prefixes = []
	# settings["EPREFIX"] should take priority over portage.const.EPREFIX
	if portage.const.EPREFIX != settings["EPREFIX"] and settings["ROOT"] == os.sep:
		prefixes.append(settings["EPREFIX"])
	prefixes.append(portage.const.EPREFIX)

	path = overrides

	if "xattr" in settings.features:
		for x in portage_bin_path:
			path.append(os.path.join(x, "ebuild-helpers", "xattr"))

	if uid != 0 and \
		"unprivileged" in settings.features and \
		"fakeroot" not in settings.features:
		for x in portage_bin_path:
			path.append(os.path.join(x,
				"ebuild-helpers", "unprivileged"))

	if settings.get("USERLAND", "GNU") != "GNU":
		for x in portage_bin_path:
			path.append(os.path.join(x, "ebuild-helpers", "bsd"))

	for x in portage_bin_path:
		path.append(os.path.join(x, "ebuild-helpers"))
	path.extend(prerootpath)

	for prefix in prefixes:
		prefix = prefix if prefix else "/"
		for x in ("usr/local/sbin", "usr/local/bin", "usr/sbin", "usr/bin", "sbin", "bin"):
			# Respect order defined in ROOTPATH
			x_abs = os.path.join(prefix, x)
			if x_abs not in rootpath_set:
				path.append(x_abs)

	path.extend(rootpath)
	settings["PATH"] = ":".join(path)

def doebuild_environment(myebuild, mydo, myroot=None, settings=None,
	debug=False, use_cache=None, db=None):
	"""
	Create and store environment variable in the config instance
	that's passed in as the "settings" parameter. This will raise
	UnsupportedAPIException if the given ebuild has an unsupported
	EAPI. All EAPI dependent code comes last, so that essential
	variables like PORTAGE_BUILDDIR are still initialized even in
	cases when UnsupportedAPIException needs to be raised, which
	can be useful when uninstalling a package that has corrupt
	EAPI metadata.
	The myroot and use_cache parameters are unused.
	"""

	if settings is None:
		raise TypeError("settings argument is required")

	if db is None:
		raise TypeError("db argument is required")

	mysettings = settings
	mydbapi = db
	ebuild_path = os.path.abspath(myebuild)
	pkg_dir     = os.path.dirname(ebuild_path)
	mytree = os.path.dirname(os.path.dirname(pkg_dir))
	mypv = os.path.basename(ebuild_path)[:-7]
	mysplit = _pkgsplit(mypv, eapi=mysettings.configdict["pkg"].get("EAPI"))
	if mysplit is None:
		raise IncorrectParameter(
			_("Invalid ebuild path: '%s'") % myebuild)

	if mysettings.mycpv is not None and \
		mysettings.configdict["pkg"].get("PF") == mypv and \
		"CATEGORY" in mysettings.configdict["pkg"]:
		# Assume that PF is enough to assume that we've got
		# the correct CATEGORY, though this is not really
		# a solid assumption since it's possible (though
		# unlikely) that two packages in different
		# categories have the same PF. Callers should call
		# setcpv or create a clean clone of a locked config
		# instance in order to ensure that this assumption
		# does not fail like in bug #408817.
		cat = mysettings.configdict["pkg"]["CATEGORY"]
		mycpv = mysettings.mycpv
	elif os.path.basename(pkg_dir) in (mysplit[0], mypv):
		# portdbapi or vardbapi
		cat = os.path.basename(os.path.dirname(pkg_dir))
		mycpv = cat + "/" + mypv
	else:
		raise AssertionError("unable to determine CATEGORY")

	# Make a backup of PORTAGE_TMPDIR prior to calling config.reset()
	# so that the caller can override it.
	tmpdir = mysettings["PORTAGE_TMPDIR"]

	if mydo == 'depend':
		if mycpv != mysettings.mycpv:
			# Don't pass in mydbapi here since the resulting aux_get
			# call would lead to infinite 'depend' phase recursion.
			mysettings.setcpv(mycpv)
	else:
		# If EAPI isn't in configdict["pkg"], it means that setcpv()
		# hasn't been called with the mydb argument, so we have to
		# call it here (portage code always calls setcpv properly,
		# but api consumers might not).
		if mycpv != mysettings.mycpv or \
			"EAPI" not in mysettings.configdict["pkg"]:
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
	mysettings["PF"]       = mypv

	if hasattr(mydbapi, 'repositories'):
		repo = mydbapi.repositories.get_repo_for_location(mytree)
		mysettings['PORTDIR'] = repo.eclass_db.porttrees[0]
		mysettings['PORTAGE_ECLASS_LOCATIONS'] = repo.eclass_db.eclass_locations_string
		mysettings.configdict["pkg"]["PORTAGE_REPO_NAME"] = repo.name

	mysettings["PORTDIR"] = os.path.realpath(mysettings["PORTDIR"])
	mysettings.pop("PORTDIR_OVERLAY", None)
	mysettings["DISTDIR"] = os.path.realpath(mysettings["DISTDIR"])
	mysettings["RPMDIR"]  = os.path.realpath(mysettings["RPMDIR"])

	mysettings["ECLASSDIR"]   = mysettings["PORTDIR"]+"/eclass"

	mysettings["PORTAGE_BASHRC_FILES"] = "\n".join(mysettings._pbashrc)

	mysettings["P"]  = mysplit[0]+"-"+mysplit[1]
	mysettings["PN"] = mysplit[0]
	mysettings["PV"] = mysplit[1]
	mysettings["PR"] = mysplit[2]

	if noiselimit < 0:
		mysettings["PORTAGE_QUIET"] = "1"

	if mysplit[2] == "r0":
		mysettings["PVR"]=mysplit[1]
	else:
		mysettings["PVR"]=mysplit[1]+"-"+mysplit[2]

	# All temporary directories should be subdirectories of
	# $PORTAGE_TMPDIR/portage, since it's common for /tmp and /var/tmp
	# to be mounted with the "noexec" option (see bug #346899).
	mysettings["BUILD_PREFIX"] = mysettings["PORTAGE_TMPDIR"]+"/portage"
	mysettings["PKG_TMPDIR"]   = mysettings["BUILD_PREFIX"]+"/._unmerge_"

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
	mysettings["SANDBOX_LOG"] = os.path.join(mysettings["T"], "sandbox.log")
	mysettings["FILESDIR"] = os.path.join(settings["PORTAGE_BUILDDIR"], "files")

	# Prefix forward compatability
	eprefix_lstrip = mysettings["EPREFIX"].lstrip(os.sep)
	mysettings["ED"] = os.path.join(
		mysettings["D"], eprefix_lstrip).rstrip(os.sep) + os.sep

	mysettings["PORTAGE_BASHRC"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_FILE)
	mysettings["PM_EBUILD_HOOK_DIR"] = os.path.join(
		mysettings["PORTAGE_CONFIGROOT"], EBUILD_SH_ENV_DIR)

	# Allow color.map to control colors associated with einfo, ewarn, etc...
	mysettings["PORTAGE_COLORMAP"] = colormap()

	if "COLUMNS" not in mysettings:
		# Set COLUMNS, in order to prevent unnecessary stty calls
		# inside the set_colors function of isolated-functions.sh.
		# We cache the result in os.environ, in order to avoid
		# multiple stty calls in cases when get_term_size() falls
		# back to stty due to a missing or broken curses module.
		columns = os.environ.get("COLUMNS")
		if columns is None:
			rows, columns = portage.output.get_term_size()
			if columns < 1:
				# Force a sane value for COLUMNS, so that tools
				# like ls don't complain (see bug #394091).
				columns = 80
			columns = str(columns)
			os.environ["COLUMNS"] = columns
		mysettings["COLUMNS"] = columns

	# EAPI is always known here, even for the "depend" phase, because
	# EbuildMetadataPhase gets it from _parse_eapi_ebuild_head().
	eapi = mysettings.configdict['pkg']['EAPI']
	_doebuild_path(mysettings, eapi=eapi)

	# All EAPI dependent code comes last, so that essential variables like
	# PATH and PORTAGE_BUILDDIR are still initialized even in cases when
	# UnsupportedAPIException needs to be raised, which can be useful
	# when uninstalling a package that has corrupt EAPI metadata.
	if not eapi_is_supported(eapi):
		raise UnsupportedAPIException(mycpv, eapi)

	if eapi_exports_REPOSITORY(eapi) and "PORTAGE_REPO_NAME" in mysettings.configdict["pkg"]:
		mysettings.configdict["pkg"]["REPOSITORY"] = mysettings.configdict["pkg"]["PORTAGE_REPO_NAME"]

	if mydo != "depend":
		if hasattr(mydbapi, "getFetchMap") and \
			("A" not in mysettings.configdict["pkg"] or \
			"AA" not in mysettings.configdict["pkg"]):
			src_uri = mysettings.configdict["pkg"].get("SRC_URI")
			if src_uri is None:
				src_uri, = mydbapi.aux_get(mysettings.mycpv,
					["SRC_URI"], mytree=mytree)
			metadata = {
				"EAPI"    : eapi,
				"SRC_URI" : src_uri,
			}
			use = frozenset(mysettings["PORTAGE_USE"].split())
			try:
				uri_map = _parse_uri_map(mysettings.mycpv, metadata, use=use)
			except InvalidDependString:
				mysettings.configdict["pkg"]["A"] = ""
			else:
				mysettings.configdict["pkg"]["A"] = " ".join(uri_map)

			try:
				uri_map = _parse_uri_map(mysettings.mycpv, metadata)
			except InvalidDependString:
				mysettings.configdict["pkg"]["AA"] = ""
			else:
				mysettings.configdict["pkg"]["AA"] = " ".join(uri_map)

		ccache = "ccache" in mysettings.features
		distcc = "distcc" in mysettings.features
		icecream = "icecream" in mysettings.features

		if ccache or distcc or icecream:
			libdir = None
			default_abi = mysettings.get("DEFAULT_ABI")
			if default_abi:
				libdir = mysettings.get("LIBDIR_" + default_abi)
			if not libdir:
				libdir = "lib"

			# The installation locations use to vary between versions...
			# Safer to look them up rather than assuming
			possible_libexecdirs = (libdir, "lib", "libexec")
			masquerades = []
			if distcc:
				masquerades.append(("distcc", "distcc"))
			if icecream:
				masquerades.append(("icecream", "icecc"))
			if ccache:
				masquerades.append(("ccache", "ccache"))

			for feature, m in masquerades:
				for l in possible_libexecdirs:
					p = os.path.join(os.sep, eprefix_lstrip,
							"usr", l, m, "bin")
					if os.path.isdir(p):
						mysettings["PATH"] = p + ":" + mysettings["PATH"]
						break
				else:
					writemsg(("Warning: %s requested but no masquerade dir "
						"can be found in /usr/lib*/%s/bin\n") % (m, m))
					mysettings.features.remove(feature)

		if 'MAKEOPTS' not in mysettings:
			nproc = get_cpu_count()
			if nproc:
				mysettings['MAKEOPTS'] = '-j%d' % (nproc)

		if not eapi_exports_KV(eapi):
			# Discard KV for EAPIs that don't support it. Cached KV is restored
			# from the backupenv whenever config.reset() is called.
			mysettings.pop('KV', None)
		elif 'KV' not in mysettings and \
			mydo in ('compile', 'config', 'configure', 'info',
			'install', 'nofetch', 'postinst', 'postrm', 'preinst',
			'prepare', 'prerm', 'setup', 'test', 'unpack'):
			mykv, err1 = ExtractKernelVersion(
				os.path.join(mysettings['EROOT'], "usr/src/linux"))
			if mykv:
				# Regular source tree
				mysettings["KV"] = mykv
			else:
				mysettings["KV"] = ""
			mysettings.backup_changes("KV")

		binpkg_compression = mysettings.get("BINPKG_COMPRESS", "bzip2")
		try:
			compression = _compressors[binpkg_compression]
		except KeyError as e:
			if binpkg_compression:
				writemsg("Warning: Invalid or unsupported compression method: %s\n" % e.args[0])
			else:
				# Empty BINPKG_COMPRESS disables compression.
				mysettings['PORTAGE_COMPRESSION_COMMAND'] = 'cat'
		else:
			try:
				compression_binary = shlex_split(varexpand(compression["compress"], mydict=settings))[0]
			except IndexError as e:
				writemsg("Warning: Invalid or unsupported compression method: %s\n" % e.args[0])
			else:
				if find_binary(compression_binary) is None:
					missing_package = compression["package"]
					writemsg("Warning: File compression unsupported %s. Missing package: %s\n" % (binpkg_compression, missing_package))
				else:
					cmd = [varexpand(x, mydict=settings) for x in shlex_split(compression["compress"])]
					# Filter empty elements
					cmd = [x for x in cmd if x != ""]
					mysettings['PORTAGE_COMPRESSION_COMMAND'] = ' '.join(cmd)

_doebuild_manifest_cache = None
_doebuild_broken_ebuilds = set()
_doebuild_broken_manifests = set()
_doebuild_commands_without_builddir = (
	'clean', 'cleanrm', 'depend', 'digest',
	'fetch', 'fetchall', 'help', 'manifest'
)

def doebuild(myebuild, mydo, _unused=DeprecationWarning, settings=None, debug=0, listonly=0,
	fetchonly=0, cleanup=0, dbkey=DeprecationWarning, use_cache=1, fetchall=0, tree=None,
	mydbapi=None, vartree=None, prev_mtimes=None,
	fd_pipes=None, returnpid=False):
	"""
	Wrapper function that invokes specific ebuild phases through the spawning
	of ebuild.sh

	@param myebuild: name of the ebuild to invoke the phase on (CPV)
	@type myebuild: String
	@param mydo: Phase to run
	@type mydo: String
	@param _unused: Deprecated (use settings["ROOT"] instead)
	@type _unused: String
	@param settings: Portage Configuration
	@type settings: instance of portage.config
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
	@return:
	1. 0 for success
	2. 1 for error

	Most errors have an accompanying error message.

	listonly and fetchonly are only really necessary for operations involving 'fetch'
	prev_mtimes are only necessary for merge operations.
	Other variables may not be strictly required, many have defaults that are set inside of doebuild.

	"""

	if settings is None:
		raise TypeError("settings parameter is required")
	mysettings = settings
	myroot = settings['EROOT']

	if _unused is not DeprecationWarning:
		warnings.warn("The third parameter of the "
			"portage.doebuild() is deprecated. Instead "
			"settings['EROOT'] is used.",
			DeprecationWarning, stacklevel=2)

	if dbkey is not DeprecationWarning:
		warnings.warn("portage.doebuild() called "
			"with deprecated dbkey argument.",
			DeprecationWarning, stacklevel=2)

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
	"instprep":["install"],
	"rpm":    ["install"],
	"package":["install"],
	"merge"  :["install"],
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
	                "install", "instprep", "rpm", "qmerge", "merge",
	                "package", "unmerge", "manifest", "nofetch"]

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
		# This case is not supported, since it bypasses the EbuildPhase class
		# which implements important functionality (including post phase hooks
		# and IPC for things like best/has_version and die).
		warnings.warn("portage.doebuild() called "
			"with returnpid parameter enabled. This usage will "
			"not be supported in the future.",
			DeprecationWarning, stacklevel=2)

	if mydo == "fetchall":
		fetchall = 1
		mydo = "fetch"

	if mydo not in clean_phases and not os.path.exists(myebuild):
		writemsg("!!! doebuild: %s not found for %s\n" % (myebuild, mydo),
			noiselevel=-1)
		return 1

	global _doebuild_manifest_cache
	pkgdir = os.path.dirname(myebuild)
	manifest_path = os.path.join(pkgdir, "Manifest")
	if tree == "porttree":
		repo_config = mysettings.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(pkgdir)))
	else:
		repo_config = None

	mf = None
	if "strict" in features and \
		"digest" not in features and \
		tree == "porttree" and \
		not repo_config.thin_manifest and \
		mydo not in ("digest", "manifest", "help") and \
		not portage._doebuild_manifest_exempt_depend and \
		not (repo_config.allow_missing_manifest and not os.path.exists(manifest_path)):
		# Always verify the ebuild checksums before executing it.
		global _doebuild_broken_ebuilds

		if myebuild in _doebuild_broken_ebuilds:
			return 1

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
			mf = repo_config.load_manifest(pkgdir, mysettings["DISTDIR"])

		else:
			mf = _doebuild_manifest_cache

		try:
			mf.checkFileHashes("EBUILD", os.path.basename(myebuild))
		except KeyError:
			if not (mf.allow_missing and
				os.path.basename(myebuild) not in mf.fhashdict["EBUILD"]):
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

		if mf is not _doebuild_manifest_cache and not mf.allow_missing:

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

		# We cache it only after all above checks succeed.
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
		if not returnpid and mydo in ("info",):
			tmpdir = tempfile.mkdtemp()
			tmpdir_orig = mysettings["PORTAGE_TMPDIR"]
			mysettings["PORTAGE_TMPDIR"] = tmpdir

		doebuild_environment(myebuild, mydo, myroot, mysettings, debug,
			use_cache, mydbapi)

		if mydo in clean_phases:
			builddir_lock = None
			if not returnpid and \
				'PORTAGE_BUILDDIR_LOCKED' not in mysettings:
				builddir_lock = EbuildBuildDir(
					scheduler=asyncio._safe_loop(),
					settings=mysettings)
				builddir_lock.scheduler.run_until_complete(
					builddir_lock.async_lock())
			try:
				return _spawn_phase(mydo, mysettings,
					fd_pipes=fd_pipes, returnpid=returnpid)
			finally:
				if builddir_lock is not None:
					builddir_lock.scheduler.run_until_complete(
						builddir_lock.async_unlock())

		# get possible slot information from the deps file
		if mydo == "depend":
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey), 2)
			if returnpid:
				return _spawn_phase(mydo, mysettings,
					fd_pipes=fd_pipes, returnpid=returnpid)
			if dbkey and dbkey is not DeprecationWarning:
				mysettings["dbkey"] = dbkey
			else:
				mysettings["dbkey"] = \
					os.path.join(mysettings.depcachedir, "aux_db_key_temp")

			return _spawn_phase(mydo, mysettings,
				fd_pipes=fd_pipes, returnpid=returnpid)

		if mydo == "nofetch":

			if returnpid:
				writemsg("!!! doebuild: %s\n" %
					_("returnpid is not supported for phase '%s'\n" % mydo),
					noiselevel=-1)

			return spawn_nofetch(mydbapi, myebuild, settings=mysettings,
				fd_pipes=fd_pipes)

		if tree == "porttree":

			if not returnpid:
				# Validate dependency metadata here to ensure that ebuilds with
				# invalid data are never installed via the ebuild command. Skip
				# this when returnpid is True (assume the caller handled it).
				rval = _validate_deps(mysettings, myroot, mydo, mydbapi)
				if rval != os.EX_OK:
					return rval

		else:
			# FEATURES=noauto only makes sense for porttree, and we don't want
			# it to trigger redundant sourcing of the ebuild for API consumers
			# that are using binary packages
			if "noauto" in mysettings.features:
				mysettings.features.discard("noauto")

		# If we are not using a private temp dir, then check access
		# to the global temp dir.
		if tmpdir is None and \
			mydo not in _doebuild_commands_without_builddir:
			rval = _check_temp_dir(mysettings)
			if rval != os.EX_OK:
				return rval

		if mydo == "unmerge":
			if returnpid:
				writemsg("!!! doebuild: %s\n" %
					_("returnpid is not supported for phase '%s'\n" % mydo),
					noiselevel=-1)
			return unmerge(mysettings["CATEGORY"],
				mysettings["PF"], myroot, mysettings, vartree=vartree)

		phases_to_run = set()
		if returnpid or \
			"noauto" in mysettings.features or \
			mydo not in actionmap_deps:
			phases_to_run.add(mydo)
		else:
			phase_stack = [mydo]
			while phase_stack:
				x = phase_stack.pop()
				if x in phases_to_run:
					continue
				phases_to_run.add(x)
				phase_stack.extend(actionmap_deps.get(x, []))
			del phase_stack

		alist = set(mysettings.configdict["pkg"].get("A", "").split())

		unpacked = False
		if tree != "porttree" or \
			mydo in _doebuild_commands_without_builddir:
			pass
		elif "unpack" not in phases_to_run:
			unpacked = os.path.exists(os.path.join(
				mysettings["PORTAGE_BUILDDIR"], ".unpacked"))
		else:
			try:
				workdir_st = os.stat(mysettings["WORKDIR"])
			except OSError:
				pass
			else:
				newstuff = False
				if not os.path.exists(os.path.join(
					mysettings["PORTAGE_BUILDDIR"], ".unpacked")):
					writemsg_stdout(_(
						">>> Not marked as unpacked; recreating WORKDIR...\n"))
					newstuff = True
				else:
					for x in alist:
						writemsg_stdout(">>> Checking %s's mtime...\n" % x)
						try:
							x_st = os.stat(os.path.join(
								mysettings["DISTDIR"], x))
						except OSError:
							# file deleted
							x_st = None

						if x_st is not None and x_st.st_mtime > workdir_st.st_mtime:
							writemsg_stdout(_(">>> Timestamp of "
								"%s has changed; recreating WORKDIR...\n") % x)
							newstuff = True
							break

				if newstuff:
					if builddir_lock is None and \
						'PORTAGE_BUILDDIR_LOCKED' not in mysettings:
						builddir_lock = EbuildBuildDir(
							scheduler=asyncio._safe_loop(),
							settings=mysettings)
						builddir_lock.scheduler.run_until_complete(
							builddir_lock.async_lock())
					try:
						_spawn_phase("clean", mysettings)
					finally:
						if builddir_lock is not None:
							builddir_lock.scheduler.run_until_complete(
								builddir_lock.async_unlock())
							builddir_lock = None
				else:
					writemsg_stdout(_(">>> WORKDIR is up-to-date, keeping...\n"))
					unpacked = True

		# Build directory creation isn't required for any of these.
		# In the fetch phase, the directory is needed only for RESTRICT=fetch
		# in order to satisfy the sane $PWD requirement (from bug #239560)
		# when pkg_nofetch is spawned.
		have_build_dirs = False
		if mydo not in ('digest', 'fetch', 'help', 'manifest'):
			if not returnpid and \
				'PORTAGE_BUILDDIR_LOCKED' not in mysettings:
				builddir_lock = EbuildBuildDir(
					scheduler=asyncio._safe_loop(),
					settings=mysettings)
				builddir_lock.scheduler.run_until_complete(
					builddir_lock.async_lock())
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
				mysettings.configdict["pkg"]["MERGE_TYPE"] = "source"
			elif tree == "bintree":
				mysettings.configdict["pkg"]["MERGE_TYPE"] = "binary"

		if tree == "porttree":
			mysettings.configdict["pkg"]["EMERGE_FROM"] = "ebuild"
		elif tree == "bintree":
			mysettings.configdict["pkg"]["EMERGE_FROM"] = "binary"

		# NOTE: It's not possible to set REPLACED_BY_VERSION for prerm
		#       and postrm here, since we don't necessarily know what
		#       versions are being installed. This could be a problem
		#       for API consumers if they don't use dblink.treewalk()
		#       to execute prerm and postrm.
		if eapi_exports_replace_vars(mysettings["EAPI"]) and \
			(mydo in ("postinst", "preinst", "pretend", "setup") or \
			("noauto" not in features and not returnpid and \
			(mydo in actionmap_deps or mydo in ("merge", "package", "qmerge")))):
			if not vartree:
				writemsg("Warning: vartree not given to doebuild. " + \
					"Cannot set REPLACING_VERSIONS in pkg_{pretend,setup}\n")
			else:
				vardb = vartree.dbapi
				cpv = mysettings.mycpv
				cpv_slot = "%s%s%s" % \
					(cpv.cp, portage.dep._slot_separator, cpv.slot)
				mysettings["REPLACING_VERSIONS"] = " ".join(
					set(portage.versions.cpv_getversion(match) \
						for match in vardb.match(cpv_slot) + \
						vardb.match('='+cpv)))

		# if any of these are being called, handle them -- running them out of
		# the sandbox -- and stop now.
		if mydo in ("config", "help", "info", "postinst",
			"preinst", "pretend", "postrm", "prerm"):
			if mydo in ("preinst", "postinst"):
				env_file = os.path.join(os.path.dirname(mysettings["EBUILD"]),
					"environment.bz2")
				if os.path.isfile(env_file):
					mysettings["PORTAGE_UPDATE_ENV"] = env_file
			try:
				return _spawn_phase(mydo, mysettings,
					fd_pipes=fd_pipes, logfile=logfile, returnpid=returnpid)
			finally:
				mysettings.pop("PORTAGE_UPDATE_ENV", None)

		mycpv = "/".join((mysettings["CATEGORY"], mysettings["PF"]))

		# Only try and fetch the files if we are going to need them ...
		# otherwise, if user has FEATURES=noauto and they run `ebuild clean
		# unpack compile install`, we will try and fetch 4 times :/
		need_distfiles = tree == "porttree" and not unpacked and \
			(mydo in ("fetch", "unpack") or \
			mydo not in ("digest", "manifest") and "noauto" not in features)
		if need_distfiles:

			src_uri = mysettings.configdict["pkg"].get("SRC_URI")
			if src_uri is None:
				src_uri, = mydbapi.aux_get(mysettings.mycpv,
					["SRC_URI"], mytree=os.path.dirname(os.path.dirname(
					os.path.dirname(myebuild))))
			metadata = {
				"EAPI"    : mysettings["EAPI"],
				"SRC_URI" : src_uri,
			}
			use = frozenset(mysettings["PORTAGE_USE"].split())
			try:
				alist = _parse_uri_map(mysettings.mycpv, metadata, use=use)
				aalist = _parse_uri_map(mysettings.mycpv, metadata)
			except InvalidDependString as e:
				writemsg("!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Invalid SRC_URI for '%s'.\n") % mycpv,
					noiselevel=-1)
				del e
				return 1

			if "mirror" in features or fetchall:
				fetchme = aalist
			else:
				fetchme = alist

			dist_digests = None
			if mf is not None:
				dist_digests = mf.getTypeDigests("DIST")

			def _fetch_subprocess(fetchme, mysettings, listonly, dist_digests):
				# For userfetch, drop privileges for the entire fetch call, in
				# order to handle DISTDIR on NFS with root_squash for bug 601252.
				if _want_userfetch(mysettings):
					_drop_privs_userfetch(mysettings)

				return fetch(fetchme, mysettings, listonly=listonly,
					fetchonly=fetchonly, allow_missing_digests=False,
					digests=dist_digests)

			loop = asyncio._safe_loop()
			if loop.is_running():
				# Called by EbuildFetchonly for emerge --pretend --fetchonly.
				success = fetch(fetchme, mysettings, listonly=listonly,
					fetchonly=fetchonly, allow_missing_digests=False,
					digests=dist_digests)
			else:
				success = loop.run_until_complete(
					loop.run_in_executor(ForkExecutor(loop=loop),
					_fetch_subprocess, fetchme, mysettings, listonly, dist_digests))
			if not success:
				# Since listonly mode is called by emerge --pretend in an
				# asynchronous context, spawn_nofetch would trigger event loop
				# recursion here, therefore delegate execution of pkg_nofetch
				# to the caller (bug 657360).
				if not listonly:
					spawn_nofetch(mydbapi, myebuild, settings=mysettings,
						fd_pipes=fd_pipes)
				return 1

		if need_distfiles:
			# Files are already checked inside fetch(),
			# so do not check them again.
			checkme = []
		elif unpacked:
			# The unpack phase is marked as complete, so it
			# would be wasteful to check distfiles again.
			checkme = []
		else:
			checkme = alist

		if mydo == "fetch" and listonly:
			return 0

		try:
			if mydo == "manifest":
				mf = None
				_doebuild_manifest_cache = None
				return not digestgen(mysettings=mysettings, myportdb=mydbapi)
			if mydo == "digest":
				mf = None
				_doebuild_manifest_cache = None
				return not digestgen(mysettings=mysettings, myportdb=mydbapi)
			if "digest" in mysettings.features:
				mf = None
				_doebuild_manifest_cache = None
				digestgen(mysettings=mysettings, myportdb=mydbapi)
		except PermissionDenied as e:
			writemsg(_("!!! Permission Denied: %s\n") % (e,), noiselevel=-1)
			if mydo in ("digest", "manifest"):
				return 1

		if mydo == "fetch":
			# Return after digestgen for FEATURES=digest support.
			# Return before digestcheck, since fetch() already
			# checked any relevant digests.
			return 0

		# See above comment about fetching only when needed
		if tree == 'porttree' and \
			not digestcheck(checkme, mysettings, "strict" in features, mf=mf):
			return 1

		# remove PORTAGE_ACTUAL_DISTDIR once cvs/svn is supported via SRC_URI
		if tree == 'porttree' and \
			((mydo != "setup" and "noauto" not in features) \
			or mydo in ("install", "unpack")):
			_prepare_fake_distdir(mysettings, alist)

		#initial dep checks complete; time to process main commands
		actionmap = _spawn_actionmap(mysettings)

		# merge the deps in so we have again a 'full' actionmap
		# be glad when this can die.
		for x in actionmap:
			if len(actionmap_deps.get(x, [])):
				actionmap[x]["dep"] = ' '.join(actionmap_deps[x])

		regular_actionmap_phase = mydo in actionmap

		if regular_actionmap_phase:
			bintree = None
			if mydo == "package":
				# Make sure the package directory exists before executing
				# this phase. This can raise PermissionDenied if
				# the current user doesn't have write access to $PKGDIR.
				if hasattr(portage, 'db'):
					bintree = portage.db[mysettings['EROOT']]['bintree']
					binpkg_tmpfile_dir = os.path.join(bintree.pkgdir, mysettings["CATEGORY"])
					bintree._ensure_dir(binpkg_tmpfile_dir)
					with tempfile.NamedTemporaryFile(
						prefix=mysettings["PF"],
						suffix=".tbz2." + str(portage.getpid()),
						dir=binpkg_tmpfile_dir,
						delete=False) as binpkg_tmpfile:
						mysettings["PORTAGE_BINPKG_TMPFILE"] = binpkg_tmpfile.name
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

			if returnpid and isinstance(retval, list):
				return retval

			if retval == os.EX_OK:
				if mydo == "package" and bintree is not None:
					pkg = bintree.inject(mysettings.mycpv,
						filename=mysettings["PORTAGE_BINPKG_TMPFILE"])
					if pkg is not None:
						infoloc = os.path.join(
							mysettings["PORTAGE_BUILDDIR"], "build-info")
						build_info = {
							"BINPKGMD5": "%s\n" % pkg._metadata["MD5"],
						}
						if pkg.build_id is not None:
							build_info["BUILD_ID"] = "%s\n" % pkg.build_id
						for k, v in build_info.items():
							with io.open(_unicode_encode(
								os.path.join(infoloc, k),
								encoding=_encodings['fs'], errors='strict'),
								mode='w', encoding=_encodings['repo.content'],
								errors='strict') as f:
								f.write(v)
			else:
				if "PORTAGE_BINPKG_TMPFILE" in mysettings:
					try:
						os.unlink(mysettings["PORTAGE_BINPKG_TMPFILE"])
					except OSError:
						pass

		elif returnpid:
			writemsg("!!! doebuild: %s\n" %
				_("returnpid is not supported for phase '%s'\n" % mydo),
				noiselevel=-1)

		if regular_actionmap_phase:
			# handled above
			pass
		elif mydo == "qmerge":
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
			_handle_self_update(mysettings, vartree.dbapi)
			#qmerge is specifically not supposed to do a runtime dep check
			retval = merge(
				mysettings["CATEGORY"], mysettings["PF"], mysettings["D"],
				os.path.join(mysettings["PORTAGE_BUILDDIR"], "build-info"),
				myroot, mysettings, myebuild=mysettings["EBUILD"], mytree=tree,
				mydbapi=mydbapi, vartree=vartree, prev_mtimes=prev_mtimes,
				fd_pipes=fd_pipes)
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
				_handle_self_update(mysettings, vartree.dbapi)
				retval = merge(mysettings["CATEGORY"], mysettings["PF"],
					mysettings["D"], os.path.join(mysettings["PORTAGE_BUILDDIR"],
					"build-info"), myroot, mysettings,
					myebuild=mysettings["EBUILD"], mytree=tree, mydbapi=mydbapi,
					vartree=vartree, prev_mtimes=prev_mtimes,
					fd_pipes=fd_pipes)

		else:
			writemsg_stdout(_("!!! Unknown mydo: %s\n") % mydo, noiselevel=-1)
			return 1

		return retval

	finally:

		if builddir_lock is not None:
			builddir_lock.scheduler.run_until_complete(
				builddir_lock.async_unlock())
		if tmpdir:
			mysettings["PORTAGE_TMPDIR"] = tmpdir_orig
			shutil.rmtree(tmpdir)

		mysettings.pop("REPLACING_VERSIONS", None)

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
	checkdir = first_existing(os.path.join(settings["PORTAGE_TMPDIR"], "portage"))

	if not os.access(checkdir, os.W_OK):
		writemsg(_("%s is not writable.\n"
			"Likely cause is that you've mounted it as readonly.\n") % checkdir,
			noiselevel=-1)
		return 1

	with tempfile.NamedTemporaryFile(prefix="exectest-", dir=checkdir) as fd:
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
		scheduler=asyncio._safe_loop(),
		settings=settings)

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

def _spawn_actionmap(settings):
	features = settings.features
	restrict = settings["PORTAGE_RESTRICT"].split()
	nosandbox = (("userpriv" in features) and \
		("usersandbox" not in features) and \
		"userpriv" not in restrict and \
		"nouserpriv" not in restrict)

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
	misc_sh = _shell_quote(misc_sh_binary) + " __dyn_%s"

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
"instprep": {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":sesandbox, "fakeroot":fakeroot}},
"rpm":      {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
"package":  {"cmd":misc_sh,   "args":{"droppriv":0,        "free":0,         "sesandbox":0,         "fakeroot":fakeroot}},
		}

	return actionmap

def _validate_deps(mysettings, myroot, mydo, mydbapi):

	invalid_dep_exempt_phases = \
		set(["clean", "cleanrm", "help", "prerm", "postrm"])
	all_keys = set(Package.metadata_keys)
	all_keys.add("SRC_URI")
	all_keys = tuple(all_keys)
	metadata = mysettings.configdict['pkg']
	if all(k in metadata for k in ("PORTAGE_REPO_NAME", "SRC_URI")):
		metadata = dict(((k, metadata[k]) for k in all_keys if k in metadata),
			repository=metadata["PORTAGE_REPO_NAME"])
	else:
		metadata = dict(zip(all_keys,
			mydbapi.aux_get(mysettings.mycpv, all_keys,
			myrepo=mysettings.get("PORTAGE_REPO_NAME"))))

	class FakeTree:
		def __init__(self, mydb):
			self.dbapi = mydb

	root_config = RootConfig(mysettings, {"porttree":FakeTree(mydbapi)}, None)

	pkg = Package(built=False, cpv=mysettings.mycpv,
		metadata=metadata, root_config=root_config,
		type_name="ebuild")

	msgs = []
	if pkg.invalid:
		for k, v in pkg.invalid.items():
			for msg in v:
				msgs.append("  %s\n" % (msg,))

	if msgs:
		portage.util.writemsg_level(_("Error(s) in metadata for '%s':\n") % \
			(mysettings.mycpv,), level=logging.ERROR, noiselevel=-1)
		for x in msgs:
			portage.util.writemsg_level(x,
				level=logging.ERROR, noiselevel=-1)
		if mydo not in invalid_dep_exempt_phases:
			return 1

	if not pkg.built and \
		mydo not in ("digest", "help", "manifest") and \
		pkg._metadata["REQUIRED_USE"] and \
		eapi_has_required_use(pkg.eapi):
		result = check_required_use(pkg._metadata["REQUIRED_USE"],
			pkg.use.enabled, pkg.iuse.is_valid_flag, eapi=pkg.eapi)
		if not result:
			reduced_noise = result.tounicode()
			writemsg("\n  %s\n" % _("The following REQUIRED_USE flag" + \
				" constraints are unsatisfied:"), noiselevel=-1)
			writemsg("    %s\n" % reduced_noise,
				noiselevel=-1)
			normalized_required_use = \
				" ".join(pkg._metadata["REQUIRED_USE"].split())
			if reduced_noise != normalized_required_use:
				writemsg("\n  %s\n" % _("The above constraints " + \
					"are a subset of the following complete expression:"),
					noiselevel=-1)
				writemsg("    %s\n" % \
					human_readable_required_use(normalized_required_use),
					noiselevel=-1)
			writemsg("\n", noiselevel=-1)
			return 1

	return os.EX_OK

# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring, mysettings, debug=False, free=False, droppriv=False,
	sesandbox=False, fakeroot=False, networked=True, ipc=True,
	mountns=False, pidns=False, **keywords):
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
	@param networked: Run this command with networking access enabled
	@type networked: Boolean
	@param ipc: Run this command with host IPC access enabled
	@type ipc: Boolean
	@param mountns: Run this command inside mount namespace
	@type mountns: Boolean
	@param pidns: Run this command in isolated PID namespace
	@type pidns: Boolean
	@param keywords: Extra options encoded as a dict, to be passed to spawn
	@type keywords: Dictionary
	@rtype: Integer
	@return:
	1. The return code of the spawned process.
	"""

	check_config_instance(mysettings)

	fd_pipes = keywords.get("fd_pipes")
	if fd_pipes is None:
		fd_pipes = {
			0:portage._get_stdin().fileno(),
			1:sys.__stdout__.fileno(),
			2:sys.__stderr__.fileno(),
		}
	# In some cases the above print statements don't flush stdout, so
	# it needs to be flushed before allowing a child process to use it
	# so that output always shows in the correct order.
	stdout_filenos = (sys.__stdout__.fileno(), sys.__stderr__.fileno())
	for fd in fd_pipes.values():
		if fd in stdout_filenos:
			sys.__stdout__.flush()
			sys.__stderr__.flush()
			break

	features = mysettings.features

	# Use Linux namespaces if available
	if uid == 0 and platform.system() == 'Linux':
		keywords['unshare_net'] = not networked
		keywords['unshare_ipc'] = not ipc
		keywords['unshare_mount'] = mountns
		keywords['unshare_pid'] = pidns

		if not networked and mysettings.get("EBUILD_PHASE") != "nofetch" and \
			("network-sandbox-proxy" in features or "distcc" in features):
			# Provide a SOCKS5-over-UNIX-socket proxy to escape sandbox
			# Don't do this for pkg_nofetch, since the spawn_nofetch
			# function creates a private PORTAGE_TMPDIR.
			try:
				proxy = get_socks5_proxy(mysettings)
			except NotImplementedError:
				pass
			else:
				mysettings['PORTAGE_SOCKS5_PROXY'] = proxy
				mysettings['DISTCC_SOCKS_PROXY'] = proxy

	# TODO: Enable fakeroot to be used together with droppriv.  The
	# fake ownership/permissions will have to be converted to real
	# permissions in the merge phase.
	fakeroot = fakeroot and uid != 0 and portage.process.fakeroot_capable
	portage_build_uid = os.getuid()
	portage_build_gid = os.getgid()
	logname = None
	if uid == 0 and portage_uid and portage_gid and hasattr(os, "setgroups"):
		if droppriv:
			logname = portage.data._portage_username
			keywords.update({
				"uid": portage_uid,
				"gid": portage_gid,
				"groups": userpriv_groups,
				"umask": 0o22
			})

			# Adjust pty ownership so that subprocesses
			# can directly access /dev/fd/{1,2}.
			stdout_fd = fd_pipes.get(1)
			if stdout_fd is not None:
				try:
					subprocess_tty = _os.ttyname(stdout_fd)
				except OSError:
					pass
				else:
					try:
						parent_tty = _os.ttyname(sys.__stdout__.fileno())
					except OSError:
						parent_tty = None

					if subprocess_tty != parent_tty:
						_os.chown(subprocess_tty,
							int(portage_uid), int(portage_gid))

		if "userpriv" in features and "userpriv" not in mysettings["PORTAGE_RESTRICT"].split() and secpass >= 2:
			# Since Python 3.4, getpwuid and getgrgid
			# require int type (no proxies).
			portage_build_uid = int(portage_uid)
			portage_build_gid = int(portage_gid)

	if "PORTAGE_BUILD_USER" not in mysettings:
		user = None
		try:
			user = pwd.getpwuid(portage_build_uid).pw_name
		except KeyError:
			if portage_build_uid == 0:
				user = "root"
			elif portage_build_uid == portage_uid:
				user = portage.data._portage_username
		if user is not None:
			mysettings["PORTAGE_BUILD_USER"] = user

	if "PORTAGE_BUILD_GROUP" not in mysettings:
		group = None
		try:
			group = grp.getgrgid(portage_build_gid).gr_name
		except KeyError:
			if portage_build_gid == 0:
				group = "root"
			elif portage_build_gid == portage_gid:
				group = portage.data._portage_grpname
		if group is not None:
			mysettings["PORTAGE_BUILD_GROUP"] = group

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

	logname_backup = None
	if logname is not None:
		logname_backup = mysettings.configdict["env"].get("LOGNAME")
		mysettings.configdict["env"]["LOGNAME"] = logname

	try:
		if keywords.get("returnpid"):
			return spawn_func(mystring, env=mysettings.environ(),
				**keywords)

		proc = EbuildSpawnProcess(
			background=False, args=mystring,
			scheduler=SchedulerInterface(asyncio._safe_loop()),
			spawn_func=spawn_func,
			settings=mysettings, **keywords)

		proc.start()
		proc.wait()

		return proc.returncode

	finally:
		if logname is None:
			pass
		elif logname_backup is None:
			mysettings.configdict["env"].pop("LOGNAME", None)
		else:
			mysettings.configdict["env"]["LOGNAME"] = logname_backup

# parse actionmap to spawn ebuild with the appropriate args
def spawnebuild(mydo, actionmap, mysettings, debug, alwaysdep=0,
	logfile=None, fd_pipes=None, returnpid=False):

	if returnpid:
		warnings.warn("portage.spawnebuild() called "
			"with returnpid parameter enabled. This usage will "
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

	if not (mydo == "install" and "noauto" in mysettings.features):
		check_file = os.path.join(
			mysettings["PORTAGE_BUILDDIR"], ".%sed" % mydo.rstrip('e'))
		if os.path.exists(check_file):
			writemsg_stdout(_(">>> It appears that "
				"'%(action)s' has already executed for '%(pkg)s'; skipping.\n") %
				{"action":mydo, "pkg":mysettings["PF"]})
			writemsg_stdout(_(">>> Remove '%(file)s' to force %(action)s.\n") %
				{"file":check_file, "action":mydo})
			return os.EX_OK

	return _spawn_phase(mydo, mysettings,
		actionmap=actionmap, logfile=logfile,
		fd_pipes=fd_pipes, returnpid=returnpid)

_post_phase_cmds = {

	"install" : [
		"install_qa_check",
		"install_symlink_html_docs",
		"install_hooks"],

	"preinst" : (
		(
			# Since SELinux does not allow LD_PRELOAD across domain transitions,
			# disable the LD_PRELOAD sandbox for preinst_selinux_labels.
			{
				"ld_preload_sandbox": False,
				"selinux_only": True,
			},
			[
				"preinst_selinux_labels",
			],
		),
		(
			{},
			[
				"preinst_sfperms",
				"preinst_suid_scan",
				"preinst_qa_check",
			],
		),
	),
	"postinst" : [
		"postinst_qa_check"],
}

def _post_phase_userpriv_perms(mysettings):
	if "userpriv" in mysettings.features and secpass >= 2:
		""" Privileged phases may have left files that need to be made
		writable to a less privileged user."""
		for path in (mysettings["HOME"], mysettings["T"]):
			apply_recursive_permissions(path,
				uid=portage_uid, gid=portage_gid, dirmode=0o700, dirmask=0,
				filemode=0o600, filemask=0)


def _post_phase_emptydir_cleanup(mysettings):
	empty_dir = os.path.join(mysettings["PORTAGE_BUILDDIR"], "empty")
	shutil.rmtree(empty_dir, ignore_errors=True)


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

	f_real = None
	if logfile.endswith('.gz'):
		f_real = f
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
		r'^configure: WARNING: [Uu]nrecognized options: (.*)')

	qa_configure_opts = ""
	try:
		with io.open(_unicode_encode(os.path.join(
			mysettings["PORTAGE_BUILDDIR"],
			"build-info", "QA_CONFIGURE_OPTIONS"),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace') as qa_configure_opts_f:
			qa_configure_opts = qa_configure_opts_f.read()
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise

	qa_configure_opts = qa_configure_opts.split()
	if qa_configure_opts:
		if len(qa_configure_opts) > 1:
			qa_configure_opts = "|".join("(%s)" % x for x in qa_configure_opts)
			qa_configure_opts = "^(%s)$" % qa_configure_opts
		else:
			qa_configure_opts = "^%s$" % qa_configure_opts[0]
		qa_configure_opts = re.compile(qa_configure_opts)

	qa_am_maintainer_mode = []
	try:
		with io.open(_unicode_encode(os.path.join(
			mysettings["PORTAGE_BUILDDIR"],
			"build-info", "QA_AM_MAINTAINER_MODE"),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace') as qa_am_maintainer_mode_f:
			qa_am_maintainer_mode = [x for x in
				qa_am_maintainer_mode_f.read().splitlines() if x]
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise

	if qa_am_maintainer_mode:
		if len(qa_am_maintainer_mode) > 1:
			qa_am_maintainer_mode = \
				"|".join("(%s)" % x for x in qa_am_maintainer_mode)
			qa_am_maintainer_mode = "^(%s)$" % qa_am_maintainer_mode
		else:
			qa_am_maintainer_mode = "^%s$" % qa_am_maintainer_mode[0]
		qa_am_maintainer_mode = re.compile(qa_am_maintainer_mode)

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

	# we deduplicate these since they is repeated for every setup.py call
	setuptools_warn = set()
	setuptools_warn_re = re.compile(r'.*\/setuptools\/.*: UserWarning: (.*)')

	def _eerror(lines):
		for line in lines:
			eerror(line, phase="install", key=mysettings.mycpv, out=out)

	try:
		for line in f:
			line = _unicode_decode(line)
			if am_maintainer_mode_re.search(line) is not None and \
				am_maintainer_mode_exclude_re.search(line) is None and \
				(not qa_am_maintainer_mode or
					qa_am_maintainer_mode.search(line) is None):
				am_maintainer_mode.append(line.rstrip("\n"))

			if bash_command_not_found_re.match(line) is not None and \
				command_not_found_exclude_re.search(line) is None:
				bash_command_not_found.append(line.rstrip("\n"))

			if helper_missing_file_re.match(line) is not None:
				helper_missing_file.append(line.rstrip("\n"))

			m = configure_opts_warn_re.match(line)
			if m is not None:
				for x in m.group(1).split(", "):
					if not qa_configure_opts or qa_configure_opts.match(x) is None:
						configure_opts_warn.append(x)

			if make_jobserver_re.match(line) is not None:
				make_jobserver.append(line.rstrip("\n"))

			m = setuptools_warn_re.match(line)
			if m is not None:
				setuptools_warn.add(m.group(1))

	except (EOFError, zlib.error) as e:
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
			"See https://wiki.gentoo.org/wiki/Project:Quality_Assurance/Autotools_failures"
            " for more information."),
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
		msg.extend("\t%s" % x for x in configure_opts_warn)
		_eqawarn(msg)

	if make_jobserver:
		msg = [_("QA Notice: make jobserver unavailable:")]
		msg.append("")
		msg.extend("\t" + line for line in make_jobserver)
		_eqawarn(msg)

	if setuptools_warn:
		msg = [_("QA Notice: setuptools warnings detected:")]
		msg.append("")
		msg.extend("\t" + line for line in sorted(setuptools_warn))
		_eqawarn(msg)

	f.close()
	if f_real is not None:
		f_real.close()

def _post_src_install_write_metadata(settings):
	"""
	It's possible that the ebuild has changed the
	CHOST variable, so revert it to the initial
	setting. Also, revert IUSE in case it's corrupted
	due to local environment settings like in bug #386829.
	"""

	eapi_attrs = _get_eapi_attrs(settings.configdict['pkg']['EAPI'])

	build_info_dir = os.path.join(settings['PORTAGE_BUILDDIR'], 'build-info')

	metadata_keys = ['IUSE']
	if eapi_attrs.iuse_effective:
		metadata_keys.append('IUSE_EFFECTIVE')

	for k in metadata_keys:
		v = settings.configdict['pkg'].get(k)
		if v is not None:
			write_atomic(os.path.join(build_info_dir, k), v + '\n')

	for k in ('CHOST',):
		v = settings.get(k)
		if v is not None:
			write_atomic(os.path.join(build_info_dir, k), v + '\n')

	with io.open(_unicode_encode(os.path.join(build_info_dir,
		'BUILD_TIME'), encoding=_encodings['fs'], errors='strict'),
		mode='w', encoding=_encodings['repo.content'],
		errors='strict') as f:
		f.write("%.0f\n" % (time.time(),))

	use = frozenset(settings['PORTAGE_USE'].split())
	for k in _vdb_use_conditional_keys:
		v = settings.configdict['pkg'].get(k)
		filename = os.path.join(build_info_dir, k)
		if v is None:
			try:
				os.unlink(filename)
			except OSError:
				pass
			continue

		if k.endswith('DEPEND'):
			if eapi_attrs.slot_operator:
				continue
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
		with io.open(_unicode_encode(os.path.join(build_info_dir,
			k), encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='strict') as f:
			f.write('%s\n' % v)

	if eapi_attrs.slot_operator:
		deps = evaluate_slot_operator_equal_deps(settings, use, QueryCommand.get_db())
		for k, v in deps.items():
			filename = os.path.join(build_info_dir, k)
			if not v:
				try:
					os.unlink(filename)
				except OSError:
					pass
				continue
			with io.open(_unicode_encode(os.path.join(build_info_dir,
				k), encoding=_encodings['fs'], errors='strict'),
				mode='w', encoding=_encodings['repo.content'],
				errors='strict') as f:
				f.write('%s\n' % v)

def _preinst_bsdflags(mysettings):
	if bsd_chflags:
		# Save all the file flags for restoration later.
		os.system("mtree -c -p %s -k flags > %s" % \
			(_shell_quote(mysettings["D"]),
			_shell_quote(os.path.join(mysettings["T"], "bsdflags.mtree"))))

		# Remove all the file flags to avoid EPERM errors.
		os.system("chflags -R noschg,nouchg,nosappnd,nouappnd %s" % \
			(_shell_quote(mysettings["D"]),))
		os.system("chflags -R nosunlnk,nouunlnk %s 2>/dev/null" % \
			(_shell_quote(mysettings["D"]),))


def _postinst_bsdflags(mysettings):
	if bsd_chflags:
		# Restore all of the flags saved above.
		os.system("mtree -e -p %s -U -k flags < %s > /dev/null" % \
			(_shell_quote(mysettings["ROOT"]),
			_shell_quote(os.path.join(mysettings["T"], "bsdflags.mtree"))))

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

	_preinst_bsdflags(mysettings)

	destdir = mysettings["D"]
	ed_len = len(mysettings["ED"])
	unicode_errors = []
	desktop_file_validate = \
		portage.process.find_binary("desktop-file-validate") is not None
	xdg_dirs = mysettings.get('XDG_DATA_DIRS', '/usr/share').split(':')
	xdg_dirs = tuple(os.path.join(i, "applications") + os.sep
		for i in xdg_dirs if i)

	qa_desktop_file = ""
	try:
		with io.open(_unicode_encode(os.path.join(
			mysettings["PORTAGE_BUILDDIR"],
			"build-info", "QA_DESKTOP_FILE"),
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace') as f:
			qa_desktop_file = f.read()
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise

	qa_desktop_file = qa_desktop_file.split()
	if qa_desktop_file:
		if len(qa_desktop_file) > 1:
			qa_desktop_file = "|".join("(%s)" % x for x in qa_desktop_file)
			qa_desktop_file = "^(%s)$" % qa_desktop_file
		else:
			qa_desktop_file = "^%s$" % qa_desktop_file[0]
		qa_desktop_file = re.compile(qa_desktop_file)

	while True:

		unicode_error = False
		size = 0
		counted_inodes = set()
		fixlafiles_announced = False
		fixlafiles = "fixlafiles" in mysettings.features
		desktopfile_errors = []

		for parent, dirs, files in os.walk(destdir):
			try:
				parent = _unicode_decode(parent,
					encoding=_encodings['merge'], errors='strict')
			except UnicodeDecodeError:
				new_parent = _unicode_decode(parent,
					encoding=_encodings['merge'], errors='replace')
				new_parent = _unicode_encode(new_parent,
					encoding='ascii', errors='backslashreplace')
				new_parent = _unicode_decode(new_parent,
					encoding=_encodings['merge'], errors='replace')
				os.rename(parent, new_parent)
				unicode_error = True
				unicode_errors.append(new_parent[ed_len:])
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
						encoding='ascii', errors='backslashreplace')
					new_fname = _unicode_decode(new_fname,
						encoding=_encodings['merge'], errors='replace')
					new_fpath = os.path.join(parent, new_fname)
					os.rename(fpath, new_fpath)
					unicode_error = True
					unicode_errors.append(new_fpath[ed_len:])
					fname = new_fname
					fpath = new_fpath
				else:
					fpath = os.path.join(parent, fname)

				fpath_relative = fpath[ed_len - 1:]
				if desktop_file_validate and fname.endswith(".desktop") and \
					os.path.isfile(fpath) and \
					fpath_relative.startswith(xdg_dirs) and \
					not (qa_desktop_file and qa_desktop_file.match(fpath_relative.strip(os.sep)) is not None):

					desktop_validate = validate_desktop_entry(fpath)
					if desktop_validate:
						desktopfile_errors.extend(desktop_validate)

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

	if desktopfile_errors:
		for l in _merge_desktopfile_error(desktopfile_errors):
			l = l.replace(mysettings["ED"], '/')
			eqawarn(l, phase='install', key=mysettings.mycpv, out=out)

	if unicode_errors:
		for l in _merge_unicode_error(unicode_errors):
			eqawarn(l, phase='install', key=mysettings.mycpv, out=out)

	build_info_dir = os.path.join(mysettings['PORTAGE_BUILDDIR'],
		'build-info')

	f = io.open(_unicode_encode(os.path.join(build_info_dir,
		'SIZE'), encoding=_encodings['fs'], errors='strict'),
		mode='w', encoding=_encodings['repo.content'],
		errors='strict')
	f.write('%d\n' % size)
	f.close()

	_reapply_bsdflags_to_image(mysettings)

def _reapply_bsdflags_to_image(mysettings):
	"""
	Reapply flags saved and removed by _preinst_bsdflags.
	"""
	if bsd_chflags:
		os.system("mtree -e -p %s -U -k flags < %s > /dev/null" % \
			(_shell_quote(mysettings["D"]),
			_shell_quote(os.path.join(mysettings["T"], "bsdflags.mtree"))))

def _post_src_install_soname_symlinks(mysettings, out):
	"""
	Check that libraries in $D have corresponding soname symlinks.
	If symlinks are missing then create them and trigger a QA Notice.
	This requires $PORTAGE_BUILDDIR/build-info/NEEDED.ELF.2 for
	operation.
	"""

	image_dir = mysettings["D"]
	needed_filename = os.path.join(mysettings["PORTAGE_BUILDDIR"],
		"build-info", "NEEDED.ELF.2")

	f = None
	try:
		f = io.open(_unicode_encode(needed_filename,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace')
		lines = f.readlines()
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		return
	finally:
		if f is not None:
			f.close()

	metadata = {}
	for k in ("QA_PREBUILT", "QA_SONAME_NO_SYMLINK"):
		try:
			with io.open(_unicode_encode(os.path.join(
				mysettings["PORTAGE_BUILDDIR"],
				"build-info", k),
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				v = f.read()
		except IOError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				raise
		else:
			metadata[k] = v

	qa_prebuilt = metadata.get("QA_PREBUILT", "").strip()
	if qa_prebuilt:
		qa_prebuilt = re.compile("|".join(
			fnmatch.translate(x.lstrip(os.sep))
			for x in portage.util.shlex_split(qa_prebuilt)))

	qa_soname_no_symlink = metadata.get("QA_SONAME_NO_SYMLINK", "").split()
	if qa_soname_no_symlink:
		if len(qa_soname_no_symlink) > 1:
			qa_soname_no_symlink = "|".join("(%s)" % x for x in qa_soname_no_symlink)
			qa_soname_no_symlink = "^(%s)$" % qa_soname_no_symlink
		else:
			qa_soname_no_symlink = "^%s$" % qa_soname_no_symlink[0]
		qa_soname_no_symlink = re.compile(qa_soname_no_symlink)

	libpaths = set(portage.util.getlibpaths(
		mysettings["ROOT"], env=mysettings))
	libpath_inodes = set()
	for libpath in libpaths:
		libdir = os.path.join(mysettings["ROOT"], libpath.lstrip(os.sep))
		try:
			s = os.stat(libdir)
		except OSError:
			continue
		else:
			libpath_inodes.add((s.st_dev, s.st_ino))

	is_libdir_cache = {}

	def is_libdir(obj_parent):
		try:
			return is_libdir_cache[obj_parent]
		except KeyError:
			pass

		rval = False
		if obj_parent in libpaths:
			rval = True
		else:
			parent_path = os.path.join(mysettings["ROOT"],
				obj_parent.lstrip(os.sep))
			try:
				s = os.stat(parent_path)
			except OSError:
				pass
			else:
				if (s.st_dev, s.st_ino) in libpath_inodes:
					rval = True

		is_libdir_cache[obj_parent] = rval
		return rval

	build_info_dir = os.path.join(
		mysettings['PORTAGE_BUILDDIR'], 'build-info')
	try:
		with io.open(_unicode_encode(os.path.join(build_info_dir,
			"PROVIDES_EXCLUDE"), encoding=_encodings['fs'],
			errors='strict'), mode='r', encoding=_encodings['repo.content'],
			errors='replace') as f:
			provides_exclude = f.read()
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		provides_exclude = ""

	try:
		with io.open(_unicode_encode(os.path.join(build_info_dir,
			"REQUIRES_EXCLUDE"), encoding=_encodings['fs'],
			errors='strict'), mode='r', encoding=_encodings['repo.content'],
			errors='replace') as f:
			requires_exclude = f.read()
	except IOError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		requires_exclude = ""

	missing_symlinks = []
	unrecognized_elf_files = []
	soname_deps = SonameDepsProcessor(
		provides_exclude, requires_exclude)

	# Parse NEEDED.ELF.2 like LinkageMapELF.rebuild() does, and
	# rewrite it to include multilib categories.
	needed_file = portage.util.atomic_ofstream(needed_filename,
		encoding=_encodings["repo.content"], errors="strict")

	for l in lines:
		l = l.rstrip("\n")
		if not l:
			continue
		try:
			entry = NeededEntry.parse(needed_filename, l)
		except InvalidData as e:
			portage.util.writemsg_level("\n%s\n\n" % (e,),
				level=logging.ERROR, noiselevel=-1)
			continue

		filename = os.path.join(image_dir,
			entry.filename.lstrip(os.sep))
		with open(_unicode_encode(filename, encoding=_encodings['fs'],
			errors='strict'), 'rb') as f:
			elf_header = ELFHeader.read(f)

		# Compute the multilib category and write it back to the file.
		entry.multilib_category = compute_multilib_category(elf_header)
		needed_file.write(str(entry))

		if entry.multilib_category is None:
			if not qa_prebuilt or qa_prebuilt.match(
				entry.filename[len(mysettings["EPREFIX"]):].lstrip(
				os.sep)) is None:
				unrecognized_elf_files.append(entry)
		else:
			soname_deps.add(entry)

		obj = entry.filename
		soname = entry.soname

		if not soname:
			continue
		if not is_libdir(os.path.dirname(obj)):
			continue
		if qa_soname_no_symlink and qa_soname_no_symlink.match(obj.strip(os.sep)) is not None:
			continue

		obj_file_path = os.path.join(image_dir, obj.lstrip(os.sep))
		sym_file_path = os.path.join(os.path.dirname(obj_file_path), soname)
		try:
			os.lstat(sym_file_path)
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				raise
		else:
			continue

		missing_symlinks.append((obj, soname))

	needed_file.close()

	if soname_deps.requires is not None:
		with io.open(_unicode_encode(os.path.join(build_info_dir,
			'REQUIRES'), encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='strict') as f:
			f.write(soname_deps.requires)

	if soname_deps.provides is not None:
		with io.open(_unicode_encode(os.path.join(build_info_dir,
			'PROVIDES'), encoding=_encodings['fs'], errors='strict'),
			mode='w', encoding=_encodings['repo.content'],
			errors='strict') as f:
			f.write(soname_deps.provides)

	if unrecognized_elf_files:
		qa_msg = ["QA Notice: Unrecognized ELF file(s):"]
		qa_msg.append("")
		qa_msg.extend("\t%s" % str(entry).rstrip()
			for entry in unrecognized_elf_files)
		qa_msg.append("")
		for line in qa_msg:
			eqawarn(line, key=mysettings.mycpv, out=out)

	if not missing_symlinks:
		return

	qa_msg = ["QA Notice: Missing soname symlink(s):"]
	qa_msg.append("")
	qa_msg.extend("\t%s -> %s" % (os.path.join(
		os.path.dirname(obj).lstrip(os.sep), soname),
		os.path.basename(obj))
		for obj, soname in missing_symlinks)
	qa_msg.append("")
	for line in qa_msg:
		eqawarn(line, key=mysettings.mycpv, out=out)

def _merge_desktopfile_error(errors):
	lines = []

	msg = _("QA Notice: This package installs one or more .desktop files "
		"that do not pass validation.")
	lines.extend(wrap(msg, 72))

	lines.append("")
	errors.sort()
	lines.extend("\t" + x for x in errors)
	lines.append("")

	return lines

def _merge_unicode_error(errors):
	lines = []

	msg = _("QA Notice: This package installs one or more file names "
		"containing characters that are not encoded with the UTF-8 encoding.")
	lines.extend(wrap(msg, 72))

	lines.append("")
	errors.sort()
	lines.extend("\t" + x for x in errors)
	lines.append("")

	return lines

def _prepare_self_update(settings):
	"""
	Call this when portage is updating itself, in order to create
	temporary copies of PORTAGE_BIN_PATH and PORTAGE_PYM_PATH, since
	the new versions may be incompatible. An atexit hook will
	automatically clean up the temporary copies.
	"""

	# sanity check: ensure that that this routine only runs once
	if portage._bin_path != portage.const.PORTAGE_BIN_PATH:
		return

	# Load lazily referenced portage submodules into memory,
	# so imports won't fail during portage upgrade/downgrade.
	_preload_elog_modules(settings)
	portage.proxy.lazyimport._preload_portage_submodules()

	# Make the temp directory inside $PORTAGE_TMPDIR/portage, since
	# it's common for /tmp and /var/tmp to be mounted with the
	# "noexec" option (see bug #346899).
	build_prefix = os.path.join(settings["PORTAGE_TMPDIR"], "portage")
	portage.util.ensure_dirs(build_prefix)
	base_path_tmp = tempfile.mkdtemp(
		"", "._portage_reinstall_.", build_prefix)
	portage.process.atexit_register(shutil.rmtree, base_path_tmp)

	orig_bin_path = portage._bin_path
	portage._bin_path = os.path.join(base_path_tmp, "bin")
	shutil.copytree(orig_bin_path, portage._bin_path, symlinks=True)

	orig_pym_path = portage._pym_path
	portage._pym_path = os.path.join(base_path_tmp, "lib")
	os.mkdir(portage._pym_path)
	for pmod in PORTAGE_PYM_PACKAGES:
		shutil.copytree(os.path.join(orig_pym_path, pmod),
			os.path.join(portage._pym_path, pmod),
			symlinks=True)

	for dir_path in (base_path_tmp, portage._bin_path, portage._pym_path):
		os.chmod(dir_path, 0o755)

def _handle_self_update(settings, vardb):
	cpv = settings.mycpv
	if settings["ROOT"] == "/" and \
		portage.dep.match_from_list(
		portage.const.PORTAGE_PACKAGE_ATOM, [cpv]):
		_prepare_self_update(settings)
		return True
	return False
