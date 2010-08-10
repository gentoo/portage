# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import paren_reduce
from portage.exception import InvalidDependString

class TestParenReduce(TestCase):

	def testParenReduce(self):

		test_cases = (
			( "A", ["A"]),
			( "( A )", [["A"]]),
			( "|| ( A B )", [ "||", ["A", "B"] ]),
			( "|| ( A || ( B C ) )", [ "||", ["A", "||", ["B", "C"]]]),
			( "|| ( A || ( B C D ) )", [ "||", ["A", "||", ["B", "C", "D"]] ]),
			( "|| ( A || ( B || ( C D ) E ) )", [ "||", ["A", "||", ["B", "||", ["C", "D"], "E"]] ]),
			( "a? ( A )", ["a?", ["A"]]),
		)
		
		test_cases_xfail = (
			"( A",
			"A )",

			"||( A B )",
			"|| (A B )",
			"|| ( A B)",
			"|| ( A B",
			"|| A B )",

			"|| A B",
			"|| ( A B ) )",
			"|| || B C",
			
			"|| ( A B || )",
			
			"a? A",
		)

		for dep_str, expected_result in test_cases:
			self.assertEqual(paren_reduce(dep_str), expected_result)

		for dep_str in test_cases_xfail:
			self.assertRaisesMsg(dep_str,
				InvalidDependString, paren_reduce, dep_str)
