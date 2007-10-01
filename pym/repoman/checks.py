# repoman: Checks
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import time
import re
import os

from repoman.errors import COPYRIGHT_ERROR, LICENSE_ERROR, CVS_HEADER_ERROR, \
	LEADING_SPACES_ERROR, READONLY_ASSIGNMENT_ERROR, TRAILING_WHITESPACE_ERROR, \
	MISSING_QUOTES_ERROR


class ContentCheckException(Exception):
	"""Parent class for exceptions relating to invalid content"""
	
	def __init__(self, str):
		Exception.__init__(self, str)


class ContentCheck(object):
	"""Given a file-like object, run checks over it's content
	
	Args:
	  contents - A file-like object, preferably a StringIO instance
	
	Raises:
		ContentCheckException or a subclass
	"""
	repoman_check_name = None
	
	def __init__(self, contents):
		self.contents = contents
		pass
	
	def Run(self):
		"""Run the check against the contents, return a sequence of errors
		   of the form ((line, error),...)
		"""
		pass


class EbuildHeaderCheck(ContentCheck):
	"""Ensure ebuilds have proper headers
	
	Args:
		modification_year - Year the ebuild was last modified
	"""

	repoman_check_name = 'ebuild.badheader'

	gentoo_copyright = r'^# Copyright ((1999|200\d)-)?%s Gentoo Foundation$'
	# Why a regex here, use a string match
	# gentoo_license = re.compile(r'^# Distributed under the terms of the GNU General Public License v2$')
	gentoo_license = r'# Distributed under the terms of the GNU General Public License v2'
	cvs_header = re.compile(r'^#\s*\$Header.*\$$')

	def __init__(self, contents, modification_year):
		ContentCheck.__init__(self, contents)
		self.modification_year = modification_year
		self.gentoo_copyright_re = re.compile(self.gentoo_copyright % self.modification_year)

	def Run(self):
		"""Locate simple header mistakes in an ebuild
		Copyright header errors
		CVS header errors
		License header errors
		"""
		errors = []
		for num, line in enumerate(self.contents):
			if num == 0:
				match = self.gentoo_copyright_re.match(line)
				if not match:
					errors.append((num + 1, COPYRIGHT_ERROR))
			if num == 1 and line.strip() != self.gentoo_license:
				errors.append((num + 1, LICENSE_ERROR))
			if num == 2:
				match = self.cvs_header.match(line)
				if not match:
					errors.append((num + 1, CVS_HEADER_ERROR))
			if num > 2:
				return errors
		return errors


class EbuildWhitespaceCheck(ContentCheck):
	"""Ensure ebuilds have proper whitespacing"""

	repoman_check_name = 'ebuild.minorsyn'

	ignore_line = re.compile(r'(^$)|(^(\t)*#)')
	leading_spaces = re.compile(r'^[\S\t]')
	trailing_whitespace = re.compile(r'.*([\S]$)')	

	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		"""Locate simple whitespace errors
		Lines with leading spaces or trailing whitespace
		"""
		errors = []
		for num, line in enumerate(self.contents):
			match = self.ignore_line.match(line)
			if match:
				continue
			match = self.leading_spaces.match(line)
			if not match:
				errors.append((num + 1, LEADING_SPACES_ERROR))
			match = self.trailing_whitespace.match(line)
			if not match:
				errors.append((num + 1, TRAILING_WHITESPACE_ERROR))
		return errors


class EbuildQuoteCheck(ContentCheck):
	"""Ensure ebuilds have valid quoting around things like D,FILESDIR, etc..."""

	repoman_check_name = 'ebuild.minorsyn'

	missing_quotes = re.compile(r'[^"]\${?(D|S|T|ROOT|FILESDIR|WORKDIR)}?\W')
	missing_quotes_exclude = re.compile(r'\[\[.*[^"]\${?(D|S|T|ROOT|FILESDIR|WORKDIR)}?\W.*\]\]')
	ignore_line = re.compile(r'(^$)|(^(\t)*#)')
	
	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		"""Locate simple errors in ebuilds:
		Missing quotes around variables that may contain spaces
		"""

		errors = []
		for num, line in enumerate(self.contents):
			match = self.ignore_line.match(line)
			if match:
				continue
			missing_quotes_line = self.missing_quotes.search(line)
			if missing_quotes_line:
				for group in missing_quotes_line.group():
					match = self.missing_quotes_exclude.search(group)
					if not match:
						errors.append((num + 1, MISSING_QUOTES_ERROR))
						break
		return errors


class EbuildAssignmentCheck(ContentCheck):
	"""Ensure ebuilds don't assign to readonly variables."""

	repoman_check_name = 'ebuild.majorsyn'

	readonly_assignment = re.compile(r'^\s*(export\s+)?(A|CATEGORY|P|PV|PN|PR|PVR|PF|D|WORKDIR|FILESDIR|FEATURES|USE)=')
	line_continuation = re.compile(r'([^#]*\S)(\s+|\t)\\$')
	ignore_line = re.compile(r'(^$)|(^(\t)*#)')

	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		"""Locate simple errors in ebuilds:
		Assigning to read-only variables.
		"""

		errors = []
		previous_line = None
		# enumerate is 0 indexed, so add one when necesseary
		for num, line in enumerate(self.contents):
			match = self.ignore_line.match(line)
			if match:
				continue
			match = self.readonly_assignment.match(line)
			if match and (not previous_line or not self.line_continuation.match(previous_line)):
				errors.append((num + 1, READONLY_ASSIGNMENT_ERROR))
			previous_line = line
		return errors
