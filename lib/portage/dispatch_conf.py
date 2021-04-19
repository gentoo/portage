# archive_conf.py -- functionality common to archive-conf and dispatch-conf
# Copyright 2003-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# Library by Wayne Davison <gentoo@blorf.net>, derived from code
# written by Jeremy Wohl (http://igmus.org)

import errno
import io
import functools
import stat
import subprocess
import sys
import tempfile

import portage
from portage import _encodings, os, shutil
from portage.env.loaders import KeyValuePairFileLoader
from portage.localization import _
from portage.util import shlex_split, varexpand
from portage.util.path import iter_parents

RCS_BRANCH = '1.1.1'
RCS_LOCK = 'rcs -ko -M -l'
RCS_PUT = 'ci -t-"Archived config file." -m"dispatch-conf update."'
RCS_GET = 'co'
RCS_MERGE = "rcsmerge -p -r" + RCS_BRANCH + " '%s' > '%s'"

DIFF3_MERGE = "diff3 -mE '%s' '%s' '%s' > '%s'"
_ARCHIVE_ROTATE_MAX = 9

def diffstatusoutput(cmd, file1, file2):
	"""
	Execute the string cmd in a shell with getstatusoutput() and return a
	2-tuple (status, output).
	"""
	# Use Popen to emulate getstatusoutput(), since getstatusoutput() may
	# raise a UnicodeDecodeError which makes the output inaccessible.
	args = shlex_split(cmd % (file1, file2))

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

class diff_mixed_wrapper:

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
		print(_('dispatch-conf: Error reading {}; fatal').format(config_path), file=sys.stderr)
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

def _archive_copy(src_st, src_path, dest_path):
	"""
	Copy file from src_path to dest_path. Regular files and symlinks
	are supported. If an EnvironmentError occurs, then it is logged
	to stderr.

	@param src_st: source file lstat result
	@type src_st: posix.stat_result
	@param src_path: source file path
	@type src_path: str
	@param dest_path: destination file path
	@type dest_path: str
	"""
	# Remove destination file in order to ensure that the following
	# symlink or copy2 call won't fail (see bug #535850).
	try:
		os.unlink(dest_path)
	except OSError:
		pass
	try:
		if stat.S_ISLNK(src_st.st_mode):
			os.symlink(os.readlink(src_path), dest_path)
		else:
			shutil.copy2(src_path, dest_path)
	except EnvironmentError as e:
		portage.util.writemsg(
			_('dispatch-conf: Error copying %(src_path)s to '
			'%(dest_path)s: %(reason)s\n') % {
				"src_path": src_path,
				"dest_path": dest_path,
				"reason": e
			}, noiselevel=-1)

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
		_archive_copy(curconf_st, curconf, archive)

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

		_archive_copy(mystat, newconf, archive)

		if has_branch:
			if mrgconf and os.path.isfile(archive) and \
				os.path.isfile(mrgconf):
				# This puts the results of the merge into mrgconf.
				ret = os.system(RCS_MERGE % (archive, mrgconf))
				os.chmod(mrgconf, mystat.st_mode)
				os.chown(mrgconf, mystat.st_uid, mystat.st_gid)
		os.rename(archive, archive + '.dist.new')

	return ret

def _file_archive_rotate(archive):
	"""
	Rename archive to archive + '.1', and perform similar rotation
	for files up to archive + '.9'.

	@param archive: file path to archive
	@type archive: str
	"""

	max_suf = 0
	try:
		for max_suf, max_st, max_path in (
			(suf, os.lstat(path), path) for suf, path in (
			(suf, "%s.%s" % (archive, suf)) for suf in range(
			1, _ARCHIVE_ROTATE_MAX + 1))):
			pass
	except OSError as e:
		if e.errno not in (errno.ENOENT, errno.ESTALE):
			raise
		# There's already an unused suffix.
	else:
		# Free the max suffix in order to avoid possible problems
		# when we rename another file or directory to the same
		# location (see bug 256376).
		if stat.S_ISDIR(max_st.st_mode):
			# Removing a directory might destroy something important,
			# so rename it instead.
			head, tail = os.path.split(archive)
			placeholder = tempfile.NamedTemporaryFile(
				prefix="%s." % tail,
				dir=head)
			placeholder.close()
			os.rename(max_path, placeholder.name)
		else:
			os.unlink(max_path)

		# The max suffix is now unused.
		max_suf -= 1

	for suf in range(max_suf + 1, 1, -1):
		os.rename("%s.%s" % (archive, suf - 1), "%s.%s" % (archive, suf))

	os.rename(archive, "%s.1" % (archive,))

def _file_archive_ensure_dir(parent_dir):
	"""
	Ensure that the parent directory for an archive exists.
	If a file exists where a directory is needed, then rename
	it (see bug 256376).

	@param parent_dir: path of parent directory
	@type parent_dir: str
	"""

	for parent in iter_parents(parent_dir):
		# Use lstat because a symlink to a directory might point
		# to a directory outside of the config archive, making
		# it an unsuitable parent.
		try:
			parent_st = os.lstat(parent)
		except OSError:
			pass
		else:
			if not stat.S_ISDIR(parent_st.st_mode):
				_file_archive_rotate(parent)
			break

	try:
		os.makedirs(parent_dir)
	except OSError:
		pass

def file_archive(archive, curconf, newconf, mrgconf):
	"""Archive existing config to the archive-dir, bumping old versions
	out of the way into .# versions (log-rotate style). Then, if mrgconf
	was specified and there is a .dist version, merge the user's changes
	and the distributed changes and put the result into mrgconf.  Lastly,
	if newconf was specified, archive it as a .dist.new version (which
	gets moved to the .dist version at the end of the processing)."""

	_file_archive_ensure_dir(os.path.dirname(archive))

	# Archive the current config file if it isn't already saved
	if (os.path.lexists(archive) and
		len(diffstatusoutput_mixed(
		"diff -aq '%s' '%s'", curconf, archive)[1]) != 0):
		_file_archive_rotate(archive)

	try:
		curconf_st = os.lstat(curconf)
	except OSError:
		curconf_st = None

	if curconf_st is not None and \
		(stat.S_ISREG(curconf_st.st_mode) or
		stat.S_ISLNK(curconf_st.st_mode)):
		_archive_copy(curconf_st, curconf, archive)

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
		if os.path.isdir(newconf_archive
			) and not os.path.islink(newconf_archive):
			_file_archive_rotate(newconf_archive)
		_archive_copy(mystat, newconf, newconf_archive)

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
		dest = "%s.dist" % archive
		if os.path.isdir(dest) and not os.path.islink(dest):
			_file_archive_rotate(dest)
		os.rename(archive + '.dist.new', dest)
