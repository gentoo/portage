# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from ConfigParser import SafeConfigParser, NoOptionError
from portage import flatten, load_mod
from portage.dep import isvalidatom, match_from_list, \
     best_match_to_list, dep_getkey, use_reduce, paren_reduce
from portage.exception import InvalidAtom

OPERATIONS = ["merge", "unmerge"]
DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]
del x

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


class SetConfigError(Exception):
	pass

class SetConfig(SafeConfigParser):
	def __init__(self, paths, settings, trees):
		SafeConfigParser.__init__(self)
		self.read(paths)
		self.errors = []
		self.psets = {}
		self.trees = trees
		self.settings = settings
		self._parsed = False
	def _parse(self):
		if self._parsed:
			return
		for sname in self.sections():
			# find classname for current section, default to file based sets
			if not self.has_option(sname, "class"):
				classname = "portage.sets.files.StaticFileSet"
			else:
				classname = self.get(sname, "class")
			
			# try to import the specified class
			try:
				setclass = load_mod(classname)
			except (ImportError, AttributeError):
				self.errors.append("Could not import '%s' for section '%s'" % (classname, sname))
				continue
			# prepare option dict for the current section
			optdict = {}
			for oname in self.options(sname):
				optdict[oname] = self.get(sname, oname)
			
			# create single or multiple instances of the given class depending on configuration
			if self.has_option(sname, "multiset") and self.getboolean(sname, "multiset"):
				if hasattr(setclass, "multiBuilder"):
					try:
						self.psets.update(setclass.multiBuilder(optdict, self.settings, self.trees))
					except SetConfigError, e:
						self.errors.append("Configuration error in section '%s': %s" % (sname, str(e)))
						continue
				else:
					self.errors.append("Section '%s' is configured as multiset, but '%s' doesn't support that configuration" % (sname, classname))
					continue
			else:
				try:
					setname = self.get(sname, "name")
				except NoOptionError:
					setname = "sets/"+sname
				if hasattr(setclass, "singleBuilder"):
					try:
						self.psets[setname] = setclass.singleBuilder(optdict, self.settings, self.trees)
					except SetConfigError, e:
						self.errors.append("Configuration error in section '%s': %s" % (sname, str(e)))
						continue
				else:
					self.errors.append("'%s' does not support individual set creation, section '%s' must be configured as multiset" % (classname, sname))
					continue
		self._parsed = True
	
	def getSets(self):
		self._parse()
		return (self.psets, self.errors)

	def getSetsWithAliases(self):
		self._parse()
		shortnames = {}
		for name in self.psets:
			mysplit = name.split("/")
			if len(mysplit) > 1 and mysplit[-1] != "":
				if mysplit[-1] in shortnames:
					del shortnames[mysplit[-1]]
				else:
					shortnames[mysplit[-1]] = self.psets[name]
		shortnames.update(self.psets)
		return (shortnames, self.errors)

def make_default_config(settings, trees):
	sc = SetConfig([], settings, trees)
	sc.add_section("security")
	sc.set("security", "class", "portage.sets.security.NewAffectedSet")
	
	sc.add_section("system")
	sc.set("system", "class", "portage.sets.profiles.PackagesSystemSet")
	
	sc.add_section("world")
	sc.set("world", "class", "portage.sets.files.WorldSet")
	
	sc.add_section("everything")
	sc.set("everything", "class", "portage.sets.dbapi.EverythingSet")

	sc.add_section("config")
	sc.set("config", "class", "portage.sets.files.ConfigFileSet")
	sc.set("config", "multiset", "true")
	
	sc.add_section("categories_installed")
	sc.set("categories_installed", "class", "portage.sets.dbapi.CategorySet")
	sc.set("categories_installed", "multiset", "true")
	sc.set("categories_installed", "repository", "vartree")
	sc.set("categories_installed", "name_pattern", "installed/$category")
	
	return sc

# adhoc test code
if __name__ == "__main__":
	import portage
	sc = make_default_config(portage.settings, portage.db["/"])
	l, e = sc.getSets()
	print l, e
	for x in l:
		print x+":"
		print "DESCRIPTION = %s" % l[x].getMetadata("Description")
		for n in sorted(l[x].getAtoms()):
			print "- "+n
		print
