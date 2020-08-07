# portage: news management code
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["NewsManager", "NewsItem", "DisplayRestriction",
	"DisplayProfileRestriction", "DisplayKeywordRestriction",
	"DisplayInstalledRestriction",
	"count_unread_news", "display_news_notifications"]

from collections import OrderedDict

import fnmatch
import io
import logging
import os as _os
import re
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.const import NEWS_LIB_PATH
from portage.util import apply_secpass_permissions, ensure_dirs, \
	grabfile, normalize_path, write_atomic, writemsg_level
from portage.data import portage_gid
from portage.dep import isvalidatom
from portage.localization import _
from portage.locks import lockfile, unlockfile
from portage.output import colorize
from portage.exception import (InvalidLocation, OperationNotPermitted,
	PermissionDenied, ReadOnlyFileSystem)

class NewsManager:
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
		self.language_id = language_id
		self.config = vardb.settings
		self.vdb = vardb
		self.portdb = portdb

		# GLEP 42 says:
		#   All news item related files should be root owned and in the
		#   portage group with the group write (and, for directories,
		#   execute) bits set. News files should be world readable.
		self._uid = int(self.config["PORTAGE_INST_UID"])
		self._gid = portage_gid
		self._file_mode = 0o0064
		self._dir_mode  = 0o0074
		self._mode_mask = 0o0000

		portdir = portdb.repositories.mainRepoLocation()
		profiles_base = None
		if portdir is not None:
			profiles_base = os.path.join(portdir, 'profiles') + os.path.sep
		profile_path = None
		if profiles_base is not None and portdb.settings.profile_path:
			profile_path = normalize_path(
				os.path.realpath(portdb.settings.profile_path))
			if profile_path.startswith(profiles_base):
				profile_path = profile_path[len(profiles_base):]
		self._profile_path = profile_path

	def _unread_filename(self, repoid):
		return os.path.join(self.unread_path, 'news-%s.unread' % repoid)

	def _skip_filename(self, repoid):
		return os.path.join(self.unread_path, 'news-%s.skip' % repoid)

	def _news_dir(self, repoid):
		repo_path = self.portdb.getRepositoryPath(repoid)
		if repo_path is None:
			raise AssertionError(_("Invalid repoID: %s") % repoid)
		return os.path.join(repo_path, self.news_path)

	def updateItems(self, repoid):
		"""
		Figure out which news items from NEWS_PATH are both unread and relevant to
		the user (according to the GLEP 42 standards of relevancy).  Then add these
		items into the news.repoid.unread file.
		"""

		# Ensure that the unread path exists and is writable.

		try:
			ensure_dirs(self.unread_path, uid=self._uid, gid=self._gid,
				mode=self._dir_mode, mask=self._mode_mask)
		except (OperationNotPermitted, PermissionDenied):
			return

		if not os.access(self.unread_path, os.W_OK):
			return

		news_dir = self._news_dir(repoid)
		try:
			news = _os.listdir(_unicode_encode(news_dir,
				encoding=_encodings['fs'], errors='strict'))
		except OSError:
			return

		skip_filename = self._skip_filename(repoid)
		unread_filename = self._unread_filename(repoid)
		unread_lock = lockfile(unread_filename, wantnewlockfile=1)
		try:
			try:
				unread = set(grabfile(unread_filename))
				unread_orig = unread.copy()
				skip = set(grabfile(skip_filename))
				skip_orig = skip.copy()
			except PermissionDenied:
				return

			for itemid in news:
				try:
					itemid = _unicode_decode(itemid,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					itemid = _unicode_decode(itemid,
						encoding=_encodings['fs'], errors='replace')
					writemsg_level(
						_("!!! Invalid encoding in news item name: '%s'\n") % \
						itemid, level=logging.ERROR, noiselevel=-1)
					continue

				if itemid in skip:
					continue
				filename = os.path.join(news_dir, itemid,
					itemid + "." + self.language_id + ".txt")
				if not os.path.isfile(filename):
					continue
				item = NewsItem(filename, itemid)
				if not item.isValid():
					continue
				if item.isRelevant(profile=self._profile_path,
					config=self.config, vardb=self.vdb):
					unread.add(item.name)
					skip.add(item.name)

			if unread != unread_orig:
				write_atomic(unread_filename,
					"".join("%s\n" % x for x in sorted(unread)))
				apply_secpass_permissions(unread_filename,
					uid=self._uid, gid=self._gid,
					mode=self._file_mode, mask=self._mode_mask)

			if skip != skip_orig:
				write_atomic(skip_filename,
					"".join("%s\n" % x for x in sorted(skip)))
				apply_secpass_permissions(skip_filename,
					uid=self._uid, gid=self._gid,
					mode=self._file_mode, mask=self._mode_mask)

		finally:
			unlockfile(unread_lock)

	def getUnreadItems(self, repoid, update=False):
		"""
		Determine if there are unread relevant items in news.repoid.unread.
		If there are unread items return their number.
		If update is specified, updateNewsItems( repoid ) will be called to
		check for new items.
		"""

		if update:
			self.updateItems(repoid)

		unread_filename = self._unread_filename(repoid)
		unread_lock = None
		try:
			unread_lock = lockfile(unread_filename, wantnewlockfile=1)
		except (InvalidLocation, OperationNotPermitted, PermissionDenied,
			ReadOnlyFileSystem):
			pass
		try:
			try:
				return len(grabfile(unread_filename))
			except PermissionDenied:
				return 0
		finally:
			if unread_lock:
				unlockfile(unread_lock)

_formatRE = re.compile(r"News-Item-Format:\s*([^\s]*)\s*$")
_installedRE = re.compile("Display-If-Installed:(.*)\n")
_profileRE = re.compile("Display-If-Profile:(.*)\n")
_keywordRE = re.compile("Display-If-Keyword:(.*)\n")
_valid_profile_RE = re.compile(r'^[^*]+(/\*)?$')

class NewsItem:
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
		self.path = path
		self.name = name
		self._parsed = False
		self._valid = True

	def isRelevant(self, vardb, config, profile):
		"""
		This function takes a dict of keyword arguments; one should pass in any
		objects need to do to lookups (like what keywords we are on, what profile,
		and a vardb so we can look at installed packages).
		Each restriction will pluck out the items that are required for it to match
		or raise a ValueError exception if the required object is not present.

		Restrictions of the form Display-X are OR'd with like-restrictions;
		otherwise restrictions are AND'd.  any_match is the ORing and
		all_match is the ANDing.
		"""

		if not self._parsed:
			self.parse()

		if not len(self.restrictions):
			return True

		kwargs = \
			{ 'vardb' : vardb,
				'config' : config,
				'profile' : profile }

		all_match = True
		for values in self.restrictions.values():
			any_match = False
			for restriction in values:
				if restriction.checkRestriction(**kwargs):
					any_match = True
			if not any_match:
				all_match = False

		return all_match

	def isValid(self):
		if not self._parsed:
			self.parse()
		return self._valid

	def parse(self):
		f = io.open(_unicode_encode(self.path,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['content'], errors='replace')
		lines = f.readlines()
		f.close()
		self.restrictions = {}
		invalids = []
		news_format = None

		# Look for News-Item-Format
		for i, line in enumerate(lines):
			format_match = _formatRE.match(line)
			if format_match is not None:
				news_format = format_match.group(1)
				if fnmatch.fnmatch(news_format, '[12].*'):
					break
				invalids.append((i + 1, line.rstrip('\n')))

		if news_format is None:
			invalids.append((0, 'News-Item-Format unspecified'))
		else:
			# Parse the rest
			for i, line in enumerate(lines):
				# Optimization to ignore regex matches on lines that
				# will never match
				if not line.startswith('D'):
					continue
				restricts = {  _installedRE : DisplayInstalledRestriction,
						_profileRE : DisplayProfileRestriction,
						_keywordRE : DisplayKeywordRestriction }
				for regex, restriction in restricts.items():
					match = regex.match(line)
					if match:
						restrict = restriction(match.groups()[0].strip(), news_format)
						if not restrict.isValid():
							invalids.append((i + 1, line.rstrip("\n")))
						else:
							self.restrictions.setdefault(
								id(restriction), []).append(restrict)
						continue

		if invalids:
			self._valid = False
			msg = []
			msg.append(_("Invalid news item: %s") % (self.path,))
			for lineno, line in invalids:
				msg.append(_("  line %d: %s") % (lineno, line))
			writemsg_level("".join("!!! %s\n" % x for x in msg),
				level=logging.ERROR, noiselevel=-1)

		self._parsed = True

class DisplayRestriction:
	"""
	A base restriction object representing a restriction of display.
	news items may have 'relevancy restrictions' preventing them from
	being important.  In this case we need a manner of figuring out if
	a particular item is relevant or not.  If any of it's restrictions
	are met, then it is displayed
	"""

	def isValid(self):
		return True

	def checkRestriction(self, **kwargs):
		raise NotImplementedError('Derived class should override this method')

class DisplayProfileRestriction(DisplayRestriction):
	"""
	A profile restriction where a particular item shall only be displayed
	if the user is running a specific profile.
	"""

	def __init__(self, profile, news_format):
		self.profile = profile
		self.format = news_format

	def isValid(self):
		if fnmatch.fnmatch(self.format, '1.*') and '*' in self.profile:
			return False
		if fnmatch.fnmatch(self.format, '2.*') and not _valid_profile_RE.match(self.profile):
			return False
		return True

	def checkRestriction(self, **kwargs):
		if fnmatch.fnmatch(self.format, '2.*') and self.profile.endswith('/*'):
			return kwargs['profile'].startswith(self.profile[:-1])
		return kwargs['profile'] == self.profile

class DisplayKeywordRestriction(DisplayRestriction):
	"""
	A keyword restriction where a particular item shall only be displayed
	if the user is running a specific keyword.
	"""

	def __init__(self, keyword, news_format):
		self.keyword = keyword
		self.format = news_format

	def checkRestriction(self, **kwargs):
		if kwargs['config'].get('ARCH', '') == self.keyword:
			return True
		return False

class DisplayInstalledRestriction(DisplayRestriction):
	"""
	An Installation restriction where a particular item shall only be displayed
	if the user has that item installed.
	"""

	def __init__(self, atom, news_format):
		self.atom = atom
		self.format = news_format

	def isValid(self):
		if fnmatch.fnmatch(self.format, '1.*'):
			return isvalidatom(self.atom, eapi='0')
		if fnmatch.fnmatch(self.format, '2.*'):
			return isvalidatom(self.atom, eapi='5')
		return isvalidatom(self.atom)

	def checkRestriction(self, **kwargs):
		vdb = kwargs['vardb']
		if vdb.match(self.atom):
			return True
		return False

def count_unread_news(portdb, vardb, repos=None, update=True):
	"""
	Returns a dictionary mapping repos to integer counts of unread news items.
	By default, this will scan all repos and check for new items that have
	appeared since the last scan.

	@param portdb: an ebuild database
	@type portdb: pordbapi
	@param vardb: an installed package database
	@type vardb: vardbapi
	@param repos: names of repos to scan (None means to scan all available repos)
	@type repos: list or None
	@param update: check for new items (default is True)
	@type update: boolean
	@rtype: dict
	@return: dictionary mapping repos to integer counts of unread news items
	"""

	NEWS_PATH = os.path.join("metadata", "news")
	UNREAD_PATH = os.path.join(vardb.settings['EROOT'], NEWS_LIB_PATH, "news")
	news_counts = OrderedDict()
	if repos is None:
		repos = portdb.getRepositories()

	permission_msgs = set()
	for repo in repos:
		try:
			manager = NewsManager(portdb, vardb, NEWS_PATH, UNREAD_PATH)
			count = manager.getUnreadItems(repo, update=True)
		except PermissionDenied as e:
			# NOTE: The NewsManager typically handles permission errors by
			# returning silently, so PermissionDenied won't necessarily be
			# raised even if we do trigger a permission error above.
			msg = "Permission denied: '%s'\n" % (e,)
			if msg in permission_msgs:
				pass
			else:
				permission_msgs.add(msg)
				writemsg_level(msg, level=logging.ERROR, noiselevel=-1)
			news_counts[repo] = 0
		else:
			news_counts[repo] = count

	return news_counts

def display_news_notifications(news_counts):
	"""
	Display a notification for unread news items, using a dictionary mapping
	repos to integer counts, like that returned from count_unread_news().
	"""
	newsReaderDisplay = False
	for repo, count in news_counts.items():
		if count > 0:
			if not newsReaderDisplay:
				newsReaderDisplay = True
				print()
			print(colorize("WARN", " * IMPORTANT:"), end=' ')
			print("%s news items need reading for repository '%s'." % (count, repo))

	if newsReaderDisplay:
		print(colorize("WARN", " *"), end=' ')
		print("Use " + colorize("GOOD", "eselect news read") + " to view new items.")
		print()
