# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import get_required_use_flags
from portage.exception import InvalidDependString

class TestCheckRequiredUse(TestCase):

	def testCheckRequiredUse(self):
		test_cases = (
			("a b c", ["a", "b", "c"]),

			("|| ( a b c )", ["a", "b", "c"]),
			("^^ ( a b c )", ["a", "b", "c"]),
			("?? ( a b c )", ["a", "b", "c"]),
			("?? ( )", []),

			("|| ( a b ^^ ( d e f ) )", ["a", "b", "d", "e", "f"]),
			("^^ ( a b || ( d e f ) )", ["a", "b", "d", "e", "f"]),

			("( ^^ ( a ( b ) ( || ( ( d e ) ( f ) ) ) ) )", ["a", "b", "d", "e", "f"]),

			("a? ( ^^ ( b c ) )", ["a", "b", "c"]),
			("a? ( ^^ ( !b !d? ( c ) ) )", ["a", "b", "c", "d"]),
		)

		test_cases_xfail = (
			("^^ ( || ( a b ) ^^ ( b c )"),
			("^^( || ( a b ) ^^ ( b c ) )"),
			("^^ || ( a b ) ^^ ( b c )"),
			("^^ ( ( || ) ( a b ) ^^ ( b c ) )"),
			("^^ ( || ( a b ) ) ^^ ( b c ) )"),
		)

		for required_use, expected in test_cases:
			result = get_required_use_flags(required_use)
			expected = set(expected)
			self.assertEqual(result, expected, \
				"REQUIRED_USE: '%s', expected: '%s', got: '%s'" % (required_use, expected, result))

		for required_use in test_cases_xfail:
			self.assertRaisesMsg("REQUIRED_USE: '%s'" % (required_use,), \
				InvalidDependString, get_required_use_flags, required_use)
