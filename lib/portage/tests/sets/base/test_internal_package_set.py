# testConfigFileSet.py -- Portage Unit Testing Functionality
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from unittest import mock

import portage._sets.base
from portage._sets.base import InternalPackageSet
from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.tests import TestCase
from portage.versions import _pkg_str


class InternalPackageSetTestCase(TestCase):
    """Simple Test Case for InternalPackageSet"""

    def testInternalPackageSet(self):
        i1_atoms = {"dev-libs/A", ">=dev-libs/A-1", "dev-libs/B"}
        i2_atoms = {"dev-libs/A", "dev-libs/*", "dev-libs/C"}
        i3_sets = {"@world", "@installed", "@system"}

        i1 = InternalPackageSet(initial_atoms=i1_atoms)
        i2 = InternalPackageSet(initial_atoms=i2_atoms, allow_wildcard=True)
        i3 = InternalPackageSet(initial_atoms=i3_sets)
        self.assertRaises(InvalidAtom, InternalPackageSet, initial_atoms=i2_atoms)

        self.assertFalse(i1.isEmpty())
        self.assertFalse(i2.isEmpty())
        self.assertFalse(i3.isEmpty())

        self.assertEqual(i1.getAtoms(), i1_atoms)
        self.assertEqual(i2.getAtoms(), i2_atoms)
        self.assertEqual(i3.getNonAtoms(), i3_sets)

        new_atom = Atom("*/*", allow_wildcard=True)
        self.assertRaises(InvalidAtom, i1.add, new_atom)
        i2.add(new_atom)

        i2_atoms.add(new_atom)

        self.assertEqual(i1.getAtoms(), i1_atoms)
        self.assertEqual(i2.getAtoms(), i2_atoms)

        removed_atom = Atom("dev-libs/A")

        i1.remove(removed_atom)
        i2.remove(removed_atom)

        i1_atoms.remove(removed_atom)
        i2_atoms.remove(removed_atom)

        self.assertEqual(i1.getAtoms(), i1_atoms)
        self.assertEqual(i2.getAtoms(), i2_atoms)

        update_atoms = [Atom("dev-libs/C"), Atom("dev-*/C", allow_wildcard=True)]

        self.assertRaises(InvalidAtom, i1.update, update_atoms)
        i2.update(update_atoms)

        i2_atoms.update(update_atoms)

        self.assertEqual(i1.getAtoms(), i1_atoms)
        self.assertEqual(i2.getAtoms(), i2_atoms)

        replace_atoms = [Atom("dev-libs/D"), Atom("*-libs/C", allow_wildcard=True)]

        self.assertRaises(InvalidAtom, i1.replace, replace_atoms)
        i2.replace(replace_atoms)

        i2_atoms = set(replace_atoms)

        self.assertEqual(i2.getAtoms(), i2_atoms)

        i2.clear()
        self.assertEqual(i2.getAtoms(), set())
        self.assertEqual(i2.getNonAtoms(), set())
        self.assertTrue(i2.isEmpty())

    def testFindAtomForPackage(self):
        pkg = _pkg_str("dev-libs/A-1", slot="0")

        def find(atoms, allow_wildcard=False):
            atom_set = InternalPackageSet(
                initial_atoms=atoms, allow_wildcard=allow_wildcard
            )
            with mock.patch.object(
                portage._sets.base,
                "best_match_to_list",
                wraps=portage._sets.base.best_match_to_list,
            ) as best_match:
                result = atom_set.findAtomForPackage(pkg)
            return result, best_match.called

        # A single match is returned without a second matching pass.
        self.assertEqual(find({"dev-libs/A"}), (Atom("dev-libs/A"), False))
        self.assertEqual(find({">=dev-libs/A-1"}), (Atom(">=dev-libs/A-1"), False))

        # With several matches, the most specific atom wins.
        self.assertEqual(
            find({"dev-libs/A", ">=dev-libs/A-1", "=dev-libs/A-1"}),
            (Atom("=dev-libs/A-1"), True),
        )
        self.assertEqual(
            find({">=dev-libs/A-1", "dev-libs/A:0"}), (Atom("dev-libs/A:0"), True)
        )

        # A wildcard atom has a different cp, so it takes the slow path.
        wildcard = Atom("dev-libs/*", allow_wildcard=True)
        self.assertEqual(find({"dev-libs/*"}, allow_wildcard=True), (wildcard, True))
        self.assertEqual(
            find({"dev-libs/*", ">=dev-libs/A-1"}, allow_wildcard=True),
            (Atom(">=dev-libs/A-1"), True),
        )

        # No match.
        self.assertEqual(find({">=dev-libs/A-2"}), (None, True))
        self.assertEqual(find({"dev-libs/B"}), (None, True))
