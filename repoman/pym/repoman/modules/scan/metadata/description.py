
'''description.py
Perform checks on the DESCRIPTION variable.
'''

from repoman.modules.scan.scanbase import ScanBase


class DescriptionChecks(ScanBase):
	'''Perform checks on the DESCRIPTION variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')

	def checkTooLong(self, **kwargs):
		'''
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		'''
		ebuild = kwargs.get('ebuild').get()
		pkg = kwargs.get('pkg').get()
		# 14 is the length of DESCRIPTION=""
		if len(pkg._metadata['DESCRIPTION']) > self.repo_settings.qadata.max_desc_len:
			self.qatracker.add_error(
				'DESCRIPTION.toolong',
				"%s: DESCRIPTION is %d characters (max %d)" %
				(ebuild.relative_path, len(
					pkg._metadata['DESCRIPTION']), self.repo_settings.qadata.max_desc_len))
		return False

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.checkTooLong])
