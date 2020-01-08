
import re

from portage.eapi import (
	eapi_has_src_prepare_and_src_configure, eapi_has_dosed_dohard,
	eapi_exports_AA, eapi_has_pkg_pretend)
from repoman.modules.linechecks.base import LineCheck


# EAPI <2 checks
class UndefinedSrcPrepareSrcConfigurePhases(LineCheck):
	repoman_check_name = 'EAPI.incompatible'
	src_configprepare_re = re.compile(r'\s*(src_configure|src_prepare)\s*\(\)')

	def check_eapi(self, eapi):
		return not eapi_has_src_prepare_and_src_configure(eapi)

	def check(self, num, line):
		m = self.src_configprepare_re.match(line)
		if m is not None:
			return ("'%s'" % m.group(1)) + \
				" phase is not defined in EAPI < 2"


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
				" has been deprecated in EAPI=3"


# EAPI <4 checks
class UndefinedPkgPretendPhase(LineCheck):
	repoman_check_name = 'EAPI.incompatible'
	pkg_pretend_re = re.compile(r'\s*(pkg_pretend)\s*\(\)')

	def check_eapi(self, eapi):
		return not eapi_has_pkg_pretend(eapi)

	def check(self, num, line):
		m = self.pkg_pretend_re.match(line)
		if m is not None:
			return ("'%s'" % m.group(1)) + \
				" phase is not defined in EAPI < 4"


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
				" has been banned in EAPI=4"


class Eapi4GoneVars(LineCheck):
	repoman_check_name = 'EAPI.incompatible'
	undefined_vars_re = re.compile(
		r'.*\$(\{(AA|KV|EMERGE_FROM)\}|(AA|KV|EMERGE_FROM))')

	def check_eapi(self, eapi):
		# AA, KV, and EMERGE_FROM should not be referenced in EAPI 4 or later.
		return not eapi_exports_AA(eapi)

	def check(self, num, line):
		m = self.undefined_vars_re.match(line)
		if m is not None:
			return ("variable '$%s'" % m.group(1)) + \
				" is gone in EAPI=4"
