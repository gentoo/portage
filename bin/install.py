#!/usr/bin/python -b
# Copyright 2013-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import argparse
import os
import stat
import sys
import subprocess
import traceback

import portage
from portage.util.movefile import _copyxattr
from portage.exception import OperationNotSupported

# Change back to original cwd _after_ all imports (bug #469338).
os.chdir(os.environ["__PORTAGE_HELPER_CWD"])

def parse_args(args):
	"""
	Parse the command line arguments using optparse for python 2.6 compatibility
	Args:
	  args: a list of the white space delimited command line
	Returns:
	  tuple of the Namespace of parsed options, and a list of order parameters
	"""
	parser = argparse.ArgumentParser(add_help=False)

	parser.add_argument(
		"-b",
		action="store_true",
		dest="shortopt_b"
	)
	parser.add_argument(
		"--backup",
		action="store",
		dest="backup"
		)
	parser.add_argument(
		"-c",
		action="store_true",
		dest="shortopt_c"
	)
	parser.add_argument(
		"--compare",
		"-C",
		action="store_true",
		dest="compare"
	)
	parser.add_argument(
		"--directory",
			"-d",
		action="store_true",
		dest="directory"
	)
	parser.add_argument(
		"-D",
		action="store_true",
		dest="shortopt_D"
	)
	parser.add_argument(
		"--owner",
		"-o",
		action="store",
		dest="owner"
	)
	parser.add_argument(
		"--group",
		"-g",
		action="store",
		dest="group"
	)
	parser.add_argument(
		"--mode",
		"-m",
		action="store",
		dest="mode"
	)
	parser.add_argument(
		"--preserve-timestamps",
		"-p",
		action="store_true",
		dest="preserve_timestamps"
	)
	parser.add_argument(
		"--strip",
		"-s",
		action="store_true",
		dest="strip"
	)
	parser.add_argument(
		"--strip-program",
		action="store",
		dest="strip_program"
	)
	parser.add_argument(
		"--suffix",
		"-S",
		action="store",
		dest="suffix"
	)
	parser.add_argument(
		"--target-directory",
		"-t",
		action="store",
		dest="target_directory"
	)
	parser.add_argument(
		"--no-target-directory",
		"-T",
		action="store_true",
		dest="no_target_directory"
	)
	parser.add_argument(
		"--verbose",
		"-v",
		action="store_true",
		dest="verbose"
	)
	parser.add_argument(
		"--help",
		action="store_true",
		dest="help"
	)
	parser.add_argument(
		"--version",
		action="store_true",
		dest="version"
	)

	# Use parse_known_args for maximum compatibility with
	# getopt handling of non-option file arguments. Note
	# that parser.add_argument("files", nargs='+') would
	# be subtly incompatible because it requires that all
	# of the file arguments be grouped sequentially. Also
	# note that we have to explicitly call add_argument
	# for known options in order for argparse to correctly
	# separate option arguments from file arguments in all
	# cases (it also allows for optparse compatibility).
	(opts, args) = parser.parse_known_args(args)

	files = []
	i = 0
	while i < len(args):
		if args[i] == "--":
			i += 1
			break
		if not args[i].startswith("-"):
			files.append(args[i])
		i += 1

	while i < len(args):
		files.append(args[i])
		i += 1

	return (opts, files)


def copy_xattrs(opts, files):
	"""
	Copy the extended attributes using portage.util.movefile._copyxattr
	Args:
	  opts:  Namespace of the parsed command line otions
	  files: list of ordered command line parameters which should be files/directories
	Returns:
	  system exit code
	"""
	if opts.directory or not files:
		return os.EX_OK

	if opts.target_directory is None:
		source, target = files[:-1], files[-1]
		target_is_directory = os.path.isdir(target)
	else:
		source, target = files, opts.target_directory
		target_is_directory = True

	exclude = os.environ.get("PORTAGE_XATTR_EXCLUDE", "")

	try:
		if target_is_directory:
			for s in source:
				abs_path = os.path.join(target, os.path.basename(s))
				_copyxattr(s, abs_path, exclude=exclude)
		else:
			_copyxattr(source[0], target, exclude=exclude)
		return os.EX_OK

	except OperationNotSupported:
		traceback.print_exc()
		return os.EX_OSERR


def Which(filename, path=None, exclude=None):
	"""
	Find the absolute path of 'filename' in a given search 'path'
	Args:
	  filename: basename of the file
	  path: colon delimited search path
	  exclude: path of file to exclude
	"""
	if path is None:
		path = os.environ.get('PATH', '')

	if exclude is not None:
		st = os.stat(exclude)
		exclude = (st.st_ino, st.st_dev)

	for p in path.split(':'):
		p = os.path.join(p, filename)
		if os.access(p, os.X_OK):
			try:
				st = os.stat(p)
			except OSError:
				# file disappeared?
				pass
			else:
				if stat.S_ISREG(st.st_mode) and \
					(exclude is None or exclude != (st.st_ino, st.st_dev)):
					return p

	return None


def main(args):
	opts, files = parse_args(args)
	install_binary = Which('install', exclude=os.environ["__PORTAGE_HELPER_PATH"])
	if install_binary is None:
		sys.stderr.write("install: command not found\n")
		return 127

	cmdline = [install_binary]
	cmdline += args

	# We can't trust that the filesystem encoding (locale dependent)
	# correctly matches the arguments, so use surrogateescape to
	# pass through the original argv bytes for Python 3.
	fs_encoding = sys.getfilesystemencoding()
	cmdline = [x.encode(fs_encoding, 'surrogateescape') for x in cmdline]
	files = [x.encode(fs_encoding, 'surrogateescape') for x in files]
	if opts.target_directory is not None:
		opts.target_directory = \
			opts.target_directory.encode(fs_encoding, 'surrogateescape')

	returncode = subprocess.call(cmdline)
	if returncode == os.EX_OK:
		returncode = copy_xattrs(opts, files)
		if returncode != os.EX_OK:
			portage.util.writemsg("!!! install: copy_xattrs failed with the "
				"following arguments: %s\n" %
				" ".join(portage._shell_quote(x) for x in args), noiselevel=-1)
	return returncode


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
