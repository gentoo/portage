# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage import flatten
from portage.dep import isvalidatom, match_from_list, \
     best_match_to_list, dep_getkey, use_reduce, paren_reduce
from portage.exception import InvalidAtom

OPERATIONS = ["merge", "unmerge"]

class PackageSet(object):
	# Set this to operations that are supported by your subclass. While 
	# technically there is no difference between "merge" and "unmerge" regarding
	# package sets, the latter doesn't make sense for some sets like "system"
	# or "security" and therefore isn't supported by them.
	_operations = ["merge"]
	description = "generic package set"
	
	def __init__(self):
		self._atoms = set()
		self._atommap = {}
		self._loaded = False
		self._loading = False
		self.errors = []
		self._nonatoms = set()

	def __contains__(self, atom):
		return atom in self.getAtoms()
	
	def __iter__(self):
		for x in self.getAtoms():
			yield x
	
	def supportsOperation(self, op):
		if not op in OPERATIONS:
			raise ValueError(op)
		return op in self._operations
	
	def getAtoms(self):
		if not (self._loaded or self._loading):
			self._loading = True
			self.load()
			self._loaded = True
			self._loading = False
		return self._atoms

	def getNonAtoms(self):
		self.getAtoms()
		return self._nonatoms

	def _setAtoms(self, atoms):
		atoms = map(str.strip, atoms)
		nonatoms = set()
		for a in atoms[:]:
			if a == "":
				atoms.remove(a)
			elif not isvalidatom(a):
				atoms.remove(a)
				self._nonatoms.add(a)
		self._atoms = set(atoms)
		self._updateAtomMap()

	def load(self):
		# This method must be overwritten by subclasses
		# Editable sets should use the value of self._mtime to determine if they
		# need to reload themselves
		raise NotImplementedError()

	def containsCPV(self, cpv):
		for a in self.getAtoms():
			if match_from_list(a, [cpv]):
				return True
		return False
	
	def getMetadata(self, key):
		if hasattr(self, key.lower()):
			return getattr(self, key.lower())
		else:
			return ""
	
	def _updateAtomMap(self, atoms=None):
		"""Update self._atommap for specific atoms or all atoms."""
		if not atoms:
			self._atommap.clear()
			atoms = self._atoms
		for a in atoms:
			cp = dep_getkey(a)
			self._atommap.setdefault(cp, set())
			self._atommap[cp].add(a)
	
	# Not sure if this one should really be in PackageSet
	def findAtomForPackage(self, cpv, metadata):
		"""Return the best match for a given package from the arguments, or
		None if there are no matches.  This matches virtual arguments against
		the PROVIDE metadata.  This can raise an InvalidDependString exception
		if an error occurs while parsing PROVIDE."""
		cpv_slot = "%s:%s" % (cpv, metadata["SLOT"])
		cp = dep_getkey(cpv)
		self.getAtoms() # make sure the atoms are loaded
		atoms = self._atommap.get(cp)
		if atoms:
			best_match = best_match_to_list(cpv_slot, atoms)
			if best_match:
				return best_match
		if not metadata["PROVIDE"]:
			return None
		provides = flatten(use_reduce(paren_reduce(metadata["PROVIDE"]),
								uselist=metadata["USE"].split()))
		for provide in provides:
			provided_cp = dep_getkey(provide)
			atoms = self._atommap.get(provided_cp)
			if atoms:
				atoms = list(atoms)
				transformed_atoms = [atom.replace(provided_cp, cp) for atom in atoms]
				best_match = best_match_to_list(cpv_slot, transformed_atoms)
				if best_match:
					return atoms[transformed_atoms.index(best_match)]
		return None

class EditablePackageSet(PackageSet):

	def update(self, atoms):
		self.getAtoms()
		self._atoms.update(atoms)
		self._updateAtomMap(atoms=atoms)
		self.write()
	
	def add(self, atom):
		self.update([atom])

	def replace(self, atoms):
		self._setAtoms(atoms)
		self.write()

	def remove(self, atom):
		self.getAtoms()
		self._atoms.discard(atom)
		self._updateAtomMap()
		self.write()

	def removePackageAtoms(self, cp):
		for a in list(self.getAtoms()):
			if dep_getkey(a) == cp:
				self.remove(a)
		self.write()

	def write(self):
		# This method must be overwritten in subclasses that should be editable
		raise NotImplementedError()

class InternalPackageSet(EditablePackageSet):
	def __init__(self, initial_atoms=None):
		super(InternalPackageSet, self).__init__()
		if initial_atoms != None:
			self.update(initial_atoms)

	def clear(self):
		self._atoms.clear()
		self._updateAtomMap()
	
	def load(self):
		pass

	def write(self):
		pass

