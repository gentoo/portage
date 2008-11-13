# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage._sets.base import PackageSet
from portage._sets import get_boolean
from portage.versions import catpkgsplit

class LibraryConsumerSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, vardbapi, debug=False):
		super(LibraryConsumerSet, self).__init__()
		self.dbapi = vardbapi
		self.debug = debug

	def mapPathsToAtoms(self, paths):
		rValue = set()
		for link, p in self.dbapi._owners.iter_owners(paths):
			cat, pn = catpkgsplit(link.mycpv)[:2]
			slot = self.dbapi.aux_get(link.mycpv, ["SLOT"])[0]
			rValue.add("%s/%s:%s" % (cat, pn, slot))
		return rValue
