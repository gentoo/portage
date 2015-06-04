# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import absolute_import

import os as _os

if hasattr(_os, "getxattr"):
	getxattr = _os.getxattr
	listxattr = _os.listxattr
	setxattr = _os.setxattr
else:
	try:
		import xattr as _xattr
	except ImportError:
		pass
	else:
		getxattr = _xattr.get
		listxattr = _xattr.list
		setxattr = _xattr.set
