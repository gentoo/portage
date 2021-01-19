
import re # pylint: disable=unused-import

from repoman.modules.linechecks.base import LineCheck


class BuiltWithUse(LineCheck):
	repoman_check_name = 'ebuild.minorsyn'
	re = re.compile(r'(^|.*\b)built_with_use\b')
	error = 'BUILT_WITH_USE'
