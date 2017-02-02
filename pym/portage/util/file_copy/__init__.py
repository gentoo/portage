# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import shutil
import tempfile

try:
	from portage.util.file_copy.reflink_linux import file_copy as _file_copy
except ImportError:
	_file_copy = None


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
	with open(src, 'rb', buffering=0) as src_file, \
		open(dst, 'wb', buffering=0) as dst_file:
		_file_copy(src_file.fileno(), dst_file.fileno())


if _file_copy is None:
	copyfile = shutil.copyfile
else:
	copyfile = _optimized_copyfile
