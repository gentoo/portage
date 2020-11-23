# Copyright 2019-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["compare_files"]

import io
import os
import stat

from portage import _encodings
from portage import _unicode_encode
from portage.util._xattr import XATTRS_WORKS, xattr

def compare_files(file1, file2, skipped_types=()):
	"""
	Compare metadata and contents of two files.

	@param file1: File 1
	@type file1: str
	@param file2: File 2
	@type file2: str
	@param skipped_types: Tuple of strings specifying types of properties excluded from comparison.
		Supported strings: type, mode, owner, group, device_number, xattr, atime, mtime, ctime, size, content
	@type skipped_types: tuple of str
	@rtype: tuple of str
	@return: Tuple of strings specifying types of properties different between compared files
	"""

	file1_stat = os.lstat(_unicode_encode(file1, encoding=_encodings["fs"], errors="strict"))
	file2_stat = os.lstat(_unicode_encode(file2, encoding=_encodings["fs"], errors="strict"))

	differences = []

	if (file1_stat.st_dev, file1_stat.st_ino) == (file2_stat.st_dev, file2_stat.st_ino):
		return ()

	if "type" not in skipped_types and stat.S_IFMT(file1_stat.st_mode) != stat.S_IFMT(file2_stat.st_mode):
		differences.append("type")
	if "mode" not in skipped_types and stat.S_IMODE(file1_stat.st_mode) != stat.S_IMODE(file2_stat.st_mode):
		differences.append("mode")
	if "owner" not in skipped_types and file1_stat.st_uid != file2_stat.st_uid:
		differences.append("owner")
	if "group" not in skipped_types and file1_stat.st_gid != file2_stat.st_gid:
		differences.append("group")
	if "device_number" not in skipped_types and file1_stat.st_rdev != file2_stat.st_rdev:
		differences.append("device_number")

	if (XATTRS_WORKS and "xattr" not in skipped_types and
		sorted(xattr.get_all(file1, nofollow=True)) != sorted(xattr.get_all(file2, nofollow=True))):
		differences.append("xattr")

	if "atime" not in skipped_types and file1_stat.st_atime_ns != file2_stat.st_atime_ns:
		differences.append("atime")
	if "mtime" not in skipped_types and file1_stat.st_mtime_ns != file2_stat.st_mtime_ns:
		differences.append("mtime")
	if "ctime" not in skipped_types and file1_stat.st_ctime_ns != file2_stat.st_ctime_ns:
		differences.append("ctime")

	if "type" in differences:
		pass
	elif file1_stat.st_size != file2_stat.st_size:
		if "size" not in skipped_types:
			differences.append("size")
		if "content" not in skipped_types:
			differences.append("content")
	else:
		if "content" not in skipped_types:
			if stat.S_ISLNK(file1_stat.st_mode):
				file1_stream = io.BytesIO(os.readlink(_unicode_encode(file1,
									encoding=_encodings["fs"],
									errors="strict")))
			else:
				file1_stream = open(_unicode_encode(file1,
							encoding=_encodings["fs"],
							errors="strict"), "rb")
			if stat.S_ISLNK(file2_stat.st_mode):
				file2_stream = io.BytesIO(os.readlink(_unicode_encode(file2,
									encoding=_encodings["fs"],
									errors="strict")))
			else:
				file2_stream = open(_unicode_encode(file2,
							encoding=_encodings["fs"],
							errors="strict"), "rb")
			while True:
				file1_content = file1_stream.read(4096)
				file2_content = file2_stream.read(4096)
				if file1_content != file2_content:
					differences.append("content")
					break
				if not file1_content or not file2_content:
					break
			file1_stream.close()
			file2_stream.close()

	return tuple(differences)
