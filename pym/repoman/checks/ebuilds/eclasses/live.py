
'''live.py
Performs Live eclass checks
'''

from repoman.repos import has_global_mask


class LiveEclassChecks(object):
	'''Performs checks for the usage of Live eclasses in ebuilds'''

	def __init__(self, qatracker):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = qatracker

	def check(self, pkg, package, ebuild, y_ebuild, keywords, global_pmaskdict):
		'''Ebuilds that inherit a "Live" eclass (darcs, subversion, git, cvs,
		etc..) should not be allowed to be marked stable

		@param pkg: Package in which we check (object).
		@param package: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param keywords: The keywords of the ebuild.
		@param global_pmaskdict: A global dictionary of all the masks.
		'''
		is_stable = lambda kw: not kw.startswith("~") and not kw.startswith("-")
		bad_stable_keywords = list(filter(is_stable, keywords))

		if bad_stable_keywords:
			self.qatracker.add_error(
				"LIVEVCS.stable", "%s/%s.ebuild with stable keywords:%s " % (
					package, y_ebuild, bad_stable_keywords))

		good_keywords_exist = len(bad_stable_keywords) < len(keywords)
		if good_keywords_exist and not has_global_mask(pkg, global_pmaskdict):
			self.qatracker.add_error("LIVEVCS.unmasked", ebuild.relative_path)
