# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
import selinux
import shutil
from selinux import is_selinux_enabled, getfilecon, lgetfilecon

def copyfile(src, dest):
	if isinstance(src, unicode):
		src = src.encode('utf_8', 'replace')
	if isinstance(dest, unicode):
		dest = dest.encode('utf_8', 'replace')
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
	if isinstance(target, unicode):
		target = target.encode('utf_8', 'replace')
	if isinstance(refdir, unicode):
		refdir = refdir.encode('utf_8', 'replace')
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
	if isinstance(src, unicode):
		src = src.encode('utf_8', 'replace')
	if isinstance(dest, unicode):
		dest = dest.encode('utf_8', 'replace')
	(rc, ctx) = selinux.lgetfilecon(src)
	if rc < 0:
		raise OSError("rename: Failed getting context of \"%s\"." % src)

	setfscreate(ctx)
	try:
		os.rename(src,dest)
	finally:
		setfscreate()

def setexec(ctx="\n"):
	if selinux.setexeccon(ctx) < 0:
		raise OSError("setexec: Failed setting exec() context \"%s\"." % ctx)

def setfscreate(ctx="\n"):
	if selinux.setfscreatecon(ctx) < 0:
		raise OSError(
			"setfscreate: Failed setting fs create context \"%s\"." % ctx)

def spawn(selinux_type, spawn_func, mycommand, opt_name=None, **keywords):
	con = getcontext().split(":")
	con[2] = selinux_type
	setexec(":".join(con))
	try:
		return spawn_func(mycommand, opt_name=opt_name, **keywords)
	finally:
		setexec()

def symlink(target, link, reflnk):
	if isinstance(target, unicode):
		target = target.encode('utf_8', 'replace')
	if isinstance(link, unicode):
		link = link.encode('utf_8', 'replace')
	if isinstance(reflnk, unicode):
		reflnk = reflnk.encode('utf_8', 'replace')
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
