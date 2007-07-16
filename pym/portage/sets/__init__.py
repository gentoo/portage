# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
from portage.exception import InvalidAtom
from portage.dep import isvalidatom, match_from_list, dep_getkey

OPERATIONS = ["merge", "unmerge"]
DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]

class PackageSet(object):
	# Set this to operations that are supported by your subclass. While 
	# technically there is no difference between "merge" and "unmerge" regarding
	# package sets, the latter doesn't make sense for some sets like "system"
	# or "security" and therefore isn't supported by them.
	_operations = ["merge"]
	description = "generic package set"
	
	def __init__(self, name):
		self._name = name
		self._atoms = set()
		self._loaded = False
	
	def supportsOperation(self, op):
		if not op in OPERATIONS:
			raise ValueError(op)
		return op in self._operations
	
	def getAtoms(self):
		if not self._loaded:
			self.load()
			self._loaded = True
		return self._atoms

	def _setAtoms(self, atoms):
		atoms = map(str.strip, atoms)
		for a in atoms[:]:
			if a == "":
				atoms.remove(a)
			elif not isvalidatom(a):
				raise InvalidAtom(a)
		self._atoms = atoms
	
	def getName(self):
		return self._name
	
	def load(self):
		# This method must be overwritten by subclasses
		# Editable sets should use the value of self._mtime to determine if they
		# need to reload themselves
		raise NotImplementedError()

	def containsCPV(self, cpv):
		for a in self.getAtoms():
			if match_from_list(a, cpv):
				return True
		return False
	
	def getMetadata(self, key):
		if hasattr(self, key.lower()):
			return getattr(self, key.lower())
		else:
			return ""
	

class EditablePackageSet(PackageSet):
	def getAtoms(self):
		self.load()
		return self._atoms

	def updateAtoms(self, atoms):
		self.load()
		self._atoms.update(atoms)
		self.write()
	
	def addAtom(self, atom):
		self.updateAtoms([atom])

	def removeAtom(self, atom):
		self.load()
		self._atoms.discard(atom)
		self.write()

	def removePackageAtoms(self, cp):
		self.load()
		for a in self.getAtoms():
			if dep_getkey(a) == cp:
				self._atoms.discard(a)
		self.write()

	def write(self):
		# This method must be overwritten in subclasses that should be editable
		raise NotImplementedError()


class InternalPackageSet(EditablePackageSet):
	_operations = ["merge", "unmerge"]
	
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
			l = [s for s in l if s.getName() in sys.argv[1:]]
	for x in l:
		print x.getName()+":"
		print "DESCRIPTION = %s" % x.getMetadata("Description")
		for n in sorted(x.getAtoms()):
			print "- "+n
		print
