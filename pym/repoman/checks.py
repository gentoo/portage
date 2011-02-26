# repoman: Checks
# Copyright 2007, 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

import re
import time
import repoman.errors as errors
from portage.eapi import eapi_supports_prefix, eapi_has_implicit_rdepend, \
	eapi_has_src_prepare_and_src_configure, eapi_has_dosed_dohard, \
	eapi_exports_AA, eapi_exports_KV

class LineCheck(object):
	"""Run a check on a line of an ebuild."""
	"""A regular expression to determine whether to ignore the line"""
	ignore_line = False

	def new(self, pkg):
		pass

	def check_eapi(self, eapi):
		""" returns if the check should be run in the given EAPI (default is True) """
		return True

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		if self.re.match(line):
			return self.error

	def end(self):
		pass

class PhaseCheck(LineCheck):
	""" basic class for function detection """

	ignore_line = re.compile(r'(^\s*#)')
	func_end_re = re.compile(r'^\}$')
	phases_re = re.compile('(%s)' % '|'.join((
		'pkg_pretend', 'pkg_setup', 'src_unpack', 'src_prepare',
		'src_configure', 'src_compile', 'src_test', 'src_install',
		'pkg_preinst', 'pkg_postinst', 'pkg_prerm', 'pkg_postrm',
		'pkg_config')))
	in_phase = ''

	def check(self, num, line):
		m = self.phases_re.match(line)
		if m is not None:
			self.in_phase = m.group(1)
		if self.in_phase != '' and \
				self.func_end_re.match(line) is not None:
			self.in_phase = ''

		return self.phase_check(num, line)

	def phase_check(self, num, line):
		""" override this function for your checks """
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

	gentoo_copyright = r'^# Copyright ((1999|2\d\d\d)-)?%s Gentoo Foundation$'
	# Why a regex here, use a string match
	# gentoo_license = re.compile(r'^# Distributed under the terms of the GNU General Public License v2$')
	gentoo_license = '# Distributed under the terms of the GNU General Public License v2'
	cvs_header = re.compile(r'^# \$Header: .*\$$')

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
			if not self.gentoo_copyright_re.match(line):
				return errors.COPYRIGHT_ERROR
		elif num == 1 and line.rstrip('\n') != self.gentoo_license:
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
		if self.leading_spaces.match(line) is None:
			return errors.LEADING_SPACES_ERROR
		if self.trailing_whitespace.match(line) is None:
			return errors.TRAILING_WHITESPACE_ERROR

class EbuildBlankLine(LineCheck):
	repoman_check_name = 'ebuild.minorsyn'
	blank_line = re.compile(r'^$')

	def new(self, pkg):
		self.line_is_blank = False

	def check(self, num, line):
		if self.line_is_blank and self.blank_line.match(line):
			return 'Useless blank line on line: %d'
		if self.blank_line.match(line):
			self.line_is_blank = True
		else:
			self.line_is_blank = False

	def end(self):
		if self.line_is_blank:
			yield 'Useless blank line on last line'

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

	# EAPI=3/Prefix vars
	var_names += ["ED", "EPREFIX", "EROOT"]

	# variables for games.eclass
	var_names += ["Ddir", "GAMES_PREFIX_OPT", "GAMES_DATADIR",
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

class Eapi3EbuildAssignment(EbuildAssignment):
	"""Ensure ebuilds don't assign to readonly EAPI 3-introduced variables."""

	readonly_assignment = re.compile(r'\s*(export\s+)?(ED|EPREFIX|EROOT)=')

	def check_eapi(self, eapi):
		return eapi_supports_prefix(eapi)

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
		r'^\s*dodoc(\s+|\s+.*\s+)(ABOUT-NLS|COPYING|LICENCE|LICENSE)($|\s)')

	def check(self, num, line):
		match = self.uselessdodoc_re.match(line)
		if match:
			return "Useless dodoc '%s'" % (match.group(2), ) + " on line: %d"


