
import re

from repoman.modules.linechecks.base import LineCheck


class EMakeParallelDisabledViaMAKEOPTS(LineCheck):
	"""Check for MAKEOPTS=-j1 that disables parallelization."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'^\s*MAKEOPTS=(\'|")?.*-j\s*1\b')
	error = 'EMAKE_PARALLEL_DISABLED_VIA_MAKEOPTS'


class WantAutoDefaultValue(LineCheck):
	"""Check setting WANT_AUTO* to latest (default value)."""
	repoman_check_name = 'ebuild.minorsyn'
	_re = re.compile(r'^WANT_AUTO(CONF|MAKE)=(\'|")?latest')

	def check(self, num, line):
		m = self._re.match(line)
		if m is not None:
			return 'WANT_AUTO' + m.group(1) + \
				' redundantly set to default value "latest"'
