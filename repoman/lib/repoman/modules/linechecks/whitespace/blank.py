
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildBlankLine(LineCheck):
	repoman_check_name = 'ebuild.minorsyn'
	ignore_comment = False
	blank_line = re.compile(r'^$')

	def new(self, pkg):
		self.line_is_blank = False

	def check(self, num, line):
		if self.line_is_blank and self.blank_line.match(line):
			return 'Useless blank line'
		if self.blank_line.match(line):
			self.line_is_blank = True
		else:
			self.line_is_blank = False

	def end(self):
		if self.line_is_blank:
			yield 'Useless blank line on last line'
