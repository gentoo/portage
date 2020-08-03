# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['prepare_build_dirs']

import errno
import gzip
import stat
import time

import portage
from portage import os, shutil, _encodings, _unicode_encode, _unicode_decode
from portage.data import portage_gid, portage_uid, secpass
from portage.exception import DirectoryNotFound, FileNotFound, \
	OperationNotPermitted, PermissionDenied, PortageException
from portage.localization import _
from portage.output import colorize
from portage.util import apply_recursive_permissions, \
	apply_secpass_permissions, ensure_dirs, normalize_path, writemsg
from portage.util.install_mask import _raise_exc

def prepare_build_dirs(myroot=None, settings=None, cleanup=False):
	"""
	The myroot parameter is ignored.
	"""
	myroot = None

	if settings is None:
		raise TypeError("settings argument is required")

	mysettings = settings
	clean_dirs = [mysettings["HOME"]]

	# We enable cleanup when we want to make sure old cruft (such as the old
	# environment) doesn't interfere with the current phase.
	if cleanup and 'keeptemp' not in mysettings.features:
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
				# Wrap with PermissionDenied if appropriate, so that callers
				# display a short error message without a traceback.
				_raise_exc(oe)

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
			ensure_dirs(mydir)
			try:
				apply_secpass_permissions(mydir,
					gid=portage_gid, uid=portage_uid, mode=0o700, mask=0)
			except PortageException:
				if not os.path.isdir(mydir):
					raise
		for dir_key in ("HOME", "PKG_LOGDIR", "T"):
			ensure_dirs(mysettings[dir_key], mode=0o755)
			apply_secpass_permissions(mysettings[dir_key],
				uid=portage_uid, gid=portage_gid)
	except PermissionDenied as e:
		writemsg(_("Permission Denied: %s\n") % str(e), noiselevel=-1)
		return 1
	except OperationNotPermitted as e:
		writemsg(_("Operation Not Permitted: %s\n") % str(e), noiselevel=-1)
		return 1
	except FileNotFound as e:
		writemsg(_("File Not Found: '%s'\n") % str(e), noiselevel=-1)
		return 1

	# Reset state for things like noauto and keepwork in FEATURES.
	for x in ('.die_hooks',):
		try:
			os.unlink(os.path.join(mysettings['PORTAGE_BUILDDIR'], x))
		except OSError:
			pass

	_prepare_workdir(mysettings)
	if mysettings.get("EBUILD_PHASE") not in ("info", "fetch", "pretend"):
		# Avoid spurious permissions adjustments when fetching with
		# a temporary PORTAGE_TMPDIR setting (for fetchonly).
		_prepare_features_dirs(mysettings)

