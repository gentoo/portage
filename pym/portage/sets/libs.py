# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.sets.base import PackageSet
from portage.sets import get_boolean
from portage.versions import catpkgsplit

class LibraryConsumerSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, vardbapi, debug=False):
		super(LibraryConsumerSet, self).__init__()
		self.dbapi = vardbapi
		self.debug = debug

	def mapPathsToAtoms(self, paths):
		rValue = set()
		root_len = len(self.dbapi.root)
		for link, relative_p in self.dbapi._owners.iter_owners(
			p[root_len:] for p in paths):
			cat, pn = catpkgsplit(link.mycpv)[:2]
			slot = self.dbapi.aux_get(link.mycpv, ["SLOT"])[0]
			rValue.add("%s/%s:%s" % (cat, pn, slot))
		return rValue

class PreservedLibraryConsumerSet(LibraryConsumerSet):
	def load(self):
		reg = self.dbapi.plib_registry
		consumers = set()
		if reg:
			for libs in reg.getPreservedLibs().values():
				for lib in libs:
					if self.debug:
						print lib
						for x in sorted(self.dbapi.linkmap.findConsumers(lib)):
							print "    ", x
						print "-"*40
					consumers.update(self.dbapi.linkmap.findConsumers(lib))
		else:
			return
		if not consumers:
			return
		self._setAtoms(self.mapPathsToAtoms(consumers))

	def singleBuilder(cls, options, settings, trees):
		debug = get_boolean(options, "debug", False)
		return PreservedLibraryConsumerSet(trees["vartree"].dbapi, debug)
	singleBuilder = classmethod(singleBuilder)
