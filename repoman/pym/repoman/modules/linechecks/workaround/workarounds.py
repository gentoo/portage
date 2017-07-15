
import re

from repoman.modules.linechecks.base import LineCheck


class NoAsNeeded(LineCheck):
	"""Check for calls to the no-as-needed function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'.*\$\(no-as-needed\)')
	error = 'NO_AS_NEEDED'


class SandboxAddpredict(LineCheck):
	"""Check for calls to the addpredict function."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'(^|\s)addpredict\b')
	error = 'SANDBOX_ADDPREDICT'
