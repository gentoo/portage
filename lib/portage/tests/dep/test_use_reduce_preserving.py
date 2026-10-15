# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from itertools import chain, combinations

from portage.dep import Atom, paren_enclose, use_reduce, use_reduce_preserving
from portage.exception import InvalidDependString
from portage.tests import TestCase


def _normalize(deps):
    """
    Canonical form of a use_reduce() result, ignoring order and
    single-member any-of groups.
    """
    result = []
    it = iter(deps)
    for x in it:
        if x == "||":
            group = next(it)
            if len(group) == 1:
                result.extend(_normalize(group))
            else:
                result.append(("||", _normalize(group)))
        elif isinstance(x, list):
            result.append(_normalize(x))
        else:
            result.append(str(x))
    return tuple(sorted(result, key=repr))


def _powerset(flags):
    flags = sorted(flags)
    return chain.from_iterable(combinations(flags, n) for n in range(len(flags) + 1))


class UseReducePreservingTestCase(TestCase):
    def testExpected(self):
        cases = (
            # No preserved flags behaves exactly like use_reduce().
            ("a? ( x/a ) b? ( x/b )", ["a"], [], "x/a"),
            ("a? ( x/a ) b? ( x/b )", ["a"], ["b"], "x/a b? ( x/b )"),
            ("a? ( x/a ) b? ( x/b )", [], ["b"], "b? ( x/b )"),
            ("!b? ( x/a ) b? ( x/b )", [], ["b"], "!b? ( x/a ) b? ( x/b )"),
            # Preserved conditionals nested in evaluated ones.
            ("a? ( b? ( x/b ) x/a )", ["a"], ["b"], "b? ( x/b ) x/a"),
            ("a? ( b? ( x/b ) x/a )", [], ["b"], ""),
            # Evaluated conditionals nested in preserved ones.
            ("b? ( a? ( x/a ) x/b )", [], ["b"], "b? ( x/b )"),
            ("b? ( a? ( x/a ) x/b )", ["a"], ["b"], "b? ( x/a x/b )"),
            # Empty groups are dropped.
            ("b? ( a? ( x/a ) )", [], ["b"], ""),
            ("|| ( a? ( x/a ) )", [], ["b"], ""),
            # Any-of groups.
            ("|| ( b? ( x/b ) x/c )", [], ["b"], "|| ( b? ( x/b ) x/c )"),
            ("|| ( a? ( x/a x/d ) x/c )", ["a"], ["b"], "|| ( ( x/a x/d ) x/c )"),
            ("|| ( a? ( x/a ) x/c )", ["a"], ["b"], "|| ( x/a x/c )"),
            # Atom USE dependencies conditional on preserved flags.
            ("x/a[a?]", ["a"], ["b"], "x/a[a]"),
            ("x/a[b?]", [], ["b"], "b? ( x/a[b] ) !b? ( x/a )"),
            ("x/a[b=]", [], ["b"], "b? ( x/a[b] ) !b? ( x/a[-b] )"),
            ("x/a[a?,b?]", ["a"], ["b"], "b? ( x/a[a,b] ) !b? ( x/a[a] )"),
            ("x/a[!b?]", [], ["b"], "b? ( x/a ) !b? ( x/a[-b] )"),
        )
        for depstr, use, preserve, expected in cases:
            with self.subTest(depstr=depstr, use=use, preserve=preserve):
                result = use_reduce_preserving(
                    depstr,
                    uselist=use,
                    preserve=preserve,
                    eapi="8",
                    token_class=Atom,
                )
                self.assertEqual(paren_enclose(result), expected)

    def testEquivalence(self):
        """
        Reducing the preserved result once the preserved flags are known
        must give the same answer as reducing the original string.
        """
        depstrs = (
            "a? ( x/a ) b? ( x/b ) c? ( x/c )",
            "|| ( b? ( x/b ) c? ( x/c ) x/d ) a? ( !b? ( x/e ) )",
            "b? ( a? ( x/a[b?,c=] ) || ( c? ( x/c ) x/d ) )",
            "!a? ( !b? ( x/a[!c?] ) ) x/f[a?,b?]",
            "c? ( || ( ( x/a x/b ) b? ( x/c x/d ) ) )",
        )
        all_flags = ("a", "b", "c")
        for depstr in depstrs:
            for preserve in _powerset(all_flags):
                for use in _powerset(all_flags):
                    reduced = paren_enclose(
                        use_reduce_preserving(
                            depstr,
                            uselist=use,
                            preserve=preserve,
                            eapi="8",
                            token_class=Atom,
                        )
                    )
                    for final in _powerset(preserve):
                        final_use = set(use).difference(preserve).union(final)
                        with self.subTest(
                            depstr=depstr, use=use, preserve=preserve, final=final
                        ):
                            self.assertEqual(
                                _normalize(
                                    use_reduce(
                                        reduced,
                                        uselist=final_use,
                                        eapi="8",
                                        token_class=Atom,
                                    )
                                ),
                                _normalize(
                                    use_reduce(
                                        depstr,
                                        uselist=final_use,
                                        eapi="8",
                                        token_class=Atom,
                                    )
                                ),
                            )

    def testStringTokens(self):
        self.assertEqual(
            paren_enclose(
                use_reduce_preserving(
                    "a? ( foo ) b? ( bar ) baz", uselist=["a"], preserve=["b"]
                )
            ),
            "foo b? ( bar ) baz",
        )

    def testInvalid(self):
        for depstr in ("b? ( x/a", "b? x/a", "|| x/a", "b? ( x/a ) )"):
            with self.subTest(depstr=depstr):
                self.assertRaises(
                    InvalidDependString,
                    use_reduce_preserving,
                    depstr,
                    preserve=["b"],
                    eapi="8",
                    token_class=Atom,
                )
