# Copyright 2010-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import paren_reduce
from portage.exception import InvalidDependString

class TestParenReduce(TestCase):

	def testParenReduce(self):

		test_cases = (
			("A", ["A"]),
			("( A )", ["A"]),
			("|| ( A B )", ["||", ["A", "B"]]),
			("|| ( A || ( B C ) )", ["||", ["A", "||", ["B", "C"]]]),
			("|| ( A || ( B C D ) )", ["||", ["A", "||", ["B", "C", "D"]]]),
			("|| ( A || ( B || ( C D ) E ) )", ["||", ["A", "||", ["B", "||", ["C", "D"], "E"]]]),
			("a? ( A )", ["a?", ["A"]]),

			("( || ( ( ( A ) B ) ) )", ["A", "B"]),
			("( || ( || ( ( A ) B ) ) )", ["||", ["A", "B"]]),
			("|| ( A )", ["A"]),
			("( || ( || ( || ( A ) foo? ( B ) ) ) )", ["||", ["A", "foo?", ["B"]]]),
			("( || ( || ( bar? ( A ) || ( foo? ( B ) ) ) ) )", ["||", ["bar?", ["A"], "foo?", ["B"]]]),
			("A || ( ) foo? ( ) B", ["A", "B"]),

			("|| ( A ) || ( B )", ["A", "B"]),
			("foo? ( A ) foo? ( B )", ["foo?", ["A"], "foo?", ["B"]]),

			("|| ( ( A B ) C )", ["||", [["A", "B"], "C"]]),
			("|| ( ( A B ) ( C ) )", ["||", [["A", "B"], "C"]]),
			# test USE dep defaults for bug #354003
			(">=dev-lang/php-5.2[pcre(+)]", [">=dev-lang/php-5.2[pcre(+)]"]),
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

			"( || ( || || ( A ) foo? ( B ) ) )",
			"( || ( || bar? ( A ) foo? ( B ) ) )",
		)

		for dep_str, expected_result in test_cases:
			self.assertEqual(paren_reduce(dep_str, _deprecation_warn=False),
				expected_result,
				"input: '%s' result: %s != %s" % (dep_str,
				paren_reduce(dep_str, _deprecation_warn=False),
				expected_result))

		for dep_str in test_cases_xfail:
			self.assertRaisesMsg(dep_str,
				InvalidDependString, paren_reduce, dep_str,
					_deprecation_warn=False)
