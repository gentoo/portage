# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tarfile
from portage import os
from portage.const import SUPPORTED_XPAK_EXTENSIONS, SUPPORTED_GPKG_EXTENSIONS
from portage.exception import InvalidBinaryPackageFormat
from portage.output import colorize
from portage.util import writemsg


def get_binpkg_format(binpkg_path, check_file=False, remote=False):
    if binpkg_path.endswith(SUPPORTED_XPAK_EXTENSIONS):
        file_ext_format = "xpak"
    elif binpkg_path.endswith(SUPPORTED_GPKG_EXTENSIONS):
        file_ext_format = "gpkg"
    else:
        file_ext_format = None

    if remote:
        if file_ext_format is not None:
            return file_ext_format
        else:
            raise InvalidBinaryPackageFormat(
                f"Unsupported binary package format from '{binpkg_path}'"
            )

    if file_ext_format is not None and not check_file:
        return file_ext_format

    try:
        with open(binpkg_path, "rb") as binpkg_file:
            header = binpkg_file.read(100)
            if b"/gpkg-1\x00" in header:
                file_format = "gpkg"
            else:
                binpkg_file.seek(-16, 2)
                tail = binpkg_file.read(16)
                if (tail[0:8] == b"XPAKSTOP") and (tail[12:16] == b"STOP"):
                    file_format = "xpak"
                else:
                    file_format = None

        # check if wrong order gpkg
        if file_format is None:
            try:
                with tarfile.open(binpkg_path) as gpkg_tar:
                    if "gpkg-1" in (os.path.basename(f) for f in gpkg_tar.getnames()):
                        file_format = "gpkg"
            except tarfile.TarError:
                pass

    except Exception as err:
        # We got many different exceptions here, so have to catch all of them.
        file_format = None
        writemsg(
            colorize("ERR", f"Error reading binpkg '{binpkg_path}': {err}"),
        )
        raise InvalidBinaryPackageFormat(f"Error reading binpkg '{binpkg_path}': {err}")

    if file_format is None:
        raise InvalidBinaryPackageFormat(
            f"Unsupported binary package format from '{binpkg_path}'"
        )

    if (file_ext_format is not None) and (file_ext_format != file_format):
        writemsg(
            colorize(
                "WARN",
                "File {} binpkg format mismatch, actual format: {}".format(
                    binpkg_path, file_format
                ),
            )
        )

    return file_format
