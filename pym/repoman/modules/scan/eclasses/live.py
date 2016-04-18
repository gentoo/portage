
'''live.py
Performs Live eclass checks
'''

from repoman._portage import portage
from repoman.modules.scan.scanbase import ScanBase

from portage.const import LIVE_ECLASSES


class LiveEclassChecks(ScanBase):
	'''Performs checks for the usage of Live eclasses in ebuilds'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')
		self.pmaskdict = kwargs.get('repo_metadata')['pmaskdict']
		self.repo_settings = kwargs.get('repo_settings')

	def is_live(self, **kwargs):
		'''Test if the ebuild inherits a live eclass

		@returns: dictionary, including {live_ebuild}
		'''
		# update the dynamic data
		dyn_live = kwargs.get('live_ebuild')
		dyn_live.update(LIVE_ECLASSES.intersection(
				kwargs.get('ebuild').inherited))
		return False

	def check(self, **kwargs):
		'''Ebuilds that inherit a "Live" eclass (darcs, subversion, git, cvs,
		etc..) should not be allowed to be marked stable

		@param pkg: Package in which we check (object).
		@param package: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param keywords: The keywords of the ebuild.
		@param global_pmaskdict: A global dictionary of all the masks.
		@returns: dictionary
		'''
		pkg = kwargs.get("pkg").result()
		package = kwargs.get('xpkg')
		ebuild = kwargs.get('ebuild').result()
		y_ebuild = kwargs.get('y_ebuild')
		keywords = ebuild.keywords

		if not (kwargs.get('live_ebuild') and
				self.repo_settings.repo_config.name == "gentoo"):
			return False

		is_stable = lambda kw: not kw.startswith("~") and not kw.startswith("-")
		bad_stable_keywords = list(filter(is_stable, keywords))

		if bad_stable_keywords:
			self.qatracker.add_error(
				"LIVEVCS.stable", "%s/%s.ebuild with stable keywords:%s " % (
					package, y_ebuild, bad_stable_keywords))

		good_keywords_exist = len(bad_stable_keywords) < len(keywords)
		if good_keywords_exist and not self._has_global_mask(pkg, self.pmaskdict):
			self.qatracker.add_error("LIVEVCS.unmasked", ebuild.relative_path)
		return False

	@staticmethod
	def _has_global_mask(pkg, global_pmaskdict):
		mask_atoms = global_pmaskdict.get(pkg.cp)
		if mask_atoms:
			pkg_list = [pkg]
			for x in mask_atoms:
				if portage.dep.match_from_list(x, pkg_list):
					return x
		return None

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.is_live, self.check])
