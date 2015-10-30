#!/usr/bin/python -b
# Copyright 2009-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import argparse
import sys
import portage
portage._internal_caller = True
from portage import os

def command_recompose(args):

	usage = "usage: recompose <binpkg_path> <metadata_dir>\n"

	if len(args) != 2:
		sys.stderr.write(usage)
		sys.stderr.write("2 arguments are required, got %s\n" % len(args))
		return 1

	binpkg_path, metadata_dir = args

	if not os.path.isfile(binpkg_path):
		sys.stderr.write(usage)
		sys.stderr.write("Argument 1 is not a regular file: '%s'\n" % \
			binpkg_path)
		return 1

	if not os.path.isdir(metadata_dir):
		sys.stderr.write(usage)
		sys.stderr.write("Argument 2 is not a directory: '%s'\n" % \
			metadata_dir)
		return 1

	t = portage.xpak.tbz2(binpkg_path)
	t.recompose(metadata_dir)
	return os.EX_OK

def main(argv):

	if argv and isinstance(argv[0], bytes):
		for i, x in enumerate(argv):
			argv[i] = portage._unicode_decode(x, errors='strict')

	valid_commands = ('recompose',)
	description = "Perform metadata operations on a binary package."
	usage = "usage: %s COMMAND [args]" % \
		os.path.basename(argv[0])

	parser = argparse.ArgumentParser(description=description, usage=usage)
	options, args = parser.parse_known_args(argv[1:])

	if not args:
		parser.error("missing command argument")

	command = args[0]

	if command not in valid_commands:
		parser.error("invalid command: '%s'" % command)

	if command == 'recompose':
		rval = command_recompose(args[1:])
	else:
		raise AssertionError("invalid command: '%s'" % command)

	return rval

if __name__ == "__main__":
	rval = main(sys.argv[:])
	sys.exit(rval)
