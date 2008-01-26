# repoman: Utilities
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import logging
import os

from portage import util
from portage import exception

normalize_path = util.normalize_path
util.initialize_logger()

def have_profile_dir(path, maxdepth=3):
	""" Try to figure out if 'path' has a /profiles dir in it by checking for a package.mask file
	"""
	while path != "/" and maxdepth:
		if os.path.exists(path + "/profiles/package.mask"):
			return normalize_path(path)
		path = normalize_path(path + "/..")
		maxdepth -= 1

def parse_use_local_desc(mylines, usedict=None):
	"""
	Records are of the form PACKAGE:FLAG - DESC
	returns a dict of the form {cpv:set(flags)}"""
	if usedict is None:
		usedict = {}
	for line_num, l in enumerate(mylines):
		if not l or l.startswith('#'):
			continue
		pkg_flag = l.split(None, 1) # None implies splitting on whitespace
		if not pkg_flag:
			continue
		try:
			pkg, flag = pkg_flag[0].split(":")
		except ValueError:
			raise exception,ParseError("line %d: Malformed input: '%s'" % \
				(linenum + 1, l.rstrip("\n")))
		usedict.setdefault(pkg, set())
		usedict[pkg].add(flag)
	return usedict

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
				cat_pkg_dir = os.path.join(p.split(os.path.sep)[-2:])
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
			scanlist.append(os.path.join(catdir, pkgdir))
	return scanlist

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
		tuple(portdir, portdir_overlay, location)
	"""

	portdir = None
	portdir_overlay = None
	location = os.getcwd()
	pwd = os.environ.get('PWD', '')
	if pwd != location and os.path.realpath(pwd) == location:
		# getcwd() returns the canonical path but that makes it hard for repoman to
		# orient itself if the user has symlinks in their portage tree structure.
		# We use os.environ["PWD"], if available, to get the non-canonical path of
		# the current working directory (from the shell).
		location = pwd

	location = normalize_path(location)

	path_ids = set()
	p = location
	s = None
	while True:
		s = os.stat(p)
		path_ids.add((s.st_dev, s.st_ino))
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
		overlay_id = (s.st_dev, s.st_ino)
		if overlay[-1] != "/":
			overlay += "/"
		if overlay_id in path_ids:
			portdir_overlay = overlay
			subdir = location[len(overlay):]
			if subdir and subdir[-1] != "/":
				subdir += "/"
			if have_profile_dir(location, subdir.count("/")):
				portdir = portdir_overlay
			break
	
	del p, s, path_ids
	
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
		raise ValueError(msg)

	if not portdir:
		portdir = settings["PORTDIR"]

	if not portdir_overlay.endswith('/'):
		portdir_overlay += '/'
	
	if not portdir.endswith('/'):
		portdir += '/'

	return map(normalize_path, (portdir, portdir_overlay, location))
