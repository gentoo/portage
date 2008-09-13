# portage: news management code
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__all__ = ["NewsManager", "NewsItem", "DisplayRestriction",
	"DisplayProfileRestriction", "DisplayKeywordRestriction",
	"DisplayInstalledRestriction"]

import errno
import os
import re
from portage.util import ensure_dirs, apply_permissions, normalize_path, grabfile, write_atomic
from portage.data import portage_gid
from portage.locks import lockfile, unlockfile
from portage.exception import OperationNotPermitted

class NewsManager(object):
	"""
	This object manages GLEP 42 style news items.  It will cache news items
	that have previously shown up and notify users when there are relevant news
	items that apply to their packages that the user has not previously read.
	
	Creating a news manager requires:
	root - typically ${ROOT} see man make.conf and man emerge for details
	news_path - path to news items; usually $REPODIR/metadata/news
	unread_path - path to the news.repoid.unread file; this helps us track news items
	
	"""

	def __init__(self, portdb, vardb, news_path, unread_path, language_id='en'):
		self.news_path = news_path
		self.unread_path = unread_path
		self.target_root = vardb.root
		self.language_id = language_id
		self.config = vardb.settings
		self.vdb = vardb
		self.portdb = portdb

		portdir = portdb.porttree_root
		profiles_base = os.path.join(portdir, 'profiles') + os.path.sep
		profile_path = None
		if portdb.mysettings.profile_path:
			profile_path = normalize_path(
				os.path.realpath(portdb.mysettings.profile_path))
			if profile_path.startswith(profiles_base):
				profile_path = profile_path[len(profiles_base):]
		self._profile_path = profile_path

		# Ensure that the unread path exists and is writable.
		dirmode  = 02070
		modemask =    02
		try:
			ensure_dirs(self.unread_path, mode=dirmode,
				mask=modemask, gid=portage_gid)
		except OperationNotPermitted:
			pass

	def updateItems(self, repoid):
		"""
		Figure out which news items from NEWS_PATH are both unread and relevant to
		the user (according to the GLEP 42 standards of relevancy).  Then add these
		items into the news.repoid.unread file.
		"""

		repos = self.portdb.getRepositories()
		if repoid not in repos:
			raise ValueError("Invalid repoID: %s" % repoid)

		path = os.path.join(self.portdb.getRepositoryPath(repoid), self.news_path)

		# Skip reading news for repoid if the news dir does not exist.  Requested by
		# NightMorph :)
		if not os.path.exists(path):
			return None
		news = os.listdir(path)

		skipfile = os.path.join(self.unread_path, "news-%s.skip" % repoid)
		skiplist = grabfile(skipfile)
		updates = []
		for itemid in news:
			if itemid in skiplist:
				continue
			try:
				filename = os.path.join(path, itemid, itemid + "." + self.language_id + ".txt")
				item = NewsItem(filename, itemid)
			except (TypeError):
				continue
			if item.isRelevant(profile=self._profile_path,
				config=self.config, vardb=self.vdb):
				updates.append(item)
		del path
		
		path = os.path.join(self.unread_path, 'news-%s.unread' % repoid)
		unread_lock = None
		try:
			unread_lock = lockfile(path)
			if not os.path.exists(path):
				#create the file if it does not exist
				open(path, "w")
			# Ensure correct perms on the unread file.
			apply_permissions( filename=path,
				uid=int(self.config['PORTAGE_INST_UID']), gid=portage_gid, mode=0664)
			# Make sure we have the correct permissions when created
			unread_file = open(path, 'a')

			for item in updates:
				unread_file.write(item.name + "\n")
				skiplist.append(item.name)
			unread_file.close()
		finally:
			if unread_lock:
				unlockfile(unread_lock)
			write_atomic(skipfile, "\n".join(skiplist)+"\n")
		try:
			apply_permissions(filename=skipfile, 
				uid=int(self.config["PORTAGE_INST_UID"]), gid=portage_gid, mode=0664)
		except OperationNotPermitted, e:
			import errno
			# skip "permission denied" errors as we're likely running in pretend mode
			# with reduced priviledges
			if e.errno == errno.EPERM:
				pass
			else:
				raise

	def getUnreadItems(self, repoid, update=False):
		"""
		Determine if there are unread relevant items in news.repoid.unread.
		If there are unread items return their number.
		If update is specified, updateNewsItems( repoid ) will be called to
		check for new items.
		"""
		
		if update:
			self.updateItems(repoid)
		
		unreadfile = os.path.join(self.unread_path, 'news-%s.unread' % repoid)
		unread_lock = None
		try:
			if os.access(os.path.dirname(unreadfile), os.W_OK):
				# TODO: implement shared readonly locks
				unread_lock = lockfile(unreadfile)
			try:
				f = open(unreadfile)
				try:
					unread = f.readlines()
				finally:
					f.close()
			except EnvironmentError, e:
				if e.errno != errno.ENOENT:
					raise
				del e
				return 0
			if len(unread):
				return len(unread)
		finally:
			if unread_lock:
				unlockfile(unread_lock)

