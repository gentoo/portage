# repoman: Checks
# Copyright 2007-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

import codecs
from itertools import chain
import re
import time
import repoman.errors as errors
import portage
from portage.eapi import eapi_supports_prefix, eapi_has_implicit_rdepend, \
	eapi_has_src_prepare_and_src_configure, eapi_has_dosed_dohard, \
	eapi_exports_AA
from portage.const import _ENABLE_INHERIT_CHECK

class LineCheck(object):
	"""Run a check on a line of an ebuild."""
	"""A regular expression to determine whether to ignore the line"""
	ignore_line = False
	"""True if lines containing nothing more than comments with optional
	leading whitespace should be ignored"""
	ignore_comment = True

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
	ignore_comment = False
	leading_spaces = re.compile(r'^[\S\t]')
	trailing_whitespace = re.compile(r'.*([\S]$)')	

	def check(self, num, line):
		if self.leading_spaces.match(line) is None:
			return errors.LEADING_SPACES_ERROR
		if self.trailing_whitespace.match(line) is None:
			return errors.TRAILING_WHITESPACE_ERROR

class EbuildBlankLine(LineCheck):
	repoman_check_name = 'ebuild.minorsyn'
	ignore_comment = False
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
	ignore_comment = False
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

	def check(self, num, line):
		match = self.readonly_assignment.match(line)
		e = None
		if match is not None:
			e = errors.READONLY_ASSIGNMENT_ERROR
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
	"""
	Check that EAPI assignment conforms to PMS section 7.3.1
	(first non-comment, non-blank line).
	"""
	repoman_check_name = 'EAPI.definition'
	ignore_comment = True
	_eapi_re = portage._pms_eapi_re

	def new(self, pkg):
		self._cached_eapi = pkg.metadata['EAPI']
		self._parsed_eapi = None
		self._eapi_line_num = None

	def check(self, num, line):
		if self._eapi_line_num is None and line.strip():
			self._eapi_line_num = num + 1
			m = self._eapi_re.match(line)
			if m is not None:
				self._parsed_eapi = m.group(2)

	def end(self):
		if self._parsed_eapi is None:
			if self._cached_eapi != "0":
				yield "valid EAPI assignment must occur on or before line: %s" % \
					self._eapi_line_num
		elif self._parsed_eapi != self._cached_eapi:
			yield ("bash returned EAPI '%s' which does not match "
				"assignment on line: %s") % \
				(self._cached_eapi, self._eapi_line_num)

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

class NoOffsetWithHelpers(LineCheck):
	""" Check that the image location, the alternate root offset, and the
	offset prefix (D, ROOT, ED, EROOT and EPREFIX) are not used with
	helpers """

	repoman_check_name = 'variable.usedwithhelpers'
	# Ignore matches in quoted strings like this:
	# elog "installed into ${ROOT}usr/share/php5/apc/."
	re = re.compile(r'^[^#"\']*\b(docinto|docompress|dodir|dohard|exeinto|fowners|fperms|insinto|into)\s+"?\$\{?(D|ROOT|ED|EROOT|EPREFIX)\b.*')
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
		"bash-completion": "bash-completion-r1",
		"gems": "ruby-fakegem",
		"git": "git-2",
		"mozconfig-2": "mozconfig-3",
		"mozcoreconf": "mozcoreconf-2",
		"php-ext-pecl-r1": "php-ext-pecl-r2",
		"php-ext-source-r1": "php-ext-source-r2",
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

