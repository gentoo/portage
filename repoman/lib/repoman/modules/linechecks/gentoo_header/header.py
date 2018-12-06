
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

	copyright_re = re.compile(r'^# Copyright ((1999|2\d\d\d)-)?(?P<year>2\d\d\d) \w')
	gentoo_license = (
		'# Distributed under the terms'
		' of the GNU General Public License v2')
	id_header_re = re.compile(r'.*\$(Id|Header)(:.*)?\$.*')
	ignore_comment = False

	def new(self, pkg):
		if pkg.mtime is None:
			self.modification_year = None
		else:
			self.modification_year = time.gmtime(pkg.mtime)[0]
		self.last_copyright_line = -1
		self.last_copyright_year = -1

	def check(self, num, line):
		if num > self.last_copyright_line + 2:
			return
		elif num == self.last_copyright_line + 1:
			# copyright can extend for a few initial lines
			copy_match = self.copyright_re.match(line)
			if copy_match is not None:
				self.last_copyright_line = num
				self.last_copyright_year = max(self.last_copyright_year,
						int(copy_match.group('year')))
			# no copyright lines found?
			elif self.last_copyright_line == -1:
				return self.errors['COPYRIGHT_ERROR']
			else:
				# verify that the newest copyright line found
				# matches the year of last modification
				if (self.modification_year is not None
						and self.last_copyright_year != self.modification_year):
					return self.errors['COPYRIGHT_DATE_ERROR']

				# copyright is immediately followed by license
				if line.rstrip('\n') != self.gentoo_license:
					return self.errors['LICENSE_ERROR']
		elif num == self.last_copyright_line + 2:
			if self.id_header_re.match(line):
				return self.errors['ID_HEADER_ERROR']
			elif line.rstrip('\n') != '':
				return self.errors['NO_BLANK_LINE_ERROR']
