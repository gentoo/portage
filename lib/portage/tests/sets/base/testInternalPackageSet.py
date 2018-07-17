# testConfigFileSet.py -- Portage Unit Testing Functionality
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.tests import TestCase
from portage._sets.base import InternalPackageSet

class InternalPackageSetTestCase(TestCase):
	"""Simple Test Case for InternalPackageSet"""

	def testInternalPackageSet(self):
		i1_atoms = set(("dev-libs/A", ">=dev-libs/A-1", "dev-libs/B"))
		i2_atoms = set(("dev-libs/A", "dev-libs/*", "dev-libs/C"))

		i1 = InternalPackageSet(initial_atoms=i1_atoms)
		i2 = InternalPackageSet(initial_atoms=i2_atoms, allow_wildcard=True)
		self.assertRaises(InvalidAtom, InternalPackageSet, initial_atoms=i2_atoms)

		self.assertEqual(i1.getAtoms(), i1_atoms)
		self.assertEqual(i2.getAtoms(), i2_atoms)

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
