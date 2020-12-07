# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import shutil
import tempfile
import logging
from portage.util         import writemsg_level
from portage.localization import _

fallback = False

try:
	from portage.util.file_copy.reflink_linux import file_copy as _file_copy
except ImportError:
	_file_copy = None
	fallback   = True

def _optimized_copyfile(src, dst):
	"""
	Copy the contents (no metadata) of the file named src to a file
	named dst.

	If possible, copying is done within the kernel, and uses
	"copy acceleration" techniques (such as reflinks). This also
	supports sparse files.

	@param src: path of source file
	@type src: str
	@param dst: path of destination file
	@type dst: str
	"""
	global fallback
	if fallback:
		shutil.copyfile(src, dst)
		return

	try:
		with open(src, 'rb', buffering=0) as src_file, \
				open(dst, 'wb', buffering=0) as dst_file:
					_file_copy(src_file.fileno(), dst_file.fileno())
	except OSError as e:
		if e.args[0] != 22: raise
		# Got an 'Invalid argument', this means the user's
		# kernel does not support this API, fallback to regular
		# method of copying.
		writemsg_level(_("!!! WARNING: _optimized_copyfile returned " \
			"'Invalid argument' (errno=22), using fallback, " \
			"incompatible kernel?") + "    ",
			noiselevel=2, level=logging.WARNING)
		fallback = True
		shutil.copyfile(src, dst)

if fallback:
	copyfile = shutil.copyfile
else:
	copyfile = _optimized_copyfile
