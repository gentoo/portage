
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildWhitespace(LineCheck):
	"""Ensure ebuilds have proper whitespacing"""

	repoman_check_name = 'ebuild.minorsyn'

	ignore_line = re.compile(r'(^$)|(^(\t)*#)')
	ignore_comment = False
	leading_spaces = re.compile(r'^[\S\t]')
	trailing_whitespace = re.compile(r'.*([\S]$)')

	def check(self, num, line):
		if self.leading_spaces.match(line) is None:
			return self.errors['LEADING_SPACES_ERROR']
		if self.trailing_whitespace.match(line) is None:
			return self.errors['TRAILING_WHITESPACE_ERROR']
