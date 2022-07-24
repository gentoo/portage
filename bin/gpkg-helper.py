#!/usr/bin/env python
# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import sys
import portage

portage._internal_caller = True
from portage import os


def command_compose(args):

    usage = "usage: compose <package_cpv> <binpkg_path> <metadata_dir> <image_dir>\n"

    if len(args) != 4:
        sys.stderr.write(usage)
        sys.stderr.write("4 arguments are required, got %s\n" % len(args))
        return 1

    cpv, binpkg_path, metadata_dir, image_dir = args

    if not os.path.isdir(metadata_dir):
        sys.stderr.write(usage)
        sys.stderr.write("Argument 3 is not a directory: '%s'\n" % metadata_dir)
        return 1

    if not os.path.isdir(image_dir):
        sys.stderr.write(usage)
        sys.stderr.write("Argument 4 is not a directory: '%s'\n" % image_dir)
        return 1

    gpkg_file = portage.gpkg.gpkg(portage.settings, cpv, binpkg_path)
    metadata = gpkg_file._generate_metadata_from_dir(metadata_dir)
    gpkg_file.compress(image_dir, metadata)
    return os.EX_OK


def main(argv):

    if argv and isinstance(argv[0], bytes):
        for i, x in enumerate(argv):
            argv[i] = portage._unicode_decode(x, errors="strict")

    valid_commands = ("compress",)
    description = "Perform metadata operations on a binary package."
    usage = "usage: %s COMMAND [args]" % os.path.basename(argv[0])

    parser = argparse.ArgumentParser(description=description, usage=usage)
    options, args = parser.parse_known_args(argv[1:])

    if not args:
        parser.error("missing command argument")

    command = args[0]

    if command not in valid_commands:
        parser.error("invalid command: '%s'" % command)

    if command == "compress":
        rval = command_compose(args[1:])
    else:
        raise AssertionError("invalid command: '%s'" % command)

    return rval


if __name__ == "__main__":
    rval = main(sys.argv[:])
    sys.exit(rval)
