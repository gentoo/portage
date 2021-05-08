# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import stat
from pathlib import Path

from portage import os
from portage.exception import PermissionDenied

def exists_raise_eaccess(path: Path):
	try:
		path.stat()
	except OSError as e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied("stat('%s')" % path)
		return False
	else:
		return True

def isdir_raise_eaccess(path: Path):
	try:
		st = path.stat()
	except OSError as e:
		if e.errno == PermissionDenied.errno:
			raise PermissionDenied("stat('%s')" % path)
		return False
	else:
		return stat.S_ISDIR(st.st_mode)
