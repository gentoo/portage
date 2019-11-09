
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildQuotedA(LineCheck):
	"""Ensure ebuilds have no quoting around ${A}"""

	repoman_check_name = 'ebuild.minorsyn'
	a_quoted = re.compile(r'.*\"\$(\{A\}|A)\"')

	def check(self, num, line):
		match = self.a_quoted.match(line)
		if match:
			return "Quoted \"${A}\""
