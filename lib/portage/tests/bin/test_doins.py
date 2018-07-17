# test_doins.py -- Portage Unit Testing Functionality
# Copyright 2007-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import grp
import os
import pwd
import stat

from portage.tests.bin import setup_env
from portage import tests

doins = setup_env.doins
exists_in_D = setup_env.exists_in_D


class DoIns(setup_env.BinTestCase):
	def testDoIns(self):
		"""Tests the most basic senario."""
		self.init()
		try:
			env = setup_env.env
			# Create a file to be installed.
			test_path = os.path.join(env['S'], 'test')
			with open(test_path, 'w'):
				pass
			doins('test')
			exists_in_D('/test')
			st = os.lstat(env['D'] + '/test')
			# By default, `install`'s permission is 755.
			if stat.S_IMODE(st.st_mode) != 0o755:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsOption(self):
		"""Tests with INSOPTIONS doins.py understands."""
		self.init()
		try:
			env = setup_env.env
			env['INSOPTIONS'] = '-pm0644'
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if stat.S_IMODE(st.st_mode) != 0o644:
				raise tests.TestCase.failureException
			self.assertEqual(
				os.stat(os.path.join(env['S'], 'test'))[stat.ST_MTIME],
				st[stat.ST_MTIME])
		finally:
			self.cleanup()

	def testDoInsOptionUnsupportedMode(self):
		"""Tests with INSOPTIONS in the format doins.py doesn't know."""
		self.init()
		try:
			env = setup_env.env
			# Parse test for -m with unsupported format.
			# It should fall back to `install` command.
			env['INSOPTIONS'] = '-m u+r'
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if stat.S_IMODE(st.st_mode) != 0o400:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsOptionUid(self):
		"""Tests setting owner by uid works."""
		self.init()
		try:
			env = setup_env.env
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			uid = os.lstat(os.path.join(env['S'], 'test')).st_uid
			# Set owner option with uid. No guarantee that this
			# runs with capability, we set the current UID so that
			# chown should success, although it is difficult to
			# check if chown actually runs or not.
			env['INSOPTIONS'] = '-o %d' % uid
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if st.st_uid != uid:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsOptionUserName(self):
		"""Tests setting owner by name works."""
		self.init()
		try:
			env = setup_env.env
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			uid = os.lstat(os.path.join(env['S'], 'test')).st_uid
			pw = pwd.getpwuid(uid)
			# Similary to testDoInsOptionUid, use user name.
			env['INSOPTIONS'] = '-o %s' % pw.pw_name
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if st.st_uid != uid:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsOptionGid(self):
		"""Tests setting group by gid works."""
		self.init()
		try:
			env = setup_env.env
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			gid = os.lstat(os.path.join(env['S'], 'test')).st_gid
			# Similary to testDoInsOptionUid, use gid.
			env['INSOPTIONS'] = '-g %d' % gid
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if st.st_gid != gid:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsOptionGroupName(self):
		"""Tests setting group by name works."""
		self.init()
		try:
			env = setup_env.env
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			gid = os.lstat(os.path.join(env['S'], 'test')).st_gid
			gr = grp.getgrgid(gid)
			# Similary to testDoInsOptionUid, use group name.
			env['INSOPTIONS'] = '-g %s' % gr.gr_name
			doins('test')
			st = os.lstat(env['D'] + '/test')
			if st.st_gid != gid:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoInsFallback(self):
		"""Tests if falling back to the `install` command works."""
		self.init()
		try:
			env = setup_env.env
			# Use an option which doins.py does not know.
			# Then, fallback to `install` command is expected.
			env['INSOPTIONS'] = '-b'
			with open(os.path.join(env['S'], 'test'), 'w'):
				pass
			doins('test')
			# So `install` should still work.
			exists_in_D('/test')
		finally:
			self.cleanup()

	def testDoInsRecursive(self):
		"""Tests installing a directory recursively."""
		self.init()
		try:
			env = setup_env.env
			os.mkdir(os.path.join(env['S'], 'testdir'))
			with open(os.path.join(env['S'], 'testdir/test'), 'w'):
				pass
			doins('-r testdir')
			exists_in_D('/testdir/test')
		finally:
			self.cleanup()

	def testDoDirOption(self):
		"""Tests with DIROPTIONS."""
		self.init()
		try:
			env = setup_env.env
			# Use an option which doins.py knows.
			env['DIROPTIONS'] = '-m0755'
			os.mkdir(os.path.join(env['S'], 'testdir'))
			with open(os.path.join(env['S'], 'testdir/test'), 'w'):
				pass
			doins('-r testdir')
			st = os.lstat(env['D'] + '/testdir')
			if stat.S_IMODE(st.st_mode) != 0o755:
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testDoDirFallback(self):
		"""Tests with DIROPTIONS which doins.py doesn't understand."""
		self.init()
		try:
			env = setup_env.env
			# Use an option which doins.py does not know.
			# Then, fallback to `install` command is expected.
			env['DIROPTIONS'] = '-p'
			os.mkdir(os.path.join(env['S'], 'testdir'))
			with open(os.path.join(env['S'], 'testdir/test'), 'w'):
				pass
			doins('-r testdir')
			# So, `install` should still work.
			exists_in_D('/testdir/test')
		finally:
			self.cleanup()

	def testSymlinkFile(self):
		"""Tests if installing a symlink works.

		In EAPI=4 and later, installing a symlink should creates a
		symlink at destination.
		"""
		self.init()
		try:
			env = setup_env.env
			env['EAPI'] = '4'  # Enable symlink.
			env['ED'] = env['D']
			env['PORTAGE_ACTUAL_DISTDIR'] = '/foo'
			# Create a file to be installed.
			test_path = os.path.join(env['S'], 'test')
			with open(test_path, 'w'):
				pass
			symlink_path = os.path.join(env['S'], 'symlink')
			os.symlink('test', symlink_path)
			doins('test symlink')
			exists_in_D('/symlink')
			# Make sure installed symlink is actually a symbolic
			# link pointing to test.
			if not os.path.islink(env['D'] + '/symlink'):
				raise tests.TestCase.failureException
			if os.readlink(env['D'] + '/symlink') != 'test':
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testSymlinkFileRecursive(self):
		"""Tests if installing a symlink in a directory works."""
		self.init()
		try:
			env = setup_env.env
			env['EAPI'] = '4'  # Enable symlink.
			env['ED'] = env['D']
			env['PORTAGE_ACTUAL_DISTDIR'] = '/foo'
			# Create a file to be installed.
			parent_path = os.path.join(env['S'], 'test')
			os.mkdir(parent_path)
			with open(os.path.join(parent_path, 'test'), 'w'):
				pass
			symlink_path = os.path.join(
				env['S'], 'test', 'symlink')
			os.symlink('test', symlink_path)
			doins('-r test')
			exists_in_D('/test/symlink')
			# Make sure installed symlink is actually a symbolic
			# link pointing to test.
			if not os.path.islink(env['D'] + '/test/symlink'):
				raise tests.TestCase.failureException
			if os.readlink(env['D'] + '/test/symlink') != 'test':
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testSymlinkDir(self):
		"""Tests installing a symlink to a directory."""
		self.init()
		try:
			env = setup_env.env
			env['EAPI'] = '4'  # Enable symlink.
			env['ED'] = env['D']
			env['PORTAGE_ACTUAL_DISTDIR'] = '/foo'
			# Create a dir to be installed.
			os.mkdir(os.path.join(env['S'], 'test'))
			symlink_path = os.path.join(env['S'], 'symlink')
			os.symlink('test', symlink_path)
			doins('test symlink')
			# Make sure installed symlink is actually a symbolic
			# link pointing to test.
			if not os.path.islink(env['D'] + '/symlink'):
				raise tests.TestCase.failureException
			if os.readlink(env['D'] + '/symlink') != 'test':
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testSymlinkDirRecursive(self):
		"""Tests installing a symlink to a directory under a directory.
		"""
		self.init()
		try:
			env = setup_env.env
			env['EAPI'] = '4'  # Enable symlink.
			env['ED'] = env['D']
			env['PORTAGE_ACTUAL_DISTDIR'] = '/foo'
			# Create a file to be installed.
			parent_path = os.path.join(env['S'], 'test')
			os.mkdir(parent_path)
			os.mkdir(os.path.join(parent_path, 'test'))
			symlink_path = os.path.join(
				env['S'], 'test', 'symlink')
			os.symlink('test', symlink_path)
			doins('-r test')
			# Make sure installed symlink is actually a symbolic
			# link pointing to test.
			if not os.path.islink(env['D'] + '/test/symlink'):
				raise tests.TestCase.failureException
			if not os.path.isdir(env['D'] + '/test/symlink'):
				raise tests.TestCase.failureException
			if os.readlink(env['D'] + '/test/symlink') != 'test':
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testSymlinkOverwrite(self):
		"""Tests installing a file to overwrite the existing file.

		Specifically, if the existing file is a symlink, it should be
		removed once, and the file content should be copied.
		"""
		self.init()
		try:
			env = setup_env.env
			test_path = os.path.join(env['S'], 'test')
			with open(test_path, 'w'):
				pass
			# Create a dangling symlink. If removal does not work,
			# this would easily cause ENOENT error.
			os.symlink('foo/bar', env['D'] + '/test')
			doins('test')
			# Actual file should be installed.
			if os.path.islink(env['D'] + '/test'):
				raise tests.TestCase.failureException
		finally:
			self.cleanup()

	def testHardlinkOverwrite(self):
		"""Tests installing a file to overwrite the hardlink.

		If the existing file is a hardlink, it should be removed once,
		and the file content should be copied.
		"""
		self.init()
		try:
			env = setup_env.env
			test_path = os.path.join(env['S'], 'test')
			with open(test_path, 'w'):
				pass
			# Create hardlink at the dest.
			os.link(test_path, env['D'] + '/test')
			doins('test')
			# The hardlink should be unlinked, and then a copy
			# should be created.
			if os.path.samefile(test_path, env['D'] + '/test'):
				raise tests.TestCase.failureException
		finally:
			self.cleanup()
