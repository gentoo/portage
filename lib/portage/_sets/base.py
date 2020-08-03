# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.dep import Atom, ExtendedAtomDict, best_match_to_list, match_from_list
from portage.exception import InvalidAtom
from portage.versions import cpv_getkey


OPERATIONS = ["merge", "unmerge"]

class PackageSet:
	# Set this to operations that are supported by your subclass. While
	# technically there is no difference between "merge" and "unmerge" regarding
	# package sets, the latter doesn't make sense for some sets like "system"
	# or "security" and therefore isn't supported by them.
	_operations = ["merge"]
	description = "generic package set"

	def __init__(self, allow_wildcard=False, allow_repo=False):
		self._atoms = set()
		self._atommap = ExtendedAtomDict(set)
		self._loaded = False
		self._loading = False
		self.errors = []
		self._nonatoms = set()
		self.world_candidate = False
		self._allow_wildcard = allow_wildcard
		self._allow_repo = allow_repo

	def __contains__(self, atom):
		self._load()
		return atom in self._atoms or atom in self._nonatoms

	def __iter__(self):
		self._load()
		for x in self._atoms:
			yield x
		for x in self._nonatoms:
			yield x

	def __bool__(self):
		self._load()
		return bool(self._atoms or self._nonatoms)

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
		self._atoms.clear()
		self._nonatoms.clear()
		for a in atoms:
			if not isinstance(a, Atom):
				if isinstance(a, str):
					a = a.strip()
				if not a:
					continue
				try:
					a = Atom(a, allow_wildcard=True, allow_repo=True)
				except InvalidAtom:
					self._nonatoms.add(a)
					continue
			if not self._allow_wildcard and a.extended_syntax:
				raise InvalidAtom("extended atom syntax not allowed here")
			if not self._allow_repo and a.repo:
				raise InvalidAtom("repository specification not allowed here")
			self._atoms.add(a)

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
		return ""

	def _updateAtomMap(self, atoms=None):
		"""Update self._atommap for specific atoms or all atoms."""
		if not atoms:
			self._atommap.clear()
			atoms = self._atoms
		for a in atoms:
			self._atommap.setdefault(a.cp, set()).add(a)

	# Not sure if this one should really be in PackageSet
	def findAtomForPackage(self, pkg, modified_use=None):
		"""Return the best match for a given package from the arguments, or
		None if there are no matches.  This matches virtual arguments against
		the PROVIDE metadata.  This can raise an InvalidDependString exception
		if an error occurs while parsing PROVIDE."""

		if modified_use is not None and modified_use is not pkg.use.enabled:
			pkg = pkg.copy()
			pkg._metadata["USE"] = " ".join(modified_use)

		# Atoms matched via PROVIDE must be temporarily transformed since
		# match_from_list() only works correctly when atom.cp == pkg.cp.
		rev_transform = {}
		for atom in self.iterAtomsForPackage(pkg):
			if atom.cp == pkg.cp:
				rev_transform[atom] = atom
			else:
				rev_transform[Atom(atom.replace(atom.cp, pkg.cp, 1), allow_wildcard=True, allow_repo=True)] = atom
		best_match = best_match_to_list(pkg, iter(rev_transform))
		if best_match:
			return rev_transform[best_match]
		return None

	def iterAtomsForPackage(self, pkg):
		"""
		Find all matching atoms for a given package. This matches virtual
		arguments against the PROVIDE metadata.  This will raise an
		InvalidDependString exception if PROVIDE is invalid.
		"""
		cpv_slot_list = [pkg]
		cp = cpv_getkey(pkg.cpv)
		self._load() # make sure the atoms are loaded

		atoms = self._atommap.get(cp)
		if atoms:
			for atom in atoms:
				if match_from_list(atom, cpv_slot_list):
					yield atom

class EditablePackageSet(PackageSet):

	def __init__(self, allow_wildcard=False, allow_repo=False):
		super(EditablePackageSet, self).__init__(allow_wildcard=allow_wildcard, allow_repo=allow_repo)

	def update(self, atoms):
		self._load()
		modified = False
		normal_atoms = []
		for a in atoms:
			if not isinstance(a, Atom):
				try:
					a = Atom(a, allow_wildcard=True, allow_repo=True)
				except InvalidAtom:
					modified = True
					self._nonatoms.add(a)
					continue
			if not self._allow_wildcard and a.extended_syntax:
				raise InvalidAtom("extended atom syntax not allowed here")
			if not self._allow_repo and a.repo:
				raise InvalidAtom("repository specification not allowed here")
			normal_atoms.append(a)

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
		self._nonatoms.discard(atom)
		self._updateAtomMap()
		self.write()

	def removePackageAtoms(self, cp):
		self._load()
		for a in list(self._atoms):
			if a.cp == cp:
				self.remove(a)
		self.write()

	def write(self):
		# This method must be overwritten in subclasses that should be editable
		raise NotImplementedError()

class InternalPackageSet(EditablePackageSet):
	def __init__(self, initial_atoms=None, allow_wildcard=False, allow_repo=True):
		"""
		Repo atoms are allowed more often than not, so it makes sense for this
		class to allow them by default. The Atom constructor and isvalidatom()
		functions default to allow_repo=False, which is sufficient to ensure
		that repo atoms are prohibited when necessary.
		"""
		super(InternalPackageSet, self).__init__(allow_wildcard=allow_wildcard, allow_repo=allow_repo)
		if initial_atoms != None:
			self.update(initial_atoms)

	def clear(self):
		self._atoms.clear()
		self._updateAtomMap()

	def load(self):
		pass

	def write(self):
		pass

class DummyPackageSet(PackageSet):
	def __init__(self, atoms=None):
		super(DummyPackageSet, self).__init__()
		if atoms:
			self._setAtoms(atoms)

	def load(self):
		pass

	def singleBuilder(cls, options, settings, trees):
		atoms = options.get("packages", "").split()
		return DummyPackageSet(atoms=atoms)
	singleBuilder = classmethod(singleBuilder)
