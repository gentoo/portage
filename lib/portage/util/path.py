# Copyright 2014-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import platform

from functools import lru_cache
from typing import Optional
from portage import os


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
    existing = False
    for path in iter_parents(path):
        try:
            os.lstat(path)
            existing = True
        except OSError as e:
            if e.errno not in (errno.ENOENT, errno.ESTALE):
                existing = True

        if existing:
            return path

    return os.sep


def iter_parents(path):
    """
    @param path: a filesystem path
    @type path: str
    @rtype: iterator
    @return: an iterator which yields path and all parents of path,
            ending with the root directory
    """
    yield path
    while path != os.sep:
        path = os.path.dirname(path)
        if not path:
            break
        yield path


@lru_cache(32)
def get_fs_type_cached(path: str) -> Optional[str]:
    return get_fs_type(path)


def get_fs_type(path: str) -> Optional[str]:
    if platform.system() == "Linux":
        return get_fs_type_linux(path)

    return None


def get_fs_type_linux(path: str) -> Optional[str]:
    real_path = os.path.realpath(path)
    best_match_len = -1
    fs_type = None

    with open("/proc/mounts", "r") as f:
        for line in f:
            parts = line.split()
            mount_point = parts[1]

            if not real_path.startswith(mount_point):
                continue

            mount_point_len = len(mount_point)
            if mount_point_len > best_match_len:
                best_match_len = mount_point_len
                fs_type = parts[2]

    return fs_type
