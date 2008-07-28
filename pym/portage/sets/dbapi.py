# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.versions import catsplit
from portage.sets.base import PackageSet
from portage.sets import SetConfigError, get_boolean

__all__ = ["CategorySet", "EverythingSet"]

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

