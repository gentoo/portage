# Copyright 2010-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import check_required_use
from portage.exception import InvalidDependString

class TestCheckRequiredUse(TestCase):

	def testCheckRequiredUse(self):
		test_cases = (
			("|| ( a b )", [], ["a", "b"], False),
			("|| ( a b )", ["a"], ["a", "b"], True),
			("|| ( a b )", ["b"], ["a", "b"], True),
			("|| ( a b )", ["a", "b"], ["a", "b"], True),

			("^^ ( a b )", [], ["a", "b"], False),
			("^^ ( a b )", ["a"], ["a", "b"], True),
			("^^ ( a b )", ["b"], ["a", "b"], True),
			("^^ ( a b )", ["a", "b"], ["a", "b"], False),
			("?? ( a b )", ["a", "b"], ["a", "b"], False),
			("?? ( a b )", ["a"], ["a", "b"], True),
			("?? ( a b )", ["b"], ["a", "b"], True),
			("?? ( a b )", [], ["a", "b"], True),
			("?? ( )", [], [], True),

			("^^ ( || ( a b ) c )", [], ["a", "b", "c"], False),
			("^^ ( || ( a b ) c )", ["a"], ["a", "b", "c"], True),

			("^^ ( || ( ( a b ) ) ( c ) )", [], ["a", "b", "c"], False),
			("( ^^ ( ( || ( ( a ) ( b ) ) ) ( ( c ) ) ) )", ["a"], ["a", "b", "c"], True),

			("a || ( b c )", ["a"], ["a", "b", "c"], False),
			("|| ( b c ) a", ["a"], ["a", "b", "c"], False),

			("|| ( a b c )", ["a"], ["a", "b", "c"], True),
			("|| ( a b c )", ["b"], ["a", "b", "c"], True),
			("|| ( a b c )", ["c"], ["a", "b", "c"], True),

			("^^ ( a b c )", ["a"], ["a", "b", "c"], True),
			("^^ ( a b c )", ["b"], ["a", "b", "c"], True),
			("^^ ( a b c )", ["c"], ["a", "b", "c"], True),
			("^^ ( a b c )", ["a", "b"], ["a", "b", "c"], False),
			("^^ ( a b c )", ["b", "c"], ["a", "b", "c"], False),
			("^^ ( a b c )", ["a", "c"], ["a", "b", "c"], False),
			("^^ ( a b c )", ["a", "b", "c"], ["a", "b", "c"], False),

			("a? ( ^^ ( b c ) )", [], ["a", "b", "c"], True),
			("a? ( ^^ ( b c ) )", ["a"], ["a", "b", "c"], False),
			("a? ( ^^ ( b c ) )", ["b"], ["a", "b", "c"], True),
			("a? ( ^^ ( b c ) )", ["c"], ["a", "b", "c"], True),
			("a? ( ^^ ( b c ) )", ["a", "b"], ["a", "b", "c"], True),
			("a? ( ^^ ( b c ) )", ["a", "b", "c"], ["a", "b", "c"], False),

			("^^ ( a? ( !b ) !c? ( d ) )", [], ["a", "b", "c", "d"], False),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a"], ["a", "b", "c", "d"], True),
			# note: this one is EAPI-dependent, it used to be True for EAPI <7
			("^^ ( a? ( !b ) !c? ( d ) )", ["c"], ["a", "b", "c", "d"], False),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a", "c"], ["a", "b", "c", "d"], True),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a", "b", "c"], ["a", "b", "c", "d"], False),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a", "b", "d"], ["a", "b", "c", "d"], True),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a", "b", "d"], ["a", "b", "c", "d"], True),
			("^^ ( a? ( !b ) !c? ( d ) )", ["a", "d"], ["a", "b", "c", "d"], False),

			("|| ( ^^ ( a b ) ^^ ( b c ) )", [], ["a", "b", "c"], False),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["a"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["b"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["c"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["a", "b"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["a", "c"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["b", "c"], ["a", "b", "c"], True),
			("|| ( ^^ ( a b ) ^^ ( b c ) )", ["a", "b", "c"], ["a", "b", "c"], False),

			("^^ ( || ( a b ) ^^ ( b c ) )", [], ["a", "b", "c"], False),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["a"], ["a", "b", "c"], True),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["b"], ["a", "b", "c"], False),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["c"], ["a", "b", "c"], True),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["a", "b"], ["a", "b", "c"], False),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["a", "c"], ["a", "b", "c"], False),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["b", "c"], ["a", "b", "c"], True),
			("^^ ( || ( a b ) ^^ ( b c ) )", ["a", "b", "c"], ["a", "b", "c"], True),

			("|| ( ( a b ) c )", ["a", "b", "c"], ["a", "b", "c"], True),
			("|| ( ( a b ) c )", ["b", "c"], ["a", "b", "c"], True),
			("|| ( ( a b ) c )", ["a", "c"], ["a", "b", "c"], True),
			("|| ( ( a b ) c )", ["a", "b"], ["a", "b", "c"], True),
			("|| ( ( a b ) c )", ["a"], ["a", "b", "c"], False),
			("|| ( ( a b ) c )", ["b"], ["a", "b", "c"], False),
			("|| ( ( a b ) c )", ["c"], ["a", "b", "c"], True),
			("|| ( ( a b ) c )", [], ["a", "b", "c"], False),

			("^^ ( ( a b ) c )", ["a", "b", "c"], ["a", "b", "c"], False),
			("^^ ( ( a b ) c )", ["b", "c"], ["a", "b", "c"], True),
			("^^ ( ( a b ) c )", ["a", "c"], ["a", "b", "c"], True),
			("^^ ( ( a b ) c )", ["a", "b"], ["a", "b", "c"], True),
			("^^ ( ( a b ) c )", ["a"], ["a", "b", "c"], False),
			("^^ ( ( a b ) c )", ["b"], ["a", "b", "c"], False),
			("^^ ( ( a b ) c )", ["c"], ["a", "b", "c"], True),
			("^^ ( ( a b ) c )", [], ["a", "b", "c"], False),
		)

		test_cases_xfail = (
			("^^ ( || ( a b ) ^^ ( b c ) )", [], ["a", "b"]),
			("^^ ( || ( a b ) ^^ ( b c )", [], ["a", "b", "c"]),
			("^^( || ( a b ) ^^ ( b c ) )", [], ["a", "b", "c"]),
			("^^ || ( a b ) ^^ ( b c )", [], ["a", "b", "c"]),
			("^^ ( ( || ) ( a b ) ^^ ( b c ) )", [], ["a", "b", "c"]),
			("^^ ( || ( a b ) ) ^^ ( b c ) )", [], ["a", "b", "c"]),
		)

		test_cases_xfail_eapi = (
			("?? ( a b )", [], ["a", "b"], "4"),
		)

		for required_use, use, iuse, expected in test_cases:
			self.assertEqual(bool(check_required_use(required_use, use, iuse.__contains__)), \
				expected, required_use + ", USE = " + " ".join(use))

		for required_use, use, iuse in test_cases_xfail:
			self.assertRaisesMsg(required_use + ", USE = " + " ".join(use), \
				InvalidDependString, check_required_use, required_use, use, iuse.__contains__)

		for required_use, use, iuse, eapi in test_cases_xfail_eapi:
			self.assertRaisesMsg(required_use + ", USE = " + " ".join(use), \
				InvalidDependString, check_required_use, required_use, use,
				iuse.__contains__, eapi=eapi)

	def testCheckRequiredUseFilterSatisfied(self):
		"""
		Test filtering of satisfied parts of REQUIRED_USE,
		in order to reduce noise for bug #353234.
		"""
		test_cases = (
			(
				"bindist? ( !amr !faac !win32codecs ) cdio? ( !cdparanoia !cddb ) dvdnav? ( dvd )",
				("cdio", "cdparanoia"),
				"cdio? ( !cdparanoia )"
			),
			(
				"|| ( !amr !faac !win32codecs ) cdio? ( !cdparanoia !cddb ) ^^ ( foo bar )",
				["cdio", "cdparanoia", "foo"],
				"cdio? ( !cdparanoia )"
			),
			(
				"^^ ( || ( a b ) c )",
				("a", "b", "c"),
				"^^ ( || ( a b ) c )"
			),
			(
				"^^ ( || ( ( a b ) ) ( c ) )",
				("a", "b", "c"),
				"^^ ( ( a b ) c )"
			),
			(
				"a? ( ( c e ) ( b d ) )",
				("a", "c", "e"),
				"a? ( b d )"
			),
			(
				"a? ( ( c e ) ( b d ) )",
				("a", "b", "c", "e"),
				"a? ( d )"
			),
			(
				"a? ( ( c e ) ( c e b c d e c ) )",
				("a", "c", "e"),
				"a? ( b d )"
			),
			(
				"^^ ( || ( a b ) ^^ ( b c ) )",
				("a", "b"),
				"^^ ( || ( a b ) ^^ ( b c ) )"
			),
			(
				"^^ ( || ( a b ) ^^ ( b c ) )",
				["a", "c"],
				"^^ ( || ( a b ) ^^ ( b c ) )"
			),
			(
				"^^ ( || ( a b ) ^^ ( b c ) )",
				["b", "c"],
				""
			),
			(
				"^^ ( || ( a b ) ^^ ( b c ) )",
				["a", "b", "c"],
				""
			),
			(
				"^^ ( ( a b c ) ( b c d ) )",
				["a", "b", "c"],
				""
			),
			(
				"^^ ( ( a b c ) ( b c d ) )",
				["a", "b", "c", "d"],
				"^^ ( ( a b c ) ( b c d ) )"
			),
			(
				"^^ ( ( a b c ) ( b c !d ) )",
				["a", "b", "c"],
				"^^ ( ( a b c ) ( b c !d ) )"
			),
			(
				"^^ ( ( a b c ) ( b c !d ) )",
				["a", "b", "c", "d"],
				""
			),
			(
				"( ( ( a ) ) ( ( ( b c ) ) ) )",
				[""],
				"a b c"
			),
			(
				"|| ( ( ( ( a ) ) ( ( ( b c ) ) ) ) )",
				[""],
				"a b c"
			),
			(
				"|| ( ( a ( ( ) ( ) ) ( ( ) ) ( b ( ) c ) ) )",
				[""],
				"a b c"
			),
			(
				"|| ( ( a b c ) ) || ( ( d e f ) )",
				[""],
				"a b c d e f"
			),
		)
		for required_use, use, expected in test_cases:
			result = check_required_use(required_use, use, lambda k: True).tounicode()
			self.assertEqual(result, expected,
				"REQUIRED_USE = '%s', USE = '%s', '%s' != '%s'" % \
				(required_use, " ".join(use), result, expected))
