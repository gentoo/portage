
import re
import time

from repoman.modules.linechecks.base import LineCheck


class EbuildHeader(LineCheck):
	"""Ensure ebuilds have proper headers
		Copyright header errors
		CVS header errors
		License header errors

	Args:
		modification_year - Year the ebuild was last modified
	"""

	repoman_check_name = 'ebuild.badheader'

	gentoo_copyright = (
		r'^# Copyright ((1999|2\d\d\d)-)?(?P<year2>%s) (?P<author>.*)$')
	gentoo_license = (
		'# Distributed under the terms'
		' of the GNU General Public License v2')
	id_header_re = re.compile(r'.*\$(Id|Header)(:.*)?\$.*')
	blank_line_re = re.compile(r'^$')
	ignore_comment = False

	def new(self, pkg):
		if pkg.mtime is None:
			self.modification_year = r'2\d\d\d'
		else:
			self.modification_year = str(time.gmtime(pkg.mtime)[0])
		self.gentoo_copyright_re = re.compile(
			self.gentoo_copyright % self.modification_year)

	def check(self, num, line):
		if num > 2:
			return
		elif num == 0:
			match = self.gentoo_copyright_re.match(line)
			if match is None:
				return self.errors['COPYRIGHT_ERROR']
			if not (match.group('author') == 'Gentoo Authors' or
					(int(match.group('year2')) < 2019 and
						match.group('author') == 'Gentoo Foundation')):
				return self.errors['COPYRIGHT_ERROR']
		elif num == 1 and line.rstrip('\n') != self.gentoo_license:
			return self.errors['LICENSE_ERROR']
		elif num == 2 and self.id_header_re.match(line):
			return self.errors['ID_HEADER_ERROR']
		elif num == 2 and not self.blank_line_re.match(line):
			return self.errors['NO_BLANK_LINE_ERROR']