class InheritEclass(LineCheck):
	"""
	Base class for checking for missing inherits, as well as excess inherits.

	Args:
		eclass: Set to the name of your eclass.
		funcs: A tuple of functions that this eclass provides.
		comprehensive: Is the list of functions complete?
		exempt_eclasses: If these eclasses are inherited, disable the missing
		                  inherit check.
	"""

	def __init__(self, eclass, funcs=None, comprehensive=False,
		exempt_eclasses=None, ignore_missing=False, **kwargs):
		self._eclass = eclass
		self._comprehensive = comprehensive
		self._exempt_eclasses = exempt_eclasses
		self._ignore_missing = ignore_missing
		inherit_re = eclass
		self._inherit_re = re.compile(r'^(\s*|.*[|&]\s*)\binherit\s(.*\s)?%s(\s|$)' % inherit_re)
		# Match when the function is preceded only by leading whitespace, a
		# shell operator such as (, {, |, ||, or &&, or optional variable
		# setting(s). This prevents false postives in things like elog
		# messages, as reported in bug #413285.
		self._func_re = re.compile(r'(^|[|&{(])\s*(\w+=.*)?\b(' + '|'.join(funcs) + r')\b')

	def new(self, pkg):
		self.repoman_check_name = 'inherit.missing'
		# We can't use pkg.inherited because that tells us all the eclass that
		# have been inherited and not just the ones we inherit directly.
		self._inherit = False
		self._func_call = False
		if self._exempt_eclasses is not None:
			inherited = pkg.inherited
			self._disabled = any(x in inherited for x in self._exempt_eclasses)
		else:
			self._disabled = False

	def check(self, num, line):
		if not self._inherit:
			self._inherit = self._inherit_re.match(line)
		if not self._inherit:
			if self._disabled or self._ignore_missing:
				return
			s = self._func_re.search(line)
			if s:
				self._func_call = True
				return '%s.eclass is not inherited, but "%s" found at line: %s' % \
					(self._eclass, s.group(3), '%d')
		elif not self._func_call:
			self._func_call = self._func_re.search(line)

	def end(self):
		if not self._disabled and self._comprehensive and self._inherit and not self._func_call:
			self.repoman_check_name = 'inherit.unused'
			yield 'no function called from %s.eclass; please drop' % self._eclass

# eclasses that export ${ECLASS}_src_(compile|configure|install)
_eclass_export_functions = (
	'ant-tasks', 'apache-2', 'apache-module', 'aspell-dict',
	'autotools-utils', 'base', 'bsdmk', 'cannadic',
	'clutter', 'cmake-utils', 'db', 'distutils', 'elisp',
	'embassy', 'emboss', 'emul-linux-x86', 'enlightenment',
	'font-ebdftopcf', 'font', 'fox', 'freebsd', 'freedict',
	'games', 'games-ggz', 'games-mods', 'gdesklets',
	'gems', 'gkrellm-plugin', 'gnatbuild', 'gnat', 'gnome2',
	'gnome-python-common', 'gnustep-base', 'go-mono', 'gpe',
	'gst-plugins-bad', 'gst-plugins-base', 'gst-plugins-good',
	'gst-plugins-ugly', 'gtk-sharp-module', 'haskell-cabal',
	'horde', 'java-ant-2', 'java-pkg-2', 'java-pkg-simple',
	'java-virtuals-2', 'kde4-base', 'kde4-meta', 'kernel-2',
	'latex-package', 'linux-mod', 'mozlinguas', 'myspell',
	'myspell-r2', 'mysql', 'mysql-v2', 'mythtv-plugins',
	'oasis', 'obs-service', 'office-ext', 'perl-app',
	'perl-module', 'php-ext-base-r1', 'php-ext-pecl-r2',
	'php-ext-source-r2', 'php-lib-r1', 'php-pear-lib-r1',
	'php-pear-r1', 'python-distutils-ng', 'python',
	'qt4-build', 'qt4-r2', 'rox-0install', 'rox', 'ruby',
	'ruby-ng', 'scsh', 'selinux-policy-2', 'sgml-catalog',
	'stardict', 'sword-module', 'tetex-3', 'tetex',
	'texlive-module', 'toolchain-binutils', 'toolchain',
	'twisted', 'vdr-plugin-2', 'vdr-plugin', 'vim',
	'vim-plugin', 'vim-spell', 'virtuoso', 'vmware',
	'vmware-mod', 'waf-utils', 'webapp', 'xemacs-elisp',
	'xemacs-packages', 'xfconf', 'x-modular', 'xorg-2',
	'zproduct'
)

