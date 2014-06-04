
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
		live_ebuild):
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
		'''
		if not self.options.straight_to_stable:
			self._checkAddedWithStableKeywords(
				package, ebuild, y_ebuild, keywords, changed)
		self._checkForDroppedKeywords(
			pkg, ebuild, ebuild_archs, live_ebuild)

		self.slot_keywords[pkg.slot].update(ebuild_archs)

	def _checkAddedWithStableKeywords(
		self, package, ebuild, y_ebuild, keywords, changed):
		catdir, pkgdir = package.split("/")

		is_stable = lambda kw: not kw.startswith("~") and not kw.startswith("-")
		stable_keywords = list(filter(is_stable, keywords))
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
				self.qatracker.add_error("KEYWORDS.dropped",
					"%s: %s" %
					(ebuild.relative_path, " ".join(sorted(dropped_keywords))))
