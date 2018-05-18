# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import tempfile

from portage.const import PORTAGE_BIN_PATH
from portage.tests import TestCase


class TestEAPI7VerFuncs(TestCase):
	def _test_output(self, test_cases):
		"""
		Test that commands in test_cases produce expected output.
		"""
		with tempfile.NamedTemporaryFile('w') as test_script:
			test_script.write('source "%s"/eapi7-ver-funcs.sh\n'
					% (PORTAGE_BIN_PATH,))
			for cmd, exp in test_cases:
				test_script.write('%s\n' % (cmd,))
			test_script.flush()

			s = subprocess.Popen(['bash', test_script.name],
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE)
			sout, serr = s.communicate()
			self.assertEqual(s.returncode, 0)

			for test_case, result in zip(test_cases, sout.decode().splitlines()):
				cmd, exp = test_case
				self.assertEqual(result, exp,
						'%s -> %s; expected: %s' % (cmd, result, exp))

	def _test_return(self, test_cases):
		"""
		Test that commands in test_cases give appropriate exit codes.
		"""
		with tempfile.NamedTemporaryFile('w+') as test_script:
			test_script.write('source "%s"/eapi7-ver-funcs.sh\n'
					% (PORTAGE_BIN_PATH,))
			for cmd, exp in test_cases:
				test_script.write('%s; echo $?\n' % (cmd,))
			test_script.flush()

			s = subprocess.Popen(['bash', test_script.name],
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE)
			sout, serr = s.communicate()
			self.assertEqual(s.returncode, 0)

			for test_case, result in zip(test_cases, sout.decode().splitlines()):
				cmd, exp = test_case
				self.assertEqual(result, exp,
						'%s -> %s; expected: %s' % (cmd, result, exp))

	def _test_fail(self, test_cases):
		"""
		Test that commands in test_cases fail.
		"""

		for cmd in test_cases:
			test = '''
source "%s"/eapi7-ver-funcs.sh
die() { exit 1; }
%s''' % (PORTAGE_BIN_PATH, cmd)

			s = subprocess.Popen(['bash', '-c', test],
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE)
			sout, serr = s.communicate()
			self.assertEqual(s.returncode, 1,
					'"%s" did not fail; output: %s; %s)'
					% (cmd, sout.decode(), serr.decode()))

	def test_ver_cut(self):
		test_cases = [
			# (command, output)
			('ver_cut 1 1.2.3', '1'),
			('ver_cut 1-1 1.2.3', '1'),
			('ver_cut 1-2 1.2.3', '1.2'),
			('ver_cut 2- 1.2.3', '2.3'),
			('ver_cut 1- 1.2.3', '1.2.3'),
			('ver_cut 3-4 1.2.3b_alpha4', '3b'),
			('ver_cut 5 1.2.3b_alpha4', 'alpha'),
			('ver_cut 1-2 .1.2.3', '1.2'),
			('ver_cut 0-2 .1.2.3', '.1.2'),
			('ver_cut 2-3 1.2.3.', '2.3'),
			('ver_cut 2- 1.2.3.', '2.3.'),
			('ver_cut 2-4 1.2.3.', '2.3.'),
		]
		self._test_output(test_cases)

	def test_ver_rs(self):
		test_cases = [
			# (command, output)
			('ver_rs 1 - 1.2.3', '1-2.3'),
			('ver_rs 2 - 1.2.3', '1.2-3'),
			('ver_rs 1-2 - 1.2.3.4', '1-2-3.4'),
			('ver_rs 2- - 1.2.3.4', '1.2-3-4'),
			('ver_rs 2 . 1.2-3', '1.2.3'),
			('ver_rs 3 . 1.2.3a', '1.2.3.a'),
			('ver_rs 2-3 - 1.2_alpha4', '1.2-alpha-4'),
			('ver_rs 3 - 2 "" 1.2.3b_alpha4', '1.23-b_alpha4'),
			('ver_rs 3-5 _ 4-6 - a1b2c3d4e5', 'a1b_2-c-3-d4e5'),
			('ver_rs 1 - .1.2.3', '.1-2.3'),
			('ver_rs 0 - .1.2.3', '-1.2.3'),
		]
		self._test_output(test_cases)

	def test_truncated_range(self):
		test_cases = [
			# (command, output)
			('ver_cut 0-2 1.2.3', '1.2'),
			('ver_cut 2-5 1.2.3', '2.3'),
			('ver_cut 4 1.2.3', ''),
			('ver_cut 0 1.2.3', ''),
			('ver_cut 4- 1.2.3', ''),
			('ver_rs 0 - 1.2.3', '1.2.3'),
			('ver_rs 3 . 1.2.3', '1.2.3'),
			('ver_rs 3- . 1.2.3', '1.2.3'),
			('ver_rs 3-5 . 1.2.3', '1.2.3'),
		]
		self._test_output(test_cases)

	def test_invalid_range(self):
		test_cases = [
			'ver_cut foo 1.2.3',
			'ver_rs -3 _ a1b2c3d4e5',
			'ver_rs 5-3 _ a1b2c3d4e5',
		]
		self._test_fail(test_cases)

	def test_ver_test(self):
		test_cases = [
			# Tests from Portage's test_vercmp.py
			('ver_test 6.0 -gt 5.0', '0'),
			('ver_test 5.0 -gt 5', '0'),
			('ver_test 1.0-r1 -gt 1.0-r0', '0'),
			('ver_test 999999999999999999 -gt 999999999999999998', '0'),  # 18 digits
			('ver_test 1.0.0 -gt 1.0', '0'),
			('ver_test 1.0.0 -gt 1.0b', '0'),
			('ver_test 1b -gt 1', '0'),
			('ver_test 1b_p1 -gt 1_p1', '0'),
			('ver_test 1.1b -gt 1.1', '0'),
			('ver_test 12.2.5 -gt 12.2b', '0'),
			('ver_test 4.0 -lt 5.0', '0'),
			('ver_test 5 -lt 5.0', '0'),
			('ver_test 1.0_pre2 -lt 1.0_p2', '0'),
			('ver_test 1.0_alpha2 -lt 1.0_p2', '0'),
			('ver_test 1.0_alpha1 -lt 1.0_beta1', '0'),
			('ver_test 1.0_beta3 -lt 1.0_rc3', '0'),
			('ver_test 1.001000000000000001 -lt 1.001000000000000002', '0'),
			('ver_test 1.00100000000 -lt 1.001000000000000001', '0'),
			('ver_test 999999999999999998 -lt 999999999999999999', '0'),
			('ver_test 1.01 -lt 1.1', '0'),
			('ver_test 1.0-r0 -lt 1.0-r1', '0'),
			('ver_test 1.0 -lt 1.0-r1', '0'),
			('ver_test 1.0 -lt 1.0.0', '0'),
			('ver_test 1.0b -lt 1.0.0', '0'),
			('ver_test 1_p1 -lt 1b_p1', '0'),
			('ver_test 1 -lt 1b', '0'),
			('ver_test 1.1 -lt 1.1b', '0'),
			('ver_test 12.2b -lt 12.2.5', '0'),
			('ver_test 4.0 -eq 4.0', '0'),
			('ver_test 1.0 -eq 1.0', '0'),
			('ver_test 1.0-r0 -eq 1.0', '0'),
			('ver_test 1.0 -eq 1.0-r0', '0'),
			('ver_test 1.0-r0 -eq 1.0-r0', '0'),
			('ver_test 1.0-r1 -eq 1.0-r1', '0'),
			('ver_test 1 -eq 2', '1'),
			('ver_test 1.0_alpha -eq 1.0_pre', '1'),
			('ver_test 1.0_beta -eq 1.0_alpha', '1'),
			('ver_test 1 -eq 0.0', '1'),
			('ver_test 1.0-r0 -eq 1.0-r1', '1'),
			('ver_test 1.0-r1 -eq 1.0-r0', '1'),
			('ver_test 1.0 -eq 1.0-r1', '1'),
			('ver_test 1.0-r1 -eq 1.0', '1'),
			('ver_test 1.0 -eq 1.0.0', '1'),
			('ver_test 1_p1 -eq 1b_p1', '1'),
			('ver_test 1b -eq 1', '1'),
			('ver_test 1.1b -eq 1.1', '1'),
			('ver_test 12.2b -eq 12.2', '1'),

			# A subset of tests from Paludis
			('ver_test 1.0_alpha -gt 1_alpha', '0'),
			('ver_test 1.0_alpha -gt 1', '0'),
			('ver_test 1.0_alpha -lt 1.0', '0'),
			('ver_test 1.2.0.0_alpha7-r4 -gt 1.2_alpha7-r4', '0'),
			('ver_test 0001 -eq 1', '0'),
			('ver_test 01 -eq 001', '0'),
			('ver_test 0001.1 -eq 1.1', '0'),
			('ver_test 01.01 -eq 1.01', '0'),
			('ver_test 1.010 -eq 1.01', '0'),
			('ver_test 1.00 -eq 1.0', '0'),
			('ver_test 1.0100 -eq 1.010', '0'),
			('ver_test 1-r00 -eq 1-r0', '0'),

			# Additional tests
			('ver_test 0_rc99 -lt 0', '0'),
			('ver_test 011 -eq 11', '0'),
			('ver_test 019 -eq 19', '0'),
			('ver_test 1.2 -eq 001.2', '0'),
			('ver_test 1.2 -gt 1.02', '0'),
			('ver_test 1.2a -lt 1.2b', '0'),
			('ver_test 1.2_pre1 -gt 1.2_pre1_beta2', '0'),
			('ver_test 1.2_pre1 -lt 1.2_pre1_p2', '0'),
			('ver_test 1.00 -lt 1.0.0', '0'),
			('ver_test 1.010 -eq 1.01', '0'),
			('ver_test 1.01 -lt 1.1', '0'),
			('ver_test 1.2_pre08-r09 -eq 1.2_pre8-r9', '0'),
			('ver_test 0 -lt 576460752303423488', '0'),  # 2**59
			('ver_test 0 -lt 9223372036854775808', '0'),  # 2**63
		]
		self._test_return(test_cases)

	def test_invalid_test(self):
		test_cases = [
			# Bad number or ordering of arguments
			'ver_test 1',
			'ver_test 1 -lt 2 3',
			'ver_test -lt 1 2',

			# Bad operators
			'ver_test 1 "<" 2',
			'ver_test 1 lt 2',
			'ver_test 1 -foo 2',

			# Malformed versions
			'ver_test "" -ne 1',
			'ver_test 1. -ne 1',
			'ver_test 1ab -ne 1',
			'ver_test b -ne 1',
			'ver_test 1-r1_pre -ne 1',
			'ver_test 1-pre1 -ne 1',
			'ver_test 1_foo -ne 1',
			'ver_test 1_pre1.1 -ne 1',
			'ver_test 1-r1.0 -ne 1',
			'ver_test cvs.9999 -ne 9999',
		]
		self._test_fail(test_cases)
