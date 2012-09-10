# repoman: Utilities
# Copyright 2007-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains utility functions to help repoman find ebuilds to
scan"""

from __future__ import print_function

__all__ = [
	"detect_vcs_conflicts",
	"editor_is_executable",
	"FindPackagesToScan",
	"FindPortdir",
	"FindVCS",
	"format_qa_output",
	"get_commit_message_with_editor",
	"get_commit_message_with_stdin",
	"get_committer_name",
	"have_ebuild_dir",
	"have_profile_dir",
	"parse_metadata_use",
	"UnknownHerdsError",
	"check_metadata",
	"UpdateChangeLog"
]

import errno
import io
from itertools import chain
import logging
import pwd
import re
import stat
import sys
import subprocess
import time
import textwrap
import difflib
from tempfile import mkstemp

from portage import os
from portage import shutil
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage import output
from portage.const import BASH_BINARY
from portage.localization import _
from portage.output import red, green
from portage.process import find_binary
from portage import exception
from portage import util
normalize_path = util.normalize_path
util.initialize_logger()

if sys.hexversion >= 0x3000000:
	basestring = str

def detect_vcs_conflicts(options, vcs):
	"""Determine if the checkout has problems like cvs conflicts.
	
	If you want more vcs support here just keep adding if blocks...
	This could be better.
	
	TODO(antarus): Also this should probably not call sys.exit() as
	repoman is run on >1 packages and one failure should not cause
	subsequent packages to fail.
	
	Args:
		vcs - A string identifying the version control system in use
	Returns:
		None (calls sys.exit on fatal problems)
	"""

	cmd = None
	if vcs == 'cvs':
		logging.info("Performing a " + output.green("cvs -n up") + \
			" with a little magic grep to check for updates.")
		cmd = "cvs -n up 2>/dev/null | " + \
			"egrep '^[^\?] .*' | " + \
			"egrep -v '^. .*/digest-[^/]+|^cvs server: .* -- ignored$'"
	if vcs == 'svn':
		logging.info("Performing a " + output.green("svn status -u") + \
			" with a little magic grep to check for updates.")
		cmd = "svn status -u 2>&1 | " + \
			"egrep -v '^.  +.*/digest-[^/]+' | " + \
			"head -n-1"

	if cmd is not None:
		# Use Popen instead of getstatusoutput(), in order to avoid
		# unicode handling problems (see bug #310789).
		args = [BASH_BINARY, "-c", cmd]
		if sys.hexversion < 0x3000000 or sys.hexversion >= 0x3020000:
			# Python 3.1 does not support bytes in Popen args.
			args = [_unicode_encode(x) for x in args]
		proc = subprocess.Popen(args, stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT)
		out = _unicode_decode(proc.communicate()[0])
		proc.wait()
		mylines = out.splitlines()
		myupdates = []
		for line in mylines:
			if not line:
				continue
			if line[0] not in " UPMARD": # unmodified(svn),Updates,Patches,Modified,Added,Removed/Replaced(svn),Deleted(svn)
				# Stray Manifest is fine, we will readd it anyway.
				if line[0] == '?' and line[1:].lstrip() == 'Manifest':
					continue
				logging.error(red("!!! Please fix the following issues reported " + \
					"from cvs: ")+green("(U,P,M,A,R,D are ok)"))
				logging.error(red("!!! Note: This is a pretend/no-modify pass..."))
				logging.error(out)
				sys.exit(1)
			elif vcs == 'cvs' and line[0] in "UP":
				myupdates.append(line[2:])
			elif vcs == 'svn' and line[8] == '*':
				myupdates.append(line[9:].lstrip(" 1234567890"))

		if myupdates:
			logging.info(green("Fetching trivial updates..."))
			if options.pretend:
				logging.info("(" + vcs + " update " + " ".join(myupdates) + ")")
				retval = os.EX_OK
			else:
				retval = os.system(vcs + " update " + " ".join(myupdates))
			if retval != os.EX_OK:
				logging.fatal("!!! " + vcs + " exited with an error. Terminating.")
				sys.exit(retval)


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

def parse_metadata_use(xml_tree):
	"""
	Records are wrapped in XML as per GLEP 56
	returns a dict with keys constisting of USE flag names and values
	containing their respective descriptions
	"""
	uselist = {}

	usetags = xml_tree.findall("use")
	if not usetags:
		return uselist

	# It's possible to have multiple 'use' elements.
	for usetag in usetags:
		flags = usetag.findall("flag")
		if not flags:
			# DTD allows use elements containing no flag elements.
			continue

		for flag in flags:
			pkg_flag = flag.get("name")
			if pkg_flag is None:
				raise exception.ParseError("missing 'name' attribute for 'flag' tag")
			flag_restrict = flag.get("restrict")

			# emulate the Element.itertext() method from python-2.7
			inner_text = []
			stack = []
			stack.append(flag)
			while stack:
				obj = stack.pop()
				if isinstance(obj, basestring):
					inner_text.append(obj)
					continue
				if isinstance(obj.text, basestring):
					inner_text.append(obj.text)
				if isinstance(obj.tail, basestring):
					stack.append(obj.tail)
				stack.extend(reversed(obj))

			if pkg_flag not in uselist:
				uselist[pkg_flag] = {}

			# (flag_restrict can be None)
			uselist[pkg_flag][flag_restrict] = " ".join("".join(inner_text).split())

	return uselist

class UnknownHerdsError(ValueError):
	def __init__(self, herd_names):
		_plural = len(herd_names) != 1
		super(UnknownHerdsError, self).__init__(
			'Unknown %s %s' % (_plural and 'herds' or 'herd',
			','.join('"%s"' % e for e in herd_names)))


def check_metadata_herds(xml_tree, herd_base):
	herd_nodes = xml_tree.findall('herd')
	unknown_herds = [name for name in
			(e.text.strip() for e in herd_nodes if e.text is not None)
			if not herd_base.known_herd(name)]

	if unknown_herds:
		raise UnknownHerdsError(unknown_herds)

def check_metadata(xml_tree, herd_base):
	if herd_base is not None:
		check_metadata_herds(xml_tree, herd_base)

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
	if repolevel == 1: # root of the tree, startdir = repodir
		for cat in settings.categories:
			path = os.path.join(startdir, cat)
			if not os.path.isdir(path):
				continue
			pkgdirs = os.listdir(path)
			scanlist.extend(AddPackagesInDir(path))
	elif repolevel == 2: # category level, startdir = catdir
		# we only want 1 segment of the directory, is why we use catdir instead of startdir
		catdir = reposplit[-2]
		if catdir not in settings.categories:
			logging.warn('%s is not a valid category according to profiles/categories, ' \
				'skipping checks in %s' % (catdir, catdir))
		else:
			scanlist = AddPackagesInDir(catdir)
	elif repolevel == 3: # pkgdir level, startdir = pkgdir
		catdir = reposplit[-2]
		pkgdir = reposplit[-1]
		if catdir not in settings.categories:
			logging.warn('%s is not a valid category according to profiles/categories, ' \
			'skipping checks in %s' % (catdir, catdir))
		else:
			path = os.path.join(catdir, pkgdir)
			logging.debug('adding %s to scanlist' % path)
			scanlist.append(path)
	return scanlist


def format_qa_output(formatter, stats, fails, dofull, dofail, options, qawarnings):
	"""Helper function that formats output properly
	
	Args:
		formatter - a subclass of Formatter
		stats - a dict of qa status items
		fails - a dict of qa status failures
		dofull - boolean to print full results or a summary
		dofail - boolean to decide if failure was hard or soft
	
	Returns:
		None (modifies formatter)
	"""
	full = options.mode == 'full'
	# we only want key value pairs where value > 0 
	for category, number in \
		filter(lambda myitem: myitem[1] > 0, iter(stats.items())):
		formatter.add_literal_data(_unicode_decode("  " + category.ljust(30)))
		if category in qawarnings:
			formatter.push_style("WARN")
		else:
			formatter.push_style("BAD")
		formatter.add_literal_data(_unicode_decode(str(number)))
		formatter.pop_style()
		formatter.add_line_break()
		if not dofull:
			if not full and dofail and category in qawarnings:
				# warnings are considered noise when there are failures
				continue
			fails_list = fails[category]
			if not full and len(fails_list) > 12:
				fails_list = fails_list[:12]
			for failure in fails_list:
				formatter.add_literal_data(_unicode_decode("   " + failure))
				formatter.add_line_break()


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


def get_commit_message_with_editor(editor, message=None):
	"""
	Execute editor with a temporary file as it's argument
	and return the file content afterwards.

	@param editor: An EDITOR value from the environment
	@type: string
	@param message: An iterable of lines to show in the editor.
	@type: iterable
	@rtype: string or None
	@return: A string on success or None if an error occurs.
	"""
	fd, filename = mkstemp()
	try:
		os.write(fd, _unicode_encode(_(
			"\n# Please enter the commit message " + \
			"for your changes.\n# (Comment lines starting " + \
			"with '#' will not be included)\n"),
			encoding=_encodings['content'], errors='backslashreplace'))
		if message:
			os.write(fd, b"#\n")
			for line in message:
				os.write(fd, _unicode_encode("#" + line,
					encoding=_encodings['content'], errors='backslashreplace'))
		os.close(fd)
		retval = os.system(editor + " '%s'" % filename)
		if not (os.WIFEXITED(retval) and os.WEXITSTATUS(retval) == os.EX_OK):
			return None
		try:
			mylines = io.open(_unicode_encode(filename,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace'
				).readlines()
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise
			del e
			return None
		return "".join(line for line in mylines if not line.startswith("#"))
	finally:
		try:
			os.unlink(filename)
		except OSError:
			pass


def get_commit_message_with_stdin():
	"""
	Read a commit message from the user and return it.

	@rtype: string or None
	@return: A string on success or None if an error occurs.
	"""
	print("Please enter a commit message. Use Ctrl-d to finish or Ctrl-c to abort.")
	commitmessage = []
	while True:
		commitmessage.append(sys.stdin.readline())
		if not commitmessage[-1]:
			break
	commitmessage = "".join(commitmessage)
	return commitmessage


def FindPortdir(settings):
	""" Try to figure out what repo we are in and whether we are in a regular
	tree or an overlay.
	
	Basic logic is:
	
	1. Determine what directory we are in (supports symlinks).
	2. Build a list of directories from / to our current location
	3. Iterate over PORTDIR_OVERLAY, if we find a match, search for a profiles directory
		 in the overlay.  If it has one, make it portdir, otherwise make it portdir_overlay.
	4. If we didn't find an overlay in PORTDIR_OVERLAY, see if we are in PORTDIR; if so, set
		 portdir_overlay to PORTDIR.  If we aren't in PORTDIR, see if PWD has a profiles dir, if
		 so, set portdir_overlay and portdir to PWD, else make them False.
	5. If we haven't found portdir_overlay yet, it means the user is doing something odd, report
		 an error.
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
		# orient itself if the user has symlinks in their portage tree structure.
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

	for overlay in settings["PORTDIR_OVERLAY"].split():
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

