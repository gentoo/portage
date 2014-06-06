
'''use_flags.py
Performs USE flag related checks
'''

# import our centrally initialized portage instance
from repoman._portage import portage

from portage import eapi
from portage.eapi import eapi_has_iuse_defaults, eapi_has_required_use


class USEFlagChecks(object):
	'''Performs checks on USE flags listed in the ebuilds and metadata.xml'''

	def __init__(self, qatracker, globalUseFlags):
		'''
		@param qatracker: QATracker instance
		@param globalUseFlags: Global USE flags
		'''
		self.qatracker = qatracker
		self.globalUseFlags = globalUseFlags
		self.useFlags = []
		self.defaultUseFlags = []
		self.usedUseFlags = set()

	def check(self, pkg, package, ebuild, y_ebuild, localUseFlags):
		'''Perform the check.

		@param pkg: Package in which we check (object).
		@param package: Package in which we check (string).
		@param ebuild: Ebuild which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param localUseFlags: Local USE flags of the package
		'''
		# reset state variables for the run
		self.useFlags = []
		self.defaultUseFlags = []
		self.usedUseFlags = set()
		self._checkGlobal(pkg)
		self._checkMetadata(package, ebuild, y_ebuild, localUseFlags)
		self._checkRequiredUSE(pkg, ebuild)

	def getUsedUseFlags(self):
		'''Get the USE flags that this check has seen'''
		return self.usedUseFlags

	def _checkGlobal(self, pkg):
		for myflag in pkg._metadata["IUSE"].split():
			flag_name = myflag.lstrip("+-")
			self.usedUseFlags.add(flag_name)
			if myflag != flag_name:
				self.defaultUseFlags.append(myflag)
			if flag_name not in self.globalUseFlags:
				self.useFlags.append(flag_name)

	def _checkMetadata(self, package, ebuild, y_ebuild, localUseFlags):
		for mypos in range(len(self.useFlags) - 1, -1, -1):
			if self.useFlags[mypos] and (self.useFlags[mypos] in localUseFlags):
				del self.useFlags[mypos]

		if self.defaultUseFlags and not eapi_has_iuse_defaults(eapi):
			for myflag in self.defaultUseFlags:
				self.qatracker.add_error(
					'EAPI.incompatible', "%s: IUSE defaults"
					" not supported with EAPI='%s': '%s'" % (
						ebuild.relative_path, eapi, myflag))

		for mypos in range(len(self.useFlags)):
			self.qatracker.add_error(
				"IUSE.invalid",
				"%s/%s.ebuild: %s" % (package, y_ebuild, self.useFlags[mypos]))

	def _checkRequiredUSE(self, pkg, ebuild):
		required_use = pkg._metadata["REQUIRED_USE"]
		if required_use:
			if not eapi_has_required_use(eapi):
				self.qatracker.add_error(
					'EAPI.incompatible', "%s: REQUIRED_USE"
					" not supported with EAPI='%s'"
					% (ebuild.relative_path, eapi,))
			try:
				portage.dep.check_required_use(
					required_use, (), pkg.iuse.is_valid_flag, eapi=eapi)
			except portage.exception.InvalidDependString as e:
				self.qatracker.add_error(
					"REQUIRED_USE.syntax",
					"%s: REQUIRED_USE: %s" % (ebuild.relative_path, e))
				del e
