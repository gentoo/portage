# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.exception import InvalidData
from portage.localization import _
from portage._sets.base import PackageSet
from portage._sets import get_boolean, SetConfigError
import portage

class LibraryConsumerSet(PackageSet):
	_operations = ["merge", "unmerge"]

	def __init__(self, vardbapi, debug=False):
		super(LibraryConsumerSet, self).__init__()
		self.dbapi = vardbapi
		self.debug = debug

	def mapPathsToAtoms(self, paths):
		rValue = set()
		for p in paths:
			for cpv in self.dbapi._linkmap.getOwners(p):
				try:
					pkg = self.dbapi._pkg_str(cpv, None)
				except (KeyError, InvalidData):
					# This is expected for preserved libraries
					# of packages that have been uninstalled
					# without replacement.
					pass
				else:
					rValue.add("%s:%s" % (pkg.cp, pkg.slot))
		return rValue

class LibraryFileConsumerSet(LibraryConsumerSet):

	"""
	Note: This does not detect libtool archive (*.la) files that consume the
	specified files (revdep-rebuild is able to detect them).
	"""

	description = "Package set which contains all packages " + \
		"that consume the specified library file(s)."

	def __init__(self, vardbapi, files, **kargs):
		super(LibraryFileConsumerSet, self).__init__(vardbapi, **kargs)
		self.files = files

	def load(self):
		consumers = set()
		for lib in self.files:
			consumers.update(
				self.dbapi._linkmap.findConsumers(lib, greedy=False))

		if not consumers:
			return
		self._setAtoms(self.mapPathsToAtoms(consumers))

	def singleBuilder(cls, options, settings, trees):
		files = tuple(portage.util.shlex_split(options.get("files", "")))
		if not files:
			raise SetConfigError(_("no files given"))
		debug = get_boolean(options, "debug", False)
		return LibraryFileConsumerSet(trees["vartree"].dbapi,
			files, debug=debug)
	singleBuilder = classmethod(singleBuilder)

class PreservedLibraryConsumerSet(LibraryConsumerSet):
	def load(self):
		reg = self.dbapi._plib_registry
		if reg is None:
			# preserve-libs is entirely disabled
			return
		consumers = set()
		if reg:
			plib_dict = reg.getPreservedLibs()
			for libs in plib_dict.values():
				for lib in libs:
					if self.debug:
						print(lib)
						for x in sorted(self.dbapi._linkmap.findConsumers(lib, greedy=False)):
							print("    ", x)
						print("-"*40)
					consumers.update(self.dbapi._linkmap.findConsumers(lib, greedy=False))
			# Don't rebuild packages just because they contain preserved
			# libs that happen to be consumers of other preserved libs.
			for libs in plib_dict.values():
				consumers.difference_update(libs)
		else:
			return
		if not consumers:
			return
		self._setAtoms(self.mapPathsToAtoms(consumers))

	def singleBuilder(cls, options, settings, trees):
		debug = get_boolean(options, "debug", False)
		return PreservedLibraryConsumerSet(trees["vartree"].dbapi,
			debug=debug)
	singleBuilder = classmethod(singleBuilder)
