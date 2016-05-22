# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ['install_mask_dir', 'InstallMask']

import errno
import fnmatch
import sys

from portage import os, _unicode_decode
from portage.exception import (
	OperationNotPermitted, PermissionDenied, FileNotFound)
from portage.util import normalize_path

if sys.hexversion >= 0x3000000:
	_unicode = str
else:
	_unicode = unicode


class InstallMask(object):
	def __init__(self, install_mask):
		"""
		@param install_mask: INSTALL_MASK value
		@type install_mask: str
		"""
		self._install_mask = install_mask.split()

	def match(self, path):
		"""
		@param path: file path relative to ${ED}
		@type path: str
		@rtype: bool
		@return: True if path matches INSTALL_MASK, False otherwise
		"""
		ret = False
		for pattern in self._install_mask:
			# if pattern starts with -, possibly exclude this path
			is_inclusive = not pattern.startswith('-')
			if not is_inclusive:
				pattern = pattern[1:]
			# absolute path pattern
			if pattern.startswith('/'):
				# match either exact path or one of parent dirs
				# the latter is done via matching pattern/*
				if (fnmatch.fnmatch(path, pattern[1:])
						or fnmatch.fnmatch(path, pattern[1:] + '/*')):
					ret = is_inclusive
			# filename
			else:
				if fnmatch.fnmatch(os.path.basename(path), pattern):
					ret = is_inclusive
		return ret


_exc_map = {
	errno.ENOENT: FileNotFound,
	errno.EPERM: OperationNotPermitted,
	errno.EACCES: PermissionDenied,
}


def _raise_exc(e):
	"""
	Wrap OSError with portage.exception wrapper exceptions, with
	__cause__ chaining when python supports it.

	@param e: os exception
	@type e: OSError
	@raise PortageException: portage.exception wrapper exception
	"""
	wrapper_cls = _exc_map.get(e.errno)
	if wrapper_cls is None:
		raise
	wrapper = wrapper_cls(_unicode(e))
	wrapper.__cause__ = e
	raise wrapper


def install_mask_dir(base_dir, install_mask, onerror=None):
	"""
	Remove files and directories matched by INSTALL_MASK.

	@param base_dir: directory path corresponding to ${ED}
	@type base_dir: str
	@param install_mask: INSTALL_MASK configuration
	@type install_mask: InstallMask
	"""
	onerror = onerror or _raise_exc
	base_dir = normalize_path(base_dir)
	base_dir_len = len(base_dir) + 1
	dir_stack = []

	# Remove masked files.
	for parent, dirs, files in os.walk(base_dir, onerror=onerror):
		try:
			parent = _unicode_decode(parent, errors='strict')
		except UnicodeDecodeError:
			continue
		dir_stack.append(parent)
		for fname in files:
			try:
				fname = _unicode_decode(fname, errors='strict')
			except UnicodeDecodeError:
				continue
			abs_path = os.path.join(parent, fname)
			relative_path = abs_path[base_dir_len:]
			if install_mask.match(relative_path):
				try:
					os.unlink(abs_path)
				except OSError as e:
					onerror(e)

	# Remove masked dirs (unless non-empty due to exclusions).
	while True:
		try:
			dir_path = dir_stack.pop()
		except IndexError:
			break

		if install_mask.match(dir_path[base_dir_len:]):
			try:
				os.rmdir(dir_path)
			except OSError:
				pass
