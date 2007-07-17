# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
from portage.exception import InvalidAtom
from portage.dep import isvalidatom, match_from_list, best_match_to_list, dep_getkey, use_reduce, paren_reduce
from portage import flatten

OPERATIONS = ["merge", "unmerge"]
DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]

class PackageSet(object):
	# Set this to operations that are supported by your subclass. While 
	# technically there is no difference between "merge" and "unmerge" regarding
	# package sets, the latter doesn't make sense for some sets like "system"
	# or "security" and therefore isn't supported by them.
	_operations = ["merge"]
	_atommap = {}
	description = "generic package set"
	
	def __init__(self, name):
		self.name = name
		self._atoms = set()
		self._atommap = {}
		self._loaded = False
		self._loading = False

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

	def _setAtoms(self, atoms):
		atoms = map(str.strip, atoms)
		for a in atoms[:]:
			if a == "":
				atoms.remove(a)
			elif not isvalidatom(a):
				raise InvalidAtom(a)
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
	
	def _updateAtomMap(self):
		for a in self._atoms:
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
	def getAtoms(self):
		self.load()
		return self._atoms

	def update(self, atoms):
		self.load()
		self._atoms.update(atoms)
		self._updateAtomMap()
		self.write()
	
	def add(self, atom):
		self.update([atom])

	def replace(self, atoms):
		self._setAtoms(atoms)
		self.write()

	def remove(self, atom):
		self.load()
		self._atoms.discard(atom)
		self._updateAtomMap()
		self.write()

	def removePackageAtoms(self, cp):
		self.load()
		for a in self.getAtoms():
			if dep_getkey(a) == cp:
				self.remove(a)
		self.write()

	def write(self):
		# This method must be overwritten in subclasses that should be editable
		raise NotImplementedError()


class InternalPackageSet(EditablePackageSet):
	def __init__(self, initial_atoms=None):
		super(InternalPackageSet, self).__init__("")
		if initial_atoms != None:
			self.update(initial_atoms)

	def clear(self):
		self._atoms.clear()
		self._updateAtomMap()
	
	def load(self):
		pass

	def write(self):
		pass

def make_default_sets(configroot, root, profile_paths, settings=None, 
		vdbapi=None, portdbapi=None):
	from portage.sets.files import StaticFileSet, ConfigFileSet
	from portage.sets.profiles import PackagesSystemSet
	from portage.sets.security import NewAffectedSet
	from portage.sets.dbapi import EverythingSet
	
	rValue = set()
	worldset = StaticFileSet("world", os.path.join(root, PRIVATE_PATH, "world"))
	worldset.description = "Set of packages that were directly installed"
	rValue.add(worldset)
	for suffix in ["mask", "unmask", "keywords", "use"]:
		myname = "package_"+suffix
		myset = ConfigFileSet(myname, os.path.join(configroot, USER_CONFIG_PATH.lstrip(os.sep), "package."+suffix))
		rValue.add(myset)
	rValue.add(PackagesSystemSet("system", profile_paths))
	if settings != None and portdbapi != None:
		rValue.add(NewAffectedSet("security", settings, vdbapi, portdbapi))
	else:
		rValue.add(InternalPackageSet("security"))
	if vdbapi != None:
		rValue.add(EverythingSet("everything", vdbapi))
	else:
		rValue.add(InternalPackageSet("everything"))

	return rValue

def make_extra_static_sets(configroot):
	from portage.sets.files import StaticFileSet
	
	rValue = set()
	mydir = os.path.join(configroot, USER_CONFIG_PATH.lstrip(os.sep), "sets")
	try:
		mysets = os.listdir(mydir)
	except (OSError, IOError):
		return rValue
	for myname in mysets:
		if myname in DEFAULT_SETS:
			continue
		rValue.add(StaticFileSet(fname, os.path.join(mydir, myname)))
	return rValue

def make_category_sets(portdbapi, settings, only_visible=True):
	from portage.sets.dbapi import CategorySet
	rValue = set()
	for c in settings.categories:
		rValue.add(CategorySet("category_%s" % c, c, portdbapi, only_visible=only_visible))
	return rValue

# adhoc test code
if __name__ == "__main__":
	import portage, sys, os
	from portage.sets.dbapi import CategorySet
	from portage.sets.files import StaticFileSet
	l = make_default_sets("/", "/", portage.settings.profiles, portage.settings, portage.db["/"]["vartree"].dbapi, portage.db["/"]["porttree"].dbapi)
	l.update(make_extra_static_sets("/"))
	if len(sys.argv) > 1:
		for s in sys.argv[1:]:
			if s.startswith("category_"):
				c = s[9:]
				l.add(CategorySet("category_%s" % c, c, portdbapi, only_visible=only_visible))
			elif os.path.exists(s):
				l.add(StaticFileSet(os.path.basename(s), s))
			elif s != "*":
				print "ERROR: could not create set '%s'" % s
		if not "*" in sys.argv:
			l = [s for s in l if s.name in sys.argv[1:]]
	for x in l:
		print x.name+":"
		print "DESCRIPTION = %s" % x.getMetadata("Description")
		for n in sorted(x.getAtoms()):
			print "- "+n
		print
