# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
from portage.exception import InvalidAtom
from portage.dep import isvalidatom

OPERATIONS = ["merge", "unmerge", "edit"]
DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]

class PackageSet(object):
	_operations = ["merge"]

	def __init__(self, name):
		self._name = name
		self._nodes = []
		self._loaded = False
	
	def supportsOperation(self, op):
		if not op in OPERATIONS:
			raise ValueError(op)
		return op in self._operations
	
	def getNodes(self):
		if not self._loaded:
			self.load()
			self._loaded = True
		return self._nodes

	def _setNodes(self, nodes):
		nodes = map(str.strip, nodes)
		for n in nodes[:]:
			if n == "":
				nodes.remove(n)
			elif not isvalidatom(n):
				raise InvalidAtom(n)
		self._nodes = nodes
	
	def getName(self):
		return self._name
	
	def addNode(self, node):
		if self.supportsOperation("edit"):
			self.load()
			self._nodes.append(node)
			self.write()
		else:
			raise NotImplementedError()

	def removeNode(self, node):
		if self.supportsOperation("edit"):
			self.load()
			self._nodes.remove(node)
			self.write()
		else:
			raise NotImplementedError()

	def write(self):
		raise NotImplementedError()

	def load(self):
		raise NotImplementedError()

class EmptyPackageSet(PackageSet):
	_operations = ["merge", "unmerge"]

def make_default_sets(configroot, root, profile_paths, settings=None, 
		vdbapi=None, portdbapi=None):
	from portage.sets.files import StaticFileSet, ConfigFileSet
	from portage.sets.profiles import PackagesSystemSet
	from portage.sets.security import AffectedSet
	from portage.sets.dbapi import EverythingSet
	
	rValue = set()
	rValue.add(StaticFileSet("world", os.path.join(root, PRIVATE_PATH, "world")))
	for suffix in ["mask", "unmask", "keywords", "use"]:
		myname = "package_"+suffix
		myset = ConfigFileSet(myname, os.path.join(configroot, USER_CONFIG_PATH.lstrip(os.sep), "package."+suffix))
		rValue.add(myset)
	rValue.add(PackagesSystemSet("system", profile_paths))
	if settings != None and portdbapi != None:
		rValue.add(AffectedSet("security", settings, vdbapi, portdbapi))
	else:
		rValue.add(EmptyPackageSet("security"))
	if vdbapi != None:
		rValue.add(EverythingSet("everything", vdbapi))
	else:
		rValue.add(EmptyPackageSet("everything"))

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

# adhoc test code
if __name__ == "__main__":
	import portage
	l = make_default_sets("/", "/", portage.settings.profiles, portage.settings, portage.db["/"]["vartree"].dbapi, portage.db["/"]["porttree"].dbapi)
	l.update(make_extra_static_sets("/"))
	for x in l:
		print x.getName()+":"
		for n in sorted(x.getNodes()):
			print "- "+n
		print
