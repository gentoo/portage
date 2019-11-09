
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildUselessDodoc(LineCheck):
	"""Check ebuild for useless files in dodoc arguments."""
	repoman_check_name = 'ebuild.minorsyn'
	uselessdodoc_re = re.compile(
		r'^\s*dodoc(\s+|\s+.*\s+)(ABOUT-NLS|COPYING|LICENCE|LICENSE)($|\s)')

	def check(self, num, line):
		match = self.uselessdodoc_re.match(line)
		if match:
			return "Useless dodoc '%s'" % match.group(2)
