
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildNonRelativeDosym(LineCheck):
	"""Check ebuild for dosym using absolute paths instead of relative."""
	repoman_check_name = 'ebuild.absdosym'
	variables = ('D', 'ED', 'ROOT', 'EROOT', 'BROOT')
	regex = re.compile(
		r'^\s*dosym\s+(["\']?((\$(%s)\W|\${(%s)(%%/)?})|/(bin|etc|lib|opt|sbin|srv|usr|var))\S*)' %
		('|'.join(variables), '|'.join(variables)), getattr(re, 'ASCII', 0))

	def check(self, num, line):
		match = self.regex.match(line)
		if match:
			return "dosym '%s'... could use relative path" % match.group(1)
