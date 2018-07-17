
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildNestedDie(LineCheck):
	"""Check ebuild for nested die statements (die statements in subshells)"""

	repoman_check_name = 'ebuild.nesteddie'
	nesteddie_re = re.compile(r'^[^#]*\s\(\s[^)]*\bdie\b')

	def check(self, num, line):
		if self.nesteddie_re.match(line):
			return self.errors['NESTED_DIE_ERROR']
