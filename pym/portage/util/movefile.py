# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['movefile']

import errno
import os as _os
import shutil as _shutil
import stat
import sys
import subprocess
import textwrap

import portage
from portage import bsd_chflags, _encodings, _os_overrides, _selinux, \
	_unicode_decode, _unicode_encode, _unicode_func_wrapper,\
	_unicode_module_wrapper
from portage.const import MOVE_BINARY
from portage.exception import OperationNotSupported
from portage.localization import _
from portage.process import spawn
from portage.util import writemsg

def _apply_stat(src_stat, dest):
	_os.chown(dest, src_stat.st_uid, src_stat.st_gid)
	_os.chmod(dest, stat.S_IMODE(src_stat.st_mode))

if hasattr(_os, "getxattr"):
	# Python >=3.3 and GNU/Linux
	def _copyxattr(src, dest):
		for attr in _os.listxattr(src):
			try:
				_os.setxattr(dest, attr, _os.getxattr(src, attr))
				raise_exception = False
			except OSError:
				raise_exception = True
			if raise_exception:
				raise OperationNotSupported("Filesystem containing file '%s' does not support extended attributes" % dest)
else:
	try:
		import xattr
	except ImportError:
		xattr = None
	if xattr is not None:
		def _copyxattr(src, dest):
			for attr in xattr.list(src):
				try:
					xattr.set(dest, attr, xattr.get(src, attr))
					raise_exception = False
				except IOError:
					raise_exception = True
				if raise_exception:
					raise OperationNotSupported("Filesystem containing file '%s' does not support extended attributes" % dest)
	else:
		_devnull = open("/dev/null", "wb")
		try:
			subprocess.call(["getfattr", "--version"], stdout=_devnull)
			subprocess.call(["setfattr", "--version"], stdout=_devnull)
			_has_getfattr_and_setfattr = True
		except OSError:
			_has_getfattr_and_setfattr = False
		_devnull.close()
		if _has_getfattr_and_setfattr:
			def _copyxattr(src, dest):
				getfattr_process = subprocess.Popen(["getfattr", "-d", "--absolute-names", src], stdout=subprocess.PIPE)
				getfattr_process.wait()
				extended_attributes = getfattr_process.stdout.readlines()
				getfattr_process.stdout.close()
				if extended_attributes:
					extended_attributes[0] = b"# file: " + _unicode_encode(dest) + b"\n"
					setfattr_process = subprocess.Popen(["setfattr", "--restore=-"], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
					setfattr_process.communicate(input=b"".join(extended_attributes))
					if setfattr_process.returncode != 0:
						raise OperationNotSupported("Filesystem containing file '%s' does not support extended attributes" % dest)
		else:
			def _copyxattr(src, dest):
				pass

def movefile(src, dest, newmtime=None, sstat=None, mysettings=None,
		hardlink_candidates=None, encoding=_encodings['fs']):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns mtime as integer on success
	and None on failure.  mtime is expressed in seconds in Python <3.3 and nanoseconds in
	Python >=3.3.  Move is atomic."""

	if mysettings is None:
		mysettings = portage.settings

	src_bytes = _unicode_encode(src, encoding=encoding, errors='strict')
	dest_bytes = _unicode_encode(dest, encoding=encoding, errors='strict')
	xattr_enabled = "xattr" in mysettings.features
	selinux_enabled = mysettings.selinux_enabled()
	if selinux_enabled:
		selinux = _unicode_module_wrapper(_selinux, encoding=encoding)
		_copyfile = selinux.copyfile
		_rename = selinux.rename
	else:
		_copyfile = _shutil.copyfile
		_rename = _os.rename

	lchown = _unicode_func_wrapper(portage.data.lchown, encoding=encoding)
	os = _unicode_module_wrapper(_os,
		encoding=encoding, overrides=_os_overrides)

	try:
		if not sstat:
			sstat=os.lstat(src)

	except SystemExit as e:
		raise
	except Exception as e:
		writemsg("!!! %s\n" % _("Stating source file failed... movefile()"),
			noiselevel=-1)
		writemsg(_unicode_decode("!!! %s\n") % (e,), noiselevel=-1)
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
			if mysettings and "D" in mysettings and \
				target.startswith(mysettings["D"]):
				target = target[len(mysettings["D"])-1:]
			if destexists and not stat.S_ISDIR(dstat[stat.ST_MODE]):
				os.unlink(dest)
			try:
				if selinux_enabled:
					selinux.symlink(target, dest, src)
				else:
					os.symlink(target, dest)
			except OSError as e:
				# Some programs will create symlinks automatically, so we have
				# to tolerate these links being recreated during the merge
				# process. In any case, if the link is pointing at the right
				# place, we're in good shape.
				if e.errno not in (errno.ENOENT, errno.EEXIST) or \
					target != os.readlink(dest):
					raise
			lchown(dest,sstat[stat.ST_UID],sstat[stat.ST_GID])
			# utime() only works on the target of a symlink, so it's not
			# possible to perserve mtime on symlinks.
			return os.lstat(dest)[stat.ST_MTIME]
		except SystemExit as e:
			raise
		except Exception as e:
			writemsg("!!! %s\n" % _("failed to properly create symlink:"),
				noiselevel=-1)
			writemsg("!!! %s -> %s\n" % (dest, target), noiselevel=-1)
			writemsg(_unicode_decode("!!! %s\n") % (e,), noiselevel=-1)
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
				selinux.rename(src, dest)
			else:
				os.rename(src,dest)
			renamefailed=0
		except OSError as e:
			if e.errno != errno.EXDEV:
				# Some random error.
				writemsg("!!! %s\n" % _("Failed to move %(src)s to %(dest)s") %
					{"src": src, "dest": dest}, noiselevel=-1)
				writemsg(_unicode_decode("!!! %s\n") % (e,), noiselevel=-1)
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		if stat.S_ISREG(sstat[stat.ST_MODE]):
			dest_tmp = dest + "#new"
			dest_tmp_bytes = _unicode_encode(dest_tmp, encoding=encoding,
				errors='strict')
			try: # For safety copy then move it over.
				_copyfile(src_bytes, dest_tmp_bytes)
				if xattr_enabled:
					try:
						_copyxattr(src_bytes, dest_tmp_bytes)
					except SystemExit:
						raise
					except:
						msg = _("Failed to copy extended attributes. "
							"In order to avoid this error, set "
							"FEATURES=\"-xattr\" in make.conf.")
						msg = textwrap.wrap(msg, 65)
						for line in msg:
							writemsg("!!! %s\n" % (line,), noiselevel=-1)
						raise
				_apply_stat(sstat, dest_tmp_bytes)
				_rename(dest_tmp_bytes, dest_bytes)
				_os.unlink(src_bytes)
			except SystemExit as e:
				raise
			except Exception as e:
				writemsg("!!! %s\n" % _('copy %(src)s -> %(dest)s failed.') %
					{"src": src, "dest": dest}, noiselevel=-1)
				writemsg(_unicode_decode("!!! %s\n") % (e,), noiselevel=-1)
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			a = spawn([MOVE_BINARY, '-f', src, dest], env=os.environ)
			if a != os.EX_OK:
				writemsg(_("!!! Failed to move special file:\n"), noiselevel=-1)
				writemsg(_("!!! '%(src)s' to '%(dest)s'\n") % \
					{"src": _unicode_decode(src, encoding=encoding),
					"dest": _unicode_decode(dest, encoding=encoding)}, noiselevel=-1)
				writemsg("!!! %s\n" % a, noiselevel=-1)
				return None # failure

	# In Python <3.3 always use stat_obj[stat.ST_MTIME] for the integral timestamp
	# which is returned, since the stat_obj.st_mtime float attribute rounds *up*
	# if the nanosecond part of the timestamp is 999999881 ns or greater.
	try:
		if hardlinked:
			if sys.hexversion >= 0x3030000:
				newmtime = os.stat(dest).st_mtime_ns
			else:
				newmtime = os.stat(dest)[stat.ST_MTIME]
		else:
			# Note: It is not possible to preserve nanosecond precision
			# (supported in POSIX.1-2008 via utimensat) with the IEEE 754
			# double precision float which only has a 53 bit significand.
			if newmtime is not None:
				if sys.hexversion >= 0x3030000:
					os.utime(dest, ns=(newmtime, newmtime))
				else:
					os.utime(dest, (newmtime, newmtime))
			else:
				if sys.hexversion >= 0x3030000:
					newmtime = sstat.st_mtime_ns
				else:
					newmtime = sstat[stat.ST_MTIME]
				if renamefailed:
					if sys.hexversion >= 0x3030000:
						# If rename succeeded then timestamps are automatically
						# preserved with complete precision because the source
						# and destination inodes are the same. Otherwise, manually
						# update timestamps with nanosecond precision.
						os.utime(dest, ns=(newmtime, newmtime))
					else:
						# If rename succeeded then timestamps are automatically
						# preserved with complete precision because the source
						# and destination inodes are the same. Otherwise, round
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
			if sys.hexversion >= 0x3030000:
				newmtime = os.stat(dest).st_mtime_ns
			else:
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
