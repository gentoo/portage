# Copyright 2014-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
from typing import Iterator
from itertools import chain

from pathlib import Path

def first_existing(path):
	"""
	Returns the first existing path element, traversing from the given
	path to the root directory. A path is considered to exist if lstat
	either succeeds or raises an error other than ENOENT or ESTALE.

	This can be particularly useful to check if there is permission to
	create a particular file or directory, without actually creating
	anything.

	@param path: a filesystem path
	@type path: str
	@rtype: str
	@return: the element that exists
	"""
	for path in chain([path], path.parents):
		if path.exists():
			return path
	# Shouldn't ever get here
	raise Exception("Broke")

def iter_parents(path: Path) -> Iterator[Path]:
	"""
	@param path: a filesystem path
	@type path: str
	@rtype: iterator
	@return: an iterator which yields path and all parents of path,
		ending with the root directory
	"""
	return iter(path.parents)


def unparent(path: Path, level: int = 0) -> Path:
	return path.relative_to(path.parents[level])