_eclass_info = {
	'autotools': {
		'funcs': (
			'eaclocal', 'eautoconf', 'eautoheader',
			'eautomake', 'eautoreconf', '_elibtoolize',
			'eautopoint'
		),
		'comprehensive': True,

		# Exempt eclasses:
		# git - An EGIT_BOOTSTRAP variable may be used to call one of
		#       the autotools functions.
		# subversion - An ESVN_BOOTSTRAP variable may be used to call one of
		#       the autotools functions.
		'exempt_eclasses': ('git', 'git-2', 'subversion', 'autotools-utils')
	},

	'eutils': {
		'funcs': (
			'estack_push', 'estack_pop', 'eshopts_push', 'eshopts_pop',
			'eumask_push', 'eumask_pop', 'epatch', 'epatch_user',
			'emktemp', 'edos2unix', 'in_iuse', 'use_if_iuse', 'usex',
			'makeopts_jobs'
		),
		'comprehensive': False,

		# These are "eclasses are the whole ebuild" type thing.
		'exempt_eclasses': _eclass_export_functions,
	},

	'flag-o-matic': {
		'funcs': (
			'filter-(ld)?flags', 'strip-flags', 'strip-unsupported-flags',
			'append-((ld|c(pp|xx)?))?flags', 'append-libs',
		),
		'comprehensive': False
	},

	'libtool': {
		'funcs': (
			'elibtoolize',
		),
		'comprehensive': True,
		'exempt_eclasses': ('autotools',)
	},

	'multilib': {
		'funcs': (
			'get_libdir',
		),

		# These are "eclasses are the whole ebuild" type thing.
		'exempt_eclasses': _eclass_export_functions + ('autotools', 'libtool'),

		'comprehensive': False
	},

	'prefix': {
		'funcs': (
			'eprefixify',
		),
		'comprehensive': True
	},

	'toolchain-funcs': {
		'funcs': (
			'gen_usr_ldscript',
		),
		'comprehensive': False
	},

	'user': {
		'funcs': (
			'enewuser', 'enewgroup',
			'egetent', 'egethome', 'egetshell', 'esethome'
		),
		'comprehensive': True
	}
}

if not _ENABLE_INHERIT_CHECK:
	# Since the InheritEclass check is experimental, in the stable branch
	# we emulate the old eprefixify.defined and inherit.autotools checks.
	_eclass_info = {
		'autotools': {
			'funcs': (
				'eaclocal', 'eautoconf', 'eautoheader',
				'eautomake', 'eautoreconf', '_elibtoolize',
				'eautopoint'
			),
			'comprehensive': True,
			'ignore_missing': True,
			'exempt_eclasses': ('git', 'git-2', 'subversion', 'autotools-utils')
		},

		'prefix': {
			'funcs': (
				'eprefixify',
			),
			'comprehensive': False
		}
	}

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
	re = re.compile(r'(^|.*\b)built_with_use\b')
	error = errors.BUILT_WITH_USE

class DeprecatedUseq(LineCheck):
	"""Checks for use of the deprecated useq function"""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'(^|.*\b)useq\b')
	error = errors.USEQ_ERROR

class DeprecatedHasq(LineCheck):
	"""Checks for use of the deprecated hasq function"""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'(^|.*\b)hasq\b')
	error = errors.HASQ_ERROR

# EAPI-3 checks
class Eapi3DeprecatedFuncs(LineCheck):
	repoman_check_name = 'EAPI.deprecated'
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
	undefined_vars_re = re.compile(r'.*\$(\{(AA|KV|EMERGE_FROM)\}|(AA|KV|EMERGE_FROM))')

	def check_eapi(self, eapi):
		# AA, KV, and EMERGE_FROM should not be referenced in EAPI 4 or later.
		return not eapi_exports_AA(eapi)

	def check(self, num, line):
		m = self.undefined_vars_re.match(line)
		if m is not None:
			return ("variable '$%s'" % m.group(1)) + \
				" is gone in EAPI=4 on line: %d"

