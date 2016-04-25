
from repoman.modules.scan.scanbase import ScanBase


class MtimeChecks(ScanBase):

	def __init__(self, **kwargs):
		self.vcs_settings = kwargs.get('vcs_settings')

	def check(self, **kwargs):
		'''Perform a changelog and untracked checks on the ebuild

		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		@param changed: dictionary instance
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild').get()
		changed = kwargs.get('changed')
		pkg = kwargs.get('pkg').get()
		if not self.vcs_settings.vcs_preserves_mtime:
			if ebuild.ebuild_path not in changed.new_ebuilds and \
					ebuild.ebuild_path not in changed.ebuilds:
				pkg.mtime = None
		return False

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
