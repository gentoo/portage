# getbinpkg.py -- Portage binary-package helper functions
# Copyright 2003-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import shlex
import sys
import time
import warnings

from portage.cache.mappings import slot_dict_class
from portage.localization import _
import portage


def file_get(
    baseurl=None, dest=None, conn=None, fcmd=None, filename=None, fcmd_vars=None
):
    """Takes a base url to connect to and read from.
    URI should be in the form <proto>://[user[:pass]@]<site>[:port]<path>"""

    if not fcmd:
        warnings.warn(
            "Use of portage.getbinpkg.file_get() without the fcmd "
            "parameter is deprecated",
            DeprecationWarning,
            stacklevel=2,
        )

        return file_get_lib(baseurl, dest, conn)

    variables = {}

    if fcmd_vars is not None:
        variables.update(fcmd_vars)

    if "DISTDIR" not in variables:
        if dest is None:
            raise portage.exception.MissingParameter(
                _("fcmd_vars is missing required 'DISTDIR' key")
            )
        variables["DISTDIR"] = dest

    if "URI" not in variables:
        if baseurl is None:
            raise portage.exception.MissingParameter(
                _("fcmd_vars is missing required 'URI' key")
            )
        variables["URI"] = baseurl

    if "FILE" not in variables:
        if not filename:
            filename = os.path.basename(variables["URI"])
        variables["FILE"] = filename

    from portage.util import varexpand
    from portage.process import spawn

    myfetch = [varexpand(x, mydict=variables) for x in shlex.split(fcmd)]
    fd_pipes = {
        0: portage._get_stdin().fileno(),
        1: sys.__stdout__.fileno(),
        2: sys.__stdout__.fileno(),
    }
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    retval = spawn(myfetch, env=os.environ.copy(), fd_pipes=fd_pipes)
    if retval != os.EX_OK:
        sys.stderr.write(_("Fetcher exited with a failure condition.\n"))
        return 0
    return 1


def _cmp_cpv(d1, d2):
    cpv1 = d1["CPV"]
    cpv2 = d2["CPV"]
    if cpv1 > cpv2:
        return 1
    if cpv1 == cpv2:
        return 0
    return -1


class PackageIndex:
    def __init__(
        self,
        allowed_pkg_keys=None,
        default_header_data=None,
        default_pkg_data=None,
        inherited_keys=None,
        translated_keys=None,
    ):
        self._pkg_slot_dict = None
        if allowed_pkg_keys:
            self._pkg_slot_dict = slot_dict_class(allowed_pkg_keys)

        self._default_header_data = default_header_data
        self._default_pkg_data = default_pkg_data
        self._inherited_keys = inherited_keys
        self._write_translation_map = {}
        self._read_translation_map = {}
        if translated_keys:
            self._write_translation_map.update(translated_keys)
            self._read_translation_map.update((y, x) for (x, y) in translated_keys)
        self.header = {}
        if self._default_header_data:
            self.header.update(self._default_header_data)
        self.packages = []
        self.modified = True

    def _readpkgindex(self, pkgfile, pkg_entry=True):
        d = {}
        allowed_keys = None
        if self._pkg_slot_dict and pkg_entry:
            d = self._pkg_slot_dict()
            allowed_keys = d.allowed_keys

        for line in pkgfile:
            line = line.rstrip("\n")
            if not line:
                break
            line = line.split(":", 1)
            if not len(line) == 2:
                continue
            k, v = line
            if v:
                v = v[1:]
            k = self._read_translation_map.get(k, k)
            if allowed_keys is not None and k not in allowed_keys:
                continue
            d[k] = v
        return d

    def _writepkgindex(self, pkgfile, items):
        for k, v in items:
            pkgfile.write(f"{self._write_translation_map.get(k, k)}: {v}\n")
        pkgfile.write("\n")

    def read(self, pkgfile):
        self.readHeader(pkgfile)
        self.readBody(pkgfile)

    def readHeader(self, pkgfile):
        self.header.update(self._readpkgindex(pkgfile, pkg_entry=False))

    def readBody(self, pkgfile):
        while True:
            d = self._readpkgindex(pkgfile)
            if not d:
                break
            mycpv = d.get("CPV")
            if not mycpv:
                continue
            if self._default_pkg_data:
                for k, v in self._default_pkg_data.items():
                    d.setdefault(k, v)
            if self._inherited_keys:
                for k in self._inherited_keys:
                    v = self.header.get(k)
                    if v:
                        d.setdefault(k, v)
            self.packages.append(d)

    def write(self, pkgfile):
        if self.modified:
            self.header["TIMESTAMP"] = str(int(time.time()))
            self.header["PACKAGES"] = str(len(self.packages))
        keys = list(self.header)
        keys.sort()
        self._writepkgindex(
            pkgfile, [(k, self.header[k]) for k in keys if self.header[k]]
        )
        for metadata in sorted(self.packages, key=portage.util.cmp_sort_key(_cmp_cpv)):
            metadata = metadata.copy()
            if self._inherited_keys:
                for k in self._inherited_keys:
                    v = self.header.get(k)
                    if v and v == metadata.get(k):
                        del metadata[k]
            if self._default_pkg_data:
                for k, v in self._default_pkg_data.items():
                    if metadata.get(k) == v:
                        metadata.pop(k, None)
            keys = list(metadata)
            keys.sort()
            self._writepkgindex(
                pkgfile, ((k, metadata[k]) for k in keys if metadata[k])
            )
