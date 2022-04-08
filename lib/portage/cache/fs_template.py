# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

import os as _os
from portage.cache import template
from portage import os_unicode_fs

from portage.proxy.lazyimport import lazyimport

lazyimport(
    globals(),
    "portage.exception:PortageException",
    "portage.util:apply_permissions,ensure_dirs",
)
del lazyimport


class FsBased(template.database):
    """template wrapping fs needed options, and providing _ensure_access as a way to
    attempt to ensure files have the specified owners/perms"""

    def __init__(self, *args, **config):

        for x, y in (("gid", -1), ("perms", 0o644)):
            if x in config:
                # Since Python 3.4, chown requires int type (no proxies).
                setattr(self, "_" + x, int(config[x]))
                del config[x]
            else:
                setattr(self, "_" + x, y)
        super(FsBased, self).__init__(*args, **config)

        if self.label.startswith(os_unicode_fs.path.sep):
            # normpath.
            self.label = os_unicode_fs.path.sep + os_unicode_fs.path.normpath(
                self.label
            ).lstrip(os_unicode_fs.path.sep)

    def _ensure_access(self, path, mtime=-1):
        """returns true or false if it's able to ensure that path is properly chmod'd and chowned.
        if mtime is specified, attempts to ensure that's correct also"""
        try:
            apply_permissions(path, gid=self._gid, mode=self._perms)
            if mtime != -1:
                mtime = int(mtime)
                os_unicode_fs.utime(path, (mtime, mtime))
        except (PortageException, EnvironmentError):
            return False
        return True

    def _ensure_dirs(self, path=None):
        """with path!=None, ensure beyond self.location.  otherwise, ensure self.location"""
        if path:
            path = os_unicode_fs.path.dirname(path)
            base = self.location
        else:
            path = self.location
            base = "/"

        for d in (
            path.lstrip(os_unicode_fs.path.sep)
            .rstrip(os_unicode_fs.path.sep)
            .split(os_unicode_fs.path.sep)
        ):
            base = os_unicode_fs.path.join(base, d)
            if ensure_dirs(base):
                # We only call apply_permissions if ensure_dirs created
                # a new directory, so as not to interfere with
                # permissions of existing directories.
                mode = self._perms
                if mode == -1:
                    mode = 0
                mode |= 0o755
                apply_permissions(base, mode=mode, gid=self._gid)

    def _prune_empty_dirs(self):
        all_dirs = []
        for parent, dirs, files in os_unicode_fs.walk(self.location):
            for x in dirs:
                all_dirs.append(_os.path.join(parent, x))
        while all_dirs:
            try:
                _os.rmdir(all_dirs.pop())
            except OSError:
                pass


def gen_label(base, label):
    """if supplied label is a path, generate a unique label based upon label, and supplied base path"""
    if label.find(os_unicode_fs.path.sep) == -1:
        return label
    label = label.strip('"').strip("'")
    label = os_unicode_fs.path.join(
        *(label.rstrip(os_unicode_fs.path.sep).split(os_unicode_fs.path.sep))
    )
    tail = os_unicode_fs.path.split(label)[1]
    return "%s-%X" % (tail, abs(label.__hash__()))
