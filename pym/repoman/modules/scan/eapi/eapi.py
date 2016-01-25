
'''eapi.py
Perform checks on the EAPI variable.
'''


class EAPIChecks(object):
	'''Perform checks on the EAPI variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		@param repo_settings: Repository settings
		'''
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')

	def check(self, **kwargs):
		'''
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		'''
		ebuild = kwargs.get('ebuild')

		if not self._checkBanned(ebuild):
			self._checkDeprecated(ebuild)
		return {'continue': False}

	def _checkBanned(self, ebuild):
		if self.repo_settings.repo_config.eapi_is_banned(ebuild.eapi):
			self.qatracker.add_error(
				"repo.eapi.banned", "%s: %s" % (ebuild.relative_path, ebuild.eapi))
			return True
		return False

	def _checkDeprecated(self, ebuild):
		if self.repo_settings.repo_config.eapi_is_deprecated(ebuild.eapi):
			self.qatracker.add_error(
				"repo.eapi.deprecated", "%s: %s" % (ebuild.relative_path, ebuild.eapi))
			return True
		return False

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
