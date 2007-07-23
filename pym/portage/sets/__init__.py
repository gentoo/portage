# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

OPERATIONS = ["merge", "unmerge"]
DEFAULT_SETS = ["world", "system", "everything", "security"] \
	+["package_"+x for x in ["mask", "unmask", "use", "keywords"]]
del x

def make_default_sets(configroot, root, profile_paths, settings=None, 
		vdbapi=None, portdbapi=None):
	from portage.sets.files import StaticFileSet, ConfigFileSet
	from portage.sets.profiles import PackagesSystemSet
	from portage.sets.security import NewAffectedSet
	from portage.sets.dbapi import EverythingSet
	from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
	
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
	from portage.const import PRIVATE_PATH, USER_CONFIG_PATH
	
	rValue = set()
	mydir = os.path.join(configroot, USER_CONFIG_PATH.lstrip(os.sep), "sets")
	try:
		mysets = os.listdir(mydir)
	except (OSError, IOError):
		return rValue
	for myname in mysets:
		if myname in DEFAULT_SETS:
			continue
		rValue.add(StaticFileSet(myname, os.path.join(mydir, myname)))
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
				l.add(CategorySet("category_%s" % c, c, portage.db['/']['porttree'].dbapi, only_visible=False))
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
