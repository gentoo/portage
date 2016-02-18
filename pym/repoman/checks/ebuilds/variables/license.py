
'''description.py
Perform checks on the LICENSE variable.
'''

# import our initialized portage instance
from repoman._portage import portage


class LicenseChecks(object):
	'''Perform checks on the LICENSE variable.'''

	def __init__(self, qatracker, liclist, liclist_deprecated):
		'''
		@param qatracker: QATracker instance
		@param liclist: List of licenses.
		@param liclist: List of deprecated licenses.
		'''
		self.qatracker = qatracker
		self.liclist = liclist
		self.liclist_deprecated = liclist_deprecated

	def check(
		self, pkg, package, ebuild, y_ebuild):
		'''
		@param pkg: Package in which we check (object).
		@param package: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		'''

		# Parse the LICENSE variable, remove USE conditions and flatten it.
		licenses = portage.dep.use_reduce(
			pkg._metadata["LICENSE"], matchall=1, flat=True)

		# Check each entry to ensure that it exists in ${PORTDIR}/licenses/.
		for lic in licenses:
			# Need to check for "||" manually as no portage
			# function will remove it without removing values.
			if lic not in self.liclist and lic != "||":
				self.qatracker.add_error(
					"LICENSE.invalid",
					package + "/" + y_ebuild + ".ebuild: %s" % lic)
			elif lic in self.liclist_deprecated:
				self.qatracker.add_error(
					"LICENSE.deprecated",
					"%s: %s" % (ebuild.relative_path, lic))