class EbuildUselessCdS(LineCheck):
	"""Check for redundant cd ${S} statements"""
	repoman_check_name = 'ebuild.minorsyn'
	method_re = re.compile(r'^\s*src_(prepare|configure|compile|install|test)\s*\(\)')
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

class EapiDefinition(LineCheck):
	""" Check that EAPI is defined before inherits"""
	repoman_check_name = 'EAPI.definition'

	eapi_re = re.compile(r'^EAPI=')
	inherit_re = re.compile(r'^\s*inherit\s')

	def new(self, pkg):
		self.inherit_line = None

	def check(self, num, line):
		if self.eapi_re.match(line) is not None:
			if self.inherit_line is not None:
				return errors.EAPI_DEFINED_AFTER_INHERIT
		elif self.inherit_re.match(line) is not None:
			self.inherit_line = line

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

class EprefixifyDefined(LineCheck):
	""" Check that prefix.eclass is inherited if needed"""

	repoman_check_name = 'eprefixify.defined'

	_eprefixify_re = re.compile(r'\beprefixify\b')
	_inherit_prefix_re = re.compile(r'^\s*inherit\s(.*\s)?prefix\b')

	def new(self, pkg):
		self._prefix_inherited = False

	def check(self, num, line):
		if self._eprefixify_re.search(line) is not None:
			if not self._prefix_inherited:
				return errors.EPREFIXIFY_MISSING_INHERIT
		elif self._inherit_prefix_re.search(line) is not None:
			self._prefix_inherited = True

class NoOffsetWithHelpers(LineCheck):
	""" Check that the image location, the alternate root offset, and the
	offset prefix (D, ROOT, ED, EROOT and EPREFIX) are not used with
	helpers """

	repoman_check_name = 'variable.usedwithhelpers'
	re = re.compile(r'^[^#]*\b(dodir|dohard|exeinto|insinto|into)\s+"?\$\{?(D|ROOT|ED|EROOT|EPREFIX)\b.*')
	error = errors.NO_OFFSET_WITH_HELPERS

class ImplicitRuntimeDeps(LineCheck):
	"""
	Detect the case where DEPEND is set and RDEPEND is unset in the ebuild,
	since this triggers implicit RDEPEND=$DEPEND assignment (prior to EAPI 4).
	"""

	repoman_check_name = 'RDEPEND.implicit'
	_assignment_re = re.compile(r'^\s*(R?DEPEND)\+?=')

	def new(self, pkg):
		self._rdepend = False
		self._depend = False

	def check_eapi(self, eapi):
		# Beginning with EAPI 4, there is no
		# implicit RDEPEND=$DEPEND assignment
		# to be concerned with.
		return eapi_has_implicit_rdepend(eapi)

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

class InheritDeprecated(LineCheck):
	"""Check if ebuild directly or indirectly inherits a deprecated eclass."""

	repoman_check_name = 'inherit.deprecated'

	# deprecated eclass : new eclass (False if no new eclass)
	deprecated_classes = {
		"gems": "ruby-fakegem",
		"php-pear": "php-pear-r1",
		"qt3": False,
		"qt4": "qt4-r2",
		"ruby": "ruby-ng",
		"ruby-gnome2": "ruby-ng-gnome2",
		"x-modular": "xorg-2",
		}

	_inherit_re = re.compile(r'^\s*inherit\s(.*)$')

	def new(self, pkg):
		self._errors = []
		self._indirect_deprecated = set(eclass for eclass in \
			self.deprecated_classes if eclass in pkg.inherited)

	def check(self, num, line):

		direct_inherits = None
		m = self._inherit_re.match(line)
		if m is not None:
			direct_inherits = m.group(1)
			if direct_inherits:
				direct_inherits = direct_inherits.split()

		if not direct_inherits:
			return

		for eclass in direct_inherits:
			replacement = self.deprecated_classes.get(eclass)
			if replacement is None:
				pass
			elif replacement is False:
				self._indirect_deprecated.discard(eclass)
				self._errors.append("please migrate from " + \
					"'%s' (no replacement) on line: %d" % (eclass, num + 1))
			else:
				self._indirect_deprecated.discard(eclass)
				self._errors.append("please migrate from " + \
					"'%s' to '%s' on line: %d" % \
					(eclass, replacement, num + 1))

	def end(self):
		for error in self._errors:
			yield error
		del self._errors

		for eclass in self._indirect_deprecated:
			replacement = self.deprecated_classes[eclass]
			if replacement is False:
				yield "please migrate from indirect " + \
					"inherit of '%s' (no replacement)" % (eclass,)
			else:
				yield "please migrate from indirect " + \
					"inherit of '%s' to '%s'" % \
					(eclass, replacement)
		del self._indirect_deprecated

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

