# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage import cpv_getkey, flatten
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
		self.world_candidate = True

	def __contains__(self, atom):
		self._load()
		return atom in self._atoms or atom in self._nonatoms
	
	def __iter__(self):
		self._load()
		for x in self._atoms:
			yield x
		for x in self._nonatoms:
			yield x

	def supportsOperation(self, op):
		if not op in OPERATIONS:
			raise ValueError(op)
		return op in self._operations

	def _load(self):
		if not (self._loaded or self._loading):
			self._loading = True
			self.load()
			self._loaded = True
			self._loading = False

	def getAtoms(self):
		self._load()
		return self._atoms.copy()

	def getNonAtoms(self):
		self._load()
		return self._nonatoms.copy()

	def _setAtoms(self, atoms):
		atoms = map(str.strip, atoms)
		self._nonatoms.clear()
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
		self._load()
		for a in self._atoms:
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
		self._load() # make sure the atoms are loaded
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

	def iterAtomsForPackage(self, pkg):
		"""
		Find all matching atoms for a given package. This matches virtual
		arguments against the PROVIDE metadata.  This will raise an
		InvalidDependString exception if PROVIDE is invalid.
		"""
		cpv_slot_list = ["%s:%s" % (pkg.cpv, pkg.metadata["SLOT"])]
		cp = cpv_getkey(pkg.cpv)
		self._load() # make sure the atoms are loaded
		atoms = self._atommap.get(cp)
		if atoms:
			for atom in atoms:
				if match_from_list(atom, cpv_slot_list):
					yield atom
		if not pkg.metadata["PROVIDE"]:
			return
		provides = flatten(use_reduce(paren_reduce(pkg.metadata["PROVIDE"]),
			uselist=pkg.metadata["USE"].split()))
		for provide in provides:
			provided_cp = dep_getkey(provide)
			atoms = self._atommap.get(provided_cp)
			if atoms:
				for atom in atoms:
					if match_from_list(atom.replace(provided_cp, cp),
						cpv_slot_list):
						yield atom

class EditablePackageSet(PackageSet):

	def update(self, atoms):
		self._load()
		modified = False
		normal_atoms = []
		for a in atoms:
			if isvalidatom(a):
				normal_atoms.append(a)
			else:
				modified = True
				self._nonatoms.add(a)
		if normal_atoms:
			modified = True
			self._atoms.update(normal_atoms)
			self._updateAtomMap(atoms=normal_atoms)
		if modified:
			self.write()
	
	def add(self, atom):
		self.update([atom])

	def replace(self, atoms):
		self._setAtoms(atoms)
		self.write()

	def remove(self, atom):
		self._load()
		self._atoms.discard(atom)
		self._updateAtomMap()
		self.write()

	def removePackageAtoms(self, cp):
		self._load()
		for a in list(self._atoms):
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

