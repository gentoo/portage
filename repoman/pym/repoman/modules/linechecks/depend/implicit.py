
import re

from portage.eapi import eapi_has_implicit_rdepend
from repoman.modules.linechecks.base import LineCheck


class ImplicitRuntimeDeps(LineCheck):
	"""
	Detect the case where DEPEND is set and RDEPEND is unset in the ebuild,
	since this triggers implicit RDEPEND=$DEPEND assignment (prior to EAPI 4).
	"""

	repoman_check_name = 'RDEPEND.implicit'
	_assignment_re = re.compile(r'^\s*(R?DEPEND)\+?=')

	def new(self, pkg):
		self._rdepend = False
		self._depend = False

	def check_eapi(self, eapi):
		# Beginning with EAPI 4, there is no
		# implicit RDEPEND=$DEPEND assignment
		# to be concerned with.
		return eapi_has_implicit_rdepend(eapi)

	def check(self, num, line):
		if not self._rdepend:
			m = self._assignment_re.match(line)
			if m is None:
				pass
			elif m.group(1) == "RDEPEND":
				self._rdepend = True
			elif m.group(1) == "DEPEND":
				self._depend = True

	def end(self):
		if self._depend and not self._rdepend:
			yield 'RDEPEND is not explicitly assigned'
