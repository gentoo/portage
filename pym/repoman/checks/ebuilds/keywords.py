
'''keywords.py
Perform KEYWORDS related checks
'''


class KeywordChecks(object):
	'''Perform checks on the KEYWORDS of an ebuild'''

	def __init__(self, qatracker, options):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = qatracker
		self.options = options
		self.slot_keywords = {}

	def prepare(self):
		'''Prepare the checks for the next package.'''
		self.slot_keywords = {}

	def check(
		self, pkg, package, ebuild, y_ebuild, keywords, ebuild_archs, changed,
		live_ebuild, kwlist, profiles):
		'''Perform the check.

		@param pkg: Package in which we check (object).
		@param package: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param keywords: All the keywords (including -...) of the ebuild.
		@param ebuild_archs: Just the architectures (no prefixes) of the ebuild.
		@param changed: Changes instance
		@param slot_keywords: A dictionary of keywords per slot.
		@param live_ebuild: A boolean that determines if this is a live ebuild.
		@param kwlist: A list of all global keywords.
		@param profiles: A list of all profiles.
		'''
		if not self.options.straight_to_stable:
			self._checkAddedWithStableKeywords(
				package, ebuild, y_ebuild, keywords, changed)

		self._checkForDroppedKeywords(
			pkg, ebuild, ebuild_archs, live_ebuild)

		self._checkForInvalidKeywords(
			pkg, package, y_ebuild, kwlist, profiles)

		self._checkForMaskLikeKeywords(
			package, y_ebuild, keywords, kwlist)

		self.slot_keywords[pkg.slot].update(ebuild_archs)

	def _isKeywordStable(self, keyword):
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
		self, pkg, ebuild, ebuild_archs, live_ebuild):
		previous_keywords = self.slot_keywords.get(pkg.slot)
		if previous_keywords is None:
			self.slot_keywords[pkg.slot] = set()
		elif ebuild_archs and "*" not in ebuild_archs and not live_ebuild:
			dropped_keywords = previous_keywords.difference(ebuild_archs)
			if dropped_keywords:
				self.qatracker.add_error(
					"KEYWORDS.dropped", "%s: %s" % (
						ebuild.relative_path,
						" ".join(sorted(dropped_keywords))))

	def _checkForInvalidKeywords(
		self, pkg, package, y_ebuild, kwlist, profiles):
		myuse = pkg._metadata["KEYWORDS"].split()

		for mykey in myuse:
			if mykey not in ("-*", "*", "~*"):
				myskey = mykey

				if not self._isKeywordStable(myskey[:1]):
					myskey = myskey[1:]

				if myskey not in kwlist:
					self.qatracker.add_error(
						"KEYWORDS.invalid",
						"%s/%s.ebuild: %s" % (
							package, y_ebuild, mykey))
				elif myskey not in profiles:
					self.qatracker.add_error(
						"KEYWORDS.invalid",
						"%s/%s.ebuild: %s (profile invalid)" % (
							package, y_ebuild, mykey))

	def _checkForMaskLikeKeywords(
		self, package, y_ebuild, keywords, kwlist):

		# KEYWORDS="-*" is a stupid replacement for package.mask
		# and screws general KEYWORDS semantics
		if "-*" in keywords:
			haskeyword = False

			for kw in keywords:
				if kw[0] == "~":
					kw = kw[1:]
				if kw in kwlist:
					haskeyword = True

			if not haskeyword:
				self.qatracker.add_error(
					"KEYWORDS.stupid", package + "/" + y_ebuild + ".ebuild")
