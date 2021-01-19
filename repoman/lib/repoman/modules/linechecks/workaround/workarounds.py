
import re # pylint: disable=unused-import

from repoman.modules.linechecks.base import LineCheck


class NoAsNeeded(LineCheck):
	"""Check for calls to the no-as-needed function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'.*\$\(no-as-needed\)')
	error = 'NO_AS_NEEDED'
