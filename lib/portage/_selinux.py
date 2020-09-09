# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# Don't use the unicode-wrapped os and shutil modules here since
# the whole _selinux module itself will be wrapped.
import os
import shutil
import warnings

try:
	import selinux
except ImportError:
	selinux = None

import portage
from portage import _encodings
from portage import _native_string, _unicode_encode
from portage.localization import _

def copyfile(src, dest):
	src = _native_string(src, encoding=_encodings['fs'], errors='strict')
	dest = _native_string(dest, encoding=_encodings['fs'], errors='strict')
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError(_("copyfile: Failed getting context of \"%s\".") % src)

	setfscreate(ctx)
	try:
		shutil.copyfile(src, dest)
	finally:
		setfscreate()

def getcontext():
	(rc, ctx) = selinux.getcon()
	if rc < 0:
		raise OSError(_("getcontext: Failed getting current process context."))

	return ctx

def is_selinux_enabled():
	return selinux.is_selinux_enabled()

def mkdir(target, refdir):
	refdir = _native_string(refdir, encoding=_encodings['fs'], errors='strict')
	(rc, ctx) = selinux.getfilecon(refdir)
	if rc < 0:
		raise OSError(
			_("mkdir: Failed getting context of reference directory \"%s\".") \
			% refdir)

	setfscreate(ctx)
	try:
		os.mkdir(_unicode_encode(target, encoding=_encodings['fs'], errors='strict'))
	finally:
		setfscreate()

def rename(src, dest):
	src = _native_string(src, encoding=_encodings['fs'], errors='strict')
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError(_("rename: Failed getting context of \"%s\".") % src)

	setfscreate(ctx)
	try:
		os.rename(
			_unicode_encode(src, encoding=_encodings['fs'], errors='strict'),
			_unicode_encode(dest, encoding=_encodings['fs'], errors='strict'))
	finally:
		setfscreate()

def settype(newtype):
	try:
		ret = getcontext().split(":")
		ret[2] = newtype
		return ":".join(ret)
	except IndexError:
		warnings.warn("Invalid SELinux context: %s" % getcontext())
		return None

def setexec(ctx="\n"):
	ctx = _native_string(ctx, encoding=_encodings['content'], errors='strict')
	rc = 0
	try:
		rc = selinux.setexeccon(ctx)
	except OSError:
		msg = _("Failed to set new SELinux execution context. " + \
			"Is your current SELinux context allowed to run Portage?")
		if selinux.security_getenforce() == 1:
			raise OSError(msg)
		else:
			portage.writemsg("!!! %s\n" % msg, noiselevel=-1)

	if rc < 0:
		if selinux.security_getenforce() == 1:
			raise OSError(_("Failed setting exec() context \"%s\".") % ctx)
		else:
			portage.writemsg("!!! " + \
				_("Failed setting exec() context \"%s\".") % ctx, \
				noiselevel=-1)

def setfscreate(ctx="\n"):
	ctx = _native_string(ctx, encoding=_encodings['content'], errors='strict')
	if selinux.setfscreatecon(ctx) < 0:
		raise OSError(
			_("setfscreate: Failed setting fs create context \"%s\".") % ctx)

class spawn_wrapper:
	"""
	Create a wrapper function for the given spawn function. When the wrapper
	is called, it will adjust the arguments such that setexec() to be called
	*after* the fork (thereby avoiding any interference with concurrent
	threads in the calling process).
	"""
	__slots__ = ("_con", "_spawn_func")

	def __init__(self, spawn_func, selinux_type):
		self._spawn_func = spawn_func
		selinux_type = _native_string(selinux_type, encoding=_encodings['content'], errors='strict')
		self._con = settype(selinux_type)

	def __call__(self, *args, **kwargs):
		if self._con is not None:
			pre_exec = kwargs.get("pre_exec")

			def _pre_exec():
				if pre_exec is not None:
					pre_exec()
				setexec(self._con)

			kwargs["pre_exec"] = _pre_exec

		return self._spawn_func(*args, **kwargs)

def symlink(target, link, reflnk):
	reflnk = _native_string(reflnk, encoding=_encodings['fs'], errors='strict')
	(rc, ctx) = selinux.lgetfilecon(reflnk)
	if rc < 0:
		raise OSError(
			_("symlink: Failed getting context of reference symlink \"%s\".") \
			% reflnk)

	setfscreate(ctx)
	try:
		os.symlink(
			_unicode_encode(target, encoding=_encodings['fs'], errors='strict'),
			_unicode_encode(link, encoding=_encodings['fs'], errors='strict'))
	finally:
		setfscreate()
