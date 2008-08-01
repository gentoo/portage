# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.versions import catpkgsplit, catsplit, pkgcmp
from portage.sets.base import PackageSet
from portage.sets import SetConfigError, get_boolean

__all__ = ["CategorySet", "DowngradeSet",
	"EverythingSet", "InheritSet", "OwnerSet"]

class EverythingSet(PackageSet):
	_operations = ["merge", "unmerge"]
	description = "Package set which contains SLOT " + \
		"atoms to match all installed packages"

	def __init__(self, vdbapi):
		super(EverythingSet, self).__init__()
		self._db = vdbapi
	
	def load(self):
		myatoms = []
		for cp in self._db.cp_all():
			if len(self._db.cp_list(cp)) > 1:
				for cpv in self._db.cp_list(cp):
					myslot = self._db.aux_get(cpv, ["SLOT"])[0]
					myatoms.append(cp+":"+myslot)
			else:
				myatoms.append(cp)
		self._setAtoms(myatoms)
	
	def singleBuilder(self, options, settings, trees):
		return EverythingSet(trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)

class OwnerSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"that own one or more files."

	def __init__(self, vardb=None, files=None):
		super(OwnerSet, self).__init__()
		self._db = vardb
		self._files = files

	def mapPathsToAtoms(self, paths):
		rValue = set()
		vardb = self._db
		aux_get = vardb.aux_get
		aux_keys = ["SLOT"]
		for link, p in vardb._owners.iter_owners(paths):
			cat, pn = catpkgsplit(link.mycpv)[:2]
			slot, = aux_get(link.mycpv, aux_keys)
			rValue.add("%s/%s:%s" % (cat, pn, slot))
		return rValue

	def load(self):
		self._setAtoms(self.mapPathsToAtoms(self._files))

	def singleBuilder(cls, options, settings, trees):
		if not "files" in options:
			raise SetConfigError("no files given")

		import shlex
		return cls(vardb=trees["vartree"].dbapi,
			files=frozenset(shlex.split(options["files"])))

	singleBuilder = classmethod(singleBuilder)

class InheritSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"that inherit one or more specific eclasses."

	def __init__(self, portdb=None, vardb=None, inherits=None):
		super(InheritSet, self).__init__()
		self._portdb = portdb
		self._db = vardb
		self._inherits = inherits

	def load(self):
		atoms = []
		inherits = self._inherits
		xmatch = self._portdb.xmatch
		xmatch_level = "bestmatch-visible"
		cp_list = self._db.cp_list
		aux_get = self._db.aux_get
		portdb_aux_get = self._portdb.aux_get
		vardb_keys = ["SLOT"]
		portdb_keys = ["INHERITED"]
		for cp in self._db.cp_all():
			for cpv in cp_list(cp):
				slot, = aux_get(cpv, vardb_keys)
				slot_atom = "%s:%s" % (cp, slot)
				ebuild = xmatch(xmatch_level, slot_atom)
				if not ebuild:
					continue
				inherited, = portdb_aux_get(ebuild, portdb_keys)
				if inherits.intersection(inherited.split()):
					atoms.append(slot_atom)

		self._setAtoms(atoms)

	def singleBuilder(cls, options, settings, trees):
		if not "inherits" in options:
			raise SetConfigError("no inherits given")

		inherits = options["inherits"]
		return cls(portdb=trees["porttree"].dbapi,
			vardb=trees["vartree"].dbapi,
			inherits=frozenset(inherits.split()))

	singleBuilder = classmethod(singleBuilder)

class DowngradeSet(PackageSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"for which the highest visible ebuild version is lower than " + \
		"the currently installed version."

	def __init__(self, portdb=None, vardb=None):
		super(DowngradeSet, self).__init__()
		self._portdb = portdb
		self._vardb = vardb

	def load(self):
		atoms = []
		xmatch = self._portdb.xmatch
		xmatch_level = "bestmatch-visible"
		cp_list = self._vardb.cp_list
		aux_get = self._vardb.aux_get
		aux_keys = ["SLOT"]
		for cp in self._vardb.cp_all():
			for cpv in cp_list(cp):
				slot, = aux_get(cpv, aux_keys)
				slot_atom = "%s:%s" % (cp, slot)
				ebuild = xmatch(xmatch_level, slot_atom)
				if not ebuild:
					continue
				ebuild_split = catpkgsplit(ebuild)[1:]
				installed_split = catpkgsplit(cpv)[1:]
				if pkgcmp(installed_split, ebuild_split) > 0:
					atoms.append(slot_atom)

		self._setAtoms(atoms)

	def singleBuilder(cls, options, settings, trees):
		return cls(portdb=trees["porttree"].dbapi,
			vardb=trees["vartree"].dbapi)

	singleBuilder = classmethod(singleBuilder)

class CategorySet(PackageSet):
	_operations = ["merge", "unmerge"]
	
	def __init__(self, category, dbapi, only_visible=True):
		super(CategorySet, self).__init__()
		self._db = dbapi
		self._category = category
		self._check = only_visible
		if only_visible:
			s="visible"
		else:
			s="all"
		self.description = "Package set containing %s packages of category %s" % (s, self._category)
			
	def load(self):
		myatoms = []
		for cp in self._db.cp_all():
			if catsplit(cp)[0] == self._category:
				if (not self._check) or len(self._db.match(cp)) > 0:
					myatoms.append(cp)
		self._setAtoms(myatoms)
	
	def _builderGetRepository(cls, options, repositories):
		repository = options.get("repository", "porttree")
		if not repository in repositories:
			raise SetConfigError("invalid repository class '%s'" % repository)
		return repository
	_builderGetRepository = classmethod(_builderGetRepository)

	def _builderGetVisible(cls, options):
		return get_boolean(options, "only_visible", True)
	_builderGetVisible = classmethod(_builderGetVisible)
		
	def singleBuilder(cls, options, settings, trees):
		if not "category" in options:
			raise SetConfigError("no category given")

		category = options["category"]
		if not category in settings.categories:
			raise SetConfigError("invalid category name '%s'" % category)

		repository = cls._builderGetRepository(options, trees.keys())
		visible = cls._builderGetVisible(options)
		
		return CategorySet(category, dbapi=trees[repository].dbapi, only_visible=visible)
	singleBuilder = classmethod(singleBuilder)

	def multiBuilder(cls, options, settings, trees):
		rValue = {}
	
		if "categories" in options:
			categories = options["categories"].split()
			invalid = set(categories).difference(settings.categories)
			if invalid:
				raise SetConfigError("invalid categories: %s" % ", ".join(list(invalid)))
		else:
			categories = settings.categories
	
		repository = cls._builderGetRepository(options, trees.keys())
		visible = cls._builderGetVisible(options)
		name_pattern = options.get("name_pattern", "$category/*")
	
		if not "$category" in name_pattern and not "${category}" in name_pattern:
			raise SetConfigError("name_pattern doesn't include $category placeholder")
	
		for cat in categories:
			myset = CategorySet(cat, trees[repository].dbapi, only_visible=visible)
			myname = name_pattern.replace("$category", cat)
			myname = myname.replace("${category}", cat)
			rValue[myname] = myset
		return rValue
	multiBuilder = classmethod(multiBuilder)

