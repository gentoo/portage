# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from ConfigParser import SafeConfigParser, NoOptionError
from portage import load_mod

DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]
del x

SETPREFIX = "@"

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
		self.active = []
		self.aliases = {}

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
					setname = sname
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
		return self.psets

	def getSetsWithAliases(self):
		self._parse()
		if not self.aliases:
			shortnames = {}
			for name in self.psets:
				mysplit = name.split("/")
				if len(mysplit) > 1 and mysplit[0] == "sets" and mysplit[-1] != "":
					if mysplit[-1] in shortnames:
						del shortnames[mysplit[-1]]
					else:
						shortnames[mysplit[-1]] = self.psets[name]
			shortnames.update(self.psets)
			self.aliases = shortnames
		return self.aliases

	def getSetAtoms(self, setname, ignorelist=[]):
		myset = self.getSetsWithAliases()[setname]
		myatoms = myset.getAtoms()
		ignorelist.append(setname)
		for n in myset.getNonAtoms():
			if n[0] == SETPREFIX and n[1:] in self.aliases:
				if n[1:] not in ignorelist:
					myatoms.update(self.getSetAtoms(n), ignorelist=ignorelist)
		return myatoms

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
	
	sc.add_section("user-sets")
	sc.set("user-sets", "class", "portage.sets.files.StaticFileSet")
	sc.set("user-sets", "multiset", "true")

	sc.add_section("rebuild-needed")
	sc.set("rebuild-needed", "class", "portage.sets.dbapi.MissingLibraryConsumerSet")
	
	return sc

# adhoc test code
if __name__ == "__main__":
	import portage
	sc = make_default_config(portage.settings, portage.db["/"])
	l, e = sc.getSets()
	for x in l:
		print x+":"
		print "DESCRIPTION = %s" % l[x].getMetadata("Description")
		for n in sorted(l[x].getAtoms()):
			print "- "+n
		print
