# repoman: Checks
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

import os
import re
import time
import repoman.errors as errors

class LineCheck(object):
	"""Run a check on a line of an ebuild."""
	"""A regular expression to determine whether to ignore the line"""
	ignore_line = False

	def new(self, pkg):
		pass

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		if self.re.match(line):
			return self.error

	def end(self):
		pass

class EbuildHeader(LineCheck):
	"""Ensure ebuilds have proper headers
		Copyright header errors
		CVS header errors
		License header errors
	
	Args:
		modification_year - Year the ebuild was last modified
	"""

	repoman_check_name = 'ebuild.badheader'

	gentoo_copyright = r'^# Copyright ((1999|200\d)-)?%s Gentoo Foundation$'
	# Why a regex here, use a string match
	# gentoo_license = re.compile(r'^# Distributed under the terms of the GNU General Public License v2$')
	gentoo_license = r'# Distributed under the terms of the GNU General Public License v2'
	cvs_header = re.compile(r'^#\s*\$Header.*\$$')

	def new(self, pkg):
		self.modification_year = str(time.gmtime(pkg.mtime)[0])
		self.gentoo_copyright_re = re.compile(
			self.gentoo_copyright % self.modification_year)

	def check(self, num, line):
		if num > 2:
			return
		elif num == 0:
			if not self.gentoo_copyright_re.match(line):
				return errors.COPYRIGHT_ERROR
		elif num == 1 and line.strip() != self.gentoo_license:
			return errors.LICENSE_ERROR
		elif num == 2:
			if not self.cvs_header.match(line):
				return errors.CVS_HEADER_ERROR


class EbuildWhitespace(LineCheck):
	"""Ensure ebuilds have proper whitespacing"""

	repoman_check_name = 'ebuild.minorsyn'

	ignore_line = re.compile(r'(^$)|(^(\t)*#)')
	leading_spaces = re.compile(r'^[\S\t]')
	trailing_whitespace = re.compile(r'.*([\S]$)')	

	def check(self, num, line):
		if not self.leading_spaces.match(line):
			return errors.LEADING_SPACES_ERROR
		if not self.trailing_whitespace.match(line):
			return errors.TRAILING_WHITESPACE_ERROR


class EbuildQuote(LineCheck):
	"""Ensure ebuilds have valid quoting around things like D,FILESDIR, etc..."""

	repoman_check_name = 'ebuild.minorsyn'
	_message_commands = ["die", "echo", "eerror",
		"einfo", "elog", "eqawarn", "ewarn"]
	_message_re = re.compile(r'\s(' + "|".join(_message_commands) + \
		r')\s+"[^"]*"\s*$')
	_ignored_commands = ["local", "export"] + _message_commands
	ignore_line = re.compile(r'(^$)|(^\s*#.*)|(^\s*\w+=.*)' + \
		r'|(^\s*(' + "|".join(_ignored_commands) + r')\s+)')
	var_names = ["D", "DISTDIR", "FILESDIR", "S", "T", "ROOT", "WORKDIR"]

	# variables for games.eclass
	var_names += ["Ddir", "dir", "GAMES_PREFIX_OPT", "GAMES_DATADIR",
		"GAMES_DATADIR_BASE", "GAMES_SYSCONFDIR", "GAMES_STATEDIR",
		"GAMES_LOGDIR", "GAMES_BINDIR"]

	var_names = "(%s)" % "|".join(var_names)
	var_reference = re.compile(r'\$(\{'+var_names+'\}|' + \
		var_names + '\W)')
	missing_quotes = re.compile(r'(\s|^)[^"\'\s]*\$\{?' + var_names + \
		r'\}?[^"\'\s]*(\s|$)')
	cond_begin =  re.compile(r'(^|\s+)\[\[($|\\$|\s+)')
	cond_end =  re.compile(r'(^|\s+)\]\]($|\\$|\s+)')
	
	def check(self, num, line):
		if self.var_reference.search(line) is None:
			return
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

			# Filter matches that appear to be an
			# argument to a message command.
			# For example: false || ewarn "foo $WORKDIR/bar baz"
			message_match = self._message_re.search(line)
			if message_match is not None and \
				message_match.start() < pos and \
				message_match.end() > pos:
				break

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

			# Any remaining matches on the same line can be ignored.
			return errors.MISSING_QUOTES_ERROR


