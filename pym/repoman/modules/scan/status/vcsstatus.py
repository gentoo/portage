# -*- coding:utf-8 -*-

from repoman.modules.scan.scanbase import ScanBase


class VCSStatus(ScanBase):
	'''Determines the status of the vcs repositories
	to determine if files are not added'''

	def __init__(self, **kwargs):
		'''Class init

		@param vcs_settings: VCSSettings instance
		'''
		super(VCSStatus, self).__init__(**kwargs)
		self.vcs_settings = kwargs.get('vcs_settings')
		self.check_not_added = kwargs.get("checks")['ebuild_notadded']

	def check(self, **kwargs):
		'''Performs an indirect status check via the
		correct vcs plugin Status class

		@param check_not_added: boolean
		@param checkdir: string, directory path
		@param checkdir_relative: repolevel determined path
		@param xpkg: the current package being checked
		'''
		checkdir = kwargs.get('checkdir')
		checkdir_relative = kwargs.get('checkdir_relative')
		xpkg = kwargs.get('xpkg')
		if self.check_not_added:
			self.vcs_settings.status.check(checkdir, checkdir_relative, xpkg)
		return {'continue': False, 'eadded': self.vcs_settings.status.eadded}

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])
