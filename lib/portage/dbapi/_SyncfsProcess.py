# Copyright 2012-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

from portage import os
from portage.util._ctypes import load_libc
from portage.util._async.ForkProcess import ForkProcess


class SyncfsProcess(ForkProcess):
    """
    Isolate ctypes usage in a subprocess, in order to avoid
    potential problems with stale cached libraries as
    described in bug #448858, comment #14 (also see
    https://bugs.python.org/issue14597).
    """

    __slots__ = ("paths",)

    def _start(self):
        self.target = functools.partial(self._target, self._get_syncfs, self.paths)
        super()._start()

    @staticmethod
    def _get_syncfs():
        (libc, _) = load_libc()
        if libc is not None:
            return getattr(libc, "syncfs", None)
        return None

    @staticmethod
    def _target(get_syncfs, paths):
        syncfs_failed = False
        syncfs = get_syncfs()

        if syncfs is not None:
            for path in paths:
                try:
                    fd = os.open(path, os.O_RDONLY)
                except OSError:
                    pass
                else:
                    try:
                        if syncfs(fd) != 0:
                            # Happens with PyPy (bug #446610)
                            syncfs_failed = True
                    finally:
                        os.close(fd)

        if syncfs is None or syncfs_failed:
            return 1
        return os.EX_OK