class EbuildAssignment(LineCheck):
	"""Ensure ebuilds don't assign to readonly variables."""

	repoman_check_name = 'variable.readonly'

	readonly_assignment = re.compile(r'^\s*(export\s+)?(A|CATEGORY|P|PV|PN|PR|PVR|PF|D|WORKDIR|FILESDIR|FEATURES|USE)=')
	line_continuation = re.compile(r'([^#]*\S)(\s+|\t)\\$')
	ignore_line = re.compile(r'(^$)|(^(\t)*#)')

	def __init__(self):
		self.previous_line = None

	def check(self, num, line):
		match = self.readonly_assignment.match(line)
		e = None
		if match and (not self.previous_line or not self.line_continuation.match(self.previous_line)):
			e = errors.READONLY_ASSIGNMENT_ERROR
		self.previous_line = line
		return e


class EbuildNestedDie(LineCheck):
	"""Check ebuild for nested die statements (die statements in subshells"""
	
	repoman_check_name = 'ebuild.nesteddie'
	nesteddie_re = re.compile(r'^[^#]*\s\(\s[^)]*\bdie\b')
	
	def check(self, num, line):
		if self.nesteddie_re.match(line):
			return errors.NESTED_DIE_ERROR


class EbuildUselessDodoc(LineCheck):
	"""Check ebuild for useless files in dodoc arguments."""
	repoman_check_name = 'ebuild.minorsyn'
	uselessdodoc_re = re.compile(
		r'^\s*dodoc(\s+|\s+.*\s+)(ABOUT-NLS|COPYING|LICENSE)($|\s)')

	def check(self, num, line):
		match = self.uselessdodoc_re.match(line)
		if match:
			return "Useless dodoc '%s'" % (match.group(2), ) + " on line: %d"


class EbuildUselessCdS(LineCheck):
	"""Check for redundant cd ${S} statements"""
	repoman_check_name = 'ebuild.minorsyn'
	method_re = re.compile(r'^\s*src_(compile|install|test)\s*\(\)')
	cds_re = re.compile(r'^\s*cd\s+("\$(\{S\}|S)"|\$(\{S\}|S))\s')

	def __init__(self):
		self.check_next_line = False

	def check(self, num, line):
		if self.check_next_line:
			self.check_next_line = False
			if self.cds_re.match(line):
				return errors.REDUNDANT_CD_S_ERROR
		elif self.method_re.match(line):
			self.check_next_line = True

class EbuildPatches(LineCheck):
	"""Ensure ebuilds use bash arrays for PATCHES to ensure white space safety"""
	repoman_check_name = 'ebuild.patches'
	re = re.compile(r'^\s*PATCHES=[^\(]')
	error = errors.PATCHES_ERROR

class EbuildQuotedA(LineCheck):
	"""Ensure ebuilds have no quoting around ${A}"""

	repoman_check_name = 'ebuild.minorsyn'
	a_quoted = re.compile(r'.*\"\$(\{A\}|A)\"')

	def check(self, num, line):
		match = self.a_quoted.match(line)
		if match:
			return "Quoted \"${A}\" on line: %d"

