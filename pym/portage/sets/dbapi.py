# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.versions import catsplit, catpkgsplit
from portage.sets import PackageSet, SetConfigError
from portage.dbapi.vartree import dblink
from portage.util import grabfile

import os

__all__ = ["CategorySet", "EverythingSet"]

class EverythingSet(PackageSet):
	_operations = ["merge", "unmerge"]
	description = "Package set containing all installed packages"
	
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
		visible = options.get("only_visible", "true").lower()
		if visible not in ["1", "0", "yes", "no", "true", "false", "on", "off"]:
			raise SetConfigError("invalid value for only_visible: %s" % visible)
		return bool(visible in ["1", "yes", "true", "on"])
	_builderGetVisible = classmethod(_builderGetVisible)
		
	def singleBuilder(cls, options, settings, trees):
		if not "category" in options:
			raise SetConfigError("no category given")

		category = options["category"]
		if not category in categories:
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

class LibraryConsumerSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, vardbapi):
		super(LibraryConsumerSet, self).__init__()
		self.dbapi = vardbapi

	def mapPathsToAtoms(self, paths):
		rValue = set()
		for cpv in self.dbapi.cpv_all():
			mysplit = catsplit(cpv)
			link = dblink(mysplit[0], mysplit[1], myroot=self.dbapi.root, \
					mysettings=self.dbapi.settings, treetype='vartree', \
					vartree=self.dbapi.vartree)
			if paths.intersection(link.getcontents().keys()):
				rValue.add("/".join(catpkgsplit(cpv)[:2]))
		return rValue
	

class PreservedLibraryConsumerSet(LibraryConsumerSet):
	def load(self):
		reg = self.dbapi.plib_registry
		libmap = self.dbapi.libmap.get()
		consumers = set()
		if reg:
			for libs in reg.getPreservedLibs().values():
				for lib in libs:
					paths = libmap.get(os.path.basename(lib), [])
					consumers.update(paths)
		else:
			return
		if not consumers:
			return
		self._setAtoms(self.mapPathsToAtoms(consumers))

	def singleBuilder(cls, options, settings, trees):
		return PreservedLibraryConsumerSet(trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)

class MissingLibraryConsumerSet(LibraryConsumerSet):
	_operations = ["merge", "unmerge"]
	
	def load(self):
		atoms = set()
		consumers = set()
		for lib in self.dbapi.libmap.get():
			found=False
			for searchdir in grabfile(os.path.join(os.sep, self.dbapi.root, "etc/ld.so.conf")):
				if os.path.exists(os.path.join(searchdir, lib)):
					found=True
					break
			if not found:
				consumers.update(self.dbapi.libmap.get()[lib])
		if not consumers:
			return
		self._setAtoms(self.mapPathsToAtoms(consumers))
	
	def singleBuilder(cls, options, settings, trees):
		return MissingLibraryConsumerSet(trees["vartree"].dbapi)
	singleBuilder = classmethod(singleBuilder)
