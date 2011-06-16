# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['prepare_build_dirs']

import errno
import gzip
import shutil
import stat
import time

from portage import os, _encodings, _unicode_encode, _unicode_decode
from portage.data import portage_gid, portage_uid, secpass
from portage.exception import DirectoryNotFound, FileNotFound, \
	OperationNotPermitted, PermissionDenied, PortageException
from portage.localization import _
from portage.output import colorize
from portage.util import apply_recursive_permissions, \
	apply_secpass_permissions, ensure_dirs, writemsg

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
			ensure_dirs(mydir)
			try:
				apply_secpass_permissions(mydir,
					gid=portage_gid, uid=portage_uid, mode=0o70, mask=0)
			except PortageException:
				if not os.path.isdir(mydir):
					raise
		for dir_key in ("PORTAGE_BUILDDIR", "HOME", "PKG_LOGDIR", "T"):
			"""These directories don't necessarily need to be group writable.
			However, the setup phase is commonly run as a privileged user prior
			to the other phases being run by an unprivileged user.  Currently,
			we use the portage group to ensure that the unprivleged user still
			has write access to these directories in any case."""
			ensure_dirs(mysettings[dir_key], mode=0o775)
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

	if background and log_path is not None:
		try:
			log_file = open(_unicode_encode(log_path,
				encoding=_encodings['fs'], errors='strict'), mode='ab')
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
					raise DirectoryNotFound(path_dir)

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
	try:
		apply_secpass_permissions(mysettings["WORKDIR"],
		uid=portage_uid, gid=portage_gid, mode=workdir_mode)
	except FileNotFound:
		pass # ebuild.sh will create it

	if mysettings.get("PORT_LOGDIR", "") == "":
		while "PORT_LOGDIR" in mysettings:
			del mysettings["PORT_LOGDIR"]
	if "PORT_LOGDIR" in mysettings:
		try:
			modified = ensure_dirs(mysettings["PORT_LOGDIR"])
			if modified:
				apply_secpass_permissions(mysettings["PORT_LOGDIR"],
					uid=portage_uid, gid=portage_gid, mode=0o2770)
		except PortageException as e:
			writemsg("!!! %s\n" % str(e), noiselevel=-1)
			writemsg(_("!!! Permission issues with PORT_LOGDIR='%s'\n") % \
				mysettings["PORT_LOGDIR"], noiselevel=-1)
			writemsg(_("!!! Disabling logging.\n"), noiselevel=-1)
			while "PORT_LOGDIR" in mysettings:
				del mysettings["PORT_LOGDIR"]

	compress_log_ext = ''
	if 'compress-build-logs' in mysettings.features:
		compress_log_ext = '.gz'

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
				mysettings["PORT_LOGDIR"], "build", "%s/%s:%s.log%s" % \
				(mysettings["CATEGORY"], mysettings["PF"], logid_time,
				compress_log_ext))
		else:
			mysettings["PORTAGE_LOG_FILE"] = os.path.join(
				mysettings["PORT_LOGDIR"], "%s:%s:%s.log%s" % \
				(mysettings["CATEGORY"], mysettings["PF"], logid_time,
				compress_log_ext))

		ensure_dirs(os.path.dirname(mysettings["PORTAGE_LOG_FILE"]))

	else:
		# NOTE: When sesandbox is enabled, the local SELinux security policies
		# may not allow output to be piped out of the sesandbox domain. The
		# current policy will allow it to work when a pty is available, but
		# not through a normal pipe. See bug #162404.
		mysettings["PORTAGE_LOG_FILE"] = os.path.join(
			mysettings["T"], "build.log%s" % compress_log_ext)
