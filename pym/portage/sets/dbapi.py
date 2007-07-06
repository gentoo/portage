# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.versions import catsplit

from portage.sets import PackageSet

class EverythingSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, name, vdbapi):
		super(EverythingSet, self).__init__(name)
		self._db = vdbapi
	
	def load(self):
		mynodes = []
		for cp in self._db.cp_all():
			if len(self._db.cp_list(cp)) > 1:
				for cpv in self._db.cp_list(cp):
					myslot = self._db.aux_get(cpv, ["SLOT"])[0]
					mynodes.append(cp+":"+myslot)
			else:
				mynodes.append(cp)
		self._setNodes(mynodes)

class CategorySet(PackageSet):
	_operations = ["merge", "unmerge"]
	
	def __init__(self, name, category, portdbapi, only_visible=True):
		super(CategorySet, self).__init__(name)
		self._db = portdbapi
		self._category = category
		self._check = only_visible
			
	def load(self):
		mynodes = []
		for cp in self._db.cp_all():
			if catsplit(cp)[0] == self._category:
				if (not self._check) or len(self._db.match(cp)) > 0:
					mynodes.append(cp)
		self._setNodes(mynodes)
	
