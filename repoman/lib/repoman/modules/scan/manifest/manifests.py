# -*- coding:utf-8 -*-

# import our initialized portage instance
from repoman._portage import portage
from repoman.modules.scan.scanbase import ScanBase

from portage import os


class Manifests(ScanBase):
	'''Creates as well as checks pkg Manifest entries/files'''

	def __init__(self, **kwargs):
		'''Class init

		@param options: the run time cli options
		@param portdb: portdb instance
		@param qatracker: QATracker instance
		@param repo_settings: repository settings instance
		'''
		self.options = kwargs.get('options')
		self.portdb = kwargs.get('portdb')
		self.qatracker = kwargs.get('qatracker')
		self.repoman_settings = kwargs.get('repo_settings').repoman_settings

	def check(self, **kwargs):
		'''Perform a changelog and untracked checks on the ebuild

		@param xpkg: Package in which we check (object).
		@param checkdir: the current package directory
		@returns: dictionary
		'''
		checkdir = kwargs.get('checkdir')
		xpkg = kwargs.get('xpkg')
		if self.options.pretend:
			return False
		self.digest_check(xpkg, checkdir)
		if self.options.mode == 'manifest-check':
			return True
		return False

	def digest_check(self, xpkg, checkdir):
		'''Check the manifest entries, report any Q/A errors

		@param xpkg: the cat/pkg name to check
		@param checkdir: the directory path to check'''
		self.repoman_settings['O'] = checkdir
		self.repoman_settings['PORTAGE_QUIET'] = '1'
		if not portage.digestcheck([], self.repoman_settings, strict=1):
			self.qatracker.add_error("manifest.bad", os.path.join(xpkg, 'Manifest'))
		self.repoman_settings.pop('PORTAGE_QUIET', None)

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])
