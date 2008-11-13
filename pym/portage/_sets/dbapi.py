# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.versions import catpkgsplit, catsplit, pkgcmp, best
from portage.dep import Atom
from portage._sets.base import PackageSet
from portage._sets import SetConfigError, get_boolean

__all__ = ["CategorySet", "DowngradeSet",
	"EverythingSet", "OwnerSet", "VariableSet"]

class EverythingSet(PackageSet):
	_operations = ["merge"]
	description = "Package set which contains SLOT " + \
		"atoms to match all installed packages"
	_filter = None

	def __init__(self, vdbapi):
		super(EverythingSet, self).__init__()
		self._db = vdbapi

	def load(self):
		myatoms = []
		db_keys = ["SLOT"]
		aux_get = self._db.aux_get
		cp_list = self._db.cp_list

		for cp in self._db.cp_all():
			cpv_list = cp_list(cp)

			if len(cpv_list) > 1:
				for cpv in cpv_list:
					slot, = aux_get(cpv, db_keys)
					atom = Atom("%s:%s" % (cp, slot))
					if self._filter:
						if self._filter(atom):
							myatoms.append(atom)
					else:
						myatoms.append(atom)

			else:
				atom = Atom(cp)
				if self._filter:
					if self._filter(atom):
						myatoms.append(atom)
				else:
					myatoms.append(atom)

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

class VariableSet(EverythingSet):

	_operations = ["merge", "unmerge"]

	description = "Package set which contains all packages " + \
		"that match specified values of a specified variable."

	def __init__(self, vardb, metadatadb=None, variable=None, includes=None, excludes=None):
		super(VariableSet, self).__init__(vardb)
		self._metadatadb = metadatadb
		self._variable = variable
		self._includes = includes
		self._excludes = excludes

	def _filter(self, atom):
		ebuild = best(self._metadatadb.match(atom))
		if not ebuild:
			return False
		values, = self._metadatadb.aux_get(ebuild, [self._variable])
		values = values.split()
		if self._includes and not self._includes.intersection(values):
			return False
		if self._excludes and self._excludes.intersection(values):
			return False
		return True

	def singleBuilder(cls, options, settings, trees):

		variable = options.get("variable")
		if variable is None:
			raise SetConfigError("missing required attribute: 'variable'")

		includes = options.get("includes", "")
		excludes = options.get("excludes", "")

		if not (includes or excludes):
			raise SetConfigError("no includes or excludes given")
		
		metadatadb = options.get("metadata-source", "vartree")
		if not metadatadb in trees.keys():
			raise SetConfigError("invalid value '%s' for option metadata-source" % metadatadb)

		return cls(trees["vartree"].dbapi,
			metadatadb=trees[metadatadb].dbapi,
			excludes=frozenset(excludes.split()),
			includes=frozenset(includes.split()),
			variable=variable)

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
	
	def _builderGetVisible(cls, options):
		return get_boolean(options, "only_visible", True)
	_builderGetVisible = classmethod(_builderGetVisible)
		
	def singleBuilder(cls, options, settings, trees):
		if not "category" in options:
			raise SetConfigError("no category given")

		category = options["category"]
		if not category in settings.categories:
			raise SetConfigError("invalid category name '%s'" % category)

		visible = cls._builderGetVisible(options)
		
		return CategorySet(category, dbapi=trees["porttree"].dbapi, only_visible=visible)
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
	
		visible = cls._builderGetVisible(options)
		name_pattern = options.get("name_pattern", "$category/*")
	
		if not "$category" in name_pattern and not "${category}" in name_pattern:
			raise SetConfigError("name_pattern doesn't include $category placeholder")
	
		for cat in categories:
			myset = CategorySet(cat, trees["porttree"].dbapi, only_visible=visible)
			myname = name_pattern.replace("$category", cat)
			myname = myname.replace("${category}", cat)
			rValue[myname] = myset
		return rValue
	multiBuilder = classmethod(multiBuilder)

class AgeSet(EverythingSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, vardb, mode="older", age=7):
		super(AgeSet, self).__init__(vardb)
		self._mode = mode
		self._age = age

	def _filter(self, atom):
		import time, os
	
		cpv = self._db.match(atom)[0]
		path = self._db.getpath(cpv, filename="COUNTER")
		age = (time.time() - os.stat(path).st_mtime) / (3600 * 24)
		if ((self._mode == "older" and age <= self._age) \
			or (self._mode == "newer" and age >= self._age)):
			return False
		else:
			return True
	
	def singleBuilder(cls, options, settings, trees):
		mode = options.get("mode", "older")
		if str(mode).lower() not in ["newer", "older"]:
			raise SetConfigError("invalid 'mode' value %s (use either 'newer' or 'older')" % mode)
		try:
			age = int(options.get("age", "7"))
		except ValueError, e:
			raise SetConfigError("value of option 'age' is not an integer")
		return AgeSet(vardb=trees["vartree"].dbapi, mode=mode, age=age)

	singleBuilder = classmethod(singleBuilder)
