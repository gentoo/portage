# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.update import parse_updates
from portage.dep import Atom

class ParseUpdatesTestCase(TestCase):

	def testParseUpdates(self):
		test_cases = (
		(
			"""
slotmove invalid_atom 0 3
slotmove !=invalid/blocker-3* 0 3
slotmove =valid/atom-3* 0 3 invalid_extra_token
slotmove =valid/atom-3* 0 3
slotmove =valid/atom-3* 0 3/3.1
slotmove =valid/atom-3* 0/0 3
move valid/atom1 valid/atom2 invalid_extra_token
move valid/atom1 invalid_atom2
move invalid_atom1 valid/atom2
move !invalid/blocker1 valid/atom2
move valid/atom1 !invalid/blocker2
move =invalid/operator-1* valid/atom2
move valid/atom1 =invalid/operator-2*
move valid/atom1 valid/atom2
""",
			[
				['slotmove', Atom('=valid/atom-3*'), '0', '3'],
				['move', Atom('valid/atom1'), Atom('valid/atom2')],
			],
			12,
		),

		)

		for input_content, expected_output, expected_error_count in test_cases:
			output_data, errors = parse_updates(input_content)
			self.assertEqual(output_data, expected_output)
			self.assertEqual(len(errors), expected_error_count)