def FindVCS():
	""" Try to figure out in what VCS' working tree we are. """

	outvcs = []

	def seek(depth = None):
		""" Seek for VCSes that have a top-level data directory only. """
		retvcs = []
		pathprep = ''

		while depth is None or depth > 0:
			if os.path.isdir(os.path.join(pathprep, '.git')):
				retvcs.append('git')
			if os.path.isdir(os.path.join(pathprep, '.bzr')):
				retvcs.append('bzr')
			if os.path.isdir(os.path.join(pathprep, '.hg')):
				retvcs.append('hg')
			if os.path.isdir(os.path.join(pathprep, '.svn')):  # >=1.7
				retvcs.append('svn')

			if retvcs:
				break
			pathprep = os.path.join(pathprep, '..')
			if os.path.realpath(pathprep).strip('/') == '':
				break
			if depth is not None:
				depth = depth - 1

		return retvcs

	# Level zero VCS-es.
	if os.path.isdir('CVS'):
		outvcs.append('cvs')
	if os.path.isdir('.svn'):  # <1.7
		outvcs.append('svn')

	# If we already found one of 'level zeros', just take a quick look
	# at the current directory. Otherwise, seek parents till we get
	# something or reach root.
	if outvcs:
		outvcs.extend(seek(1))
	else:
		outvcs = seek()

	if len(outvcs) > 1:
		# eliminate duplicates, like for svn in bug #391199
		outvcs = list(set(outvcs))

	return outvcs

