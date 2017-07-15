
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildNonRelativeDosym(LineCheck):
	"""Check ebuild for dosym using absolute paths instead of relative."""
	repoman_check_name = 'ebuild.absdosym'
	regex = re.compile(
		r'^\s*dosym\s+["\']?(/(bin|etc|lib|opt|sbin|srv|usr|var)\S*)')

	def check(self, num, line):
		match = self.regex.match(line)
		if match:
			return "dosym '%s'... could use relative path" % (match.group(1), ) + " on line: %d"
