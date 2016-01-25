
'''license.py
Perform checks on the LICENSE variable.
'''

# import our initialized portage instance
from repoman._portage import portage


class LicenseChecks(object):
	'''Perform checks on the LICENSE variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		@param repo_metadata: dictionary of various repository items.
		'''
		self.qatracker = kwargs.get('qatracker')
		self.repo_metadata = kwargs.get('repo_metadata')

	def check(self, **kwargs):
		'''
		@param xpkg: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		'''
		xpkg = kwargs.get('xpkg')
		ebuild = kwargs.get('ebuild')
		y_ebuild = kwargs.get('y_ebuild')
		if not kwargs.get('badlicsyntax'):
			# Parse the LICENSE variable, remove USE conditions and flatten it.
			licenses = portage.dep.use_reduce(
				ebuild.metadata["LICENSE"], matchall=1, flat=True)

			# Check each entry to ensure that it exists in ${PORTDIR}/licenses/.
			for lic in licenses:
				# Need to check for "||" manually as no portage
				# function will remove it without removing values.
				if lic not in self.repo_metadata['liclist'] and lic != "||":
					self.qatracker.add_error("LICENSE.invalid",
						"%s/%s.ebuild: %s" % (xpkg, y_ebuild, lic))
				elif lic in self.repo_metadata['lic_deprecated']:
					self.qatracker.add_error("LICENSE.deprecated",
						"%s: %s" % (ebuild.relative_path, lic))
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
