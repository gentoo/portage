# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage._sets.base import InternalPackageSet
from _emerge.DependencyArg import DependencyArg

class AtomArg(DependencyArg):

	__slots__ = ('atom', 'pset')

	def __init__(self, atom=None, **kwargs):
		DependencyArg.__init__(self, **kwargs)
		self.atom = atom
		self.pset = InternalPackageSet(initial_atoms=(self.atom,), allow_repo=True)
