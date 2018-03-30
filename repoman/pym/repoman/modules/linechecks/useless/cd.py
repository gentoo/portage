
import re

from repoman.modules.linechecks.base import LineCheck


class EbuildUselessCdS(LineCheck):
	"""Check for redundant cd ${S} statements"""
	repoman_check_name = 'ebuild.minorsyn'
	_src_phases = r'^\s*src_(prepare|configure|compile|install|test)\s*\(\)'
	method_re = re.compile(_src_phases)
	cds_re = re.compile(r'^\s*cd\s+("\$(\{S\}|S)"|\$(\{S\}|S))\s')

	def __init__(self, errors):
		self.errors = errors
		self.check_next_line = False

	def check(self, num, line):
		if self.check_next_line:
			self.check_next_line = False
			if self.cds_re.match(line):
				return self.errors['REDUNDANT_CD_S_ERROR']
		elif self.method_re.match(line):
			self.check_next_line = True
