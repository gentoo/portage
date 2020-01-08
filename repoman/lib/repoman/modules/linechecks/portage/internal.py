
import re

from repoman.modules.linechecks.base import LineCheck


class PortageInternal(LineCheck):
	repoman_check_name = 'portage.internal'
	ignore_comment = True
	# Match when the command is preceded only by leading whitespace or a shell
	# operator such as (, {, |, ||, or &&. This prevents false positives in
	# things like elog messages, as reported in bug #413285.

	internal_portage_func_or_var = (
		'ecompress|ecompressdir|env-update|prepall|prepalldocs|preplib')
	re = re.compile(
		r'^(\s*|.*[|&{(]+\s*)\b(%s)\b' % internal_portage_func_or_var)

	def check(self, num, line):
		"""Run the check on line and return error if there is one"""
		m = self.re.match(line)
		if m is not None:
			return "'%s' called" % m.group(2)


class PortageInternalVariableAssignment(LineCheck):
	repoman_check_name = 'portage.internal'
	internal_assignment = re.compile(
		r'\s*(export\s+)?(EXTRA_ECONF|EXTRA_EMAKE)\+?=')

	def check(self, num, line):
		match = self.internal_assignment.match(line)
		if match is not None:
			return 'Assignment to variable %s' % match.group(2)
