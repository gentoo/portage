# -*- coding:utf-8 -*-
# repoman: Utilities
# Copyright 2007-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains utility functions to help repoman find ebuilds to
scan"""

from __future__ import print_function

__all__ = [
	"editor_is_executable",
	"FindPackagesToScan",
	"FindPortdir",
	"get_commit_message_with_editor",
	"get_committer_name",
	"have_ebuild_dir",
	"have_profile_dir",
	"UpdateChangeLog"
]

import errno
import io
from itertools import chain
import logging
import pwd
import stat
import sys
import time
import textwrap
import difflib
import tempfile

# import our initialized portage instance
from repoman._portage import portage

from portage import os
from portage import shutil
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage import util
from portage.localization import _
from portage.process import find_binary
from portage.output import green

from repoman.copyrights import update_copyright, update_copyright_year


normalize_path = util.normalize_path
util.initialize_logger()


def have_profile_dir(path, maxdepth=3, filename="profiles.desc"):
	"""
	Try to figure out if 'path' has a profiles/
	dir in it by checking for the given filename.
	"""
	while path != "/" and maxdepth:
		if os.path.exists(os.path.join(path, "profiles", filename)):
			return normalize_path(path)
		path = normalize_path(path + "/..")
		maxdepth -= 1


def have_ebuild_dir(path, maxdepth=3):
	"""
	Try to figure out if 'path' or a subdirectory contains one or more
	ebuild files named appropriately for their parent directory.
	"""
	stack = [(normalize_path(path), 1)]
	while stack:
		path, depth = stack.pop()
		basename = os.path.basename(path)
		try:
			listdir = os.listdir(path)
		except OSError:
			continue
		for filename in listdir:
			abs_filename = os.path.join(path, filename)
			try:
				st = os.stat(abs_filename)
			except OSError:
				continue
			if stat.S_ISDIR(st.st_mode):
				if depth < maxdepth:
					stack.append((abs_filename, depth + 1))
			elif stat.S_ISREG(st.st_mode):
				if filename.endswith(".ebuild") and \
					filename.startswith(basename + "-"):
					return os.path.dirname(os.path.dirname(path))


def FindPackagesToScan(settings, startdir, reposplit):
	""" Try to find packages that need to be scanned

	Args:
		settings - portage.config instance, preferably repoman_settings
		startdir - directory that repoman was run in
		reposplit - root of the repository
	Returns:
		A list of directories to scan
	"""

	def AddPackagesInDir(path):
		""" Given a list of dirs, add any packages in it """
		ret = []
		pkgdirs = os.listdir(path)
		for d in pkgdirs:
			if d == 'CVS' or d.startswith('.'):
				continue
			p = os.path.join(path, d)

			if os.path.isdir(p):
				cat_pkg_dir = os.path.join(*p.split(os.path.sep)[-2:])
				logging.debug('adding %s to scanlist' % cat_pkg_dir)
				ret.append(cat_pkg_dir)
		return ret

	scanlist = []
	repolevel = len(reposplit)
	if repolevel == 1:  # root of the tree, startdir = repodir
		for cat in settings.categories:
			path = os.path.join(startdir, cat)
			if not os.path.isdir(path):
				continue
			scanlist.extend(AddPackagesInDir(path))
	elif repolevel == 2:  # category level, startdir = catdir
		# We only want 1 segment of the directory,
		# this is why we use catdir instead of startdir.
		catdir = reposplit[-2]
		if catdir not in settings.categories:
			logging.warn(
				'%s is not a valid category according to profiles/categories, '
				'skipping checks in %s' % (catdir, catdir))
		else:
			scanlist = AddPackagesInDir(catdir)
	elif repolevel == 3:  # pkgdir level, startdir = pkgdir
		catdir = reposplit[-2]
		pkgdir = reposplit[-1]
		if catdir not in settings.categories:
			logging.warn(
				'%s is not a valid category according to profiles/categories, '
				'skipping checks in %s' % (catdir, catdir))
		else:
			path = os.path.join(catdir, pkgdir)
			logging.debug('adding %s to scanlist' % path)
			scanlist.append(path)
	return scanlist


def editor_is_executable(editor):
	"""
	Given an EDITOR string, validate that it refers to
	an executable. This uses shlex_split() to split the
	first component and do a PATH lookup if necessary.

	@param editor: An EDITOR value from the environment.
	@type: string
	@rtype: bool
	@return: True if an executable is found, False otherwise.
	"""
	editor_split = util.shlex_split(editor)
	if not editor_split:
		return False
	filename = editor_split[0]
	if not os.path.isabs(filename):
		return find_binary(filename) is not None
	return os.access(filename, os.X_OK) and os.path.isfile(filename)


def get_commit_message_with_editor(editor, message=None, prefix=""):
	"""
	Execute editor with a temporary file as it's argument
	and return the file content afterwards.

	@param editor: An EDITOR value from the environment
	@type: string
	@param message: An iterable of lines to show in the editor.
	@type: iterable
	@param prefix: Suggested prefix for the commit message summary line.
	@type: string
	@rtype: string or None
	@return: A string on success or None if an error occurs.
	"""
	commitmessagedir = tempfile.mkdtemp(".repoman.msg")
	filename = os.path.join(commitmessagedir, "COMMIT_EDITMSG")
	try:
		with open(filename, "wb") as mymsg:
			mymsg.write(
				_unicode_encode(_(
					prefix +
					"\n\n# Please enter the commit message "
					"for your changes.\n# (Comment lines starting "
					"with '#' will not be included)\n"),
					encoding=_encodings['content'], errors='backslashreplace'))
			if message:
				mymsg.write(b"#\n")
				for line in message:
					mymsg.write(
						_unicode_encode(
							"#" + line, encoding=_encodings['content'],
							errors='backslashreplace'))
		retval = os.system(editor + " '%s'" % filename)
		if not (os.WIFEXITED(retval) and os.WEXITSTATUS(retval) == os.EX_OK):
			return None
		try:
			with io.open(_unicode_encode(
				filename, encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace') as f:
				mylines = f.readlines()
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			return None
		return "".join(line for line in mylines if not line.startswith("#"))
	finally:
		try:
			shutil.rmtree(commitmessagedir)
		except OSError:
			pass


def FindPortdir(settings):
	""" Try to figure out what repo we are in and whether we are in a regular
	tree or an overlay.

	Basic logic is:

	1. Determine what directory we are in (supports symlinks).
	2. Build a list of directories from / to our current location
	3. Iterate over PORTDIR_OVERLAY, if we find a match,
	search for a profiles directory in the overlay.  If it has one,
	make it portdir, otherwise make it portdir_overlay.
	4. If we didn't find an overlay in PORTDIR_OVERLAY,
	see if we are in PORTDIR; if so, set portdir_overlay to PORTDIR.
	If we aren't in PORTDIR, see if PWD has a profiles dir, if so,
	set portdir_overlay and portdir to PWD, else make them False.
	5. If we haven't found portdir_overlay yet,
	it means the user is doing something odd, report an error.
	6. If we haven't found a portdir yet, set portdir to PORTDIR.

	Args:
		settings - portage.config instance, preferably repoman_settings
	Returns:
		list(portdir, portdir_overlay, location)
	"""

	portdir = None
	portdir_overlay = None
	location = os.getcwd()
	pwd = _unicode_decode(os.environ.get('PWD', ''), encoding=_encodings['fs'])
	if pwd and pwd != location and os.path.realpath(pwd) == location:
		# getcwd() returns the canonical path but that makes it hard for repoman to
		# orient itself if the user has symlinks in their repository structure.
		# We use os.environ["PWD"], if available, to get the non-canonical path of
		# the current working directory (from the shell).
		location = pwd

	location = normalize_path(location)

	path_ids = {}
	p = location
	s = None
	while True:
		s = os.stat(p)
		path_ids[(s.st_dev, s.st_ino)] = p
		if p == "/":
			break
		p = os.path.dirname(p)
	if location[-1] != "/":
		location += "/"

	for overlay in portage.util.shlex_split(settings["PORTDIR_OVERLAY"]):
		overlay = os.path.realpath(overlay)
		try:
			s = os.stat(overlay)
		except OSError:
			continue
		overlay = path_ids.get((s.st_dev, s.st_ino))
		if overlay is None:
			continue
		if overlay[-1] != "/":
			overlay += "/"
		if True:
			portdir_overlay = overlay
			subdir = location[len(overlay):]
			if subdir and subdir[-1] != "/":
				subdir += "/"
			if have_profile_dir(location, subdir.count("/")):
				portdir = portdir_overlay
			break

	# Couldn't match location with anything from PORTDIR_OVERLAY,
	# so fall back to have_profile_dir() checks alone. Assume that
	# an overlay will contain at least a "repo_name" file while a
	# master repo (portdir) will contain at least a "profiles.desc"
	# file.
	if not portdir_overlay:
		portdir_overlay = have_profile_dir(location, filename="repo_name")
		if not portdir_overlay:
			portdir_overlay = have_ebuild_dir(location)
		if portdir_overlay:
			subdir = location[len(portdir_overlay):]
			if subdir and subdir[-1] != os.sep:
				subdir += os.sep
			if have_profile_dir(location, subdir.count(os.sep)):
				portdir = portdir_overlay

	if not portdir_overlay:
		if (settings["PORTDIR"] + os.path.sep).startswith(location):
			portdir_overlay = settings["PORTDIR"]
		else:
			portdir_overlay = have_profile_dir(location)
		portdir = portdir_overlay

	if not portdir_overlay:
		msg = 'Repoman is unable to determine PORTDIR or PORTDIR_OVERLAY' + \
			' from the current working directory'
		logging.critical(msg)
		return (None, None, None)

	if not portdir:
		portdir = settings["PORTDIR"]

	if not portdir_overlay.endswith('/'):
		portdir_overlay += '/'

	if not portdir.endswith('/'):
		portdir += '/'

	return [normalize_path(x) for x in (portdir, portdir_overlay, location)]


def get_committer_name(env=None):
	"""Generate a committer string like echangelog does."""
	if env is None:
		env = os.environ
	if 'GENTOO_COMMITTER_NAME' in env and 'GENTOO_COMMITTER_EMAIL' in env:
		user = '%s <%s>' % (
			env['GENTOO_COMMITTER_NAME'],
			env['GENTOO_COMMITTER_EMAIL'])
	elif 'GENTOO_AUTHOR_NAME' in env and 'GENTOO_AUTHOR_EMAIL' in env:
		user = '%s <%s>' % (
			env['GENTOO_AUTHOR_NAME'],
			env['GENTOO_AUTHOR_EMAIL'])
	elif 'ECHANGELOG_USER' in env:
		user = env['ECHANGELOG_USER']
	else:
		pwd_struct = pwd.getpwuid(os.getuid())
		gecos = pwd_struct.pw_gecos.split(',')[0]  # bug #80011
		user = '%s <%s@gentoo.org>' % (gecos, pwd_struct.pw_name)
	return user


def UpdateChangeLog(
	pkgdir, user, msg, skel_path, category, package,
	new=(), removed=(), changed=(), pretend=False, quiet=False):
	"""
	Write an entry to an existing ChangeLog, or create a new one.
	Updates copyright year on changed files, and updates the header of
	ChangeLog with the contents of skel.ChangeLog.
	"""

	if '<root@' in user:
		if not quiet:
			logging.critical('Please set ECHANGELOG_USER or run as non-root')
		return None

	# ChangeLog times are in UTC
	gmtime = time.gmtime()
	year = time.strftime('%Y', gmtime)
	date = time.strftime('%d %b %Y', gmtime)

	cl_path = os.path.join(pkgdir, 'ChangeLog')
	clold_lines = []
	clnew_lines = []
	old_header_lines = []
	header_lines = []

	clold_file = None
	try:
		clold_file = io.open(_unicode_encode(
			cl_path, encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace')
	except EnvironmentError:
		pass

	f, clnew_path = tempfile.mkstemp()

	# construct correct header first
	try:
		if clold_file is not None:
			# retain header from old ChangeLog
			first_line = True
			for line in clold_file:
				line_strip = line.strip()
				if line_strip and line[:1] != "#":
					clold_lines.append(line)
					break
				# always make sure cat/pkg is up-to-date in case we are
				# moving packages around, or copied from another pkg, or ...
				if first_line:
					if line.startswith('# ChangeLog for'):
						line = '# ChangeLog for %s/%s\n' % (category, package)
					first_line = False
				old_header_lines.append(line)
				header_lines.append(update_copyright_year(year, line))
				if not line_strip:
					break

		clskel_file = None
		if not header_lines:
			# delay opening this until we find we need a header
			try:
				clskel_file = io.open(_unicode_encode(
					skel_path, encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'],
					errors='replace')
			except EnvironmentError:
				pass

		if clskel_file is not None:
			# read skel.ChangeLog up to first empty line
			for line in clskel_file:
				line_strip = line.strip()
				if not line_strip:
					break
				line = line.replace('<CATEGORY>', category)
				line = line.replace('<PACKAGE_NAME>', package)
				line = update_copyright_year(year, line)
				header_lines.append(line)
			header_lines.append('\n')
			clskel_file.close()

		# write new ChangeLog entry
		clnew_lines.extend(header_lines)
		newebuild = False
		for fn in new:
			if not fn.endswith('.ebuild'):
				continue
			ebuild = fn.split(os.sep)[-1][0:-7]
			clnew_lines.append('*%s (%s)\n' % (ebuild, date))
			newebuild = True
		if newebuild:
			clnew_lines.append('\n')
		trivial_files = ('ChangeLog', 'Manifest')
		display_new = [
			'+' + elem
			for elem in new
			if elem not in trivial_files]
		display_removed = [
			'-' + elem
			for elem in removed]
		display_changed = [
			elem for elem in changed
			if elem not in trivial_files]
		if not (display_new or display_removed or display_changed):
			# If there's nothing else to display, show one of the
			# trivial files.
			for fn in trivial_files:
				if fn in new:
					display_new = ['+' + fn]
					break
				elif fn in changed:
					display_changed = [fn]
					break

		display_new.sort()
		display_removed.sort()
		display_changed.sort()

		mesg = '%s; %s %s:' % (date, user, ', '.join(chain(
			display_new, display_removed, display_changed)))
		for line in textwrap.wrap(
			mesg, 80, initial_indent='  ', subsequent_indent='  ',
			break_on_hyphens=False):
			clnew_lines.append('%s\n' % line)
		for line in textwrap.wrap(
			msg, 80, initial_indent='  ', subsequent_indent='  '):
			clnew_lines.append('%s\n' % line)
		# Don't append a trailing newline if the file is new.
		if clold_file is not None:
			clnew_lines.append('\n')

		f = io.open(
			f, mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace')

		for line in clnew_lines:
			f.write(line)

		# append stuff from old ChangeLog
		if clold_file is not None:

			if clold_lines:
				# clold_lines may contain a saved non-header line
				# that we want to write first.
				# Also, append this line to clnew_lines so that the
				# unified_diff call doesn't show it as removed.
				for line in clold_lines:
					f.write(line)
					clnew_lines.append(line)

			else:
				# ensure that there is no more than one blank
				# line after our new entry
				for line in clold_file:
					if line.strip():
						f.write(line)
						break

			# Now prepend old_header_lines to clold_lines, for use
			# in the unified_diff call below.
			clold_lines = old_header_lines + clold_lines

			# Trim any trailing newlines.
			lines = clold_file.readlines()
			clold_file.close()
			while lines and lines[-1] == '\n':
				del lines[-1]
			f.writelines(lines)
		f.close()

		# show diff
		if not quiet:
			for line in difflib.unified_diff(
				clold_lines, clnew_lines,
				fromfile=cl_path, tofile=cl_path, n=0):
				util.writemsg_stdout(line, noiselevel=-1)
			util.writemsg_stdout("\n", noiselevel=-1)

		if pretend:
			# remove what we've done
			os.remove(clnew_path)
		else:
			# rename to ChangeLog, and set permissions
			try:
				clold_stat = os.stat(cl_path)
			except OSError:
				clold_stat = None

			shutil.move(clnew_path, cl_path)

			if clold_stat is None:
				util.apply_permissions(cl_path, mode=0o644)
			else:
				util.apply_stat_permissions(cl_path, clold_stat)

		if clold_file is None:
			return True
		else:
			return False
	except IOError as e:
		err = 'Repoman is unable to create/write to Changelog.new file: %s' % (e,)
		logging.critical(err)
		# try to remove if possible
		try:
			os.remove(clnew_path)
		except OSError:
			pass
		return None


def repoman_sez(msg):
	print (green("RepoMan sez:"), msg)
