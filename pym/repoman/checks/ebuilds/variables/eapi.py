
'''eapi.py
Perform checks on the EAPI variable.
'''


class EAPIChecks(object):
	'''Perform checks on the EAPI variable.'''

	def __init__(self, qatracker, repo_settings):
		'''
		@param qatracker: QATracker instance
		@param repo_settings: Repository settings
		'''
		self.qatracker = qatracker
		self.repo_settings = repo_settings

	def check(self, pkg, ebuild):
		'''
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		'''
		eapi = pkg._metadata["EAPI"]

		if not self._checkBanned(ebuild, eapi):
			self._checkDeprecated(ebuild, eapi)

	def _checkBanned(self, ebuild, eapi):
		if self.repo_settings.repo_config.eapi_is_banned(eapi):
			self.qatracker.add_error(
				"repo.eapi.banned", "%s: %s" % (ebuild.relative_path, eapi))

			return True

		return False

	def _checkDeprecated(self, ebuild, eapi):
		if self.repo_settings.repo_config.eapi_is_deprecated(eapi):
			self.qatracker.add_error(
				"repo.eapi.deprecated", "%s: %s" % (ebuild.relative_path, eapi))

			return True

		return False