class ImplicitRuntimeDeps(LineCheck):
	"""
	Detect the case where DEPEND is set and RDEPEND is unset in the ebuild,
	since this triggers implicit RDEPEND=$DEPEND assignment.
	"""

	repoman_check_name = 'RDEPEND.implicit'
	_assignment_re = re.compile(r'^\s*(R?DEPEND)=')

	def new(self, pkg):
		self._rdepend = False
		self._depend = False

	def check(self, num, line):
		if not self._rdepend:
			m = self._assignment_re.match(line)
			if m is None:
				pass
			elif m.group(1) == "RDEPEND":
				self._rdepend = True
			elif m.group(1) == "DEPEND":
				self._depend = True

	def end(self):
		if self._depend and not self._rdepend:
			yield 'RDEPEND is not explicitly assigned'

class InheritAutotools(LineCheck):
	"""
	Make sure appropriate functions are called in
	ebuilds that inherit autotools.eclass.
	"""

	repoman_check_name = 'inherit.autotools'
	ignore_line = re.compile(r'(^|\s*)#')
	_inherit_autotools_re = re.compile(r'^\s*inherit\s(.*\s)?autotools(\s|$)')
	_autotools_funcs = (
		"eaclocal", "eautoconf", "eautoheader",
		"eautomake", "eautoreconf", "_elibtoolize")
	_autotools_func_re = re.compile(r'\b(' + \
		"|".join(_autotools_funcs) + r')\b')
	# Exempt eclasses:
	# git - An EGIT_BOOTSTRAP variable may be used to call one of
	#       the autotools functions.
	# subversion - An ESVN_BOOTSTRAP variable may be used to call one of
	#       the autotools functions.
	_exempt_eclasses = frozenset(["git", "subversion"])

	def new(self, pkg):
		self._inherit_autotools = None
		self._autotools_func_call = None
		self._disabled = self._exempt_eclasses.intersection(pkg.inherited)

	def check(self, num, line):
		if self._disabled:
			return
		if self._inherit_autotools is None:
			self._inherit_autotools = self._inherit_autotools_re.match(line)
		if self._inherit_autotools is not None and \
			self._autotools_func_call is None:
			self._autotools_func_call = self._autotools_func_re.search(line)

	def end(self):
		if self._inherit_autotools and self._autotools_func_call is None:
			yield 'no eauto* function called'

class IUseUndefined(LineCheck):
	"""
	Make sure the ebuild defines IUSE (style guideline
	says to define IUSE even when empty).
	"""

	repoman_check_name = 'IUSE.undefined'
	_iuse_def_re = re.compile(r'^IUSE=.*')

	def new(self, pkg):
		self._iuse_def = None

	def check(self, num, line):
		if self._iuse_def is None:
			self._iuse_def = self._iuse_def_re.match(line)

	def end(self):
		if self._iuse_def is None:
			yield 'IUSE is not defined'

class EMakeParallelDisabled(LineCheck):
	"""Check for emake -j1 calls which disable parallelization."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'^\s*emake\s+-j\s*1\s')
	error = errors.EMAKE_PARALLEL_DISABLED

class DeprecatedBindnowFlags(LineCheck):
	"""Check for calls to the deprecated bindnow-flags function."""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'.*\$\(bindnow-flags\)')
	error = errors.DEPRECATED_BINDNOW_FLAGS

_constant_checks = tuple((c() for c in (
	EbuildHeader, EbuildWhitespace, EbuildQuote,
	EbuildAssignment, EbuildUselessDodoc,
	EbuildUselessCdS, EbuildNestedDie,
	EbuildPatches, EbuildQuotedA,
	IUseUndefined, ImplicitRuntimeDeps, InheritAutotools,
	EMakeParallelDisabled, DeprecatedBindnowFlags)))

def run_checks(contents, pkg):
	checks = _constant_checks

	for lc in checks:
		lc.new(pkg)
	for num, line in enumerate(contents):
		for lc in checks:
			ignore = lc.ignore_line
			if not ignore or not ignore.match(line):
				e = lc.check(num, line)
				if e:
					yield lc.repoman_check_name, e % (num + 1)
	for lc in checks:
		i = lc.end()
		if i is not None:
			for e in i:
				yield lc.repoman_check_name, e
