# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# Don't use the unicode-wrapped os and shutil modules here since
# the whole _selinux module itself will be wrapped.
import os
import shutil

import portage
import selinux
from selinux import is_selinux_enabled, getfilecon, lgetfilecon

def copyfile(src, dest):
	src = portage._unicode_encode(src)
	dest = portage._unicode_encode(dest)
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError("copyfile: Failed getting context of \"%s\"." % src)

	setfscreate(ctx)
	try:
		shutil.copyfile(src, dest)
	finally:
		setfscreate()

def getcontext():
	(rc, ctx) = selinux.getcon()
	if rc < 0:
		raise OSError("getcontext: Failed getting current process context.")

	return ctx

def mkdir(target, refdir):
	target = portage._unicode_encode(target)
	refdir = portage._unicode_encode(refdir)
	(rc, ctx) = selinux.getfilecon(refdir)
	if rc < 0:
		raise OSError(
			"mkdir: Failed getting context of reference directory \"%s\"." \
			% refdir)

	setfscreatecon(ctx)
	try:
		os.mkdir(target)
	finally:
		setfscreatecon()

def rename(src, dest):
	src = portage._unicode_encode(src)
	dest = portage._unicode_encode(dest)
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError("rename: Failed getting context of \"%s\"." % src)

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
	if isinstance(ctx, unicode):
		ctx = ctx.encode('utf_8', 'replace')
	if selinux.setexeccon(ctx) < 0:
		raise OSError("setexec: Failed setting exec() context \"%s\"." % ctx)

def setfscreate(ctx="\n"):
	ctx = portage._unicode_encode(ctx)
	if selinux.setfscreatecon(ctx) < 0:
		raise OSError(
			"setfscreate: Failed setting fs create context \"%s\"." % ctx)

def spawn_wrapper(spawn_func, selinux_type):

	def wrapper_func(*args, **kwargs):
		selinux_type = portage._unicode_encode(selinux_type)
		con = settype(selinux_type)
		setexec(con)
		try:
			return spawn_func(*args, **kwargs)
		finally:
			setexec()

	return wrapper_func

def symlink(target, link, reflnk):
	target = portage._unicode_encode(target)
	link = portage._unicode_encode(link)
	reflnk = portage._unicode_encode(reflnk)
	(rc, ctx) = selinux.lgetfilecon(reflnk)
	if rc < 0:
		raise OSError(
			"symlink: Failed getting context of reference symlink \"%s\"." \
			% reflnk)

	setfscreate(ctx)
	try:
		os.symlink(target, link)
	finally:
		setfscreate()
