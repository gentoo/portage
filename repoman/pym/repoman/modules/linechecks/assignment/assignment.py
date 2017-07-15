
import re

from portage.eapi import eapi_supports_prefix
from repoman.modules.linechecks.base import LineCheck


class EbuildAssignment(LineCheck):
	"""Ensure ebuilds don't assign to readonly variables."""

	repoman_check_name = 'variable.readonly'
	read_only_vars = 'A|CATEGORY|P|P[VNRF]|PVR|D|WORKDIR|FILESDIR|FEATURES|USE'
	readonly_assignment = re.compile(r'^\s*(export\s+)?(%s)=' % read_only_vars)

	def check(self, num, line):
		match = self.readonly_assignment.match(line)
		e = None
		if match is not None:
			e = self.errors['READONLY_ASSIGNMENT_ERROR']
		return e


class Eapi3EbuildAssignment(EbuildAssignment):
	"""Ensure ebuilds don't assign to readonly EAPI 3-introduced variables."""

	readonly_assignment = re.compile(r'\s*(export\s+)?(ED|EPREFIX|EROOT)=')

	def check_eapi(self, eapi):
		return eapi_supports_prefix(eapi)