class EMakeParallelDisabled(PhaseCheck):
	"""Check for emake -j1 calls which disable parallelization."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'^\s*emake\s+.*-j\s*1\b')
	error = errors.EMAKE_PARALLEL_DISABLED

	def phase_check(self, num, line):
		if self.in_phase == 'src_compile' or self.in_phase == 'src_install':
			if self.re.match(line):
				return self.error

class EMakeParallelDisabledViaMAKEOPTS(LineCheck):
	"""Check for MAKEOPTS=-j1 that disables parallelization."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'^\s*MAKEOPTS=(\'|")?.*-j\s*1\b')
	error = errors.EMAKE_PARALLEL_DISABLED_VIA_MAKEOPTS

class NoAsNeeded(LineCheck):
	"""Check for calls to the no-as-needed function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'.*\$\(no-as-needed\)')
	error = errors.NO_AS_NEEDED

class PreserveOldLib(LineCheck):
	"""Check for calls to the preserve_old_lib function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'.*preserve_old_lib')
	error = errors.PRESERVE_OLD_LIB

class SandboxAddpredict(LineCheck):
	"""Check for calls to the addpredict function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'(^|\s)addpredict\b')
	error = errors.SANDBOX_ADDPREDICT

class DeprecatedBindnowFlags(LineCheck):
	"""Check for calls to the deprecated bindnow-flags function."""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'.*\$\(bindnow-flags\)')
	error = errors.DEPRECATED_BINDNOW_FLAGS

class WantAutoDefaultValue(LineCheck):
	"""Check setting WANT_AUTO* to latest (default value)."""
	repoman_check_name = 'ebuild.minorsyn'
	_re = re.compile(r'^WANT_AUTO(CONF|MAKE)=(\'|")?latest')

	def check(self, num, line):
		m = self._re.match(line)
		if m is not None:
			return 'WANT_AUTO' + m.group(1) + \
				' redundantly set to default value "latest" on line: %d'

class SrcCompileEconf(PhaseCheck):
	repoman_check_name = 'ebuild.minorsyn'
	configure_re = re.compile(r'\s(econf|./configure)')

	def check_eapi(self, eapi):
		return eapi_has_src_prepare_and_src_configure(eapi)

	def phase_check(self, num, line):
		if self.in_phase == 'src_compile':
			m = self.configure_re.match(line)
			if m is not None:
				return ("'%s'" % m.group(1)) + \
					" call should be moved to src_configure from line: %d"

class SrcUnpackPatches(PhaseCheck):
	repoman_check_name = 'ebuild.minorsyn'
	src_prepare_tools_re = re.compile(r'\s(e?patch|sed)\s')

	def check_eapi(self, eapi):
		return eapi_has_src_prepare_and_src_configure(eapi)

	def phase_check(self, num, line):
		if self.in_phase == 'src_unpack':
			m = self.src_prepare_tools_re.search(line)
			if m is not None:
				return ("'%s'" % m.group(1)) + \
					" call should be moved to src_prepare from line: %d"

class BuiltWithUse(LineCheck):
	repoman_check_name = 'ebuild.minorsyn'
	ignore_line = re.compile(r'^\s*#')
	re = re.compile('^.*built_with_use')
	error = errors.BUILT_WITH_USE

# EAPI-3 checks
class Eapi3DeprecatedFuncs(LineCheck):
	repoman_check_name = 'EAPI.deprecated'
	ignore_line = re.compile(r'(^\s*#)')
	deprecated_commands_re = re.compile(r'^\s*(check_license)\b')

	def check_eapi(self, eapi):
		return eapi not in ('0', '1', '2')

	def check(self, num, line):
		m = self.deprecated_commands_re.match(line)
		if m is not None:
			return ("'%s'" % m.group(1)) + \
				" has been deprecated in EAPI=3 on line: %d"

# EAPI-4 checks
class Eapi4IncompatibleFuncs(LineCheck):
	repoman_check_name = 'EAPI.incompatible'
	ignore_line = re.compile(r'(^\s*#)')
	banned_commands_re = re.compile(r'^\s*(dosed|dohard)')

	def check_eapi(self, eapi):
		return not eapi_has_dosed_dohard(eapi)

	def check(self, num, line):
		m = self.banned_commands_re.match(line)
		if m is not None:
			return ("'%s'" % m.group(1)) + \
				" has been banned in EAPI=4 on line: %d"

class Eapi4GoneVars(LineCheck):
	repoman_check_name = 'EAPI.incompatible'
	ignore_line = re.compile(r'(^\s*#)')
	undefined_vars_re = re.compile(r'.*\$(\{(AA|KV)\}|(AA|KV))')

	def check_eapi(self, eapi):
		return not eapi_exports_AA(eapi) or not eapi_exports_KV(eapi)

	def check(self, num, line):
		m = self.undefined_vars_re.match(line)
		if m is not None:
			return ("variable '$%s'" % m.group(1)) + \
				" is gone in EAPI=4 on line: %d"

class PortageInternal(LineCheck):
	repoman_check_name = 'portage.internal'
	re = re.compile(r'[^#]*\b(ecompress|ecompressdir|prepalldocs)\b')

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		m = self.re.match(line)
		if m is not None:
			return ("'%s'" % m.group(1)) + " called on line: %d"

_constant_checks = tuple((c() for c in (
	EbuildHeader, EbuildWhitespace, EbuildBlankLine, EbuildQuote,
	EbuildAssignment, Eapi3EbuildAssignment, EbuildUselessDodoc,
	EbuildUselessCdS, EbuildNestedDie,
	EbuildPatches, EbuildQuotedA, EapiDefinition, EprefixifyDefined,
	ImplicitRuntimeDeps, InheritAutotools, InheritDeprecated, IUseUndefined,
	EMakeParallelDisabled, EMakeParallelDisabledViaMAKEOPTS, NoAsNeeded,
	DeprecatedBindnowFlags, SrcUnpackPatches, WantAutoDefaultValue,
	SrcCompileEconf, Eapi3DeprecatedFuncs, NoOffsetWithHelpers,
	Eapi4IncompatibleFuncs, Eapi4GoneVars, BuiltWithUse,
	PreserveOldLib, SandboxAddpredict, PortageInternal)))

_here_doc_re = re.compile(r'.*\s<<[-]?(\w+)$')

def run_checks(contents, pkg):
	checks = _constant_checks
	here_doc_delim = None

	for lc in checks:
		lc.new(pkg)
	for num, line in enumerate(contents):

		# Check if we're inside a here-document.
		if here_doc_delim is not None:
			if here_doc_delim.match(line):
				here_doc_delim = None
		if here_doc_delim is None:
			here_doc = _here_doc_re.match(line)
			if here_doc is not None:
				here_doc_delim = re.compile(r'^\s*%s$' % here_doc.group(1))

		if here_doc_delim is None:
			# We're not in a here-document.
			for lc in checks:
				if lc.check_eapi(pkg.metadata['EAPI']):
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
