# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.DependencyArg import DependencyArg
from _emerge.Package import Package
import portage
from portage._sets.base import InternalPackageSet
from portage.dep import _repo_separator

class PackageArg(DependencyArg):
	def __init__(self, package=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.package = package
		atom = "=" + package.cpv
		if package.repo != Package.UNKNOWN_REPO:
			atom += _repo_separator + package.repo
		self.atom = portage.dep.Atom(atom, allow_repo=True)
		self.pset = InternalPackageSet(initial_atoms=(self.atom,),
			allow_repo=True)
