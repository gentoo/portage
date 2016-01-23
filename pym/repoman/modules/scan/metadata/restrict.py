
'''restrict.py
Perform checks on the RESTRICT variable.
'''

# import our initialized portage instance
from repoman._portage import portage

from repoman.qa_data import valid_restrict


class RestrictChecks(object):
	'''Perform checks on the RESTRICT variable.'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = kwargs.get('qatracker')

	def check(self, **kwargs):
		xpkg = kwargs.get('xpkg')
		ebuild = kwargs.get('ebuild')
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
			mybadrestrict = myrestrict.difference(valid_restrict)

			if mybadrestrict:
				for mybad in mybadrestrict:
					self.qatracker.add_error("RESTRICT.invalid",
						"%s/%s.ebuild: %s" % (xpkg, y_ebuild, mybad))
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])

