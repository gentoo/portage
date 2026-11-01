# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from unittest import mock

from portage._sets.base import WildcardPackageSet
from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.tests import TestCase
from portage.versions import _pkg_str


class WildcardPackageSetTestCase(TestCase):
    """Test case for WildcardPackageSet"""

    def testWildcardPackageSet(self):
        ambig_atoms = {"A", "B", "C"}
        norm_atoms = {"dev-libs/A", ">=dev-libs/A-1"}
        wild_atoms = {"dev-libs/*", "*/B"}
        sets = {"@world", "@installed", "@system"}

        w1 = WildcardPackageSet(initial_atoms=norm_atoms)
        w2 = WildcardPackageSet(initial_atoms=wild_atoms)
        self.assertRaises(InvalidAtom, WildcardPackageSet, initial_atoms=sets)

        self.assertEqual(w1.getAtoms(), norm_atoms)
        self.assertEqual(w2.getAtoms(), wild_atoms)

        w3 = WildcardPackageSet(initial_atoms=ambig_atoms)
        self.assertEqual(w3.getAtoms(), {"*/" + a for a in ambig_atoms})

        w4 = WildcardPackageSet(initial_atoms=(Atom(a) for a in norm_atoms))
        self.assertEqual(w4.getAtoms(), norm_atoms)

    def testFindAtomForPackage(self):
        pkg = _pkg_str("dev-libs/A-1", slot="0")

        def find(atoms):
            atom_set = WildcardPackageSet(initial_atoms=atoms)
            results = set()
            # The set's iteration order depends on string hashing, so check
            # both orders explicitly.
            for order in (atoms, atoms[::-1]):
                ordered = [Atom(a, allow_wildcard=True) for a in order]
                with mock.patch.object(
                    atom_set,
                    "iterAtomsForPackage",
                    return_value=ordered,
                ):
                    results.add(atom_set.findAtomForPackage(pkg))
            self.assertEqual(len(results), 1, f"{atoms} gave {results}")
            return results.pop()

        # An exact atom is more specific than a wildcard, with or without a slot.
        self.assertEqual(find(["dev-libs/*", "dev-libs/A"]), "dev-libs/A")
        self.assertEqual(find(["dev-libs/*:0", "dev-libs/A"]), "dev-libs/A")
        self.assertEqual(find(["dev-libs/*", ">=dev-libs/A-1"]), ">=dev-libs/A-1")

        # Among wildcards, one with a slot is more specific.
        self.assertEqual(find(["dev-libs/*", "dev-libs/*:0"]), "dev-libs/*:0")

        # A lone wildcard is returned as itself.
        self.assertEqual(
            WildcardPackageSet(initial_atoms=["dev-libs/*"]).findAtomForPackage(pkg),
            "dev-libs/*",
        )
        self.assertIsNone(
            WildcardPackageSet(initial_atoms=["sys-apps/*"]).findAtomForPackage(pkg)
        )
