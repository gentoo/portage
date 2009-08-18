# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# Don't use the unicode-wrapped os and shutil modules here since
# the whole _selinux module itself will be wrapped.
import os
import shutil

from portage import _content_encoding
from portage import _fs_encoding
from portage import _unicode_encode
from portage.localization import _

import selinux
from selinux import is_selinux_enabled

def copyfile(src, dest):
	src = _unicode_encode(src, encoding=_fs_encoding, errors='strict')
	dest = _unicode_encode(dest, encoding=_fs_encoding, errors='strict')
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

def mkdir(target, refdir):
	target = _unicode_encode(target, encoding=_fs_encoding, errors='strict')
	refdir = _unicode_encode(refdir, encoding=_fs_encoding, errors='strict')
	(rc, ctx) = selinux.getfilecon(refdir)
	if rc < 0:
		raise OSError(
			_("mkdir: Failed getting context of reference directory \"%s\".") \
			% refdir)

	selinux.setfscreatecon(ctx)
	try:
		os.mkdir(target)
	finally:
		selinux.setfscreatecon()

def rename(src, dest):
	src = _unicode_encode(src, encoding=_fs_encoding, errors='strict')
	dest = _unicode_encode(dest, encoding=_fs_encoding, errors='strict')
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError(_("rename: Failed getting context of \"%s\".") % src)

	setfscreate(ctx)
	try:
		os.rename(src,dest)
	finally:
		setfscreate()

def settype(newtype):
	ret = getcontext().split(":")
	ret[2] = newtype
	return ":".join(ret)

def setexec(ctx="\n"):
	ctx = _unicode_encode(ctx, encoding=_content_encoding, errors='strict')
	if selinux.setexeccon(ctx) < 0:
		raise OSError(_("setexec: Failed setting exec() context \"%s\".") % ctx)

def setfscreate(ctx="\n"):
	ctx = _unicode_encode(ctx,
		encoding=_content_encoding, errors='strict')
	if selinux.setfscreatecon(ctx) < 0:
		raise OSError(
			_("setfscreate: Failed setting fs create context \"%s\".") % ctx)

def spawn_wrapper(spawn_func, selinux_type):

	selinux_type = _unicode_encode(selinux_type,
		encoding=_content_encoding, errors='strict')

	def wrapper_func(*args, **kwargs):
		con = settype(selinux_type)
		setexec(con)
		try:
			return spawn_func(*args, **kwargs)
		finally:
			setexec()

	return wrapper_func

def symlink(target, link, reflnk):
	target = _unicode_encode(target, encoding=_fs_encoding, errors='strict')
	link = _unicode_encode(link, encoding=_fs_encoding, errors='strict')
	reflnk = _unicode_encode(reflnk, encoding=_fs_encoding, errors='strict')
	(rc, ctx) = selinux.lgetfilecon(reflnk)
	if rc < 0:
		raise OSError(
			_("symlink: Failed getting context of reference symlink \"%s\".") \
			% reflnk)

	setfscreate(ctx)
	try:
		os.symlink(target, link)
	finally:
		setfscreate()
