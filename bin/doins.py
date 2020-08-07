#!/usr/bin/python -b
# Copyright 2017-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Core implementation of doins ebuild helper command.

This script is designed to be executed by ebuild-helpers/doins.
"""

import argparse
import errno
import grp
import logging
import os
import pwd
import shlex
import shutil
import stat
import subprocess
import sys

from portage.util import movefile
from portage.util.file_copy import copyfile


def _warn(helper, msg):
	"""Output warning message to stderr.

	Args:
		helper: helper executable name.
		msg: Message to be output.
	"""
	print('!!! %s: %s\n' % (helper, msg), file=sys.stderr)


def _parse_group(group):
	"""Parses gid.

	Args:
		group: string representation of the group. Maybe name or gid.
	Returns:
		Parsed gid.
	"""
	try:
		return grp.getgrnam(group).gr_gid
	except KeyError:
		pass
	return int(group)


def _parse_user(user):
	"""Parses uid.

	Args:
		user: string representation of the user. Maybe name or uid.
	Returns:
		Parsed uid.
	"""
	try:
		return pwd.getpwnam(user).pw_uid
	except KeyError:
		pass
	return int(user)


def _parse_mode(mode):
	"""Parses mode.

	Args:
		mode: string representation of the permission.
	Returns:
		Parsed mode.
	"""
	# `install`'s --mode option is complicated. So here is partially
	# supported.
	try:
		return int(mode, 8)
	except ValueError:
		# In case of fail, returns None, so that caller can check
		# if unknown '-m' is set or not.
		return None


def _parse_install_options(
	options, is_strict, helper, inprocess_runner_class,
	subprocess_runner_class):
	"""Parses command line arguments for `install` command.

	Args:
		options: string representation of `install` options.
		is_strict: bool. If True, this exits the program in case of
			that an unknown option is found.
		helper: helper executable name.
		inprocess_runner_class: Constructor to run procedure which
			`install` command will do.
		subprocess_runner_class: Constructor to run `install` command.
	"""
	parser = argparse.ArgumentParser()
	parser.add_argument('-g', '--group', default=-1, type=_parse_group)
	parser.add_argument('-o', '--owner', default=-1, type=_parse_user)
	parser.add_argument('-m', '--mode', default=0o755, type=_parse_mode)
	parser.add_argument('-p', '--preserve-timestamps', action='store_true')
	split_options = shlex.split(options)
	namespace, remaining = parser.parse_known_args(split_options)
	# Because parsing '--mode' option is partially supported. If unknown
	# arg for --mode is passed, namespace.mode is set to None.
	if remaining or namespace.mode is None:
		_warn(helper, 'Unknown install options: %s, %r' % (
			options, remaining))
		if is_strict:
			sys.exit(1)
		_warn(helper, 'Continue with falling back to `install` '
			'command execution, which can be slower.')
		return subprocess_runner_class(split_options)
	return inprocess_runner_class(namespace)


def _set_attributes(options, path):
	"""Sets attributes the file/dir at given |path|.

	Args:
		options: object which has |owner|, |group| and |mode| fields.
			|owner| is int value representing uid. Similary |group|
			represents gid.
			If -1 is set, just unchanged.
			|mode| is the bits of permissions.
		path: File/directory path.
	"""
	if options.owner != -1 or options.group != -1:
		os.lchown(path, options.owner, options.group)
	if options.mode is not None:
		os.chmod(path, options.mode)


def _set_timestamps(source_stat, dest):
	"""Apply timestamps from source_stat to dest.

	Args:
		source_stat: stat result for the source file.
		dest: path to the dest file.
	"""
	os.utime(dest, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))


class _InsInProcessInstallRunner:
	"""Implements `install` command behavior running in a process."""

	def __init__(self, opts, parsed_options):
		"""Initializes the instance.

		Args:
			opts: namespace object containing the parsed
				arguments for this program.
			parsed_options: namespace object contaning the parsed
				options for `install`.
		"""
		self._parsed_options = parsed_options
		self._helper = opts.helper
		self._copy_xattr = opts.enable_copy_xattr
		if self._copy_xattr:
			self._xattr_exclude = opts.xattr_exclude

	def run(self, source, dest_dir):
		"""Installs a file at |source| into |dest_dir| in process.

		Args:
			source: Path to the file to be installed.
			dest_dir: Path to the directory which |source| will be
				installed into.
		Returns:
			True on success, otherwise False.
		"""
		dest = os.path.join(dest_dir, os.path.basename(source))
		# Raise an exception if stat(source) fails, intentionally.
		sstat = os.stat(source)
		if not self._is_install_allowed(source, sstat, dest):
			return False

		# To emulate the `install` command, remove the dest file in
		# advance.
		try:
			os.unlink(dest)
		except OSError as e:
			# Removing a non-existing entry should be handled as a
			# regular case.
			if e.errno != errno.ENOENT:
				raise
		try:
			copyfile(source, dest)
			_set_attributes(self._parsed_options, dest)
			if self._copy_xattr:
				movefile._copyxattr(
					source, dest,
					exclude=self._xattr_exclude)
			if self._parsed_options.preserve_timestamps:
				_set_timestamps(sstat, dest)
		except Exception:
			logging.exception(
				'Failed to copy file: '
				'_parsed_options=%r, source=%r, dest_dir=%r',
				self._parsed_options, source, dest_dir)
			return False
		return True

	def _is_install_allowed(self, source, source_stat, dest):
		"""Returns if installing source into dest should work.

		This is to keep compatibility with the `install` command.

		Args:
			source: path to the source file.
			source_stat: stat result for the source file, using stat()
				rather than lstat(), in order to match the `install`
				command
			dest: path to the dest file.

		Returns:
			True if it should succeed.
		"""
		# To match `install` command, use stat() for source, while
		# lstat() for dest.
		try:
			dest_lstat = os.lstat(dest)
		except OSError as e:
			# It is common to install a file into a new path,
			# so if the destination doesn't exist, ignore it.
			if e.errno == errno.ENOENT:
				return True
			raise

		# Allowing install, if the target is a symlink.
		if stat.S_ISLNK(dest_lstat.st_mode):
			return True

		# Allowing install, if source file and dest file are different.
		# Note that, later, dest will be unlinked.
		if not os.path.samestat(source_stat, dest_lstat):
			return True

		# Allowing install, in hardlink case, if the actual path are
		# different, because source can be preserved even after dest is
		# unlinked.
		if (dest_lstat.st_nlink > 1 and
			os.path.realpath(source) != os.path.realpath(dest)):
			return True

		_warn(self._helper, '%s and %s are same file.' % (
			source, dest))
		return False


class _InsSubprocessInstallRunner:
	"""Runs `install` command in a subprocess to install a file."""

	def __init__(self, split_options):
		"""Initializes the instance.

		Args:
			split_options: Command line options to be passed to
				`install` command. List of str.
		"""
		self._split_options = split_options

	def run(self, source, dest_dir):
		"""Installs a file at |source| into |dest_dir| by `install`.

		Args:
			source: Path to the file to be installed.
			dest_dir: Path to the directory which |source| will be
			installed into.
		Returns:
			True on success, otherwise False.
		"""
		command = ['install'] + self._split_options + [source, dest_dir]
		return subprocess.call(command) == 0


class _DirInProcessInstallRunner:
	"""Implements `install` command behavior running in a process."""

	def __init__(self, parsed_options):
		"""Initializes the instance.

		Args:
			parsed_options: namespace object contaning the parsed
				options for `install`.
		"""
		self._parsed_options = parsed_options

	def run(self, dest):
		"""Installs a dir into |dest| in process.

		Args:
			dest: Path where a directory should be created.
		"""
		try:
			os.makedirs(dest)
		except OSError as e:
			if e.errno != errno.EEXIST or not os.path.isdir(dest):
				raise
		_set_attributes(self._parsed_options, dest)


class _DirSubprocessInstallRunner:
	"""Runs `install` command to create a directory."""

	def __init__(self, split_options):
		"""Initializes the instance.

		Args:
			split_options: Command line options to be passed to
				`install` command. List of str.
		"""
		self._split_options = split_options

	def run(self, dest):
		"""Installs a dir into |dest| by `install` command.

		Args:
			dest: Path where a directory should be created.
		"""
		command = ['install', '-d'] + self._split_options + [dest]
		subprocess.check_call(command)


class _InstallRunner:
	"""Handles `install` command operation.

	Runs operations which `install` command should work. If possible,
	this may just call in-process functions, instead of executing `install`
	in a subprocess for performance.
	"""

	def __init__(self, opts):
		"""Initializes the instance.

		Args:
			opts: namespace object containing the parsed
				arguments for this program.
		"""
		self._ins_runner = _parse_install_options(
			opts.insoptions,
			opts.strict_option,
			opts.helper,
			lambda options: _InsInProcessInstallRunner(
				opts, options),
			_InsSubprocessInstallRunner)
		self._dir_runner = _parse_install_options(
			opts.diroptions,
			opts.strict_option,
			opts.helper,
			_DirInProcessInstallRunner,
			_DirSubprocessInstallRunner)
		self._helpers_can_die = opts.helpers_can_die

	def install_file(self, source, dest_dir):
		"""Installs a file at |source| into |dest_dir| directory.

		Args:
			source: Path to the file to be installed.
			dest_dir: Path to the directory which |source| will be
				installed into.
		Returns:
			True on success, otherwise False.
		"""
		return self._ins_runner.run(source, dest_dir)

	def install_dir(self, dest):
		"""Creates a directory at |dest|.

		Args:
			dest: Path where a directory should be created.
		"""
		try:
			self._dir_runner.run(dest)
		except Exception:
			if self._helpers_can_die:
				raise
			logging.exception('install_dir failed.')


def _doins(opts, install_runner, relpath, source_root):
	"""Installs a file as if `install` command runs.

	Installs a file at |source_root|/|relpath| into
	|opts.dest|/|relpath|.
	If |args.preserve_symlinks| is set, creates symlink if the source is a
	symlink.

	Args:
		opts: parsed arguments. It should have following fields.
			- preserve_symlinks: bool representing whether symlinks
				needs to be preserved.
			- dest: Destination root directory.
			- distdir: location where Portage stores the downloaded
				source code archives.
		install_runner: _InstallRunner instance for file install.
		relpath: Relative path of the file being installed.
		source_root: Source root directory.

	Returns: True on success.
	"""
	source = os.path.join(source_root, relpath)
	dest = os.path.join(opts.dest, relpath)
	if os.path.islink(source):
		# Our fake $DISTDIR contains symlinks that should not be
		# reproduced inside $D. In order to ensure that things like
		# dodoc "$DISTDIR"/foo.pdf work as expected, we dereference
		# symlinked files that refer to absolute paths inside
		# $PORTAGE_ACTUAL_DISTDIR/.
		try:
			if (opts.preserve_symlinks and
				not os.readlink(source).startswith(
					opts.distdir)):
				linkto = os.readlink(source)
				try:
					os.unlink(dest)
				except OSError as e:
					if e.errno == errno.EISDIR:
						shutil.rmtree(dest, ignore_errors=True)
				os.symlink(linkto, dest)
				return True
		except Exception:
			logging.exception(
				'Failed to create symlink: '
				'opts=%r, relpath=%r, source_root=%r',
				opts, relpath, source_root)
			return False

	return install_runner.install_file(source, os.path.dirname(dest))


def _create_arg_parser():
	"""Returns the parser for the command line arguments."""
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		'--recursive', action='store_true',
		help='If set, installs files recursively. Otherwise, '
		'just skips directories.')
	parser.add_argument(
		'--preserve_symlinks', action='store_true',
		help='If set, a symlink will be installed as symlink.')
	parser.add_argument(
		'--helpers_can_die', action='store_true',
		help='If set, die in isolated-functions.sh is enabled. '
		'Specifically this is used to keep compatible dodir\'s '
		'behavior.')
	parser.add_argument(
		'--distdir', default='', help='Path to the actual distdir.')
	parser.add_argument(
		'--insoptions', default='',
		help='Options passed to `install` command for installing a '
		'file.')
	parser.add_argument(
		'--diroptions', default='',
		help='Options passed to `install` command for installing a '
		'dir.')
	parser.add_argument(
		'--strict_option', action='store_true',
		help='If set True, abort if insoptions/diroptions contains an '
		'option which cannot be interpreted by this script, instead of '
		'fallback to execute `install` command.')
	parser.add_argument(
		'--enable_copy_xattr', action='store_true',
		help='Copies xattrs, if set True')
	parser.add_argument(
		'--xattr_exclude', default='',
		help='White space delimited glob pattern to exclude xattr copy.'
		'Used only if --enable_xattr_copy is set.')

	# If helper is dodoc, it changes the behavior for the directory
	# install without --recursive.
	parser.add_argument('--helper', help='Name of helper.')
	parser.add_argument(
		'--dest',
		help='Destination where the files are installed.')
	parser.add_argument(
		'sources', nargs='*',
		help='Source file/directory paths to be installed.')

	return parser


def _parse_args(argv):
	"""Parses the command line arguments.

	Args:
		argv: command line arguments to be parsed.
	Returns:
		namespace instance containing the parsed argument data.
	"""
	parser = _create_arg_parser()
	opts = parser.parse_args(argv)

	# Encode back to the original byte stream. Please see
	# http://bugs.python.org/issue8776.
	opts.distdir = os.fsencode(opts.distdir) + b'/'
	opts.dest = os.fsencode(opts.dest)
	opts.sources = [os.fsencode(source) for source in opts.sources]

	return opts


def _install_dir(opts, install_runner, source):
	"""Installs directory at |source|.

	Args:
		opts: namespace instance containing parsed command line
			argument data.
		install_runner: _InstallRunner instance for dir install.
		source: Path to the source directory.
	Returns:
		True on success, False on failure, or None on skipped.
	"""
	if not opts.recursive:
		if opts.helper == 'dodoc':
			_warn(opts.helper, '%s is a directory' % (source,))
			return False
		# Neither success nor fail. Return None to indicate skipped.
		return None

	# Strip trailing '/'s.
	source = source.rstrip(b'/')
	source_root = os.path.dirname(source)
	dest_dir = os.path.join(opts.dest, os.path.basename(source))
	install_runner.install_dir(dest_dir)

	relpath_list = []
	for dirpath, dirnames, filenames in os.walk(source):
		for dirname in dirnames:
			source_dir = os.path.join(dirpath, dirname)
			relpath = os.path.relpath(source_dir, source_root)
			if os.path.islink(source_dir):
				# If this is a symlink, it will be processed
				# in _doins() called later.
				relpath_list.append(relpath)
			else:
				dest = os.path.join(opts.dest, relpath)
				install_runner.install_dir(dest)
		relpath_list.extend(
			os.path.relpath(
				os.path.join(dirpath, filename), source_root)
			for filename in filenames)

	if not relpath_list:
		# NOTE: Even if only an empty directory is installed here, it
		# still counts as success, since an empty directory given as
		# an argument to doins -r should not trigger failure.
		return True
	success = True
	for relpath in relpath_list:
		if not _doins(opts, install_runner, relpath, source_root):
			success = False
	return success


def main(argv):
	opts = _parse_args(argv)
	install_runner = _InstallRunner(opts)

	if not os.path.isdir(opts.dest):
		install_runner.install_dir(opts.dest)

	any_success = False
	any_failure = False
	for source in opts.sources:
		if (os.path.isdir(source) and
			(not opts.preserve_symlinks or
			not os.path.islink(source))):
			ret = _install_dir(opts, install_runner, source)
			if ret is None:
				continue
			if ret:
				any_success = True
			else:
				any_failure = True
		else:
			if _doins(
				opts, install_runner,
				os.path.basename(source),
				os.path.dirname(source)):
				any_success = True
			else:
				any_failure = True

	return 0 if not any_failure and any_success else 1


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
