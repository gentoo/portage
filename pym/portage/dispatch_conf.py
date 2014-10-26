# archive_conf.py -- functionality common to archive-conf and dispatch-conf
# Copyright 2003-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


# Library by Wayne Davison <gentoo@blorf.net>, derived from code
# written by Jeremy Wohl (http://igmus.org)

from __future__ import print_function, unicode_literals

import io
import functools
import os
import shutil
import stat
import subprocess
import sys
import tempfile

import portage
from portage import _encodings
from portage.env.loaders import KeyValuePairFileLoader
from portage.localization import _
from portage.util import shlex_split, varexpand

RCS_BRANCH = '1.1.1'
RCS_LOCK = 'rcs -ko -M -l'
RCS_PUT = 'ci -t-"Archived config file." -m"dispatch-conf update."'
RCS_GET = 'co'
RCS_MERGE = "rcsmerge -p -r" + RCS_BRANCH + " '%s' > '%s'"

DIFF3_MERGE = "diff3 -mE '%s' '%s' '%s' > '%s'"

def diffstatusoutput(cmd, file1, file2):
	"""
	Execute the string cmd in a shell with getstatusoutput() and return a
	2-tuple (status, output).
	"""
	# Use Popen to emulate getstatusoutput(), since getstatusoutput() may
	# raise a UnicodeDecodeError which makes the output inaccessible.
	args = shlex_split(cmd % (file1, file2))

	if sys.hexversion < 0x3020000 and sys.hexversion >= 0x3000000 and \
		not os.path.isabs(args[0]):
		# Python 3.1 _execvp throws TypeError for non-absolute executable
		# path passed as bytes (see http://bugs.python.org/issue8513).
		fullname = portage.process.find_binary(args[0])
		if fullname is None:
			raise portage.exception.CommandNotFound(args[0])
		args[0] = fullname

	args = [portage._unicode_encode(x, errors='strict') for x in args]
	proc = subprocess.Popen(args,
		stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	output = portage._unicode_decode(proc.communicate()[0])
	if output and output[-1] == "\n":
		# getstatusoutput strips one newline
		output = output[:-1]
	return (proc.wait(), output)

def diff_mixed(func, file1, file2):
	tempdir = None
	try:
		if os.path.islink(file1) and \
			not os.path.islink(file2) and \
			os.path.isfile(file1) and \
			os.path.isfile(file2):
			# If a regular file replaces a symlink to a regular
			# file, then show the diff between the regular files
			# (bug #330221).
			diff_files = (file2, file2)
		else:
			files = [file1, file2]
			diff_files = [file1, file2]
			for i in range(len(diff_files)):
				try:
					st = os.lstat(diff_files[i])
				except OSError:
					st = None
				if st is not None and stat.S_ISREG(st.st_mode):
					continue

				if tempdir is None:
					tempdir = tempfile.mkdtemp()
				diff_files[i] = os.path.join(tempdir, "%d" % i)
				if st is None:
					content = "/dev/null\n"
				elif stat.S_ISLNK(st.st_mode):
					link_dest = os.readlink(files[i])
					content = "SYM: %s -> %s\n" % \
						(file1, link_dest)
				elif stat.S_ISDIR(st.st_mode):
					content = "DIR: %s\n" % (file1,)
				elif stat.S_ISFIFO(st.st_mode):
					content = "FIF: %s\n" % (file1,)
				else:
					content = "DEV: %s\n" % (file1,)
				with io.open(diff_files[i], mode='w',
					encoding=_encodings['stdio']) as f:
					f.write(content)

		return func(diff_files[0], diff_files[1])

	finally:
		if tempdir is not None:
			shutil.rmtree(tempdir)

class diff_mixed_wrapper(object):

	def __init__(self, f, *args):
		self._func = f
		self._args = args

	def __call__(self, *args):
		return diff_mixed(
			functools.partial(self._func, *(self._args + args[:-2])),
			*args[-2:])

diffstatusoutput_mixed = diff_mixed_wrapper(diffstatusoutput)

def read_config(mandatory_opts):
	eprefix = portage.settings["EPREFIX"]
	if portage._not_installed:
		config_path = os.path.join(portage.PORTAGE_BASE_PATH, "cnf", "dispatch-conf.conf")
	else:
		config_path = os.path.join(eprefix or os.sep, "etc/dispatch-conf.conf")
	loader = KeyValuePairFileLoader(config_path, None)
	opts, _errors = loader.load()
	if not opts:
		print(_('dispatch-conf: Error reading /etc/dispatch-conf.conf; fatal'), file=sys.stderr)
		sys.exit(1)

	# Handle quote removal here, since KeyValuePairFileLoader doesn't do that.
	quotes = "\"'"
	for k, v in opts.items():
		if v[:1] in quotes and v[:1] == v[-1:]:
			opts[k] = v[1:-1]

	for key in mandatory_opts:
		if key not in opts:
			if key == "merge":
				opts["merge"] = "sdiff --suppress-common-lines --output='%s' '%s' '%s'"
			else:
				print(_('dispatch-conf: Missing option "%s" in /etc/dispatch-conf.conf; fatal') % (key,), file=sys.stderr)

	# archive-dir supports ${EPREFIX} expansion, in order to avoid hardcoding
	variables = {"EPREFIX": eprefix}
	opts['archive-dir'] = varexpand(opts['archive-dir'], mydict=variables)

	if not os.path.exists(opts['archive-dir']):
		os.mkdir(opts['archive-dir'])
		# Use restrictive permissions by default, in order to protect
		# against vulnerabilities (like bug #315603 involving rcs).
		os.chmod(opts['archive-dir'], 0o700)
	elif not os.path.isdir(opts['archive-dir']):
		print(_('dispatch-conf: Config archive dir [%s] must exist; fatal') % (opts['archive-dir'],), file=sys.stderr)
		sys.exit(1)

	return opts


def rcs_archive(archive, curconf, newconf, mrgconf):
	"""Archive existing config in rcs (on trunk). Then, if mrgconf is
	specified and an old branch version exists, merge the user's changes
	and the distributed changes and put the result into mrgconf.  Lastly,
	if newconf was specified, leave it in the archive dir with a .dist.new
	suffix along with the last 1.1.1 branch version with a .dist suffix."""

	try:
		os.makedirs(os.path.dirname(archive))
	except OSError:
		pass

	try:
		curconf_st = os.lstat(curconf)
	except OSError:
		curconf_st = None

	if curconf_st is not None and \
		(stat.S_ISREG(curconf_st.st_mode) or
		stat.S_ISLNK(curconf_st.st_mode)):
		try:
			if stat.S_ISLNK(curconf_st.st_mode):
				os.symlink(os.readlink(curconf), archive)
			else:
				shutil.copy2(curconf, archive)
		except(IOError, os.error) as why:
			print(_('dispatch-conf: Error copying %(curconf)s to %(archive)s: %(reason)s; fatal') % \
				{"curconf": curconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

	if os.path.lexists(archive + ',v'):
		os.system(RCS_LOCK + ' ' + archive)
	os.system(RCS_PUT + ' ' + archive)

	ret = 0
	mystat = None
	if newconf:
		try:
			mystat = os.lstat(newconf)
		except OSError:
			pass

	if mystat is not None and \
		(stat.S_ISREG(mystat.st_mode) or
		stat.S_ISLNK(mystat.st_mode)):
		os.system(RCS_GET + ' -r' + RCS_BRANCH + ' ' + archive)
		has_branch = os.path.lexists(archive)
		if has_branch:
			os.rename(archive, archive + '.dist')

		try:
			if stat.S_ISLNK(mystat.st_mode):
				os.symlink(os.readlink(newconf), archive)
			else:
				shutil.copy2(newconf, archive)
		except(IOError, os.error) as why:
			print(_('dispatch-conf: Error copying %(newconf)s to %(archive)s: %(reason)s; fatal') % \
				{"newconf": newconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

		if has_branch:
			if mrgconf and os.path.isfile(archive) and \
				os.path.isfile(mrgconf):
				# This puts the results of the merge into mrgconf.
				ret = os.system(RCS_MERGE % (archive, mrgconf))
				os.chmod(mrgconf, mystat.st_mode)
				os.chown(mrgconf, mystat.st_uid, mystat.st_gid)
		os.rename(archive, archive + '.dist.new')

	return ret


def file_archive(archive, curconf, newconf, mrgconf):
	"""Archive existing config to the archive-dir, bumping old versions
	out of the way into .# versions (log-rotate style). Then, if mrgconf
	was specified and there is a .dist version, merge the user's changes
	and the distributed changes and put the result into mrgconf.  Lastly,
	if newconf was specified, archive it as a .dist.new version (which
	gets moved to the .dist version at the end of the processing)."""

	try:
		os.makedirs(os.path.dirname(archive))
	except OSError:
		pass

	# Archive the current config file if it isn't already saved
	if (os.path.lexists(archive) and
		len(diffstatusoutput_mixed(
		"diff -aq '%s' '%s'", curconf, archive)[1]) != 0):
		suf = 1
		while suf < 9 and os.path.lexists(archive + '.' + str(suf)):
			suf += 1

		while suf > 1:
			os.rename(archive + '.' + str(suf-1), archive + '.' + str(suf))
			suf -= 1

		os.rename(archive, archive + '.1')

	try:
		curconf_st = os.lstat(curconf)
	except OSError:
		curconf_st = None

	if curconf_st is not None and \
		(stat.S_ISREG(curconf_st.st_mode) or
		stat.S_ISLNK(curconf_st.st_mode)):
		try:
			if stat.S_ISLNK(curconf_st.st_mode):
				os.symlink(os.readlink(curconf), archive)
			else:
				shutil.copy2(curconf, archive)
		except(IOError, os.error) as why:
			print(_('dispatch-conf: Error copying %(curconf)s to %(archive)s: %(reason)s; fatal') % \
				{"curconf": curconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

	mystat = None
	if newconf:
		try:
			mystat = os.lstat(newconf)
		except OSError:
			pass

	if mystat is not None and \
		(stat.S_ISREG(mystat.st_mode) or
		stat.S_ISLNK(mystat.st_mode)):
		# Save off new config file in the archive dir with .dist.new suffix
		newconf_archive = archive + '.dist.new'
		try:
			if stat.S_ISLNK(mystat.st_mode):
				os.symlink(os.readlink(newconf), newconf_archive)
			else:
				shutil.copy2(newconf, newconf_archive)
		except(IOError, os.error) as why:
			print(_('dispatch-conf: Error copying %(newconf)s to %(archive)s: %(reason)s; fatal') % \
				{"newconf": newconf, "archive": archive + '.dist.new', "reason": str(why)}, file=sys.stderr)

		ret = 0
		if mrgconf and os.path.isfile(curconf) and \
			os.path.isfile(newconf) and \
			os.path.isfile(archive + '.dist'):
			# This puts the results of the merge into mrgconf.
			ret = os.system(DIFF3_MERGE % (curconf, archive + '.dist', newconf, mrgconf))
			os.chmod(mrgconf, mystat.st_mode)
			os.chown(mrgconf, mystat.st_uid, mystat.st_gid)

		return ret


def rcs_archive_post_process(archive):
	"""Check in the archive file with the .dist.new suffix on the branch
	and remove the one with the .dist suffix."""
	os.rename(archive + '.dist.new', archive)
	if os.path.lexists(archive + '.dist'):
		# Commit the last-distributed version onto the branch.
		os.system(RCS_LOCK + RCS_BRANCH + ' ' + archive)
		os.system(RCS_PUT + ' -r' + RCS_BRANCH + ' ' + archive)
		os.unlink(archive + '.dist')
	else:
		# Forcefully commit the last-distributed version onto the branch.
		os.system(RCS_PUT + ' -f -r' + RCS_BRANCH + ' ' + archive)


def file_archive_post_process(archive):
	"""Rename the archive file with the .dist.new suffix to a .dist suffix"""
	if os.path.lexists(archive + '.dist.new'):
		os.rename(archive + '.dist.new', archive + '.dist')
