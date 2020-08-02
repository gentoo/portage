# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ['install_mask_dir', 'InstallMask']

import collections
import errno
import fnmatch
import operator

from portage import os, _unicode_decode
from portage.exception import (
	FileNotFound,
	IsADirectory,
	OperationNotPermitted,
	PermissionDenied,
	ReadOnlyFileSystem,
)
from portage.util import normalize_path


def _defaultdict_tree():
	return collections.defaultdict(_defaultdict_tree)


_pattern = collections.namedtuple('_pattern', (
	'orig_index',
	'is_inclusive',
	'pattern',
	'leading_slash',
))


class InstallMask:
	def __init__(self, install_mask):
		"""
		@param install_mask: INSTALL_MASK value
		@type install_mask: str
		"""
		# Patterns not anchored with leading slash
		self._unanchored = []

		# Patterns anchored with leading slash are indexed by leading
		# non-glob components, making it possible to minimize the
		# number of fnmatch calls. For example:
		# /foo*/bar -> {'.': ['/foo*/bar']}
		# /foo/bar* -> {'foo': {'.': ['/foo/bar*']}}
		# /foo/bar/ -> {'foo': {'bar': {'.': ['/foo/bar/']}}}
		self._anchored = _defaultdict_tree()
		for orig_index, pattern in enumerate(install_mask.split()):
			# if pattern starts with -, possibly exclude this path
			is_inclusive = not pattern.startswith('-')
			if not is_inclusive:
				pattern = pattern[1:]
			pattern_obj = _pattern(orig_index, is_inclusive, pattern, pattern.startswith('/'))
			# absolute path pattern
			if pattern_obj.leading_slash:
				current_dir = self._anchored
				for component in list(filter(None, pattern.split('/'))):
					if '*' in component:
						break
					else:
						current_dir = current_dir[component]
				current_dir.setdefault('.', []).append(pattern_obj)

			# filename
			else:
				self._unanchored.append(pattern_obj)

	def _iter_relevant_patterns(self, path):
		"""
		Iterate over patterns that may be relevant for the given path.

		Patterns anchored with leading / are indexed by leading
		non-glob components, making it possible to minimize the
		number of fnmatch calls.
		"""
		current_dir = self._anchored
		components = list(filter(None, path.split('/')))
		patterns = []
		patterns.extend(current_dir.get('.', []))
		for component in components:
			next_dir = current_dir.get(component, None)
			if next_dir is None:
				break
			current_dir = next_dir
			patterns.extend(current_dir.get('.', []))

		if patterns:
			# Sort by original pattern index, since order matters for
			# non-inclusive patterns.
			patterns.extend(self._unanchored)
			if any(not pattern.is_inclusive for pattern in patterns):
				patterns.sort(key=operator.attrgetter('orig_index'))
			return iter(patterns)

		return iter(self._unanchored)

	def match(self, path):
		"""
		@param path: file path relative to ${ED}
		@type path: str
		@rtype: bool
		@return: True if path matches INSTALL_MASK, False otherwise
		"""
		ret = False

		for pattern_obj in self._iter_relevant_patterns(path):
			is_inclusive, pattern = pattern_obj.is_inclusive, pattern_obj.pattern
			# absolute path pattern
			if pattern_obj.leading_slash:
				# handle trailing slash for explicit directory match
				if path.endswith('/'):
					pattern = pattern.rstrip('/') + '/'
				# match either exact path or one of parent dirs
				# the latter is done via matching pattern/*
				if (fnmatch.fnmatch(path, pattern[1:])
						or fnmatch.fnmatch(path, pattern[1:].rstrip('/') + '/*')):
					ret = is_inclusive
			# filename
			else:
				if fnmatch.fnmatch(os.path.basename(path), pattern):
					ret = is_inclusive
		return ret


_exc_map = {
	errno.EISDIR: IsADirectory,
	errno.ENOENT: FileNotFound,
	errno.EPERM: OperationNotPermitted,
	errno.EACCES: PermissionDenied,
	errno.EROFS: ReadOnlyFileSystem,
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
	wrapper = wrapper_cls(str(e))
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

		if install_mask.match(dir_path[base_dir_len:] + '/'):
			try:
				os.rmdir(dir_path)
			except OSError:
				pass