def _adjust_perms_msg(settings, msg):

	def write(msg):
		writemsg(msg, noiselevel=-1)

	background = settings.get("PORTAGE_BACKGROUND") == "1"
	log_path = settings.get("PORTAGE_LOG_FILE")
	log_file = None
	log_file_real = None

	if background and log_path is not None:
		try:
			log_file = open(_unicode_encode(log_path,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
			log_file_real = log_file
		except IOError:
			def write(msg):
				pass
		else:
			if log_path.endswith('.gz'):
				log_file =  gzip.GzipFile(filename='',
					mode='ab', fileobj=log_file)
			def write(msg):
				log_file.write(_unicode_encode(msg))
				log_file.flush()

	try:
		write(msg)
	finally:
		if log_file is not None:
			log_file.close()
			if log_file_real is not log_file:
				log_file_real.close()

def _prepare_features_dirs(mysettings):

	# Use default ABI libdir in accordance with bug #355283.
	libdir = None
	default_abi = mysettings.get("DEFAULT_ABI")
	if default_abi:
		libdir = mysettings.get("LIBDIR_" + default_abi)
	if not libdir:
		libdir = "lib"

	features_dirs = {
		"ccache":{
			"basedir_var":"CCACHE_DIR",
			"default_dir":os.path.join(mysettings["PORTAGE_TMPDIR"], "ccache"),
			"always_recurse":False},
		"distcc":{
			"basedir_var":"DISTCC_DIR",
			"default_dir":os.path.join(mysettings["BUILD_PREFIX"], ".distcc"),
			"subdirs":("lock", "state"),
			"always_recurse":True}
	}
	dirmode  = 0o2070
	filemode =   0o60
	modemask =    0o2
	restrict = mysettings.get("PORTAGE_RESTRICT","").split()
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
				mydirs = [mysettings[kwargs["basedir_var"]]]
				if "subdirs" in kwargs:
					for subdir in kwargs["subdirs"]:
						mydirs.append(os.path.join(basedir, subdir))
				for mydir in mydirs:
					modified = ensure_dirs(mydir)
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
							raise OperationNotPermitted(
								_("Failed to apply recursive permissions for the portage group."))

			except DirectoryNotFound as e:
				failure = True
				writemsg(_("\n!!! Directory does not exist: '%s'\n") % \
					(e,), noiselevel=-1)
				writemsg(_("!!! Disabled FEATURES='%s'\n") % myfeature,
					noiselevel=-1)

			except PortageException as e:
				failure = True
				writemsg("\n!!! %s\n" % str(e), noiselevel=-1)
				writemsg(_("!!! Failed resetting perms on %s='%s'\n") % \
					(kwargs["basedir_var"], basedir), noiselevel=-1)
				writemsg(_("!!! Disabled FEATURES='%s'\n") % myfeature,
					noiselevel=-1)

			if failure:
				mysettings.features.remove(myfeature)
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

	permissions = {'mode': workdir_mode}
	if portage.data.secpass >= 2:
		permissions['uid'] = portage_uid
	if portage.data.secpass >= 1:
		permissions['gid'] = portage_gid

	# Apply PORTAGE_WORKDIR_MODE to PORTAGE_BUILDDIR, since the child
	# directory ${D} and its children may have vulnerable permissions
	# as reported in bug 692492.
	ensure_dirs(mysettings["PORTAGE_BUILDDIR"], **permissions)
	ensure_dirs(mysettings["WORKDIR"], **permissions)

	if mysettings.get("PORTAGE_LOGDIR", "") == "":
		while "PORTAGE_LOGDIR" in mysettings:
			del mysettings["PORTAGE_LOGDIR"]
	if "PORTAGE_LOGDIR" in mysettings:
		try:
			modified = ensure_dirs(mysettings["PORTAGE_LOGDIR"])
			if modified:
				# Only initialize group/mode if the directory doesn't
				# exist, so that we don't override permissions if they
				# were previously set by the administrator.
				# NOTE: These permissions should be compatible with our
				# default logrotate config as discussed in bug 374287.
				apply_secpass_permissions(mysettings["PORTAGE_LOGDIR"],
					uid=portage_uid, gid=portage_gid, mode=0o2770)
		except PortageException as e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg(_("!!! Permission issues with PORTAGE_LOGDIR='%s'\n") % \
				mysettings["PORTAGE_LOGDIR"], noiselevel=-1)
			writemsg(_("!!! Disabling logging.\n"), noiselevel=-1)
			while "PORTAGE_LOGDIR" in mysettings:
				del mysettings["PORTAGE_LOGDIR"]

	compress_log_ext = ''
	if 'compress-build-logs' in mysettings.features:
		compress_log_ext = '.gz'

	logdir_subdir_ok = False
	if "PORTAGE_LOGDIR" in mysettings and \
		os.access(mysettings["PORTAGE_LOGDIR"], os.W_OK):
		logdir = normalize_path(mysettings["PORTAGE_LOGDIR"])
		logid_path = os.path.join(mysettings["PORTAGE_BUILDDIR"], ".logid")
		if not os.path.exists(logid_path):
			open(_unicode_encode(logid_path), 'w').close()
		logid_time = _unicode_decode(time.strftime("%Y%m%d-%H%M%S",
			time.gmtime(os.stat(logid_path).st_mtime)),
			encoding=_encodings['content'], errors='replace')

		if "split-log" in mysettings.features:
			log_subdir = os.path.join(logdir, "build", mysettings["CATEGORY"])
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				log_subdir, "%s:%s.log%s" %
				(mysettings["PF"], logid_time, compress_log_ext))
		else:
			log_subdir = logdir
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				logdir, "%s:%s:%s.log%s" % \
				(mysettings["CATEGORY"], mysettings["PF"], logid_time,
				compress_log_ext))

		if log_subdir is logdir:
			logdir_subdir_ok = True
		else:
			try:
				_ensure_log_subdirs(logdir, log_subdir)
			except PortageException as e:
				writemsg("!!! %s\n" % (e,), noiselevel=-1)

			if os.access(log_subdir, os.W_OK):
				logdir_subdir_ok = True
			else:
				writemsg("!!! %s: %s\n" %
					(_("Permission Denied"), log_subdir), noiselevel=-1)

	tmpdir_log_path = os.path.join(
		mysettings["T"], "build.log%s" % compress_log_ext)
	if not logdir_subdir_ok:
		# NOTE: When sesandbox is enabled, the local SELinux security policies
		# may not allow output to be piped out of the sesandbox domain. The
		# current policy will allow it to work when a pty is available, but
		# not through a normal pipe. See bug #162404.
		mysettings["PORTAGE_LOG_FILE"] = tmpdir_log_path
	else:
		# Create a symlink from tmpdir_log_path to PORTAGE_LOG_FILE, as
		# requested in bug #412865.
		make_new_symlink = False
		try:
			target = os.readlink(tmpdir_log_path)
		except OSError:
			make_new_symlink = True
		else:
			if target != mysettings["PORTAGE_LOG_FILE"]:
				make_new_symlink = True
		if make_new_symlink:
			try:
				os.unlink(tmpdir_log_path)
			except OSError:
				pass
			os.symlink(mysettings["PORTAGE_LOG_FILE"], tmpdir_log_path)

