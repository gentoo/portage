#!/usr/bin/python
# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import sys
import subprocess
import traceback

from portage.util.movefile import _copyxattr
from portage.exception import OperationNotSupported

try:
	from argparse import ArgumentParser
except ImportError:
	# Compatibility with Python 2.6 and 3.1
	from optparse import OptionParser

	class ArgumentParser(object):
		def __init__(self, **kwargs):
			add_help = kwargs.pop("add_help", None)
			if add_help is not None:
				kwargs["add_help_option"] = add_help
			parser = OptionParser(**kwargs)
			self.add_argument = parser.add_option
			self.parse_known_args = parser.parse_args

def parse_args(args):
	"""
	Parse the command line arguments using optparse for python 2.6 compatibility
	Args:
	  args: a list of the white space delimited command line
	Returns:
	  tuple of the Namespace of parsed options, and a list of order parameters
	"""
	parser = ArgumentParser(add_help=False)

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
		"--context",
		"-Z",
		action="store",
		dest="context"
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
	parsed_args = parser.parse_known_args()

	opts  = parsed_args[0]
	files = parsed_args[1]
	files = [f for f in files if f != "--"]	# filter out "--"

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
	if opts.directory:
		return os.EX_OK

	if opts.target_directory is None:
		source, target = files[:-1], files[-1]
		target_is_directory = os.path.isdir(target)
	else:
		source, target = files, opts.target_directory
		target_is_directory = True

	try:
		if target_is_directory:
			for s in source:
				abs_path = os.path.join(target, os.path.basename(s))
				_copyxattr(s, abs_path)
		else:
			_copyxattr(source[0], target)
		return os.EX_OK

	except OperationNotSupported:
		traceback.print_exc()
		return os.EX_OSERR


def Which(filename, path=None, all=False):
	"""
	Find the absolute path of 'filename' in a given search 'path'
	Args:
	  filename: basename of the file
	  path: colon delimited search path
	  all: return a list of all intances if true, else return just the first
	"""
	if path is None:
		path = os.environ.get('PATH', '')
	ret = []
	for p in path.split(':'):
		p = os.path.join(p, filename)
		if os.access(p, os.X_OK):
			if all:
				ret.append(p)
			else:
				return p
	if all:
		return ret
	else:
		return None


def main(args):
	opts, files = parse_args(args)
	path_installs = Which('install', all=True)
	cmdline = path_installs[0:1]
	cmdline += args
	returncode = subprocess.call(cmdline)
	if returncode == os.EX_OK:
		returncode = copy_xattrs(opts, files)
	return returncode


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
