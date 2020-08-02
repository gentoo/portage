# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class RootConfig:
	"""This is used internally by depgraph to track information about a
	particular $ROOT."""
	__slots__ = ("mtimedb", "root", "setconfig", "sets", "settings", "trees")

	pkg_tree_map = {
		"ebuild"    : "porttree",
		"binary"    : "bintree",
		"installed" : "vartree"
	}

	tree_pkg_map = {}
	for k, v in pkg_tree_map.items():
		tree_pkg_map[v] = k

	def __init__(self, settings, trees, setconfig):
		self.trees = trees
		self.settings = settings
		self.root = self.settings['EROOT']
		self.setconfig = setconfig
		if setconfig is None:
			self.sets = {}
		else:
			self.sets = self.setconfig.getSets()

	def update(self, other):
		"""
		Shallow copy all attributes from another instance.
		"""
		for k in self.__slots__:
			try:
				setattr(self, k, getattr(other, k))
			except AttributeError:
				# mtimedb is currently not a required attribute
				try:
					delattr(self, k)
				except AttributeError:
					pass
