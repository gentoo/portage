# portage: news management code
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage_const import INCREMENTALS, PROFILE_PATH, NEWS_LIB_PATH
from portage import config, vartree, vardbapi, portdbapi
from portage_util import ensure_dirs, apply_permissions
from portage_data import portage_gid
from portage_locks import lockfile, unlockfile, lockdir, unlockdir
from portage_exception import FileNotFound
import os, re

class NewsManager(object):
	"""
	This object manages GLEP 42 style news items.  It will cache news items
	that have previously shown up and notify users when there are relevant news
	items that apply to their packages that the user has not previously read.
	
	Creating a news manager requires:
	root - typically ${ROOT} see man make.conf and man emerge for details
	NEWS_PATH - path to news items; usually $REPODIR/metadata/news
	UNREAD_PATH - path to the news.repoid.unread file; this helps us track news items
	
	"""

	TIMESTAMP_FILE = "news-timestamp"

	def __init__( self, root, NEWS_PATH, UNREAD_PATH, LANGUAGE_ID='en' ):
		self.NEWS_PATH = NEWS_PATH
		self.UNREAD_PATH = UNREAD_PATH
		self.TIMESTAMP_PATH = os.path.join( root, NEWS_LIB_PATH, NewsManager.TIMESTAMP_FILE )
		self.target_root = root
		self.LANGUAGE_ID = LANGUAGE_ID
		self.config = config( config_root = os.environ.get("PORTAGE_CONFIGROOT", "/"),
				target_root = root, config_incrementals = INCREMENTALS)
		self.vdb = vardbapi( settings = self.config, root = root,
			vartree = vartree( root = root, settings = self.config ) )
		self.portdb = portdbapi( porttree_root = self.config["PORTDIR"], mysettings = self.config )

		# Ensure that the unread path exists and is writable.
		dirmode  = 02070
		modemask =    02
		ensure_dirs(self.UNREAD_PATH, mode=dirmode, mask=modemask, gid=portage_gid)

	def updateItems( self, repoid ):
		"""
		Figure out which news items from NEWS_PATH are both unread and relevant to
		the user (according to the GLEP 42 standards of relevancy).  Then add these
		items into the news.repoid.unread file.
		"""

		repos = self.portdb.getRepositories()
		if repoid not in repos:
			raise ValueError("Invalid repoID: %s" % repoid)

		timestamp_file = self.TIMESTAMP_PATH + repoid
		if os.path.exists(timestamp_file):
			# Make sure the timestamp has correct permissions.
			apply_permissions( filename=timestamp_file, 
				uid=self.config["PORTAGE_INST_UID"], gid=portage_gid, mode=664 )
			timestamp = os.stat(timestamp_file).st_mtime
		else:
			timestamp = 0

		path = os.path.join( self.portdb.getRepositoryPath( repoid ), self.NEWS_PATH )
		newsdir_lock = None
		try:
			newsdir_lock = lockdir( self.portdb.getRepositoryPath(repoid) )
			# Skip reading news for repoid if the news dir does not exist.  Requested by
			# NightMorph :)
			if not os.path.exists( path ):
				return None
			news = os.listdir( path )
			updates = []
			for item in news:
				try:
					file = os.path.join( path, item, item + "." + self.LANGUAGE_ID + ".txt")
					tmp = NewsItem( file , timestamp )
				except TypeError:
					continue

				if tmp.isRelevant( profile=os.readlink(PROFILE_PATH), config=config, vardb=self.vdb):
					updates.append( tmp )
		finally:
			if newsdir_lock:
				unlockdir(newsdir_lock)
		
		del path
		
		path = os.path.join( self.UNREAD_PATH, "news-" + repoid + ".unread" )
		try:
			unread_lock = lockfile( path )
			if not os.path.exists( path ):
				#create the file if it does not exist
				open( path, "w" )
			# Ensure correct perms on the unread file.
			apply_permissions( filename=path,
				uid=self.config["PORTAGE_INST_UID"], gid=portage_gid, mode=664 )
			# Make sure we have the correct permissions when created
			unread_file = open( path, "a" )

			for item in updates:
				unread_file.write( item.path + "\n" )
			unread_file.close()
		finally:
			unlockfile(unread_lock)
		
		# Touch the timestamp file
		f = open(timestamp_file, "w")
		f.close()

	def getUnreadItems( self, repoid, update=False ):
		"""
		Determine if there are unread relevant items in news.repoid.unread.
		If there are unread items return their number.
		If update is specified, updateNewsItems( repoid ) will be called to
		check for new items.
		"""
		
		if update:
			self.updateItems( repoid )
		
		unreadfile = os.path.join( self.UNREAD_PATH, "news-"+ repoid +".unread" )
		try:
			unread_lock = lockfile(unreadfile)
			# Set correct permissions on the news-repoid.unread file
			apply_permissions( filename=unreadfile,
				uid=int(self.config["PORTAGE_INST_UID"]), gid=portage_gid, mode=0664 )
				
			if os.path.exists( unreadfile ):
				unread = open( unreadfile ).readlines()
				if len(unread):
					return len(unread)
		except FileNotFound:
			pass # unread file may not exist
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
	
	def __init__( self, path, cache_mtime = 0 ):
		""" 
		For a given news item we only want if it path is a file and it's 
		mtime is newer than the cache'd timestamp.
		"""
		if not os.path.isfile( path ):
			raise TypeError
		if not os.stat( path ).st_mtime > cache_mtime:
			raise TypeError
		self.path = path
		self._parsed = False

	def isRelevant( self, vardb, config, profile ):
		"""
		This function takes a dict of keyword arguments; one should pass in any
		objects need to do to lookups (like what keywords we are on, what profile,
		and a vardb so we can look at installed packages).
		Each restriction will pluck out the items that are required for it to match
		or raise a ValueError exception if the required object is not present.
		"""

		if not len(self.restrictions):
			return True # no restrictions to match means everyone should see it
		
		kwargs = { 'vardb' : vardb,
			   'config' : config,
			   'profile' : profile }

		for restriction in self.restrictions:
			if restriction.checkRestriction( **kwargs ):
				return True
			
		return False # No restrictions were met; thus we aren't relevant :(

	def parse( self ):
		lines = open(self.path).readlines()
		self.restrictions = []
		for line in lines:
			#Optimization to ignore regex matchines on lines that
			#will never match
			if not line.startswith("D"):
				continue
			restricts = {  _installedRE : DisplayInstalledRestriction,
					_profileRE : DisplayProfileRestriction,
					_keywordRE : DisplayKeywordRestriction }
			for regex, restriction in restricts.iteritems():
				match = regex.match(line)
				if match:
					self.restrictions.append( restriction( match.groups()[0].strip() ) )
					continue
		self._parsed = True

	def __getattr__( self, attr ):
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

	def checkRestriction( self, **kwargs ):
		raise NotImplementedError("Derived class should over-ride this method")

class DisplayProfileRestriction(DisplayRestriction):
	"""
	A profile restriction where a particular item shall only be displayed
	if the user is running a specific profile.
	"""

	def __init__( self, profile ):
		self.profile = profile

	def checkRestriction( self, **kwargs ):
		if self.profile == kwargs['profile']:
			return True
		return False

class DisplayKeywordRestriction(DisplayRestriction):
	"""
	A keyword restriction where a particular item shall only be displayed
	if the user is running a specific keyword.
	"""

	def __init__( self, keyword ):
		self.keyword = keyword

	def checkRestriction( self, **kwargs ):
		if kwargs['config']["ARCH"] == self.keyword:
			return True
		return False

class DisplayInstalledRestriction(DisplayRestriction):
	"""
	An Installation restriction where a particular item shall only be displayed
	if the user has that item installed.
	"""
	
	def __init__( self, cpv ):
		self.cpv = cpv

	def checkRestriction( self, **kwargs ):
		vdb = kwargs['vardb']
		if vdb.match( self.cpv ):
			return True
		return False
