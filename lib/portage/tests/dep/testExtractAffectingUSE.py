# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import extract_affecting_use
from portage.exception import InvalidDependString

class TestExtractAffectingUSE(TestCase):

	def testExtractAffectingUSE(self):
		test_cases = (
			("a? ( A ) !b? ( B ) !c? ( C ) d? ( D )", "A", ("a",)),
			("a? ( A ) !b? ( B ) !c? ( C ) d? ( D )", "B", ("b",)),
			("a? ( A ) !b? ( B ) !c? ( C ) d? ( D )", "C", ("c",)),
			("a? ( A ) !b? ( B ) !c? ( C ) d? ( D )", "D", ("d",)),

			("a? ( b? ( AB ) )", "AB", ("a", "b")),
			("a? ( b? ( c? ( ABC ) ) )", "ABC", ("a", "b", "c")),

			("a? ( A b? ( c? ( ABC ) AB ) )", "A", ("a",)),
			("a? ( A b? ( c? ( ABC ) AB ) )", "AB", ("a", "b")),
			("a? ( A b? ( c? ( ABC ) AB ) )", "ABC", ("a", "b", "c")),
			("a? ( A b? ( c? ( ABC ) AB ) ) X", "X", []),
			("X a? ( A b? ( c? ( ABC ) AB ) )", "X", []),

			("ab? ( || ( A B ) )", "A", ("ab",)),
			("!ab? ( || ( A B ) )", "B", ("ab",)),
			("ab? ( || ( A || ( b? ( || ( B C ) ) ) ) )", "A", ("ab",)),
			("ab? ( || ( A || ( b? ( || ( B C ) ) ) ) )", "B", ("ab", "b")),
			("ab? ( || ( A || ( b? ( || ( B C ) ) ) ) )", "C", ("ab", "b")),

			("( ab? ( || ( ( A ) || ( b? ( ( ( || ( B ( C ) ) ) ) ) ) ) ) )", "A", ("ab",)),
			("( ab? ( || ( ( A ) || ( b? ( ( ( || ( B ( C ) ) ) ) ) ) ) ) )", "B", ("ab", "b")),
			("( ab? ( || ( ( A ) || ( b? ( ( ( || ( B ( C ) ) ) ) ) ) ) ) )", "C", ("ab", "b")),

			("a? ( A )", "B", []),

			("a? ( || ( A B ) )", "B", ["a"]),

			# test USE dep defaults for bug #363073
			("a? ( >=dev-lang/php-5.2[pcre(+)] )", ">=dev-lang/php-5.2[pcre(+)]", ["a"]),
		)

		test_cases_xfail = (
			("? ( A )", "A"),
			("!? ( A )", "A"),
			("( A", "A"),
			("A )", "A"),

			("||( A B )", "A"),
			("|| (A B )", "A"),
			("|| ( A B)", "A"),
			("|| ( A B", "A"),
			("|| A B )", "A"),
			("|| A B", "A"),
			("|| ( A B ) )", "A"),
			("|| || B C", "A"),
			("|| ( A B || )", "A"),
			("a? A", "A"),
			("( || ( || || ( A ) foo? ( B ) ) )", "A"),
			("( || ( || bar? ( A ) foo? ( B ) ) )", "A"),
		)

		for dep, atom, expected in test_cases:
			expected = set(expected)
			result = extract_affecting_use(dep, atom, eapi="0")
			fail_msg = "dep: " + dep + ", atom: " + atom + ", got: " + \
				" ".join(sorted(result)) + ", expected: " + " ".join(sorted(expected))
			self.assertEqual(result, expected, fail_msg)

		for dep, atom in test_cases_xfail:
			fail_msg = "dep: " + dep + ", atom: " + atom + ", got: " + \
				" ".join(sorted(result)) + ", expected: " + " ".join(sorted(expected))
			self.assertRaisesMsg(fail_msg, \
				InvalidDependString, extract_affecting_use, dep, atom, eapi="0")
