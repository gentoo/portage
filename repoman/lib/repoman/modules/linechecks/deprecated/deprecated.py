
import re # pylint: disable=unused-import

from repoman.modules.linechecks.base import LineCheck


class DeprecatedUseq(LineCheck):
	"""Checks for use of the deprecated useq function"""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'(^|.*\b)useq\b')
	error = 'USEQ_ERROR'


class DeprecatedHasq(LineCheck):
	"""Checks for use of the deprecated hasq function"""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'(^|.*\b)hasq\b')
	error = 'HASQ_ERROR'


class PreserveOldLib(LineCheck):
	"""Check for calls to the deprecated preserve_old_lib function."""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'.*preserve_old_lib')
	error = 'PRESERVE_OLD_LIB'


class DeprecatedBindnowFlags(LineCheck):
	"""Check for calls to the deprecated bindnow-flags function."""
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'.*\$\(bindnow-flags\)')
	error = 'DEPRECATED_BINDNOW_FLAGS'
