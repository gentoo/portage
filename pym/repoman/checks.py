# repoman: Checks
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import time
import re
import os

from repoman.errors import COPYRIGHT_ERROR, LICENSE_ERROR, CVS_HEADER_ERROR, \
	LEADING_SPACES_ERROR, READONLY_ASSIGNMENT_ERROR, TRAILING_WHITESPACE_ERROR, \
	MISSING_QUOTES_ERROR, NESTED_DIE_ERROR, REDUNDANT_CD_S_ERROR


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


class EbuildHeader(ContentCheck):
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


class EbuildWhitespace(ContentCheck):
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


class EbuildQuote(ContentCheck):
	"""Ensure ebuilds have valid quoting around things like D,FILESDIR, etc..."""

	repoman_check_name = 'ebuild.minorsyn'
	ignore_line = re.compile(r'(^$)|(^\s*#.*)|(^\s*\w+=.*)|(^\s*(local|export)\s+)')
	var_names = r'(D|S|T|ROOT|FILESDIR|WORKDIR)'
	var_reference = re.compile(r'\$({'+var_names+'}|' + \
		r'\$' + var_names + '\W)')
	missing_quotes = re.compile(r'(\s|^)[^"\s]*\${?' + var_names + \
		r'}?[^"\s]*(\s|$)')
	cond_begin =  re.compile(r'(^|\s+)\[\[($|\\$|\s+)')
	cond_end =  re.compile(r'(^|\s+)\]\]($|\\$|\s+)')
	
	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		"""Locate simple errors in ebuilds:
		Missing quotes around variables that may contain spaces
		"""

		errors = []
		for num, line in enumerate(self.contents):
			if self.ignore_line.match(line) is not None:
				continue
			if self.var_reference.search(line) is None:
				continue
			# There can be multiple matches / violations on a single line. We
			# have to make sure none of the matches are violators. Once we've
			# found one violator, any remaining matches on the same line can
			# be ignored.
			pos = 0
			while pos <= len(line) - 1:
				missing_quotes = self.missing_quotes.search(line, pos)
				if not missing_quotes:
					break
				# If the last character of the previous match is a whitespace
				# character, that character may be needed for the next
				# missing_quotes match, so search overlaps by 1 character.
				group = missing_quotes.group()
				pos = missing_quotes.end() - 1

				# Filter out some false positives that can
				# get through the missing_quotes regex.
				if self.var_reference.search(group) is None:
					continue

				# This is an attempt to avoid false positives without getting
				# too complex, while possibly allowing some (hopefully
				# unlikely) violations to slip through. We just assume
				# everything is correct if the there is a ' [[ ' or a ' ]] '
				# anywhere in the whole line (possibly continued over one
				# line).
				if self.cond_begin.search(line) is not None:
					continue
				if self.cond_end.search(line) is not None:
					continue

				errors.append((num + 1, MISSING_QUOTES_ERROR))
				# Any remaining matches on the same line can be ignored.
				break
		return errors


class EbuildAssignment(ContentCheck):
	"""Ensure ebuilds don't assign to readonly variables."""

	repoman_check_name = 'variable.readonly'

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

class EbuildNestedDie(ContentCheck):
	"""Check ebuild for nested die statements (die statements in subshells"""
	
	repoman_check_name = 'ebuild.nesteddie'
	nesteddie_re = re.compile(r'^[^#]*\([^)]*\bdie\b')
	
	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		errors = []
		for num, line in enumerate(self.contents):
			match = self.nesteddie_re.match(line)
			if match:
				errors.append((num + 1, NESTED_DIE_ERROR))
		return errors

class EbuildUselessDodoc(ContentCheck):
	"""Check ebuild for useless files in dodoc arguments."""
	repoman_check_name = 'ebuild.minorsyn'
	uselessdodoc_re = re.compile(
		r'^\s*dodoc(\s+|\s+.*\s+)(ABOUT-NLS|COPYING|LICENSE)($|\s)')

	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		errors = []
		uselessdodoc_re = self.uselessdodoc_re
		for num, line in enumerate(self.contents):
			match = uselessdodoc_re.match(line)
			if match:
				errors.append((num + 1, "Useless dodoc '%s'" % \
					(match.group(2), ) + " on line: %d"))
		return errors

class EbuildUselessCdS(ContentCheck):
	"""Check for redundant cd ${S} statements"""
	repoman_check_name = 'ebuild.minorsyn'
	method_re = re.compile(r'^\s*src_(compile|install|test)\s*\(\)')
	cds_re = re.compile(r'^\s*cd\s+("\$(\{S\}|S)"|\$(\{S\}|S))\s')

	def __init__(self, contents):
		ContentCheck.__init__(self, contents)

	def Run(self):
		errors = []
		check_next_line = False
		for num, line in enumerate(self.contents):
			if check_next_line:
				check_next_line = False
				if self.cds_re.match(line):
					errors.append((num + 1, REDUNDANT_CD_S_ERROR))
			elif self.method_re.match(line):
				check_next_line = True
		return errors
