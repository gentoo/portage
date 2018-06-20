# -*- coding:utf-8 -*-

'''keywords.py
Perform KEYWORDS related checks

'''

from repoman.modules.scan.scanbase import ScanBase


class KeywordChecks(ScanBase):
	'''Perform checks on the KEYWORDS of an ebuild'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		@param options: argparse options instance
		'''
		super(KeywordChecks, self).__init__(**kwargs)
		self.qatracker = kwargs.get('qatracker')
		self.options = kwargs.get('options')
		self.repo_metadata = kwargs.get('repo_metadata')
		self.profiles = kwargs.get('profiles')
		self.slot_keywords = {}

	def prepare(self, **kwargs):
		'''Prepare the checks for the next package.'''
		self.slot_keywords = {}
		self.dropped_keywords = {}
		return False

	def check(self, **kwargs):
		'''Perform the check.

		@param pkg: Package in which we check (object).
		@param xpkg: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param ebuild_archs: Just the architectures (no prefixes) of the ebuild.
		@param changed: Changes instance
		@returns: dictionary
		'''
		pkg = kwargs.get('pkg').get()
		xpkg =kwargs.get('xpkg')
		ebuild = kwargs.get('ebuild').get()
		y_ebuild = kwargs.get('y_ebuild')
		changed = kwargs.get('changed')
		if not self.options.straight_to_stable:
			self._checkAddedWithStableKeywords(
				xpkg, ebuild, y_ebuild, ebuild.keywords, changed)

		self._checkForDroppedKeywords(pkg, ebuild, ebuild.archs)

		self._checkForInvalidKeywords(ebuild, xpkg, y_ebuild)

		self._checkForMaskLikeKeywords(xpkg, y_ebuild, ebuild.keywords)

		self._checkForUnsortedKeywords(ebuild, xpkg, y_ebuild)

		self.slot_keywords[pkg.slot].update(ebuild.archs)
		return False

	def check_dropped_keywords(self, **kwargs):
		'''Report on any dropped keywords for the latest ebuild in a slot

		@returns: boolean
		'''
		for ebuild, arches in self.dropped_keywords.values():
			if arches:
				self.qatracker.add_error(
					"KEYWORDS.dropped", "%s: %s" % (
						ebuild,
						" ".join(sorted(arches))))
		return False

	@staticmethod
	def _isKeywordStable(keyword):
		return not keyword.startswith("~") and not keyword.startswith("-")

	def _checkAddedWithStableKeywords(
		self, package, ebuild, y_ebuild, keywords, changed):
		catdir, pkgdir = package.split("/")

		stable_keywords = list(filter(self._isKeywordStable, keywords))
		if stable_keywords:
			if ebuild.ebuild_path in changed.new_ebuilds and catdir != "virtual":
				stable_keywords.sort()
				self.qatracker.add_error(
					"KEYWORDS.stable",
					"%s/%s.ebuild added with stable keywords: %s" %
					(package, y_ebuild, " ".join(stable_keywords)))

	def _checkForDroppedKeywords(
		self, pkg, ebuild, ebuild_archs):
		previous_keywords = self.slot_keywords.get(pkg.slot)
		if previous_keywords is None:
			self.slot_keywords[pkg.slot] = set()
		elif ebuild_archs and "*" not in ebuild_archs and not ebuild.live_ebuild:
			self.slot_keywords[pkg.slot].update(ebuild_archs)
			dropped_keywords = previous_keywords.difference(ebuild_archs)
			self.dropped_keywords[pkg.slot] = (ebuild.relative_path, { arch for arch in dropped_keywords})

	def _checkForInvalidKeywords(self, ebuild, xpkg, y_ebuild):
		myuse = ebuild.keywords

		for mykey in myuse:
			if mykey not in ("-*", "*", "~*"):
				myskey = mykey

				if not self._isKeywordStable(myskey[:1]):
					myskey = myskey[1:]

				if myskey not in self.repo_metadata['kwlist']:
					self.qatracker.add_error("KEYWORDS.invalid",
						"%s/%s.ebuild: %s" % (xpkg, y_ebuild, mykey))
				elif myskey not in self.profiles:
					self.qatracker.add_error(
						"KEYWORDS.invalid",
						"%s/%s.ebuild: %s (profile invalid)"
							% (xpkg, y_ebuild, mykey))

	def _checkForMaskLikeKeywords(self, xpkg, y_ebuild, keywords):
		# KEYWORDS="-*" is a stupid replacement for package.mask
		# and screws general KEYWORDS semantics
		if "-*" in keywords:
			haskeyword = False

			for kw in keywords:
				if kw[0] == "~":
					kw = kw[1:]
				if kw in self.repo_metadata['kwlist']:
					haskeyword = True

			if not haskeyword:
				self.qatracker.add_error("KEYWORDS.stupid",
					"%s/%s.ebuild" % (xpkg, y_ebuild))

	def _checkForUnsortedKeywords(self, ebuild, xpkg, y_ebuild):
		'''Ebuilds that contain KEYWORDS
		which are not sorted alphabetically.'''
		def sort_keywords(kw):
			# Split keywords containing hyphens. The part after
			# the hyphen should be treated as the primary key.
			# This is consistent with ekeyword.
			parts = list(reversed(kw.lstrip("~-").split("-", 1)))
			# Hack to make sure that keywords
			# without hyphens are sorted first
			if len(parts) == 1:
				parts.insert(0, "")
			return parts
		sorted_keywords = sorted(ebuild.keywords, key=sort_keywords)
		if sorted_keywords != ebuild.keywords:
			self.qatracker.add_error("KEYWORDS.unsorted",
				"%s/%s.ebuild contains unsorted keywords" %
				(xpkg, y_ebuild))

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.prepare])

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])

	@property
	def runInFinal(self):
		'''Final package level scans'''
		return (True, [self.check_dropped_keywords])
