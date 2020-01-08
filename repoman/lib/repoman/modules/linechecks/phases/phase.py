
import re

from portage.eapi import eapi_has_src_prepare_and_src_configure
from repoman.modules.linechecks.base import LineCheck


class PhaseCheck(LineCheck):
	""" basic class for function detection """

	func_end_re = re.compile(r'^\}$')
	phases_re = re.compile('(%s)' % '|'.join((
		'pkg_pretend', 'pkg_setup', 'src_unpack', 'src_prepare',
		'src_configure', 'src_compile', 'src_test', 'src_install',
		'pkg_preinst', 'pkg_postinst', 'pkg_prerm', 'pkg_postrm',
		'pkg_config')))
	in_phase = ''

	def check(self, num, line):
		m = self.phases_re.match(line)
		if m is not None:
			self.in_phase = m.group(1)
		if self.in_phase != '' and self.func_end_re.match(line) is not None:
			self.in_phase = ''

		return self.phase_check(num, line)

	def phase_check(self, num, line):
		""" override this function for your checks """
		pass


class EMakeParallelDisabled(PhaseCheck):
	"""Check for emake -j1 calls which disable parallelization."""
	repoman_check_name = 'upstream.workaround'
	re = re.compile(r'^\s*emake\s+.*-j\s*1\b')

	def phase_check(self, num, line):
		if self.in_phase == 'src_compile' or self.in_phase == 'src_install':
			if self.re.match(line):
				return self.errors['EMAKE_PARALLEL_DISABLED']


class SrcCompileEconf(PhaseCheck):
	repoman_check_name = 'ebuild.minorsyn'
	configure_re = re.compile(r'\s(econf|./configure)')

	def check_eapi(self, eapi):
		return eapi_has_src_prepare_and_src_configure(eapi)

	def phase_check(self, num, line):
		if self.in_phase == 'src_compile':
			m = self.configure_re.match(line)
			if m is not None:
				return ("'%s'" % m.group(1)) + \
					" call should be moved to src_configure"


class SrcUnpackPatches(PhaseCheck):
	repoman_check_name = 'ebuild.minorsyn'
	src_prepare_tools_re = re.compile(r'\s(e?patch|sed)\s')

	def check_eapi(self, eapi):
		return eapi_has_src_prepare_and_src_configure(eapi)

	def phase_check(self, num, line):
		if self.in_phase == 'src_unpack':
			m = self.src_prepare_tools_re.search(line)
			if m is not None:
				return ("'%s'" % m.group(1)) + \
					" call should be moved to src_prepare"