_copyright_re1 = re.compile(br'^(# Copyright \d\d\d\d)-\d\d\d\d ')
_copyright_re2 = re.compile(br'^(# Copyright )(\d\d\d\d) ')


class _copyright_repl(object):
	__slots__ = ('year',)
	def __init__(self, year):
		self.year = year
	def __call__(self, matchobj):
		if matchobj.group(2) == self.year:
			return matchobj.group(0)
		else:
			return matchobj.group(1) + matchobj.group(2) + \
				b'-' + self.year + b' '

def _update_copyright_year(year, line):
	"""
	These two regexes are taken from echangelog
	update_copyright(), except that we don't hardcode
	1999 here (in order to be more generic).
	"""
	is_bytes = isinstance(line, bytes)
	if is_bytes:
		if not line.startswith(b'# Copyright '):
			return line
	else:
		if not line.startswith('# Copyright '):
			return line

	year = _unicode_encode(year)
	line = _unicode_encode(line)

	line = _copyright_re1.sub(br'\1-' + year + b' ', line)
	line = _copyright_re2.sub(_copyright_repl(year), line)
	if not is_bytes:
		line = _unicode_decode(line)
	return line

def update_copyright(fn_path, year, pretend=False):
	"""
	Check file for a Copyright statement, and update its year.  The
	patterns used for replacing copyrights are taken from echangelog.
	Only the first lines of each file that start with a hash ('#') are
	considered, until a line is found that doesn't start with a hash.
	Files are read and written in binary mode, so that this function
	will work correctly with files encoded in any character set, as
	long as the copyright statements consist of plain ASCII.
	"""

	try:
		fn_hdl = io.open(_unicode_encode(fn_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='rb')
	except EnvironmentError:
		return

	orig_header = []
	new_header = []

	for line in fn_hdl:
		line_strip = line.strip()
		orig_header.append(line)
		if not line_strip or line_strip[:1] != b'#':
			new_header.append(line)
			break

		line = _update_copyright_year(year, line)
		new_header.append(line)

	difflines = 0
	for line in difflib.unified_diff(
		[_unicode_decode(line) for line in orig_header],
		[_unicode_decode(line) for line in new_header],
			fromfile=fn_path, tofile=fn_path, n=0):
		util.writemsg_stdout(line, noiselevel=-1)
		difflines += 1
	util.writemsg_stdout("\n", noiselevel=-1)

	# unified diff has three lines to start with
	if difflines > 3 and not pretend:
		# write new file with changed header
		f, fnnew_path = mkstemp()
		f = io.open(f, mode='wb')
		for line in new_header:
			f.write(line)
		for line in fn_hdl:
			f.write(line)
		f.close()
		try:
			fn_stat = os.stat(fn_path)
		except OSError:
			fn_stat = None

		shutil.move(fnnew_path, fn_path)

		if fn_stat is None:
			util.apply_permissions(fn_path, mode=0o644)
		else:
			util.apply_stat_permissions(fn_path, fn_stat)
	fn_hdl.close()

def get_committer_name(env=None):
	"""Generate a committer string like echangelog does."""
	if env is None:
		env = os.environ
	if 'GENTOO_COMMITTER_NAME' in env and \
		'GENTOO_COMMITTER_EMAIL' in env:
		user = '%s <%s>' % (env['GENTOO_COMMITTER_NAME'],
			env['GENTOO_COMMITTER_EMAIL'])
	elif 'GENTOO_AUTHOR_NAME' in env and \
			'GENTOO_AUTHOR_EMAIL' in env:
		user = '%s <%s>' % (env['GENTOO_AUTHOR_NAME'],
			env['GENTOO_AUTHOR_EMAIL'])
	elif 'ECHANGELOG_USER' in env:
		user = env['ECHANGELOG_USER']
	else:
		pwd_struct = pwd.getpwuid(os.getuid())
		gecos = pwd_struct.pw_gecos.split(',')[0]  # bug #80011
		user = '%s <%s@gentoo.org>' % (gecos, pwd_struct.pw_name)
	return user

def UpdateChangeLog(pkgdir, user, msg, skel_path, category, package,
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

	# check modified files and the ChangeLog for copyright updates
	# patches and diffs (identified by .patch and .diff) are excluded
	for fn in chain(new, changed):
		if fn.endswith('.diff') or fn.endswith('.patch'):
			continue
		update_copyright(os.path.join(pkgdir, fn), year, pretend=pretend)

	cl_path = os.path.join(pkgdir, 'ChangeLog')
	clold_lines = []
	clnew_lines = []
	old_header_lines = []
	header_lines = []

	clold_file = None
	try:
		clold_file = io.open(_unicode_encode(cl_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace')
	except EnvironmentError:
		pass

	f, clnew_path = mkstemp()

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
				header_lines.append(_update_copyright_year(year, line))
				if not line_strip:
					break

		clskel_file = None
		if not header_lines:
			# delay opening this until we find we need a header
			try:
				clskel_file = io.open(_unicode_encode(skel_path,
					encoding=_encodings['fs'], errors='strict'),
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
				line = _update_copyright_year(year, line)
				header_lines.append(line)
			header_lines.append(_unicode_decode('\n'))
			clskel_file.close()

		# write new ChangeLog entry
		clnew_lines.extend(header_lines)
		newebuild = False
		for fn in new:
			if not fn.endswith('.ebuild'):
				continue
			ebuild = fn.split(os.sep)[-1][0:-7] 
			clnew_lines.append(_unicode_decode('*%s (%s)\n' % (ebuild, date)))
			newebuild = True
		if newebuild:
			clnew_lines.append(_unicode_decode('\n'))
		trivial_files = ('ChangeLog', 'Manifest')
		display_new = ['+' + elem for elem in new
			if elem not in trivial_files]
		display_removed = ['-' + elem for elem in removed]
		display_changed = [elem for elem in changed
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
		for line in textwrap.wrap(mesg, 80, \
				initial_indent='  ', subsequent_indent='  ', \
				break_on_hyphens=False):
			clnew_lines.append(_unicode_decode('%s\n' % line))
		for line in textwrap.wrap(msg, 80, \
				initial_indent='  ', subsequent_indent='  '):
			clnew_lines.append(_unicode_decode('%s\n' % line))
		# Don't append a trailing newline if the file is new.
		if clold_file is not None:
			clnew_lines.append(_unicode_decode('\n'))

		f = io.open(f, mode='w', encoding=_encodings['repo.content'],
			errors='backslashreplace')

		for line in clnew_lines:
			f.write(_unicode_decode(line))

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
			for line in difflib.unified_diff(clold_lines, clnew_lines,
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

