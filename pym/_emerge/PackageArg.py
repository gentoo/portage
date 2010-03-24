# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DependencyArg import DependencyArg
import portage

class PackageArg(DependencyArg):
	def __init__(self, package=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.package = package
		self.atom = portage.dep.Atom("=" + package.cpv)
		self.set = (self.atom, )
