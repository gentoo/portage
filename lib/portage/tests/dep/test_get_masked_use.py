# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dep import get_masked_use
from portage.exception import InvalidDependString
from portage.tests import TestCase


class TestGetMaskedUse(TestCase):
    def testGetMaskedUse(self):
        test_cases = (
            # (MASKED_USE, enabled flags, masked flags)
            ("", ["a"], []),
            ("a", ["a"], ["a"]),
            ("a", [], ["a"]),
            ("!a? ( b c )", ["b"], ["b", "c"]),
            ("!a? ( b c )", ["a", "b"], []),
            ("a? ( b )", ["a", "b"], ["b"]),
            ("a? ( b )", ["b"], []),
            ("!a? ( b ) !c? ( d )", ["c", "d"], ["b"]),
            ("!a? ( b ) !a? ( c )", [], ["b", "c"]),
            ("( a b )", [], ["a", "b"]),
            # Nested conditionals
            ("!a? ( b !c? ( d ) )", [], ["b", "d"]),
            ("!a? ( b !c? ( d ) )", ["c"], ["b"]),
            ("!a? ( b !c? ( d ) )", ["a"], []),
            # A masked flag is disabled, which satisfies further conditionals
            # regardless of the order of the groups.
            ("!a? ( b ) !b? ( c )", ["b", "c"], ["b", "c"]),
            ("!b? ( c ) !a? ( b )", ["b", "c"], ["b", "c"]),
            ("!c? ( d ) !b? ( c ) !a? ( b )", ["b", "c", "d"], ["b", "c", "d"]),
            ("!c? ( d ) !b? ( c ) !a? ( b )", ["a", "b", "c", "d"], []),
            # A masked flag stays masked, even when masking another flag
            # removes the reason that it was masked.
            ("a? ( b ) !b? ( a )", ["a", "b"], ["a", "b"]),
            ("a? ( a )", ["a"], ["a"]),
        )

        test_cases_xfail = (
            "|| ( a b )",
            "^^ ( a b )",
            "?? ( a b )",
            "!a? ( || ( b c ) )",
            "!a",
            "-a",
            "!a? ( !b )",
            "!a? ( cat/pkg )",
            "!a? b",
            "!a? ( b",
            "!a? ( b ) )",
            "!a?( b )",
        )

        for masked_use, use, expected in test_cases:
            self.assertEqual(
                get_masked_use(masked_use, use),
                frozenset(expected),
                f"MASKED_USE: '{masked_use}', USE: '{' '.join(use)}'",
            )

        for masked_use in test_cases_xfail:
            for kwargs in ({}, {"matchall": True}):
                self.assertRaisesMsg(
                    f"MASKED_USE: '{masked_use}'",
                    InvalidDependString,
                    get_masked_use,
                    masked_use,
                    [],
                    **kwargs,
                )

    def testGetMaskedUseMatchall(self):
        self.assertEqual(
            get_masked_use("!a? ( b !c? ( d ) ) e? ( f )", ["a"], matchall=True),
            frozenset(["b", "d", "f"]),
        )

    def testGetMaskedUseValidFlag(self):
        iuse = frozenset(["a", "b"])

        def is_valid_flag(flag):
            return flag in iuse

        self.assertEqual(
            get_masked_use("!a? ( b )", [], is_valid_flag=is_valid_flag),
            frozenset(["b"]),
        )

        for masked_use in ("!a? ( c )", "!c? ( b )", "c"):
            self.assertRaisesMsg(
                f"MASKED_USE: '{masked_use}'",
                InvalidDependString,
                get_masked_use,
                masked_use,
                [],
                is_valid_flag=is_valid_flag,
                matchall=True,
            )
