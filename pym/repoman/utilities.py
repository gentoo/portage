# repoman: Utilities
# Copyright 2007-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains utility functions to help repoman find ebuilds to
scan"""

__all__ = [
	"detect_vcs_conflicts",
	"editor_is_executable",
	"FindPackagesToScan",
	"FindPortdir",
	"FindVCS",
	"format_qa_output",
	"get_commit_message_with_editor",
	"get_commit_message_with_stdin",
	"have_profile_dir",
	"parse_metadata_use",
	"UnknownHerdsError",
	"check_metadata"
]

import codecs
import errno
import logging
import sys
from portage import os
from portage import subprocess_getstatusoutput
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage import output
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
	retval = ("","")
	if vcs == 'cvs':
		logging.info("Performing a " + output.green("cvs -n up") + \
			" with a little magic grep to check for updates.")
		retval = subprocess_getstatusoutput("cvs -n up 2>&1 | " + \
			"egrep '^[^\?] .*' | " + \
			"egrep -v '^. .*/digest-[^/]+|^cvs server: .* -- ignored$'")
	if vcs == 'svn':
		logging.info("Performing a " + output.green("svn status -u") + \
			" with a little magic grep to check for updates.")
		retval = subprocess_getstatusoutput("svn status -u 2>&1 | " + \
			"egrep -v '^.  +.*/digest-[^/]+' | " + \
			"head -n-1")

	if vcs in ['cvs', 'svn']:
		mylines = retval[1].splitlines()
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
				logging.error(retval[1])
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
	@returns: True if an executable is found, False otherwise.
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
	@returns: A string on success or None if an error occurs.
	"""
	from tempfile import mkstemp
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
			mylines = codecs.open(_unicode_encode(filename,
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
	@returns: A string on success or None if an error occurs.
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
	pwd = os.environ.get('PWD', '')
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
		""" Seek for distributed VCSes. """
		retvcs = []
		pathprep = ''

		while depth is None or depth > 0:
			if os.path.isdir(os.path.join(pathprep, '.git')):
				retvcs.append('git')
			if os.path.isdir(os.path.join(pathprep, '.bzr')):
				retvcs.append('bzr')
			if os.path.isdir(os.path.join(pathprep, '.hg')):
				retvcs.append('hg')

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
	if os.path.isdir('.svn'):
		outvcs.append('svn')

	# If we already found one of 'level zeros', just take a quick look
	# at the current directory. Otherwise, seek parents till we get
	# something or reach root.
	if outvcs:
		outvcs.extend(seek(1))
	else:
		outvcs = seek()

	return outvcs
