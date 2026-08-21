# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.is_valid_package_atom import is_valid_package_atom

from portage.dep import Atom
from portage.tests import TestCase


class IsValidPackageAtomTestCase(TestCase):
    def testStringAtoms(self):
        for atom, expected in (
            ("dev-libs/A", True),
            (">=dev-libs/A-1", True),
            ("A", True),
            ("!dev-libs/A", False),
            ("dev-libs/A[", False),
        ):
            self.assertEqual(is_valid_package_atom(atom), expected, atom)

    def testAtomInstances(self):
        for atom, expected in (
            (Atom("dev-libs/A"), True),
            (Atom(">=dev-libs/A-1"), True),
            (Atom("dev-libs/A:0/1"), True),
            (Atom("dev-libs/A::gentoo", allow_repo=True), True),
            (Atom("dev-libs/*", allow_wildcard=True), True),
            (Atom("!dev-libs/A"), False),
        ):
            self.assertEqual(
                is_valid_package_atom(atom, allow_repo=True), expected, atom
            )

    def testMissingEqConcatenation(self):
        # A blocker Atom is rejected above, so action_uninstall() retries it
        # as "=" + str(x), which must not raise.
        atom = Atom("!dev-libs/A")
        self.assertFalse(is_valid_package_atom("=" + str(atom)))
