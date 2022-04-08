# Copyright 2014-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno

from portage import os_unicode_fs


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
            os_unicode_fs.lstat(path)
            existing = True
        except OSError as e:
            if e.errno not in (errno.ENOENT, errno.ESTALE):
                existing = True

        if existing:
            return path

    return os_unicode_fs.sep


def iter_parents(path):
    """
    @param path: a filesystem path
    @type path: str
    @rtype: iterator
    @return: an iterator which yields path and all parents of path,
            ending with the root directory
    """
    yield path
    while path != os_unicode_fs.sep:
        path = os_unicode_fs.path.dirname(path)
        if not path:
            break
        yield path