_installedRE = re.compile("Display-If-Installed:(.*)\n")
_profileRE = re.compile("Display-If-Profile:(.*)\n")
_keywordRE = re.compile("Display-If-Keyword:(.*)\n")

class NewsItem(object):
	"""
	This class encapsulates a GLEP 42 style news item.
	It's purpose is to wrap parsing of these news items such that portage can determine
	whether a particular item is 'relevant' or not.  This requires parsing the item
	and determining 'relevancy restrictions'; these include "Display if Installed" or
	"display if arch: x86" and so forth.

	Creation of a news item involves passing in the path to the particular news item.

	"""
	
	def __init__(self, path, name):
		""" 
		For a given news item we only want if it path is a file.
		"""
		if not os.path.isfile(path):
			raise TypeError("%s is no regular file" % path)
		self.path = path
		self.name = name
		self._parsed = False

	def isRelevant(self, vardb, config, profile):
		"""
		This function takes a dict of keyword arguments; one should pass in any
		objects need to do to lookups (like what keywords we are on, what profile,
		and a vardb so we can look at installed packages).
		Each restriction will pluck out the items that are required for it to match
		or raise a ValueError exception if the required object is not present.
		"""

		if not len(self.restrictions):
			return True # no restrictions to match means everyone should see it
		
		kwargs = \
			{ 'vardb' : vardb,
				'config' : config,
				'profile' : profile }

		for restriction in self.restrictions:
			if restriction.checkRestriction(**kwargs):
				return True
			
		return False # No restrictions were met; thus we aren't relevant :(

	def parse(self):
		lines = open(self.path).readlines()
		self.restrictions = []
		for line in lines:
			#Optimization to ignore regex matchines on lines that
			#will never match
			if not line.startswith('D'):
				continue
			restricts = {  _installedRE : DisplayInstalledRestriction,
					_profileRE : DisplayProfileRestriction,
					_keywordRE : DisplayKeywordRestriction }
			for regex, restriction in restricts.iteritems():
				match = regex.match(line)
				if match:
					self.restrictions.append(restriction(match.groups()[0].strip()))
					continue
		self._parsed = True

	def __getattr__(self, attr):
		if not self._parsed:
			self.parse()
		return self.__dict__[attr]

class DisplayRestriction(object):
	"""
	A base restriction object representing a restriction of display.
	news items may have 'relevancy restrictions' preventing them from
	being important.  In this case we need a manner of figuring out if
	a particular item is relevant or not.  If any of it's restrictions
	are met, then it is displayed
	"""

	def checkRestriction(self, **kwargs):
		raise NotImplementedError('Derived class should over-ride this method')

class DisplayProfileRestriction(DisplayRestriction):
	"""
	A profile restriction where a particular item shall only be displayed
	if the user is running a specific profile.
	"""

	def __init__(self, profile):
		self.profile = profile

	def checkRestriction(self, **kwargs):
		if self.profile == kwargs['profile']:
			return True
		return False

class DisplayKeywordRestriction(DisplayRestriction):
	"""
	A keyword restriction where a particular item shall only be displayed
	if the user is running a specific keyword.
	"""

	def __init__(self, keyword):
		self.keyword = keyword

	def checkRestriction(self, **kwargs):
		if kwargs['config']['ARCH'] == self.keyword:
			return True
		return False

class DisplayInstalledRestriction(DisplayRestriction):
	"""
	An Installation restriction where a particular item shall only be displayed
	if the user has that item installed.
	"""
	
	def __init__(self, cpv):
		self.cpv = cpv

	def checkRestriction(self, **kwargs):
		vdb = kwargs['vardb']
		if vdb.match(self.cpv):
			return True
		return False
