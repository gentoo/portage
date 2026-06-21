#!/usr/bin/env python
# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import locale
import os
import sys

if (
    sys.getfilesystemencoding().lower() != "utf-8"
    or locale.getpreferredencoding(False).lower() != "utf-8"
):
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


import argparse
import portage

portage._internal_caller = True
from portage import os_unicode_fs as os
from portage.output import EOutput


def command_compose(args):
    eout = EOutput()

    usage = "usage: compose <package_cpv> <binpkg_path> <metadata_dir> <image_dir>\n"

    if len(args) != 4:
        sys.stderr.write(usage)
        sys.stderr.write(f"4 arguments are required, got {len(args)}\n")
        return 1

    basename, binpkg_path, metadata_dir, image_dir = args

    if not os.path.isdir(metadata_dir):
        sys.stderr.write(usage)
        sys.stderr.write(f"Argument 3 is not a directory: '{metadata_dir}'\n")
        return 1

    if not os.path.isdir(image_dir):
        sys.stderr.write(usage)
        sys.stderr.write(f"Argument 4 is not a directory: '{image_dir}'\n")
        return 1

    try:
        gpkg_file = portage.gpkg.gpkg(portage.settings, basename, binpkg_path)
        metadata = gpkg_file._generate_metadata_from_dir(metadata_dir)
        gpkg_file.compress(image_dir, metadata)
    except portage.exception.CompressorOperationFailed:
        eout.eerror("Compressor Operation Failed")
        exit(1)
    return os.EX_OK


def main(argv):
    if argv and isinstance(argv[0], bytes):
        for i, x in enumerate(argv):
            argv[i] = x.decode("utf-8", "strict")

    valid_commands = ("compress",)
    description = "Perform metadata operations on a binary package."
    usage = f"usage: {os.path.basename(argv[0])} COMMAND [args]"

    parser = argparse.ArgumentParser(description=description, usage=usage)
    options, args = parser.parse_known_args(argv[1:])

    if not args:
        parser.error("missing command argument")

    command = args[0]

    if command not in valid_commands:
        parser.error(f"invalid command: '{command}'")

    if command == "compress":
        rval = command_compose(args[1:])
    else:
        raise AssertionError(f"invalid command: '{command}'")

    return rval


if __name__ == "__main__":
    rval = main(sys.argv[:])
    sys.exit(rval)
