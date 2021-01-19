
'''restrict.py
Perform checks on the RESTRICT variable.
'''

# import our initialized portage instance
from repoman._portage import portage

from repoman.modules.scan.scanbase import ScanBase


class RestrictChecks(ScanBase):
	'''Perform checks on the RESTRICT variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')
		if self.repo_settings.repo_config.restrict_allowed is None:
			self._restrict_allowed = self.repo_settings.qadata.valid_restrict
		else:
			self._restrict_allowed = self.repo_settings.repo_config.restrict_allowed

	def check(self, **kwargs):
		xpkg = kwargs.get('xpkg')
		ebuild = kwargs.get('ebuild').get()
		y_ebuild = kwargs.get('y_ebuild')
		myrestrict = None

		try:
			myrestrict = portage.dep.use_reduce(
				ebuild.metadata["RESTRICT"], matchall=1, flat=True)
		except portage.exception.InvalidDependString as e:
			self.qatracker.add_error("RESTRICT.syntax",
				"%s: RESTRICT: %s" % (ebuild.relative_path, e))
			del e

		if myrestrict:
			myrestrict = set(myrestrict)
			mybadrestrict = myrestrict.difference(self._restrict_allowed)

			if mybadrestrict:
				for mybad in mybadrestrict:
					self.qatracker.add_error("RESTRICT.invalid",
						"%s/%s.ebuild: %s" % (xpkg, y_ebuild, mybad))
		return False

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
