
'''restrict.py
Perform checks on the RESTRICT variable.
'''

# import our initialized portage instance
from repoman._portage import portage

from repoman.qa_data import valid_restrict


class RestrictChecks(object):
	'''Perform checks on the RESTRICT variable.'''

	def __init__(self, qatracker):
		'''
		@param qatracker: QATracker instance
		'''
		self.qatracker = qatracker

	def check(self, pkg, package, ebuild, y_ebuild):
		myrestrict = None

		try:
			myrestrict = portage.dep.use_reduce(
				pkg._metadata["RESTRICT"], matchall=1, flat=True)
		except portage.exception.InvalidDependString as e:
			self. qatracker.add_error(
				"RESTRICT.syntax",
				"%s: RESTRICT: %s" % (ebuild.relative_path, e))
			del e

		if myrestrict:
			myrestrict = set(myrestrict)
			mybadrestrict = myrestrict.difference(valid_restrict)

			if mybadrestrict:
				for mybad in mybadrestrict:
					self.qatracker.add_error(
						"RESTRICT.invalid",
						package + "/" + y_ebuild + ".ebuild: %s" % mybad)
