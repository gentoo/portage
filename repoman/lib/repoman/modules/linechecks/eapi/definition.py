
from repoman.modules.linechecks.base import LineCheck
from repoman._portage import portage


class EapiDefinition(LineCheck):
	"""
	Check that EAPI assignment conforms to PMS section 7.3.1
	(first non-comment, non-blank line).
	"""
	repoman_check_name = 'EAPI.definition'
	ignore_comment = True
	_eapi_re = portage._pms_eapi_re

	def new(self, pkg):
		self._cached_eapi = pkg.eapi
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
			yield (
				"bash returned EAPI '%s' which does not match "
				"assignment on line: %s" %
				(self._cached_eapi, self._eapi_line_num))