def _ensure_log_subdirs(logdir, subdir):
	"""
	This assumes that logdir exists, and creates subdirectories down
	to subdir as necessary. The gid of logdir is copied to all
	subdirectories, along with 0x2070 mode bits if present. Both logdir
	and subdir are assumed to be normalized absolute paths.
	"""
	st = os.stat(logdir)
	uid = -1
	gid = st.st_gid
	grp_mode = 0o2070 & st.st_mode

	# If logdir is writable by the portage group but its uid
	# is not portage_uid, then set the uid to portage_uid if
	# we have privileges to do so, for compatibility with our
	# default logrotate config (see bug 378451). With the
	# "su portage portage" directive and logrotate-3.8.0,
	# logrotate's chown call during the compression phase will
	# only succeed if the log file's uid is portage_uid.
	if grp_mode and gid == portage_gid and \
		portage.data.secpass >= 2:
		uid = portage_uid
		if st.st_uid != portage_uid:
			ensure_dirs(logdir, uid=uid)

	logdir_split_len = len(logdir.split(os.sep))
	subdir_split = subdir.split(os.sep)[logdir_split_len:]
	subdir_split.reverse()
	current = logdir
	while subdir_split:
		current = os.path.join(current, subdir_split.pop())
		ensure_dirs(current, uid=uid, gid=gid, mode=grp_mode, mask=0)

def _prepare_fake_filesdir(settings):
	real_filesdir = settings["O"]+"/files"
	symlink_path = settings["FILESDIR"]

	try:
		link_target = os.readlink(symlink_path)
	except OSError:
		os.symlink(real_filesdir, symlink_path)
	else:
		if link_target != real_filesdir:
			os.unlink(symlink_path)
			os.symlink(real_filesdir, symlink_path)

def _prepare_fake_distdir(settings, alist):
	orig_distdir = settings["DISTDIR"]
	edpath = os.path.join(settings["PORTAGE_BUILDDIR"], "distdir")
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