class PortageInternal(LineCheck):
	repoman_check_name = 'portage.internal'
	ignore_comment = True
	# Match when the command is preceded only by leading whitespace or a shell
	# operator such as (, {, |, ||, or &&. This prevents false postives in
	# things like elog messages, as reported in bug #413285.
	re = re.compile(r'^(\s*|.*[|&{(]+\s*)\b(ecompress|ecompressdir|env-update|prepall|prepalldocs|preplib)\b')

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		m = self.re.match(line)
		if m is not None:
			return ("'%s'" % m.group(2)) + " called on line: %d"

class PortageInternalVariableAssignment(LineCheck):

	repoman_check_name = 'portage.internal'
	internal_assignment = re.compile(r'\s*(export\s+)?(EXTRA_ECONF|EXTRA_EMAKE)\+?=')

	def check(self, num, line):
		match = self.internal_assignment.match(line)
		e = None
		if match is not None:
			e = 'Assignment to variable %s' % match.group(2)
			e += ' on line: %d'
		return e

_constant_checks = tuple(chain((c() for c in (
	EbuildHeader, EbuildWhitespace, EbuildBlankLine, EbuildQuote,
	EbuildAssignment, Eapi3EbuildAssignment, EbuildUselessDodoc,
	EbuildUselessCdS, EbuildNestedDie,
	EbuildPatches, EbuildQuotedA, EapiDefinition,
	ImplicitRuntimeDeps,
	EMakeParallelDisabled, EMakeParallelDisabledViaMAKEOPTS, NoAsNeeded,
	DeprecatedBindnowFlags, SrcUnpackPatches, WantAutoDefaultValue,
	SrcCompileEconf, Eapi3DeprecatedFuncs, NoOffsetWithHelpers,
	Eapi4IncompatibleFuncs, Eapi4GoneVars, BuiltWithUse,
	PreserveOldLib, SandboxAddpredict, PortageInternal,
	PortageInternalVariableAssignment, DeprecatedUseq, DeprecatedHasq)),
	(InheritEclass(k, **kwargs) for k, kwargs in _eclass_info.items())))

_here_doc_re = re.compile(r'.*\s<<[-]?(\w+)$')
_ignore_comment_re = re.compile(r'^\s*#')

def run_checks(contents, pkg):
	unicode_escape_codec = codecs.lookup('unicode_escape')
	unicode_escape = lambda x: unicode_escape_codec.decode(x)[0]
	checks = _constant_checks
	here_doc_delim = None
	multiline = None

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
		if here_doc_delim is not None:
			continue

		# Unroll multiline escaped strings so that we can check things:
		#		inherit foo bar \
		#			moo \
		#			cow
		# This will merge these lines like so:
		#		inherit foo bar 	moo 	cow
		try:
			# A normal line will end in the two bytes: <\> <\n>.  So decoding
			# that will result in python thinking the <\n> is being escaped
			# and eat the single <\> which makes it hard for us to detect.
			# Instead, strip the newline (which we know all lines have), and
			# append a <0>.  Then when python escapes it, if the line ended
			# in a <\>, we'll end up with a <\0> marker to key off of.  This
			# shouldn't be a problem with any valid ebuild ...
			line_escaped = unicode_escape(line.rstrip('\n') + '0')
		except SystemExit:
			raise
		except:
			# Who knows what kind of crazy crap an ebuild will have
			# in it -- don't allow it to kill us.
			line_escaped = line
		if multiline:
			# Chop off the \ and \n bytes from the previous line.
			multiline = multiline[:-2] + line
			if not line_escaped.endswith('\0'):
				line = multiline
				num = multinum
				multiline = None
			else:
				continue
		else:
			if line_escaped.endswith('\0'):
				multinum = num
				multiline = line
				continue

		# Finally we have a full line to parse.
		is_comment = _ignore_comment_re.match(line) is not None
		for lc in checks:
			if is_comment and lc.ignore_comment:
				continue
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
