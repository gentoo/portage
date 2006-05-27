# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import selinux
from selinux import is_selinux_enabled
from selinux_aux import setexec, secure_symlink, secure_rename, \
	secure_copy, secure_mkdir

def getcontext():
	return selinux.getcon()[1]

def get_sid(filename):
	return selinux.getfilecon(filename)[1]

def get_lsid(filename):
	return selinux.lgetfilecon(filename)[1]
